"""Comprehension gate: who may vote, and with what weight, decided by a random examiner board.

Flow (all steps are chain-verifiable):
  1. A QuestionBank is committed (Merkle root) before the record closes. Answer keys stay with the
     bank committee and are revealed only at grading, where each key is checked against its commit.
  2. The voter opens an attempt at the chain (attempt counter is per (issue, voter): re-rolling
     tickets cannot bypass the attempt limit). The ticket is pseudonymous: H(voter, issue, attempt,
     secret). Examiners see the ticket, never the AgentID.
  3. Proposal-topic questions are mandatory. The voter also DECLARES the articles it read (R_d);
     a seeded random sample of them is spot-checked. All sampled pass -> R = R_d. Otherwise R is
     extrapolated down proportionally and the voter's bond is slashed (lying has positive expected cost).
  4. Each board member grades independently; the majority verdict per item decides. The board
     signs an EligibilityToken; the chain accepts it only with >= threshold valid board signatures.
  5. Canary items (known answers, inserted by the chain) score every examiner; persistent misses
     flag the examiner for suspension.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .crypto_sim import MerkleTree, SimKeyring, H, hx
from .params import BPS, Params
from .sortition import threshold
from .treasury import RuleViolation

PROPOSAL_ARTICLE = "__proposal__"


def commit_key(answer: int, salt: str) -> str:
    return hx("qkey", answer, salt)


@dataclass(frozen=True)
class Question:
    qid: str
    article_id: str       # PROPOSAL_ARTICLE for topic questions
    options: int
    key_commit: str

    def leaf(self) -> bytes:
        return H(self.qid, self.article_id, self.options, self.key_commit)


class QuestionBank:
    def __init__(self, issue_id: str, questions: list[Question], article_cluster: dict[str, str]):
        self.issue_id = issue_id
        self.questions = {q.qid: q for q in questions}
        self.order = sorted(self.questions)
        self.article_cluster = dict(article_cluster)   # article -> dedup cluster (R counts clusters)
        self._tree = MerkleTree([self.questions[q].leaf() for q in self.order])
        self._keys: dict[str, tuple[int, str]] = {}

    @property
    def root(self) -> str:
        return self._tree.root.hex()

    def load_keys(self, keys: dict[str, tuple[int, str]]) -> None:
        for qid, (ans, salt) in keys.items():
            if commit_key(ans, salt) != self.questions[qid].key_commit:
                raise RuleViolation(f"key for {qid} does not match its commitment")
        self._keys = dict(keys)

    def answer_ok(self, qid: str, answer: int) -> bool:
        if qid not in self._keys:
            raise RuleViolation("key not revealed")
        return self._keys[qid][0] == answer

    def draw(self, seed: bytes, article_id: str, n: int) -> list[Question]:
        pool = [q for q in self.questions.values() if q.article_id == article_id]
        pool.sort(key=lambda q: H(b"draw", seed, q.qid))
        return pool[:n]

    def articles(self) -> list[str]:
        return sorted(a for a in self.article_cluster)


@dataclass(frozen=True)
class Attempt:
    issue: str
    voter: str
    n: int
    ticket: str


class AttemptRegistry:
    """Chain-side: counts attempts by identity (known to chain, hidden from examiners)."""

    def __init__(self, p: Params):
        self.p = p
        self.count: dict[tuple, int] = {}
        self.ticket_owner: dict[str, str] = {}   # sealed on chain; never shown to the board

    def open(self, issue: str, voter: str, secret: str) -> Attempt:
        k = (issue, voter)
        n = self.count.get(k, 0) + 1
        if n > self.p.exam_max_attempts:
            raise RuleViolation("attempt limit reached")
        self.count[k] = n
        ticket = hx("ticket", voter, issue, n, secret)
        self.ticket_owner[ticket] = voter
        return Attempt(issue, voter, n, ticket)

    def owns(self, voter: str, ticket: str) -> bool:
        return self.ticket_owner.get(ticket) == voter


@dataclass(frozen=True)
class Submission:
    ticket: str
    declared_articles: tuple
    answers: tuple   # ((qid, answer), ...) for proposal + sampled article questions


@dataclass(frozen=True)
class ExamPlan:
    proposal_qs: tuple
    sampled: tuple     # ((article_id, Question), ...) articles chosen for spot-check
    declared: tuple    # distinct clusters after dedup, capped at R_max


def plan_exam(bank: QuestionBank, seed: bytes, ticket: str, declared: tuple, p: Params) -> ExamPlan:
    s = H(b"exam", seed, ticket)
    # Dedup by cluster so splitting one argument into many articles adds nothing.
    seen, dedup = set(), []
    for a in sorted(declared):
        c = bank.article_cluster.get(a)
        if c is None:
            raise RuleViolation(f"unknown article {a}")
        if c not in seen:
            seen.add(c)
            dedup.append(a)
    dedup = dedup[: p.max_articles_counted]
    pq = bank.draw(s, PROPOSAL_ARTICLE, p.exam_items)
    if not pq:
        raise RuleViolation("bank has no proposal questions")
    order = sorted(dedup, key=lambda a: H(b"sample", s, a))[: p.sample_articles]
    sampled = []
    for a in order:
        qs = bank.draw(s, a, 1)
        if not qs:
            raise RuleViolation(f"no question for {a}")
        sampled.append((a, qs[0]))
    return ExamPlan(tuple(pq), tuple(sampled), tuple(dedup))


@dataclass(frozen=True)
class Verdict:
    passed: bool
    R: int
    slash: bool


def grade_item_verdicts(bank: QuestionBank, plan: ExamPlan, sub: Submission) -> dict[str, bool]:
    """One board member's per-item verdicts (auto-gradable items; FREE items are supplied
    directly by members in `judge`)."""
    ans = dict(sub.answers)
    out = {}
    for q in plan.proposal_qs:
        out[q.qid] = q.qid in ans and bank.answer_ok(q.qid, ans[q.qid])
    for _, q in plan.sampled:
        out[q.qid] = q.qid in ans and bank.answer_ok(q.qid, ans[q.qid])
    return out


def majority(verdicts_by_member: dict[str, dict[str, bool]], items: list[str]) -> dict[str, bool]:
    n = len(verdicts_by_member)
    need = n // 2 + 1
    return {it: sum(1 for v in verdicts_by_member.values() if v.get(it)) >= need for it in items}


def evaluate(plan: ExamPlan, item_result: dict[str, bool], p: Params) -> Verdict:
    m = len(plan.proposal_qs)
    correct = sum(1 for q in plan.proposal_qs if item_result.get(q.qid))
    if correct * BPS < p.exam_pass_bps * m:
        return Verdict(False, 0, False)
    rd = len(plan.declared)
    k = len(plan.sampled)
    if k == 0:
        return Verdict(True, 0, False)  # nothing declared -> R = 0
    passed = sum(1 for _, q in plan.sampled if item_result.get(q.qid))
    if passed == k:
        return Verdict(True, rd, False)
    return Verdict(True, passed * rd // k, True)


@dataclass(frozen=True)
class Token:
    issue: str
    ticket: str
    R: int
    expires: int
    board_id: str
    sigs: tuple     # ((member, sig), ...)

    def message(self) -> bytes:
        return H(b"eligibility", self.issue, self.ticket, self.R, self.expires, self.board_id)


@dataclass
class Board:
    board_id: str
    members: tuple
    issue: str

    @property
    def threshold(self) -> int:
        return threshold(len(self.members))


def issue_token(board: Board, keyring: SimKeyring, issue: str, ticket: str, verdict: Verdict,
                signers: list[str], height: int, p: Params) -> Token:
    if not verdict.passed:
        raise RuleViolation("cannot issue a token for a failed exam")
    tok = Token(issue, ticket, verdict.R, height + p.token_ttl, board.board_id, ())
    sigs = tuple((m, keyring.sign(m, tok.message())) for m in signers if m in board.members)
    return Token(issue, ticket, verdict.R, tok.expires, board.board_id, sigs)


def verify_token(tok: Token, board: Board, keyring: SimKeyring, issue: str, height: int) -> None:
    if tok.issue != issue or tok.board_id != board.board_id:
        raise RuleViolation("token for a different issue or board")
    if height >= tok.expires:
        raise RuleViolation("token expired")
    good = {m for m, s in tok.sigs if m in board.members and keyring.verify(m, tok.message(), s)}
    if len(good) < board.threshold:
        raise RuleViolation("insufficient board signatures")


@dataclass
class Scoreboard:
    """Examiner accountability: agreement with the final majority and canary accuracy."""
    p: Params
    canary_total: dict = field(default_factory=dict)
    canary_ok: dict = field(default_factory=dict)
    disagreements: dict = field(default_factory=dict)

    def record_canary(self, member: str, correct: bool) -> None:
        self.canary_total[member] = self.canary_total.get(member, 0) + 1
        self.canary_ok[member] = self.canary_ok.get(member, 0) + int(correct)

    def record_item(self, member: str, agreed: bool) -> None:
        if not agreed:
            self.disagreements[member] = self.disagreements.get(member, 0) + 1

    def flagged(self) -> list[str]:
        out = []
        for m, tot in self.canary_total.items():
            if tot >= self.p.canary_min_samples and \
                    self.canary_ok[m] * BPS < self.p.canary_min_accuracy_bps * tot:
                out.append(m)
        return sorted(out)
