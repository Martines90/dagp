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
from .campaign import Campaign
from .roles import Actor, Role, RoleRegistry, Status
from .sortition import audit_sample_size, draw
from .scale import (Electorate, ElectionShard, ShardSummary, election_from_shards, shard_count,
                    shard_of, summarize_election_shard, summarize_shard, tally_sharded)
from .tally import Ballot, BillResult, Kind, Outcome, TallyResult, weight,tally_bill,YES,NO,ABSTAIN
from .treasury import CreditLedger, RuleViolation, Treasury

ELECTION = "ELECTION"


def snapshot_electorate(registry: RoleRegistry, height: int, exclude=frozenset()) -> Electorate:
    """Eligible = citizens with civic standing and minimum age, minus recused/board ids.
    DORMANT, judicially SUSPENDED, BANNED, PROBATION and EXITED never appear.
    Registrar spam freezes preserve civic eligibility to prevent unilateral censorship."""
    return Electorate(a for a, i in registry.ids.items()
                      if registry.can(a,"VOTE",height)[0] and a not in exclude)


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
    milestones: tuple = ()
    credit_month: tuple | None = None
    point_budgets: tuple = ()
    point_tranches: tuple = ()
    point_milestones: tuple = ()


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
                 pool: list | None = None, approved_record_hash: str = "",point_ids: tuple = (),point_dependencies: tuple = (),parameter_changes: tuple = (),campaign: Campaign | None = None):
        if electorate_size <= 0:
            raise RuleViolation("empty electorate")
        if kind == ELECTION and not qualified_parties:
            raise RuleViolation("election needs qualified parties")
        self.issue, self.kind, self.p = issue, kind, p
        self.registry, self.keyring = registry, keyring
        self.campaign=campaign;self._campaign_hash=campaign.digest() if type(campaign) is Campaign else ""
        self._campaign_conflicts=frozenset(campaign.member_operators) if type(campaign) is Campaign else frozenset()
        if kind==ELECTION:
            if type(campaign) is not Campaign:raise RuleViolation("election requires a finalized campaign record")
            campaign.check(bank,qualified_parties,p)
            if any(not registry.can(a,"GRADE",open_height,{"operators_involved":self._campaign_conflicts})[0] for a in board.members):
                raise RuleViolation("independent eligible election certification board required")
            campaign_registry=getattr(registry,"party_registry",None)
            if campaign_registry is None or campaign_registry._campaigns.get(campaign.pre_commitment)!=(self._campaign_hash,issue,False):
                raise RuleViolation("registered unused campaign authorization required")
            if open_height<campaign.end_height or windows.challenge_end+p.challenge_resolution_grace>campaign.election_deadline:
                raise RuleViolation("election outside frozen campaign cycle")
        elif campaign is not None:raise RuleViolation("campaign belongs to election only")
        self.root, self.size = electorate_root, electorate_size
        self.board, self.bank, self.attempts, self.beacon = board, bank, attempts, beacon
        self.open_height, self.w = open_height, windows
        self.recused = recused
        self.effects = replace(effects, tranches=list(effects.tranches)) if effects else Effects()
        if kind==ELECTION and (self.effects.treasury is not None or self.effects.credits is not None or self.effects.ceiling):
            raise RuleViolation("elections cannot carry proposal budget effects")
        self.point_ids=tuple(point_ids);self.point_dependencies=tuple(point_dependencies)
        if self.point_ids and (not approved_record_hash or kind==ELECTION or len(self.point_ids)>p.max_bill_points
                               or len(set(self.point_ids))!=len(self.point_ids)
                               or len(self.point_dependencies)!=len(self.point_ids)):
            raise RuleViolation('point ballots require a valid locked review')
        self.parameter_changes=tuple(parameter_changes)
        self.effective_points=()
        self.approved_record_hash = approved_record_hash
        self._effects_hash = self._effect_commitment()
        if self.effects.ceiling:
            from .treasury import _budget
            if _budget(self.effects.tranches)>self.effects.ceiling:
                raise RuleViolation("tranches exceed vote ceiling")
        self.record_hash = bank.record_hash()
        if not (open_height < windows.vote_end < windows.certify_end < windows.challenge_end):
            raise RuleViolation("invalid voting windows")
        self.w = replace(windows)
        self.qualified = list(qualified_parties or [])
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

        if kind==ELECTION:campaign_registry._campaigns[campaign.pre_commitment]=(self._campaign_hash,issue,True)

    # ------------------------------------------------------------- eligibility & exam
    def _matter(self) -> dict:
        return {"proposer_party_members": set(self.recused),
                "operators_involved": self._campaign_conflicts}

    def _effect_commitment(self):
        e=self.effects
        return hx("vote-effects",e.project,e.ceiling,e.tranches,e.proposer_party,e.milestones,e.credit_month,e.point_budgets,e.point_tranches,e.point_milestones,self.point_ids,self.point_dependencies,self.parameter_changes)

    def _check_review_effects(self):
        if self.kind==ELECTION:
            if type(self.campaign) is not Campaign or self.campaign.digest()!=self._campaign_hash:
                raise RuleViolation("campaign changed during election")
            self.campaign.check(self.bank,self.qualified,self.p)
        if self.approved_record_hash and self._effect_commitment()!=self._effects_hash:
            raise RuleViolation("reviewed vote effects changed")

    def _check_open(self, height: int) -> None:
        self._check_review_effects()
        if self.bank.record_hash() != self.record_hash:
            raise RuleViolation("examination record changed after vote opened")
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
        record = self.attempts.records.get(ticket)
        if record is None or record.issue != self.issue:
            raise RuleViolation("unknown ticket for this issue")
        owner = record.voter
        # A voter-chosen secret MUST NOT select the panel. All retries keep the same panel.
        members = tuple(draw(H(b"exam-panel-v2", self.beacon, self.issue, owner), self.pool, self.p.exam_panel,
                             exclude={a for a in self.pool if a == owner or a in self.recused
                                      or self.registry.get(a).operator == self.registry.get(owner).operator
                                      or (self.campaign and self.registry.get(a).operator in self._campaign_conflicts)}))
        if len(members) < self.p.exam_panel:
            raise RuleViolation("examiner pool too small for a grader panel")
        return Board(f"panel-{ticket[:12]}", members, self.issue)

    def plan(self, attempt, declared: tuple):
        if self.campaign:
            seed=H(b'campaign-voter-exam',self.beacon,self.issue,attempt.voter,attempt.n)
            return self.campaign.plan(self.bank,seed,declared,self.p)
        return plan_exam(self.bank, self.beacon, attempt.ticket, declared, self.p)

    def grade(self, attempt, sub: Submission, member_verdicts: dict, signers: list, height: int
              ) -> tuple[Token, bool]:
        """Board step. member_verdicts: member -> {qid: bool}. Returns (token, bond_slashed).
        Raises if the exam failed (voter may retry until attempts run out)."""
        self._check_open(height)
        if (sub.ticket != attempt.ticket or self.attempts.records.get(attempt.ticket) != attempt
                or attempt.issue != self.issue):
            raise RuleViolation("unknown ticket")
        if attempt.ticket in self.issued:
            raise RuleViolation("ticket already graded")
        self._check_voter(attempt.voter, height)
        panel = self.panel_for(attempt.ticket)
        if any(m not in panel.members for m in member_verdicts):
            raise RuleViolation("verdict from a member outside this ticket's panel")
        if any(not self.registry.can(m, "GRADE", height, self._matter())[0] for m in member_verdicts):
            raise RuleViolation("grader lacks current independent examiner authority")
        if len(member_verdicts) < panel.threshold:
            raise RuleViolation("not enough graders")
        plan = self.plan(attempt,sub.declared_articles)
        items = [q.qid for q in plan.proposal_qs] + [q.qid for _, q in plan.sampled]
        res = majority(member_verdicts, items)
        verdict = evaluate(plan, res, self.p)
        if not verdict.passed:
            raise RuleViolation("comprehension check failed")
        if (len(set(signers)) != len(signers) or not set(signers) <= set(member_verdicts)
                or not set(signers) <= set(panel.members)):
            raise RuleViolation("token signers must be distinct graders on this panel")
        tok = issue_token(panel, self.keyring, self.issue, attempt.ticket, verdict, signers,
                          height, self.p)
        verify_token(tok, panel, self.keyring, self.issue, height)
        # Commit scores/bonds only once token validation has succeeded.
        for m, v in member_verdicts.items():
            for it in items:
                self.scoreboard.record_item(m, v.get(it, False) == res[it])
        slashed = verdict.slash
        if slashed:
            ident = self.registry.get(attempt.voter)
            ident.bond -= min(ident.bond, self.p.citizen_bond // 10)
            self.slashed.append(attempt.voter)
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
        recorded = self.issued.get(ticket)
        if recorded is None or recorded[2] != voter:
            raise RuleViolation("unrecorded eligibility token")
        if self.kind == ELECTION:
            w = 1
            if not isinstance(choice, tuple):
                raise RuleViolation("election ballot must be a tuple of picks")
        else:
            recorded = self.issued.get(ticket)
            if recorded is None or recorded[2] != voter:
                raise RuleViolation("unrecorded eligibility token")
            # Valid old signatures cannot undo a board's authoritative downward correction.
            w = weight(min(token.R, recorded[0].R), self.p)
        if self.point_ids and (type(choice) is not tuple or len(choice)!=len(self.point_ids)
                               or any(c not in (YES,NO,ABSTAIN,None) for c in choice)
                               or all(c is None for c in choice)):
            raise RuleViolation('point ballot must match the locked point list')
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
        # Audit assignment also ignores the client secret, preventing offline sample evasion.
        labels = {hx("audit-slot", self.issue, self.attempts.records[t].voter,
                     self.attempts.records[t].n): t for t in self.issued}
        return [labels[label] for label in draw(H(b"audit-v2", self.beacon), sorted(labels), min(n, len(labels)))]

    def audit(self, ticket: str, true_verdict, height: int) -> str:
        """Board re-grades one issued token while voting is still open. Returns OK | CORRECTED |
        STRUCK. A wrong token revokes it, strikes/corrects the sealed ballot, and flags the
        panel members who signed it."""
        self._check_open(height)
        if ticket not in self.issued:
            raise RuleViolation("unknown ticket")
        tok, panel, voter = self.issued[ticket]
        if type(true_verdict.R) is not int or not 0 <= true_verdict.R <= tok.R:
            raise RuleViolation("an audit may only reduce verified reading")
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
            corrected = weight(true_verdict.R, self.p)
            self._sealed[voter] = (choice, corrected)
            self.commits[voter] = hx("ballot-commit", voter, self.issue, str(choice), corrected)
        self.issued[ticket] = (replace(tok, R=true_verdict.R), panel, voter)
        return "CORRECTED"

    # ------------------------------------------------------------- close / certify
    def certificate_message(self) -> bytes:
        if self.phase is Phase.VOTING:
            raise RuleViolation("not closed")
        if self._campaign_hash:
            return H(b"tally-cert-campaign",self.issue,self._campaign_hash,self.commitment,self._outcome_label())
        if self.approved_record_hash:
            return H(b"tally-cert-reviewed",self.issue,self.approved_record_hash,self._effects_hash,
                     self.commitment,self._outcome_label())
        return H(b"tally-cert", self.issue, self.commitment, self._outcome_label())

    def _outcome_label(self) -> str:
        r = self.result
        if isinstance(r, ElectionResult):
            return f"{r.valid}:{sorted(r.credits.items())}:{r.governing_parties}"
        if isinstance(r,BillResult):
            return f"{r.outcome.value}:{r.point_outcomes}:{r.passing_points}"
        return f"{r.outcome.value}:{r.yes_w}:{r.no_w}:{r.abstain_n}:{r.participation}"

    def close(self, height: int) -> None:
        self._check_review_effects()
        if self.phase is not Phase.VOTING:
            raise RuleViolation("already closed")
        if height < self.w.vote_end:
            raise RuleViolation("voting window still open")
        if self.rules_hash != self.p.snapshot_hash():
            raise RuleViolation("rules changed during vote")
        shards = shard_count(self.size, self.p)
        if self.point_ids:
            columns=[[Ballot(v,choices[i],w) for v,(choices,w) in self._sealed.items() if choices[i] is not None]
                     for i in range(len(self.point_ids))]
            result=tally_bill(columns,self.size,self.kind,self.p)
            passing=set(result.passing_points)
            indexes={q:i for i,q in enumerate(self.point_ids)}
            while True:
                retained={i for i in passing if all(indexes[q] in passing for q in self.point_dependencies[i])}
                if retained==passing:break
                passing=retained
            outcome=(Outcome.PASSED if len(passing)==len(self.point_ids) else Outcome.PARTIAL if passing else
                     result.outcome if result.outcome not in (Outcome.PASSED,Outcome.PARTIAL) else Outcome.FAILED)
            self.result=BillResult(outcome,result.point_outcomes,tuple(sorted(passing)),result.review_flag)
            self.commitment=H(b'point-ballots',self.issue,self.point_ids,sorted(self._sealed.items()),self._outcome_label())
        elif self.kind == ELECTION:
            groups: list[dict] = [dict() for _ in range(shards)]
            for v, (choice, _) in self._sealed.items():
                groups[shard_of(v, shards)][v] = choice
            es = [summarize_election_shard(g, self.qualified, self.p) for g in groups]
            self.result = election_from_shards(es, self.qualified, self.p)
            if sum(e.count-e.invalid for e in es)*10000<self.size*self.p.quorum_bps:
                self.result=ElectionResult(False,'NO_QUORUM',self.result.points,self.result.total_points,{},self.result.invalid_ballots)
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
        if self.phase is not Phase.CHALLENGE or not self.w.vote_end <= height < self.w.challenge_end:
            raise RuleViolation("no open challenge window")
        ok, why = self.registry.can(by, "FILE_CASE", height)
        if not ok:
            raise RuleViolation(f"cannot file: {why}")
        if any(ch.by == by for ch in self.challenges):
            raise RuleViolation("one challenge per identity per issue")
        if not isinstance(grounds, str) or not 0 < len(grounds) <= 1024:
            raise RuleViolation("challenge grounds outside bounds")
        self.challenges.append(Challenge(by, grounds))
        return len(self.challenges) - 1

    def rule(self, court: Actor, idx: int, upheld: bool, height: int) -> None:
        if self.phase is not Phase.CHALLENGE or height < self.w.vote_end:
            raise RuleViolation("not in challenge phase")
        if type(idx) is not int or not 0 <= idx < len(self.challenges):
            raise RuleViolation("unknown challenge")
        self.registry._authorize(court, {"COURT"}, height, "CHALLENGE", f"{self.issue}:{idx}")
        ch = self.challenges[idx]
        if ch.status != "OPEN":
            raise RuleViolation("already ruled")
        self.registry._spend(court)
        ch.status = "UPHELD" if upheld else "REJECTED"

    def extend(self, actor: Actor, delta: int) -> None:
        """Halt compensation: an outage of `delta` cannot shorten any remaining window."""
        if self.phase in (Phase.FINAL, Phase.VOIDED):
            raise RuleViolation("terminal session")
        if actor.kind != "MODULE" or type(delta) is not int or delta <= 0:
            raise RuleViolation("module only, positive delta")
        if self.phase is Phase.VOTING:
            self.w.vote_end += delta
        self.w.certify_end += delta
        self.w.challenge_end += delta

    def finalize(self, height: int) -> Outcome | str:
        self._check_review_effects()
        if self.phase is not Phase.CHALLENGE:
            raise RuleViolation("not in challenge phase")
        if height < self.w.challenge_end:
            raise RuleViolation("challenge window still open")
        if any(c.status == "OPEN" for c in self.challenges):
            if height < self.w.challenge_end + self.p.challenge_resolution_grace:
                raise RuleViolation("unresolved challenge")
            # Fail closed on court unavailability: no grant, no permanent reservation.
            self._unwind(refund=True)
            self.phase, self.outcome = Phase.VOIDED, None
            self.registry._log(height, Actor("MODULE", "tally"), "CHALLENGE_TIMEOUT", self.issue)
            return "VOIDED"
        if any(c.status == "UPHELD" for c in self.challenges):
            self._unwind(refund=True)
            self.phase, self.outcome = Phase.VOIDED, None
            return "VOIDED"
        r = self.result
        if isinstance(r, ElectionResult):
            self.phase = Phase.FINAL
            self.outcome = Outcome.PASSED if r.valid else Outcome.NO_QUORUM if r.reason=='NO_QUORUM' else Outcome.FAILED
            return self.outcome
        e = self.effects
        if r.outcome in (Outcome.PASSED,Outcome.PARTIAL):
            if e.treasury and e.ceiling:
                tranches=e.tranches;milestones=e.milestones
                if isinstance(r,BillResult):
                    tranches=[amount for i in r.passing_points for amount in e.point_tranches[i]]
                    milestones=tuple(m for i in r.passing_points for m in e.point_milestones[i])
                if tranches:
                    e.treasury.commit_reserved(e.project,tranches)
                    e.treasury.milestone_conditions[e.project]=tuple(milestones)
                else:e.treasury.release_reservation(e.project)
            if isinstance(r,BillResult):self.effective_points=tuple(self.point_ids[i] for i in r.passing_points)
        else:
            self._unwind(refund=(r.outcome is Outcome.NO_QUORUM and self.p.refund_on_no_quorum))
        self.phase, self.outcome = Phase.FINAL, r.outcome
        return self.outcome

    def _unwind(self, refund: bool) -> None:
        e = self.effects
        if e.treasury and e.ceiling and e.project in e.treasury.reserved:
            e.treasury.release_reservation(e.project)
        if refund and e.credits and e.proposer_party and e.credits.month==e.credit_month:
            e.credits.grant(e.proposer_party, self.p.proposal_cost)   # D-12
