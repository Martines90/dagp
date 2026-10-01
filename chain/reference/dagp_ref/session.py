"""VoteSession: one proposal vote or one election, end to end.

Phases:  EXAM/VOTING -> CLOSED -> (CERTIFIED) -> CHALLENGE -> FINAL | VOIDED

Examiner board duties: grade comprehension, sign eligibility tokens, co-sign the tally certificate.
What the board can NOT do: change a tally. The chain recomputes the tally itself (sharded), so a
hostile board can only (a) wrongly deny/grant eligibility, bounded by appeal and canaries, or
(b) refuse to certify, which only delays by `certify_end` and gets its members flagged.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional

from .comprehension import (AttemptRegistry, Board, QuestionBank, Scoreboard, Submission, Token,
                            evaluate, grade_item_verdicts, issue_token, majority, plan_exam,
                            verify_token)
from .crypto_sim import H, SimKeyring, hx, verify_proof
from .election import ElectionResult
from .params import Params
from .roles import Actor, Role, RoleRegistry, Status
from .sortition import audit_sample_size, draw
from .scale import (Electorate, ElectionShard, ShardSummary, election_from_shards, shard_count,
                    shard_of, summarize_election_shard, summarize_shard, tally_sharded)
from .tally import Ballot, Kind, Outcome, TallyResult, weight
from .treasury import CreditLedger, RuleViolation, Treasury

ELECTION = "ELECTION"


def snapshot_electorate(registry: RoleRegistry, height: int, exclude=frozenset()) -> Electorate:
    """Eligible = ACTIVE citizens aged >= min_citizen_age, minus excluded (recused, board).
    DORMANT, SUSPENDED, BANNED, PROBATION and EXITED never appear (D-01)."""
    return Electorate(a for a, i in registry.ids.items()
                      if i.status is Status.ACTIVE and Role.CITIZEN in i.roles
                      and height - i.activated >= registry.p.min_citizen_age and a not in exclude)


class Phase(str, Enum):
    VOTING = "VOTING"
    CLOSED = "CLOSED"
    CERTIFIED = "CERTIFIED"
    CHALLENGE = "CHALLENGE"
    FINAL = "FINAL"
    VOIDED = "VOIDED"


@dataclass
class Windows:
    vote_end: int
    certify_end: int
    challenge_end: int


@dataclass
class Effects:
    """Money and credit consequences bound to the vote (optional)."""
    treasury: Optional[Treasury] = None
    credits: Optional[CreditLedger] = None
    project: str = ""
    ceiling: int = 0
    tranches: list = field(default_factory=list)
    proposer_party: str = ""


@dataclass
class Challenge:
    by: str
    grounds: str
    status: str = "OPEN"      # OPEN | UPHELD | REJECTED


class VoteSession:
    def __init__(self, issue: str, kind, p: Params, registry: RoleRegistry, keyring: SimKeyring,
                 electorate_root: bytes, electorate_size: int, board: Board, bank: QuestionBank,
                 attempts: AttemptRegistry, beacon: bytes, open_height: int, windows: Windows,
                 recused: frozenset = frozenset(), effects: Effects | None = None,
                 qualified_parties: list | None = None, scoreboard: Scoreboard | None = None,
                 pool: list | None = None):
        if electorate_size <= 0:
            raise RuleViolation("empty electorate")
        if kind == ELECTION and not qualified_parties:
            raise RuleViolation("election needs qualified parties")
        self.issue, self.kind, self.p = issue, kind, p
        self.registry, self.keyring = registry, keyring
        self.root, self.size = electorate_root, electorate_size
        self.board, self.bank, self.attempts, self.beacon = board, bank, attempts, beacon
        self.open_height, self.w = open_height, windows
        self.recused = recused
        self.effects = effects or Effects()
        self.qualified = qualified_parties or []
        self.scoreboard = scoreboard or Scoreboard(p)
        # Exam graders come from `pool` (never the certification board); one small panel per ticket.
        self.pool = sorted(set(pool if pool is not None else []) - set(board.members))
        self.issued: dict[str, tuple] = {}           # ticket -> (token, panel, voter)
        self.revoked: set[str] = set()
        self.struck: list[str] = []
        self.rules_hash = p.snapshot_hash()          # P4: rules locked at open
        self.phase = Phase.VOTING
        self._sealed: dict[str, tuple] = {}          # voter -> (choice, weight); hidden until close
        self.commits: dict[str, str] = {}
        self.result = None
        self.commitment = b""
        self.certs: dict[str, str] = {}
        self.challenges: list[Challenge] = []
        self.board_default = False
        self.flagged_members: list[str] = []
        self.outcome: Outcome | None = None
        self.slashed: list[str] = []
        self.token_count = 0
        if self.effects.treasury and self.effects.ceiling:
            self.effects.treasury.reserve(self.effects.project, self.effects.ceiling)  # D-02

    # ------------------------------------------------------------- eligibility & exam
    def _matter(self) -> dict:
        return {"proposer_party_members": set(self.recused)}

    def _check_open(self, height: int) -> None:
        if self.phase is not Phase.VOTING:
            raise RuleViolation(f"phase is {self.phase.value}")
        if not (self.open_height <= height < self.w.vote_end):
            raise RuleViolation("outside voting window")

    def _check_voter(self, voter: str, height: int) -> None:
        if voter in self.board.members:
            raise RuleViolation("board members cannot vote on the matter they certify")
        ok, why = self.registry.can(voter, "VOTE", height, self._matter())
        if not ok:
            raise RuleViolation(f"voter not allowed: {why}")

    def request_exam(self, voter: str, secret: str, height: int):
        self._check_open(height)
        self._check_voter(voter, height)
        return self.attempts.open(self.issue, voter, secret)

    def panel_for(self, ticket: str) -> Board:
        """Deterministic, publicly recomputable grader panel for one exam ticket."""
        owner = self.attempts.ticket_owner.get(ticket)
        members = tuple(draw(H(b"exam-panel", self.beacon, ticket), self.pool, self.p.exam_panel,
                             exclude={owner} if owner else frozenset()))
        if len(members) < self.p.exam_panel:
            raise RuleViolation("examiner pool too small for a grader panel")
        return Board(f"panel-{ticket[:12]}", members, self.issue)

    def plan(self, attempt, declared: tuple):
        return plan_exam(self.bank, self.beacon, attempt.ticket, declared, self.p)

    def grade(self, attempt, sub: Submission, member_verdicts: dict, signers: list, height: int
              ) -> tuple[Token, bool]:
        """Board step. member_verdicts: member -> {qid: bool}. Returns (token, bond_slashed).
        Raises if the exam failed (voter may retry until attempts run out)."""
        self._check_open(height)
        if sub.ticket != attempt.ticket or self.attempts.ticket_owner.get(attempt.ticket) is None:
            raise RuleViolation("unknown ticket")
        panel = self.panel_for(attempt.ticket)
        if any(m not in panel.members for m in member_verdicts):
            raise RuleViolation("verdict from a member outside this ticket's panel")
        if len(member_verdicts) < panel.threshold:
            raise RuleViolation("not enough graders")
        plan = plan_exam(self.bank, self.beacon, attempt.ticket, sub.declared_articles, self.p)
        items = [q.qid for q in plan.proposal_qs] + [q.qid for _, q in plan.sampled]
        res = majority(member_verdicts, items)
        for m, v in member_verdicts.items():
            for it in items:
                self.scoreboard.record_item(m, v.get(it, False) == res[it])
        verdict = evaluate(plan, res, self.p)
        if not verdict.passed:
            raise RuleViolation("comprehension check failed")
        slashed = False
        if verdict.slash:
            owner = self.attempts.ticket_owner[attempt.ticket]
            ident = self.registry.get(owner)
            ident.bond -= min(ident.bond, self.p.citizen_bond // 10)
            self.slashed.append(owner)
            slashed = True
        tok = issue_token(panel, self.keyring, self.issue, attempt.ticket, verdict, signers,
                          height, self.p)
        verify_token(tok, panel, self.keyring, self.issue, height)       # panel must reach threshold
        self.token_count += 1
        self.issued[attempt.ticket] = (tok, panel, self.attempts.ticket_owner[attempt.ticket])
        return tok, slashed

    # ------------------------------------------------------------- ballots
    def cast_ballot(self, voter: str, choice, token: Token, secret: str, attempt_n: int,
                    proof: list, height: int) -> None:
        self._check_open(height)
        self._check_voter(voter, height)
        if voter in self._sealed:
            raise RuleViolation("already voted")
        if not verify_proof(self.root, voter.encode(), proof):
            raise RuleViolation("not in electorate snapshot")
        ticket = hx("ticket", voter, self.issue, attempt_n, secret)
        if ticket != token.ticket or not self.attempts.owns(voter, ticket):
            raise RuleViolation("token does not belong to this voter")
        if ticket in self.revoked:
            raise RuleViolation("token revoked by audit")
        verify_token(token, self.panel_for(ticket), self.keyring, self.issue, height)
        if self.kind == ELECTION:
            w = 1
            if not isinstance(choice, tuple):
                raise RuleViolation("election ballot must be a tuple of picks")
        else:
            w = weight(token.R, self.p)
        self._sealed[voter] = (choice, w)
        self.commits[voter] = hx("ballot-commit", voter, self.issue, str(choice), w)

    def ballots_public(self) -> dict:
        if self.phase in (Phase.VOTING,):
            raise RuleViolation("ballots are sealed until close")
        return dict(self._sealed)

    # ------------------------------------------------------------- audits (certification board)
    def audit_sample(self) -> list[str]:
        """Random sample of issued tickets for re-grading. Its size depends only on the fraud
        rate to detect and the miss probability, NOT on how many voters there are."""
        n = audit_sample_size(self.p.audit_fraud_bps, self.p.audit_miss_den)
        return draw(H(b"audit", self.beacon), sorted(self.issued), min(n, len(self.issued)))

    def audit(self, ticket: str, true_verdict, height: int) -> str:
        """Board re-grades one issued token while voting is still open. Returns OK | CORRECTED |
        STRUCK. A wrong token revokes it, strikes/corrects the sealed ballot, and flags the
        panel members who signed it."""
        if self.phase is not Phase.VOTING:
            raise RuleViolation("audits run while voting is open")
        if ticket not in self.issued:
            raise RuleViolation("unknown ticket")
        tok, panel, voter = self.issued[ticket]
        if true_verdict.passed and true_verdict.R == tok.R:
            return "OK"
        for m, _ in tok.sigs:
            self.scoreboard.record_item(m, False)
        if not true_verdict.passed:
            self.revoked.add(ticket)
            self._sealed.pop(voter, None)
            self.commits.pop(voter, None)
            self.struck.append(voter)
            return "STRUCK"
        if voter in self._sealed:
            choice, _ = self._sealed[voter]
            self._sealed[voter] = (choice, weight(true_verdict.R, self.p))
        self.issued[ticket] = (replace(tok, R=true_verdict.R), panel, voter)
        return "CORRECTED"

    # ------------------------------------------------------------- close / certify
    def certificate_message(self) -> bytes:
        if self.phase is Phase.VOTING:
            raise RuleViolation("not closed")
        return H(b"tally-cert", self.issue, self.commitment, self._outcome_label())

    def _outcome_label(self) -> str:
        r = self.result
        if isinstance(r, ElectionResult):
            return f"{r.valid}:{sorted(r.credits.items())}"
        return f"{r.outcome.value}:{r.yes_w}:{r.no_w}:{r.abstain_n}:{r.participation}"

    def close(self, height: int) -> None:
        if self.phase is not Phase.VOTING:
            raise RuleViolation("already closed")
        if height < self.w.vote_end:
            raise RuleViolation("voting window still open")
        if self.rules_hash != self.p.snapshot_hash():
            raise RuleViolation("rules changed during vote")
        shards = shard_count(self.size, self.p)
        if self.kind == ELECTION:
            groups: list[dict] = [dict() for _ in range(shards)]
            for v, (choice, _) in self._sealed.items():
                groups[shard_of(v, shards)][v] = choice
            es = [summarize_election_shard(g, self.qualified, self.p) for g in groups]
            self.result = election_from_shards(es, self.qualified, self.p)
            self.commitment = H(b"election", sorted(self.result.points.items()), self.result.reason)
        else:
            groups_b: list[list[Ballot]] = [[] for _ in range(shards)]
            for v, (choice, w) in self._sealed.items():
                groups_b[shard_of(v, shards)].append(Ballot(v, choice, w))
            sums = [summarize_shard(i, shards, groups_b[i], self.p) for i in range(shards)]
            self.result, self.commitment = tally_sharded(sums, shards, self.size, self.kind, self.p)
            self.shard_summaries = sums
        self.phase = Phase.CLOSED

    def certify(self, member: str, sig: str, height: int) -> None:
        if self.phase not in (Phase.CLOSED, Phase.CERTIFIED):
            raise RuleViolation("not awaiting certification")
        if height >= self.w.certify_end:
            raise RuleViolation("certification window over")
        if member not in self.board.members:
            raise RuleViolation("not a board member")
        if not self.keyring.verify(member, self.certificate_message(), sig):
            raise RuleViolation("signature does not match the chain's own tally")
        self.certs[member] = sig       # late signers after the threshold are recorded, not refused
        if self.phase is Phase.CLOSED and len(self.certs) >= self.board.threshold:
            self.phase = Phase.CERTIFIED

    def advance(self, height: int) -> None:
        """Move CLOSED/CERTIFIED into the challenge window. A silent board cannot block:
        after certify_end the chain proceeds on its own tally and flags the non-signers."""
        if self.phase is Phase.CERTIFIED:
            self.phase = Phase.CHALLENGE
        elif self.phase is Phase.CLOSED:
            if height < self.w.certify_end:
                raise RuleViolation("certification window still open")
            self.board_default = True
            self.flagged_members = sorted(set(self.board.members) - set(self.certs))
            self.phase = Phase.CHALLENGE
        else:
            raise RuleViolation(f"cannot advance from {self.phase.value}")
        r = self.result
        if not isinstance(r, ElectionResult) and r.review_flag:      # D-15
            self.challenges.append(Challenge("MODULE", "INCOHERENCE"))

    # ------------------------------------------------------------- challenge / finalize
    def challenge(self, by: str, grounds: str, height: int) -> int:
        if self.phase is not Phase.CHALLENGE or height >= self.w.challenge_end:
            raise RuleViolation("no open challenge window")
        ok, why = self.registry.can(by, "FILE_CASE", height)
        if not ok:
            raise RuleViolation(f"cannot file: {why}")
        self.challenges.append(Challenge(by, grounds))
        return len(self.challenges) - 1

    def rule(self, court: Actor, idx: int, upheld: bool, height: int) -> None:
        self.registry._authorize(court, {"COURT"}, height, "CHALLENGE", f"{self.issue}:{idx}")
        ch = self.challenges[idx]
        if ch.status != "OPEN":
            raise RuleViolation("already ruled")
        self.registry._spend(court)
        ch.status = "UPHELD" if upheld else "REJECTED"

    def extend(self, actor: Actor, delta: int) -> None:
        """Halt compensation: an outage of `delta` cannot shorten any remaining window."""
        if actor.kind != "MODULE" or delta <= 0:
            raise RuleViolation("module only, positive delta")
        if self.phase is Phase.VOTING:
            self.w.vote_end += delta
        self.w.certify_end += delta
        self.w.challenge_end += delta

    def finalize(self, height: int) -> Outcome | str:
        if self.phase is not Phase.CHALLENGE:
            raise RuleViolation("not in challenge phase")
        if height < self.w.challenge_end:
            raise RuleViolation("challenge window still open")
        if any(c.status == "OPEN" for c in self.challenges):
            raise RuleViolation("unresolved challenge")
        if any(c.status == "UPHELD" for c in self.challenges):
            self.phase, self.outcome = Phase.VOIDED, None
            self._unwind(refund=True)
            return "VOIDED"
        self.phase = Phase.FINAL
        r = self.result
        if isinstance(r, ElectionResult):
            self.outcome = Outcome.PASSED if r.valid else Outcome.FAILED
            return self.outcome
        self.outcome = r.outcome
        e = self.effects
        if r.outcome is Outcome.PASSED:
            if e.treasury and e.ceiling:
                e.treasury.commit_reserved(e.project, e.tranches)
        else:
            self._unwind(refund=(r.outcome is Outcome.NO_QUORUM and self.p.refund_on_no_quorum))
        return self.outcome

    def _unwind(self, refund: bool) -> None:
        e = self.effects
        if e.treasury and e.ceiling and e.project in e.treasury.reserved:
            e.treasury.release_reservation(e.project)
        if refund and e.credits and e.proposer_party:
            e.credits.grant(e.proposer_party, self.p.proposal_cost)   # D-12
