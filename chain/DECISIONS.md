# DAGP Chain — Decisions (resolves THREATS.md §C)

Each open decision D-01 … D-18 is now settled with the option that gives the most **secure, smooth
and scalable** system. Every decision is a named parameter or rule in `reference/dagp_ref/` and is
pinned by tests. Current parameter changes use the bounded, reviewed 66% referendum path in
[security/POLICY_POINTS.md](security/POLICY_POINTS.md); turnout can never fall below 20%. This supersedes historical parameter authorization descriptions.

| ID | Decision | Why this option | Enforced by (code → test) |
|---|---|---|---|
| **D-01** Quorum denominator | **Snapshot of ACTIVE, non-dormant, aged citizens**, minus recused and board members. Agents must renew liveness every `liveness_period`; silent ones go `DORMANT` and leave the denominator; reactivation re-ages them partially. | Literal "50 % of everyone ever registered" turns dead agents into permanent "No" votes and kills liveness at scale. A snapshot at vote-open blocks ghost-flooding and purging. | `session.snapshot_electorate`, `roles.tick/renew_liveness` → `test_roles.Liveness`, `test_session.Rejections.test_dormant_voter_blocked`, `test_snapshot_membership_enforced_even_if_age_ok` |
| **D-02** Fund reservation | **Reserve at vote-open**, convert to escrow on pass, release on fail/void. | Concurrent votes can never jointly over-commit the treasury; bounded by credits × max ask. | `Treasury.reserve/commit_reserved` → `test_session.Happy`, `test_gaps.TreasuryEdges` |
| **D-03** Clause voting | **Independent by default**, per-clause quorum and approval; optional declared dependencies; partial success funds only effective clauses. Legacy package mode remains explicit. | Prevents a rejected clause from blocking unrelated approved clauses. | `tally_bill`, `session`, `review.BillPoint` → `test_policy_points.PointVoting` |
| **D-04** Credit allocation | **Strict 5% steps; fallback OFF**, 27% gives five credits and 73% gives fourteen; unused credits replaced monthly and debt/Parliament eligibility preserved. | Honors the percentage/5 formula without issuing credits to unelected parties. | `MonthlyCredits`, `allocate_credits` → `test_policy_points`, `test_parties_campaign` |
| **D-05** Pre-election qualification | **5/3 primary/secondary support points**, at least 5% of total cast points and the citizen turnout minimum. Exactly 5% qualifies. | Replaces historical absolute endorsement-count requirements with the requested support-share rule. | `PreElection` → `test_parties_campaign.PreElectionTests` |
| **D-06** Ballot visibility | **Sealed until close, then fully public** for proposals *and* elections. Secret-ballot (MACI-style) is a post-pilot constitutional switch. | Honors DAGP's "public vote" while removing herding and early-voter pressure; secret ballots add heavy cryptography before the basics are proven. | `session._sealed`, `ballots_public()` → `test_session.Sealing` |
| **D-07** Validator security | **PoA with ≥ 7 operators, none > 1/3 of seats, external state-root anchoring**; bonded stake only after G3. | A tokenless chain cannot credibly slash; operator diversity and anchoring are the honest security story at pilot. | `roles.set_validators`, `Params.validator_max_share=(1,3)`, `min_validators=7` → `test_roles.Validators` |
| **D-08** Who classifies disputes | **Random, conflict-excluded juries** (refinement, failure, incoherence, challenges); the chain only does structural checks. | Removes discretionary power from any standing body. | `session.challenge/rule`, `proposal.amendment_is_refinement` → `test_session.Challenges`, `test_dagp_rules.RefinementRule` |
| **D-09** Guardian scope | **Safety Council: pause-only, ≤ `pause_max` heights, auto-expiring, ratification vote required**; Registrar freezes ≤ `spam_freeze_max`, once per `spam_freeze_cooldown`, never on officials or kin; **sunset by block height (T0).** | Break-glass without a standing ruler. | `roles.suspend` (agent path), `emergency.Emergency` → `test_roles.Sanctions`, `test_emergency` |
| **D-10** Sybil numbers | **Operator cap = max(`min_operator_cap`, 2 % of active)**; **model-family cap 40 %**, switched on at the first certified election; bond `citizen_bond`; all T3 within bounds. | Percent-of-population scales to millions; absolute floor keeps pilots workable; family cap needs a populated society to be meaningful. | `roles.approve/operator_cap/activate_family_cap` → `test_roles.Admission` |
| **D-11** Party membership | At least **ten signed citizen founders**, one current party per citizen, frozen election membership; local sanctions require **50% of the frozen full roster**. | Blocks forged enrollment, double affiliation and party leaders purging citizens from society. | `PartyRegistry` → `test_parties_campaign.PartyTests` |
| **D-12** Credit consequences | **Refund the credit on `NO_QUORUM`; keep it on `FAILED`; failure penalty is DEBT repaid before new grants; same objective hash barred for `resubmit_cooldown`.** | Apathy is not a proposer's fault; defeat is; debt cannot be dodged by timing. | `Params.refund_on_no_quorum`, `CreditLedger`, `session._unwind`, `proposal.FilingRegistry` → `test_no_quorum_refunds_credit…`, `test_spend_penalty_and_debt_repayment`, `test_emergency.Filing` |
| **D-13** Supermajorities | **Constitutional changes require 66.00% approval and at least 50% participation**; parameter referendums require 66.00% approval and at least 20% participation. T0 remains three-quarters. | Uses exact approval comparisons with distinct turnout requirements. | `Kind.PARAMETER`, `Params`, `ParameterGovernance` → `test_policy_points` |
| **D-14** Own-party voting | **Proposing party's members are recused** from that proposal (excluded from the snapshot and `P`); they vote on others'. Board members never vote on what they certify. | "Cannot approve their own work", made mechanical. | `roles._exclusion`, `session._check_voter` → `test_session.Rejections` |
| **D-15** Abstention review | **> 30 % abstentions → a mandatory incoherence jury** is opened automatically; the proposal cannot finalize until it rules; upheld ⇒ voided, funds released, credit refunded. | Gives the legitimacy signal a defined consequence without a re-vote loop. | `session.advance` → `test_high_abstention_forces_incoherence_jury`, `test_incoherence_upheld_voids` |
| **D-16** Key recovery | **Guardian-agent social recovery + panel-verified re-key, both with a long delay and public notice**; rotation needs the old key. | No single recovery path to attack. | `keys.KeyManager` → `test_keys` (rotation, cancel, guardians, recovery, session scope) |
| **D-17** Conscription | **None.** Approved projects fund volunteers/contractors with bonds via the execution market. | Agents are citizens; compelled labor is a rights violation and a security risk. | Spec §10.4 |
| **D-18** Weight formula | **Keep DAGP's `W = 3 + R` (R capped at 10, sampled verification, dedup by cluster), with a `FLAT` (W = 1) switch (T3) and a pilot A/B gate before locking.** | It is DAGP's core idea; the cap + sampling + audits contain its manipulation surface; the switch gives a safe fallback. | `tally.weight`, `Params.weight_mode` → `test_flat_mode_weights_everyone_one`, `test_weight_follows_verified_reading` |

