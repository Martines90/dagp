"""Governance parameters. All ratios are integers (basis points or exact fractions); no floats.

A Params object is frozen and hashed into a RuleSnapshot when a vote opens, so a
tally always runs against the rules that were in force when voting began.
Defaults encode the decisions recorded in DECISIONS.md (D-01 .. D-18).
Time is an abstract monotonically increasing `height` (blocks); EPOCH heights = 1 epoch.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

BPS = 10_000


@dataclass(frozen=True)
class Params:
    # --- voting (exact fractions as (numerator, denominator)) ---
    quorum_bps: int = 5_000              # participation >= 50% of snapshot electorate
    ordinary: tuple = (1, 2)             # Yw/(Yw+Nw) strictly greater than
    supermajority: tuple = (2, 3)        # at least (D-13: "66 percent" read as two-thirds)
    core: tuple = (3, 4)                 # T0 entrenched core (each of two votes)
    abstain_review_bps: int = 3_000      # above this share an incoherence jury is mandatory (D-15)
    base_weight: int = 3
    weight_mode: str = "WEIGHTED"        # or "FLAT" (D-18: weighted by default, flat is a T3 switch)
    max_articles_counted: int = 10       # cap on R so W <= base_weight + 10
    max_bill_points: int = 10
    package_fail_basis: str = "NOT_PASSED"  # D-03 (alt: "NO_MAJORITY")
    # --- elections ---
    ballot_picks: tuple = (4, 2, 1)
    party_threshold_bps: int = 500
    credit_step_bps: int = 500
    credit_ceiling_bps: int = 5_000
    min_qualified_parties: int = 3
    min_party_members: int = 10
    endorse_bps: int = 910               # frozen to an absolute number per cycle (D-05, ceil)
    endorsements_per_agent: int = 2
    min_total_credits: int = 3           # D-04: agenda-starvation floor ON
    floor_credits_each: int = 1
    # --- credits ---
    proposal_cost: int = 1
    failure_penalty: int = 1
    refund_on_no_quorum: bool = True     # D-12
    resubmit_cooldown: int = 500         # heights before the same objective may be re-filed
    # --- identity / roles (D-01, D-09, D-10, D-11) ---
    epoch: int = 100
    min_citizen_age: int = 200
    liveness_period: int = 1_000
    citizen_bond: int = 10
    examiner_stake: int = 50
    max_operator_share_bps: int = 200    # per operator, of active citizens ...
    min_operator_cap: int = 3            # ... but never below this absolute floor
    max_family_share_bps: int = 4_000    # per model family, enforced after first election
    validator_max_share: tuple = (1, 3)   # one operator may hold at most 1/3 of validator seats
    min_validators: int = 7
    registrar_quota_per_epoch: int = 50
    spam_freeze_max: int = 50
    spam_freeze_cooldown: int = 500
    pause_max: int = 300
    ban_slash_bps: int = 5_000
    # --- comprehension / board (D-08) ---
    exam_pass_bps: int = 7_000
    exam_max_attempts: int = 3
    exam_items: int = 5                  # proposal-topic questions per attempt
    sample_articles: int = 3             # declared articles spot-checked per attempt
    token_ttl: int = 500
    exam_panel: int = 5                  # graders per voter exam, drawn per ticket (O(1) per voter)
    audit_fraud_bps: int = 100           # detect token fraud at >= 1% ...
    audit_miss_den: int = 1_000          # ... with >= 99.9% probability
    assumed_bad_bps: int = 2_000         # design assumption: <=20% of examiner pool is hostile
    board_fail_den: int = 1_000_000      # target P(hostile majority on a board) <= 1e-6
    canary_min_accuracy_bps: int = 8_000
    canary_min_samples: int = 20
    # Rolling model-day windows; native keepers must use committed consensus time.
    protection_day_blocks: int = 14_400
    sanction_actor_limit: int = 2
    sanction_operator_limit: int = 2
    sanction_global_limit: int = 20
    sanction_population_bps: int = 200
    sanction_population_floor: int = 3
    ban_global_limit: int = 5
    admission_actor_limit: int = 50
    admission_global_limit: int = 250
    pause_actor_limit: int = 2
    pause_global_limit: int = 10
    pause_concurrent_bps: int = 2_000
    admin_containment_duration: int = 300
    admin_vote_window: int = 100
    admin_min_council: int = 5
    challenge_resolution_grace: int = 100  # unresolved juries cannot lock funds forever
    challenge_window: int = 200
    rotation_delay: int = 50             # key rotation takes effect this long after the signed request
    recovery_delay: int = 250            # guardian recovery: long, public, cancellable (D-16)
    max_session_ttl: int = 500
    min_guardians: int = 3
    shard_target: int = 10_000           # ballots per tally shard (scale, constant work per shard)

    def __post_init__(self):
        positive = (self.protection_day_blocks,self.sanction_actor_limit,self.sanction_operator_limit,
                    self.sanction_global_limit,self.sanction_population_floor,self.ban_global_limit,
                    self.admission_actor_limit,self.admission_global_limit,self.pause_actor_limit,
                    self.pause_global_limit,self.admin_containment_duration,self.admin_vote_window,
                    self.admin_min_council)
        if any(type(n) is not int or n <= 0 for n in positive):
            raise ValueError("protection limits and windows must be positive integers")
        if any(type(n) is not int or not 0 < n <= BPS for n in
               (self.sanction_population_bps,self.pause_concurrent_bps)):
            raise ValueError("protection fractions outside (0,10000]")
        if self.admin_min_council < 3:
            raise ValueError("admin council needs at least three members")

    def snapshot_hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()

    @property
    def credit_cap(self) -> int:
        return self.credit_ceiling_bps // self.credit_step_bps