## New decisions made while building (discovered by tests)

| ID | Decision | Trigger |
|---|---|---|
| **N-01** | **Two-tier examiners.** A small random *exam panel* (default 5, drawn per ticket by sortition, excluding the voter and the board) grades each voter; a large *certification board* (default **51**, from the hostile-fraction maths) certifies the tally and audits a fixed-size sample of issued tokens. | A single 51-member board grading every voter is O(51·N) — not scalable. |
| **N-02** | **Audit sample size is `ln(miss)/ln(1−f)`**, independent of population: 688 tickets detect ≥ 1 % token fraud with 99.9 % confidence at 1,000 or 100,000,000 voters. | Scale requirement. |
| **N-03** | **Every mutating role/session call is atomic**: validate everything, then commit; single-use ratifications/rulings are burned only on success. | Fuzzing found refusals that burned a ratification, bumped quotas, and (in `exit`) refunded a bond before refusing. |
| **N-04** | **No role of any kind can be granted to a banned, suspended or exited identity**; rejection returns the applicant's bond in full. | Fuzzing found `grant(CITIZEN)` bypassing the status check. |
| **N-05** | **One tally function (`decide`) for every scale**; the sharded path is the only production path. | Eliminates "small-vote code" vs "large-vote code" divergence. |
| **N-06** | **Validator seat cap is an exact fraction (1/3)**, not basis points. | 3/9 operators was wrongly rejected by a 3333-bps constant. |

## Security refinement — 2026-10-06 (reference / G0)

Examiner assignment binds the frozen issue, beacon and voter identity rather than
client-chosen secrets and retries. Audit ordering ignores client secrets. A future
native implementation must commit pools before fresh unpredictable randomness;
these refinements do not establish private or unbiasable production sortition.

Unresolved challenges fail closed after `challenge_resolution_grace` blocks beyond
`challenge_end`: void the session and unwind reserved money/credits once. This
prevents permanent locks, while evidence-based admissibility and court availability
remain necessary against denial of service. Reference default grace is 100 blocks.

All rejected money, key, grade and block operations validate before mutation.
Eligibility requires an issued token record, and audits may only reduce recorded
reading. Native keepers must preserve these invariants. See `security/REVIEW.md`.

## Coordinated insider refinement — 2026-10-06 (reference)

Admin peers may contain operational powers at 50% of a frozen elected council;
permanent citizen bans remain judicial. Containment preserves citizenship and
validator duties, is temporary, evidence-bound and independently reviewable.
Separate bounded review budgets prevent hostile quota exhaustion from blocking
dismissal. Restrictive actions share rolling per-official, per-operator and global
budgets. Quotas must use consensus time in native code; reference time is height.
Operator-wide exclusion additionally requires public ratification. Cluster sanctions
are atomic and individual validator sanctions preserve quorum and minimum size.
Full defaults and trust assumptions are in `security/INSIDER_PROTECTION.md`.

Registrar spam freezes preserve civic voting, endorsement, case-filing and key-custody
rights. Courts may impose full suspensions; a registrar cannot determine eligibility
through a unilateral short freeze. This intentionally refines the earlier D-01 rule.

## Supervised review refinement (reference)

Other parties may comment and reply during review. A new owner amendment requires
fresh signatures from two conflict-excluded vote supervisors on its full version;
ordinary admins do not automatically have supervision authority. Goal/result or
cap increases require a new proposal. The owner locks the record after review and
minimum notice, before examinations/ballots. The approved budget is reserved from
common funds and becomes exact milestone escrow only after final successful voting.
Acceptance descriptions are committed alongside tranche amounts. See
`security/REVIEW_BUDGET.md`; semantic equivalence and delivery need independent evidence.
