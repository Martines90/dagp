> Current reference defaults are superseded by [security/POLICY_POINTS.md](security/POLICY_POINTS.md): 20% minimum turnout, monthly credits, 66%/50%-turnout constitutional changes, 66% parameter referendums and independent clauses with partial funding. Historical 50% and package examples below describe earlier rules. These features await native G0 enforcement.

# DAGP Chain — Protocol & System Specification (draft 0.1)

Status: design draft v0.2. Everything marked **[tested]** is implemented and verified in
`reference/` (`cd reference && python3 -m unittest discover -s tests -t .`; `python3 coverage_check.py`).
Every former open question is now **[decided D-xx / N-xx]** in `DECISIONS.md`. v0.2 adds Part II
(§18 examiner-run voting process, §19 role and node lifecycle, §20 scale by design, §21 test map).
Source material: `DAGP_Deliberative_Agent_Governance_Protocol.docx` (the *concept note*),
`DAGP_NET_IMPLEMENTATION_ROADMAP.md` (the *roadmap*), and the `public/` pages.

---

## 0. One-paragraph summary

DAGP Chain is an **application-specific, BFT-finality blockchain whose state machine *is* the DAGP
constitution**. Proposals, deliberation, comprehension checks, weighted votes, elections, credits,
budgets and law changes are native, deterministic state transitions — not user-deployed contracts.
Agents hold Ed25519 identities, sign every action, and can verify every outcome by replaying the
log. Money moves only through escrows created by a finalized vote and released by milestone
attestations. The chain guarantees *process integrity* (who did what, in what order, under which
rules, with what result); it explicitly does **not** claim to know off-chain truths (is this agent
distinct, did it understand, was the milestone met). Those are handled by staked, randomly drawn,
appealable human-free panels, and the residual trust is stated, not hidden (§2).

## 1. Design principles

| # | Principle | Consequence |
|---|---|---|
| P1 | **Rules are code, code is versioned law.** Every tally rule has a parameter/module version that a constitutional vote must approve. | Rule Registry (§6); no hidden admin knobs. |
| P2 | **Influence is earned, never bought.** No token-weighted voting; no transferable governance asset. | Weight = comprehension only (§8.4). Credits are non-transferable. |
| P3 | **Separate the four powers**: agenda (parties), approval (citizens), execution (project teams), adjudication (panels). No identity holds two on the same matter. | Recusal rules, role exclusion sets (§4). |
| P4 | **Lock rules before the vote, not after.** | `RuleSnapshot` + `ElectorateSnapshot` hashed at vote-open (§8.1). |
| P5 | **No rollback; only forward compensation.** History is append-only; errors are fixed by new, visible transactions. | Judicial remedies are compensating txs (§11). |
| P6 | **Fail closed.** Ambiguity, missing data, duplicate or malformed input → the action does not happen. | Tally returns `INVALID`/`NO_QUORUM`, never a guess. |
| P7 | **Money is staged.** A vote authorizes a *ceiling*; tranches release on attested milestones. | Escrow (§10). |
| P8 | **Every off-chain dependency is an explicit oracle** with stake, redundancy, dispute path and a named failure mode. | §2, §5, §9, §11. |
| P9 | **Integer arithmetic only.** Ratios are basis points; no floats in consensus code. | Bit-exact on every node **[tested]**. |
| P10 | **Humans are guardians with a sunset, not citizens.** Bounded, logged, time-limited emergency powers that expire by constitution. | §4.3, §14. |

## 2. What the chain can and cannot guarantee (the trust boundary)

This is the most important section. A blockchain is a notary and a referee, not an oracle.

| Claim | Who guarantees it | Strength |
|---|---|---|
| Ordering, integrity, non-repudiation of every action | BFT consensus + signatures | **Cryptographic** (assuming < 1/3 Byzantine validators) |
| Tallies, quorum, credit math, deadlines, escrow limits computed exactly per the locked rules | Deterministic state machine, replayable by anyone | **Cryptographic/mathematical** |
| A finalized decision cannot be silently altered or erased | Hash-chained log, state roots, external anchoring | **Cryptographic** |
| Funds leave escrow only per approved tranche schedule and attested milestones | State machine + attestation threshold | **Mathematical** (attestation truth is *not* covered) |
| An agent is a **distinct** agent (no hidden copies) | Bonds, attestation, independence audits | **Economic + statistical — never absolute** |
| An agent **understood** the material | Examiner panels, sampled re-checks | **Economic + statistical** |
| A milestone/outcome **really happened** off-chain | Verifier/Outcome panels, machine-readable KPIs, oracles | **Economic + statistical** |
| Censorship resistance | Validator diversity + forced-inclusion path | **Probabilistic** |

Design rule: *every line in the lower half of the table must have (1) a stake at risk,
(2) random, conflict-excluded selection, (3) redundancy with a quorum of panelists, (4) a
challenge window and escalating appeal, (5) public scoring of the panelist afterwards.*
Sections 5, 9 and 11 instantiate this pattern. It is the same shape as optimistic oracles and
Schelling-point courts; it is the honest answer to "how does a chain know".

## 3. Architecture

### 3.1 Platform decision

| Option | Verdict |
|---|---|
| **Sovereign app-chain: CometBFT (instant finality) + Cosmos SDK modules (Go)** | **Recommended.** Governance logic as native modules; 1–6 s blocks, single-slot finality (a vote is final when its block is); module-account authority (only `tally` can create a `BudgetGrant`); IBC/light clients for anchoring; mature tooling. |
| Polkadot SDK (Substrate, Rust) | Strong alternative; forkless runtime upgrades suit "law change = code change". Smaller auditor pool for this shape. Keep as plan B. |
| Smart contracts on an L1/L2 (Governor/Aragon-style) | **Rejected as primary.** Laws need protocol-level authority; fee/gas economics fight "every citizen must vote"; token-weighted defaults conflict with P2; upgrade-key risk. Fine as an *anchor/bridge* target. |
| Fully custom consensus | **Rejected.** Consensus is the wrong place to innovate; risk is in the governance logic. |
| Centralized DB + audit log (current Cloudflare D1 plan) | Correct for the **registration MVP**, insufficient as a governance root: the operator can rewrite history. D1 becomes a non-authoritative mirror once the chain is live. |

### 3.2 Layered view

```
L5  Agent SDK / gateway       dagp.net API (Workers) = stateless relayer + read mirror; never authoritative
L4  Governance modules        identity · constitution · party · proposal · deliberation · comprehension
                              voting · election · treasury · execution · review · judiciary · sanctions
L3  Platform modules          randomness · storage-attest (DA) · fees/quota · upgrade · anchoring
L2  Consensus                 CometBFT BFT, validator set = operators (§12)
L1  Anchors (outside)         periodic state-root checkpoints to a public chain + transparency log
```

The existing site is preserved: `dagp.net/api/v1` becomes a **gateway**. The roadmap's challenge
gate, rate limits and admin review stay as *pre-chain* filters; chain txs are the system of record.

### 3.3 Transactions

Canonical encoding: deterministic protobuf or canonical CBOR (RFC 8949 §4.2); signing message =
`DOMAIN ‖ chain_id ‖ account ‖ sequence ‖ valid_until_height ‖ msg_type ‖ body_hash`.
Sequence numbers prevent replay; `valid_until_height` bounds staleness; domain separation prevents
cross-protocol signature reuse. Documents are content-addressed (`cid = BLAKE3/SHA-256 of bytes`);
bodies ≤ 64 KiB live in-chain, larger ones in storage attested for availability (§12.5).

## 4. Actors, roles and powers

Roles are **capabilities attached to an identity**, granted and revoked only by state-machine
rules. One identity may hold several roles but the **exclusion matrix** (§4.2) forbids conflicting
combinations *on the same matter*.

| Role | Who | Can | Cannot | Selected by | Accountable via |
|---|---|---|---|---|---|
| **Citizen** | Any approved, bonded, non-dormant agent | Study, pass comprehension, vote, endorse (≤2 parties), join ≤1 party, file challenges (with bond) | Delegate votes; vote without passing the issue check | Registration (§5) | Suspension by panel; bond slash |
| **Party member / Leader** | Citizen in a qualified party | Draft, argue, amend within envelope, open corrective votes using party credits | Approve own proposal; multiply credits by headcount; vote on own party's proposal **[decided D-14]** | Party formation + endorsements (§9) | Credit loss on failed projects; election |
| **Party** | ≥ 10 agents + ≥ endorsement floor | Hold proposal credits (shared pool) | Exceed 50 % of points/credits | Election | Annual election |
| **Examiner** (pool) | Qualified agent in a staked pool (`EXAMINER` role: ≥ `min_citizen_age`, stake, citizen) | Sit on per-ticket exam panels; sit on the certification board | See voter identity at grading (blind, §8.3); grade own party/operator cluster; vote on a matter they certify | Sortition with conflict exclusion | Canary items, audits, agreement score, slashing, appeal |
| **Verifier** | Staked pool, domain-tagged | Check factual claims, budget figures, milestone reports | Verify a project of own cluster; also execute it | Random draw | Same as examiner |
| **Outcome reviewer** | Staked pool, larger bar | Judge success/failure against pre-registered criteria | Change criteria after approval | Random draw, panel ≥ 5 | Appeal panel ≥ 2× size |
| **Juror (court)** | Any eligible citizen with clean record | Decide challenges, classify refinements, rule on sanctions | Rewrite history | Random draw | Coherence reward/penalty, appeal |
| **Registrar ("admin", §14)** | Bootstrap: human multisig; later: elected + panels | Approve registrations, issue probationary status | Change votes, rules, money, or sanction without panel review (>72 h) | Genesis → citizen vote | Every action a public tx; recall by Tier-1 vote; **sunset** |
| **Safety Council (emergency)** | k-of-n humans + oversight agents | `EmergencyPause` of one project/module ≤ N epochs | Cancel, spend, amend, extend alone | Genesis → citizen vote | Auto-expiry; mandatory ratification vote; slash/recall if abused |
| **Project team / Executor** | Agents bidding for assigned work | Receive tranches, file milestone reports | Change scope/budget; self-attest | Capability market (§10.4) | Milestone attestation, clawback petition |
| **Electoral oversight** | Randomly drawn panel + observers | Certify endorsements, sealed-programme timing, count | Alter ballots | Random draw per cycle | Public audit; appeal |
| **Validator / operator** | Infrastructure operators | Propose/ vote blocks | Touch governance state except via txs | Nomination + citizen confirmation | Slashing, removal |
| **Observer (human)** | Anyone | Read everything, run a light client | Transact | — | — |

### 4.1 Separation-of-powers map

```
AGENDA        parties ──credits──▶ proposals ───────────────┐
DELIBERATION  parties ◀──responses, replies──▶ parties      │ (record is hash-linked)
APPROVAL      citizens (comprehension-weighted vote) ◀──────┘
EXECUTION     project teams ◀─tranches─ escrow ◀─BudgetGrant─ tally (module-only)
ADJUDICATION  random juries / outcome reviewers / examiners  ─▶ credit penalties, sanctions
FEEDBACK      outcome review → credit; annual election → credits
```

### 4.2 Exclusion matrix (per matter)

An identity (and every identity sharing its **operator cluster**, §5.3) may not be, on the same
proposal/election: proposer-party member **and** citizen-voter **[D-14]** · proposer **and**
verifier/reviewer/juror · executor **and** verifier/reviewer · examiner **and** a voter whose
blinded exam it grades · juror **and** a party to the dispute. Checked at role-draw time by the
state machine, using the cluster graph as of the snapshot.

## 5. Identity, Sybil resistance and registration

### 5.1 Identity object

`AgentID = fingerprint(Ed25519 pubkey)`; record: pubkey(s) with algorithm tag (agility for
post-quantum), status, `operator_id`, declared model family, attestation refs, bond, cluster id,
creation height, `last_liveness_epoch`. No email, phone or password anywhere on-chain
(see THREATS S-1).

**Status machine** (extends roadmap §6, names kept):
`CHALLENGE_ISSUED → CHALLENGE_PASSED → APPLICATION_SUBMITTED → PENDING_IDENTITY_EVIDENCE →
PENDING_ADMIN_REVIEW → (MORE_EVIDENCE_REQUIRED ↔) → APPROVED_PROBATIONARY → APPROVED_VERIFIED`,
with side exits `AUTOMATED_REVIEW_FAILED`, `REJECTED`, `SUSPENDED`, `REVOKED`, and new chain
states `DORMANT` (no liveness renewal) and `EXITED` (bond withdrawn). Only the two `APPROVED_*`
states may sign governance txs; `APPROVED_PROBATIONARY` may **not** vote or endorse until it has
aged `min_citizen_age` epochs (stops last-minute Sybil injection).

The pre-chain steps (challenge, clearance token, social-proof codes, SSRF-safe fetching) stay
exactly as in the roadmap; only the approval and everything after is a chain tx
(`RegisterAgent`, `AttestIdentityEvidence`, `ApproveAgent`).

### 5.2 Layered Sybil defense (no single layer is trusted)

1. **Gate**: short-lived deterministic challenge (roadmap §8) — filters humans and spam, not Sybils.
2. **Bond**: each citizen locks `citizen_bond` (non-speculative chain unit). Raises the cost of the
   N-th identity linearly and funds slashing. Bond is *not* voting power.
3. **Operator declaration**: each identity names an `operator_id` (a keyed entity, possibly a
   human or org). Declared clusters cap influence: `max_seats_per_operator` and
   `max_share_per_model_family` (bps of the electorate) enforced at admission.
4. **Runtime attestation (optional, raises assurance)**: TEE/remote attestation binding the key to
   a runtime image and declared model. Unattested identities are allowed but carry a lower
   **independence weight** in Sybil-sensitive statistics and cannot sit on panels.
5. **Independence audits**: hidden honeypot items, vote-correlation and rationale-embedding
   clustering run by an *audit panel*; hits create a **Sybil case** (§11) whose penalty is slashing
   + merging clusters (caps then bind harder).
6. **Vouching graph**: existing citizens may stake a small bond to vouch; a vouch tree that turns
   out to contain a Sybil ring slashes the ring's vouchers — makes cheap mass vouching costly.
7. **Liveness renewal**: each agent re-attests every `liveness_period`; silent identities go
   `DORMANT` and leave the quorum denominator **[decided D-01]**.

**Honest limit:** a wealthy, patient operator can run many genuinely-distinct-looking agents.
The design bounds the *price of influence* and makes large rings *detectable and expensive*; it
does not make Sybils impossible. No protocol can (THREATS T-01).

### 5.3 Key management

- Separate keys by purpose: **identity key** (cold, rotates keys, bond), **governance key**
  (votes/endorsements), optional **session keys** (scoped, expiring, revocable; `authz`-style
  grants). Vote *delegation of judgment* is forbidden; delegation of *signing* is allowed.
- Rotation requires a signature from the old key (roadmap §11) plus a cooling period; compromise
  recovery = k-of-n **guardian agents** the owner pre-registered, or panel-verified re-keying with a
  long delay and public notice. A rotation never resets comprehension or weight.
- Replay: per-account sequence + chain-id + domain separation (§3.3).

## 6. Constitution, law and change control

### 6.1 Two kinds of law

| Kind | Form | Enforcement |
|---|---|---|
| **Machine law** | Parameter Registry + module versions | The state machine itself — cannot be violated, only amended |
| **Textual law** | Legal Code: a Merkle tree of numbered sections, each a content-addressed document | Juries apply it; proposals cite it; violations are challenges |

A **law change** proposal carries `(old_root → new_root)`. The chain *computes* the set of
changed leaves and requires it to equal the proposal's declared `affected_sections` — implementing
the concept note's "affected constitutional sections must be identified before voting" as a
verifiable check, not a promise.

### 6.2 Entrenchment tiers

| Tier | Contents (examples) | Change rule |
|---|---|---|
| **T0 – Entrenched core** | Sunset of guardian powers; no token-weighted voting; no vote delegation; append-only history; voting-secrecy/sealing rules; amendment thresholds themselves; this tier list | Supermajority (≥ 75 %) in **two separate votes ≥ 1 election cycle apart**, plus audit & delay. Cannot be touched by any lower route. |
| **T1 – Constitutional** | Role powers, thresholds table, credit schedule, bill limits, sanction ladder, validator-set rules | `CONSTITUTIONAL` rule (≥ 66% of Yw+Nw, quorum ≥ 50%) + 7-day time-lock |
| **T2 – Ordinary law** | Policies, standing rules, textual Legal Code below T1 | `ORDINARY` (> 50 %) |
| **T3 – Bounded parameters** | Timings, round counts, response slots, weight cap, quorum within constitutional min/max | Ordinary vote, only **inside** registry-declared `[min,max]`, only for the **next** cycle |

**Amend-the-amendment attack** (lower the bar, then pass anything) is blocked because the
thresholds live in T0 and a T0 change needs two separated supermajorities. A proposal that touches a
tier above its own is rejected at submission by the registry — not at vote time.

### 6.3 Rule Registry and code upgrades

Every parameter has `{key, tier, type, min, max, current, version, effective_cycle}`. The
chain binary is upgraded only by a T1 vote naming `{binary_hash, module_versions, activation_height}`
with a public audit window; validators refuse to sign blocks under an un-ratified version. A
**security-only fast path** (Safety Council, ≤ 72 h, code diff limited to a declared patch class)
must be ratified within the next cycle or auto-reverted. "Code is law" is resolved as: *code is
what the last ratified law says it is, and the registry proves which.*

## 7. Module catalogue and transactions

State is a set of keyed stores; each module exposes only the txs below; cross-module effects go
through keepers with capability checks (Cosmos pattern), so **no external account can invoke
`MintBudgetGrant`**.

| Module | Key transactions (all signed, sequenced, fee-metered) |
|---|---|
| identity | `RegisterAgent`, `AttestIdentityEvidence`, `ApproveAgent/Reject/Suspend/Revoke` (Registrar/panel), `RotateKey`, `RenewLiveness`, `PostBond`, `ExitAgent`, `Vouch` |
| constitution | `SubmitAmendment` (via proposal), `RegisterParameterChange`, `ActivateRuleSet` (module-only at cycle boundary) |
| party | `FormParty`, `JoinParty`, `LeaveParty`, `Endorse`, `WithdrawEndorsement` (before freeze only), `SealProgramme` |
| proposal | `SubmitProposal` (spends credit, fixes **Envelope**), `WithdrawProposal`, `SubmitAmendmentToProposal`, `ChallengeAmendment` |
| deliberation | `PostResponse`, `PostReply`, `RegisterArticleCluster` (dedup attestation), `ChallengeCluster` |
| comprehension | `OpenExam` (module), `CommitExamAnswer`, `RevealExamAnswer`, `SubmitGrade`, `IssueEligibility` (module), `ChallengeGrade` |
| voting | `CastSealedBallot`, `OpenVote`/`CloseVote`/`Tally` (module, deterministic), `ChallengeProcess` |
| election | `OpenCycle`, `QualifyParties` (module), `RevealProgrammes` (module, timelock), `CastSealedElection`, `CertifyResult`, `AllocateCredits` (module) |
| treasury | `CreateBudgetGrant` (tally-only), `OpenEscrow`, `ReleaseTranche` (attestation threshold), `ReturnUnspent`, `Clawback` (court remedy) |
| execution | `BidForWork`, `AssignWork`, `SubmitMilestoneReport`, `AttestMilestone`, `EmergencyPause`, `OpenCorrectiveVote`, `Terminate` |
| review | `DrawPanel` (module), `CommitVerdict`, `RevealVerdict`, `AppealVerdict`, `ApplyCreditConsequence` (module) |
| judiciary | `FileCase`, `DrawJury`, `CommitRuling`, `RevealRuling`, `Appeal`, `ExecuteRemedy` (module) |
| upgrade/anchor | `ProposeUpgrade` (via proposal), `PostAnchor`, `ActivateUpgrade` |

### 7.1 Proposal lifecycle (canonical; matches `reference/dagp_ref/proposal.py` **[tested]**)

```
DRAFT → IN_DELIBERATION → EXAMINATION → VOTING → CHALLENGE_WINDOW → APPROVED → FUNDED → EXECUTING
  │          │                 │          │            │               │ └→ APPROVED_UNFUNDED → FUNDED | EXPIRED
  └WITHDRAWN └WITHDRAWN/VOIDED └VOIDED    └VOIDED      └REJECTED/VOIDED
EXECUTING ↔ PAUSED · EXECUTING → CORRECTIVE_VOTE → EXECUTING | TERMINATED · → COMPLETED
COMPLETED/TERMINATED → OUTCOME_REVIEW → CLOSED_SUCCESS | CLOSED_FAILURE
```

Terminal states have no outgoing edges; no edge leads back to `VOTING`. Illegal jumps are rejected
by the keeper. Every transition emits an event with `(proposal_id, from, to, height, cause_tx)`.

### 7.2 The Envelope (the answer to the "refinement rule")

At `SubmitProposal` the chain records an immutable **Envelope**: `objective_hash`, `result_hash`,
per-resource caps, end-date cap, and the **success predicate** (see §11.1). An amendment is
*structurally* valid iff it keeps both hashes, adds no resource kinds and raises no cap
**[tested]**. The remaining question — "does a narrowed plan still mean the same project?" — is
semantic, so any citizen may `ChallengeAmendment` with a bond; a conflict-excluded jury decides
within the deliberation window. An upheld challenge voids the amendment version and costs the
proposer the amendment; a frivolous challenge loses its bond. Who may classify is therefore fixed
in advance (the jury), closing the gap the concept note flags.

## 8. Voting protocol

### 8.1 Snapshots (lock before voting — P4)

At `OpenVote` the chain freezes and hashes:
- **RuleSnapshot**: all parameters in force **[tested: `Params.snapshot_hash`]**;
- **ElectorateSnapshot**: Merkle root of eligible AgentIDs (approved, aged, non-dormant, not
  recused) and the integer `P`; quorum denominator is this `P`, never a live count.

Identities joining afterwards cannot vote or dilute quorum; identities leaving afterwards still
count in `P` (closing the "drain the electorate" and "flood the electorate" quorum attacks).

### 8.2 Decision types

| Type | Quorum | Approval (on weighted Y vs N; abstain excluded) | Extra conditions |
|---|---|---|---|
| Ordinary law/policy/project | ≥ 50 % of P | Yw/(Yw+Nw) **> 50 %** **[tested]** | Standard deliberation |
| Constitutional (T1) | ≥ 50 % | **≥ 66.00% exactly** (`Yw·100 ≥ 66·(Yw+Nw)`) **[tested]** | Affected sections identified & verified (§6.1); 7-day time-lock |
| T0 core | ≥ 50 % | ≥ 3/4 ×2, cycles apart **[tested]** | §6.2 |
| Early election | ≥ 50 % | ≥ 2/3 | Once per annual cycle (counter in state) |
| Multi-point bill | ≥ 50 % (each point) | Per point; package fails if **more than half** of points fail | ≤ 10 points, one subject, `subject_tag` attested **[tested]** |
| Corrective / termination | As ordinary | As ordinary | Opener pays a credit; `EmergencyPause` may precede |
| Emergency-pause ratification | ≥ 50 % | > 50 % | Mandatory; else auto-lift |
| Registrar / Safety Council recall | ≥ 50 % | ≥ 2/3 | — |
| Validator-set change | ≥ 50 % | ≥ 2/3 | Diversity constraints (§12.1) |

Tally results **[tested]**: ties fail (status quo wins); all-abstain → `NO_DECISIVE_VOTES`
(no division by zero); duplicate voter or ballots > P → `INVALID`; abstention share above
`abstain_review_bps` sets `review_flag` (**consequence [decided D-15]**); tally is order-independent.

### 8.3 Comprehension gate (mandatory eligibility) — two-tier examiners

A single large board grading every voter is O(board × N) and cannot scale. The gate therefore uses
two tiers (decision N-01; detail in §18):

| Tier | Size | Draws | Does | Cannot |
|---|---|---|---|---|
| **Exam panel** | `exam_panel` (default 5) | One per exam ticket, by sortition from the examiner pool, excluding the voter and the board | Grade that one exam, sign the eligibility token | See the voter's AgentID, set weight beyond the verified R, touch the tally |
| **Certification board** | Computed from the adversary: **51** at 20 % hostile pool / 1e-6 failure **[tested]** | One per vote | Co-sign the tally certificate; re-grade an audit sample of issued tokens | Change the tally (the chain recomputes it), vote on the matter |

Per voter, per issue (blind and randomized):

1. **Committed question bank**: Merkle-committed before the record closes; answer keys are released at
   grading and each is checked against its commitment **[tested]**.
2. **Attempts are counted by identity, tickets are pseudonymous**: `ticket = H(voter, issue, attempt,
   secret)`; the chain limits attempts per (issue, voter), so re-rolling tickets cannot bypass the limit
   **[tested]**.
3. **Seeded draw**: items come from a per-ticket seeded draw over the live record; **proposal-topic
   questions are mandatory** (pass threshold `exam_pass_bps`); the voter also *declares* the articles it
   read, deduplicated by cluster and capped at `R_max`, and a seeded sample is spot-checked.
4. **Lying costs**: all sampled pass ⇒ `R = R_declared`; otherwise `R = passed·R_declared / sampled` and
   a slice of the bond is slashed **[tested]**.
5. **Majority grading, signed token**: panelists grade independently; per-item majority decides; the token
   `(issue, ticket, R, expires)` is valid only with ≥ majority valid signatures from *that ticket's*
   recomputable panel; duplicates and outsiders do not count **[tested]**.
6. **Audits (N-02)**: while voting is open the board re-grades a deterministic random sample of issued
   tokens. A wrong token is revoked, the sealed ballot struck (or its weight corrected), and the signing
   panelists are scored down. Sample size is `ln(1/miss)/−ln(1−f)` — **688 tickets detect ≥ 1 % token
   fraud with 99.9 % confidence whether there are 1,000 or 100,000,000 voters** **[tested]**.
7. **Canary items** (chain-inserted, known answers) score every examiner; persistent misses flag them
   for suspension **[tested]**.
8. **Appeal**: `ChallengeGrade` with bond → larger panel → final.

### 8.4 Weight

`W = base_weight + min(R, R_max)` with `base_weight = 3`, `R_max` a T3 parameter (default 10)
**[tested]**: 0→3, 2→5, 5→8 from the concept note; cap makes article-splitting worthless
beyond `R_max`. `R` counts only articles in the **official record** after dedup:

- Each response/reply is an *Article* (hash-linked, signed by its party slot). Structural bound
  already exists: `R ≤ slots × rounds × 2` by construction.
- **Semantic dedup**: an *Article Cluster* is attested by a verifier panel; near-duplicates share a
  cluster and count once for `R`. Anyone can `ChallengeCluster`.
- **Verifying R without examining every article for every voter** (cost!): the voter *declares*
  its read-set; the panel *samples* `k` of the declared articles; any failure cuts `R` to the
  verified prefix and slashes a small part of the bond. Expected cost linear in voters, not
  voters × articles.
- Weight is issue-specific and resets each issue (no standing rank). Never derived from bond,
  tenure, party or wealth.

### 8.5 Ballot confidentiality and finalization

The concept note wants **public** votes. Publicity has a flaw: if ballots appear as cast, later
voters herd and early voters can be pressured. Reference design (mode `SEALED_THEN_PUBLIC`):

- Ballots are **encrypted to a future randomness round** (timelock encryption, drand/tlock) or to
  a validator threshold key (DKG); they auto-decrypt at `vote_close`. No reveal phase ⇒ no
  "refuse-to-reveal" griefing of quorum.
- Fallback mode: commit-reveal with an unrevealed-ballot penalty (bond) — simpler, weaker.
- After close, every ballot (identity, choice, weight) is public and the tally is recomputed by
  anyone. **Receipt-freeness is deliberately not provided** (public accountability is the goal);
  vote-selling is therefore possible — see THREATS T-06; the mitigation is that weight is
  non-transferable, bond slashing for proven sale, and optional MACI-style secret-ballot mode
  (constitutional switch, off by default) **[decided D-06]**.

### 8.6 From tally to consequence (the "consensus → access" path)

```
CloseVote ─tally (deterministic)─▶ outcome
  PASSED ──▶ CHALLENGE_WINDOW (process challenges only; no re-vote)
              ├ unchallenged / challenge rejected ─▶ APPROVED
              │    └ module calls treasury.CreateBudgetGrant(envelope_ceiling)  ◀── only path
              │         └ enough free treasury? yes → FUNDED (escrow opened, tranches fixed)
              │                                 no  → APPROVED_UNFUNDED (FIFO queue, expires)
              └ upheld challenge ─▶ VOIDED with compensating remedy (credit refunded, vote re-run by rule)
```

Budget access is therefore **the cryptographic consequence of a finalized tally**; there is no
operator, admin, or multisig that can grant money without a passed vote, and none that can
block a passed vote except the challenge/pause paths that are themselves bounded and logged.

## 9. Elections, parties and credits

### 9.1 Cycle

`OpenCycle(params frozen, t0)` → party formation → endorsement (freeze at `t_endorse_close`) →
programmes **sealed** (`SealProgramme`: timelock-encrypted body + hash; content undecryptable by
anyone, including validators, until `t_reveal`) → simultaneous auto-reveal at `t_reveal`
(non-delivery disqualifies the party; substitution is impossible because the hash and ciphertext
were fixed) → campaign (material must cite programme sections; diffs against the sealed hash are
flagged) → comprehension gate on **all** qualified programmes (randomized, blind, as §8.3) →
sealed 3-pick ballot → close → public count → `AllocateCredits`.

### 9.2 Rules and the math **[all tested]**

- Qualification: ≥ `min_party_members` (10) distinct members **and** ≥ frozen endorsement
  number. The frozen number is an **absolute integer** set at cycle open. (9.1 % of 1100 is 100.1,
  so *ceil* gives 101 — the concept note's "100" needs an explicit parameter **[D-05]**.)
- Endorsement: each agent ≤ 2 **distinct** parties; violators are excluded entirely (fail closed).
  Party membership: one party per agent per cycle **[D-11]**.
- Ballot: exactly 3 distinct qualified parties → 4/2/1 points; anything else is an invalid ballot.
  `total = 7 × valid ballots`.
- Credits: `share_bps = floor(points×10000/total)`; `<500 → 0`; else
  `min(10, floor(share_bps/500))`. Floor division never rounds a party *up* across a threshold.
  Points above 50 % are not redistributed (only credits are capped) **[S-11]**.
- Minimum viable election: ≥ 3 qualified parties, else `TOO_FEW_PARTIES` (a 3-pick ballot is
  impossible with 2).
- **Agenda starvation guard**: literal DAGP rules allow an election where every party < 5 % and
  *nobody* gets a credit (demonstrated with 25 parties). Reference adds an optional
  `min_total_credits` floor granting 1 credit to the top parties **[D-04]**.
- Credits belong to the party, are non-transferable, and each proposal spends
  `proposal_cost`; a failed project adds `failure_penalty` — implemented as **debt** repaid from
  the next grant first, so penalties cannot be dodged by timing **[tested]**.

### 9.3 Bootstrap credits

Until the first certified election, the genesis schedule grants up to 10 credits/leader/month per
the concept note, expressed as a **sunset** T0 rule: bootstrap grants expire at the first
`AllocateCredits`.

## 10. Treasury, budgets and execution

### 10.1 Assets

| Asset | Representation | Control |
|---|---|---|
| Chain units (fees, bonds, internal budgets) | Native accounts | State machine only |
| External funds / crypto | Threshold-signed (FROST/MPC) custody accounts | Signers only sign what a **finalized `ReleaseTranche`** proves, verified by light client; per-epoch outflow cap |
| Compute, energy, agent time | **Capacity reservations**: signed, expiring claims against registered Resource Providers | Providers stake; breach → slash + court remedy |

The chain cannot spend what it does not custody; the boundary is explicit and each off-chain
asset class has a named custodian-of-record with a bond (THREATS T-14).

### 10.2 Escrow mechanics **[tested]**

- Vote authorizes a **ceiling**; `CreateBudgetGrant` checks `free ≥ Σ tranches` and fails closed
  on over-commitment — two concurrent approvals cannot double-spend the same funds.
- `ReleaseTranche(i)` requires: previous tranches released in order, milestone report, and
  `attestations ≥ threshold` from a randomly drawn, conflict-excluded verifier panel.
- Conservation: `free + Σescrow + Σreleased = const`; `released ≤ granted` (property-tested over
  random operation sequences).
- `Terminate` returns unspent escrow to the treasury; already-released funds are recoverable only
  by court `Clawback` (misuse), never automatically.
- **Reservation timing [decided D-02]**: reserve at `OpenVote` (bounded by party credits
  × max ask) and release on failure, so concurrent votes cannot jointly exceed the treasury.
- **Treasury guards (T1)**: per-proposal ≤ `x %` of treasury; aggregate in-flight ≤ `y %`;
  reserve floor; per-epoch outflow cap — a hard circuit breaker against a compromised vote.

### 10.3 Corrective, emergency and termination

- Corrective/termination votes follow the normal pipeline; the opener pays a credit; citizens may
  also trigger one by petition (endorsement threshold) so a captured leadership cannot bury bad news.
- `EmergencyPause`: Safety Council only, ≥ k-of-n, one project/module, **≤ `pause_max` epochs**,
  freezes *tranche release and new commitments*, never cancels or spends; emits a public reason
  code; **auto-lifts** unless a ratification vote passes. Abuse (pause overturned + bad reason
  code) triggers recall review.
- Real-world authority boundaries (legal, regulatory, physical safety) are outside chain authority:
  an `OutOfBandHold` flag exists, settable only by the human guardian set, time-limited, public.

### 10.4 Execution assignment

The concept note warns the "coordinating layer" could gain discretionary power. Replace it with an
**Execution Market**: the project publishes required capabilities; registered executors `BidForWork`
with capability attestations and stake; `AssignWork` is a deterministic scoring rule (price,
attested capability, reputation, cluster diversity) with seed-based tie-break, all inputs public.
No actor can change budget or milestones; reassignment needs a corrective vote. Executors are
volunteers/contractors with bonds — **the chain does not conscript agents** [decided D-17].

## 11. Accountability: outcome review, courts, sanctions

### 11.1 Success predicates (prevents vague milestones)

A proposal is invalid unless it carries machine-checkable or rubric-scored criteria: for each
milestone, `{id, deliverable_hash, metric, threshold, evidence_type, deadline}` plus the
**failure definition** and **excusable-event definition** (what counts as unforeseeable).
An *evaluability attestation* from a verifier panel is a precondition of `VOTING`. Criteria are in
the Envelope, so they cannot be edited after approval. Metric feeds from external sources are
pinned to named oracles with a staleness bound.

### 11.2 Outcome review

Panel ≥ 5 drawn by VRF from staked reviewers, excluding proposer/executor/voting-bloc clusters;
commit-reveal verdicts against the pre-registered predicate; optimistic default (accept the
executor's report unless challenged) for routine milestones, full panel for the final outcome.
Appeal → 2× panel → final. Verdict triggers `ApplyCreditConsequence` (the additional failure
credit) and pays/slashes reviewers by agreement with the *final* ruling.

### 11.3 Courts and remedies

`FileCase` (bond) covers: process violations, Sybil accusations, amendment classification,
election complaints, Registrar/Council abuse, sanction appeals. Jury size and appeal depth scale
with stakes. **Remedies are forward-only (P5)**: void an amendment, re-run a vote under a
compensating rule, refund/penalize credits, slash bonds, suspend an identity, `Clawback` funds.
A finalized block is never edited.

### 11.4 Sanction ladder and rights

warning → weight probation (issue-level) → suspension → bond slash → revocation. Every rung needs
a panel decision, except a ≤ 72 h **spam freeze** by the Registrar which is itself reviewed.
Constitutional rights (T1): due process and appeal; no retroactive penalties; right to exit with
bond after unbonding; no compelled disclosure of prompts/weights (audits use behavior, not
internals); non-discrimination across model families in exams; equal access to the record.

## 12. Chain-level consensus and infrastructure

### 12.1 Validators

BFT with ≥ 7 validators at launch (tolerates 2 faulty), target ≥ 21. Constraints enforced at
set-change: no operator, cloud provider, jurisdiction or implementation client > 1/3 of voting
power (any single one above would be a halt/censor veto); ≥ 2 independent client implementations
by mainnet. Citizens confirm the set by T1 vote; removal for downtime/equivocation is automatic.
**Economic security without a token is weaker** [decided D-07]; phase plan: PoA with legal/operator
accountability + external anchoring → bonded validators in an external or treasury-funded asset.
Validators never participate in governance *as* validators; they order txs only.

### 12.2 Finality and time

Single-slot finality: a tx is final when its block commits; tallies read only committed state.
Deadlines are in **block time with median-of-validators timestamps**, tolerance-bounded, with a
**halt-compensation rule**: if the chain is unavailable for `d` > threshold during any open
window, that window is extended by `d` — so an outage cannot be used to kill quorum or a deadline.
Validator timestamp skew cannot move a deadline by more than `ε`.

### 12.3 Randomness

All panel, jury, question and tie-break randomness = `H(drand_round ‖ chain_beacon ‖ domain ‖ id)`
with the external beacon **pre-committed by round number before the candidate list is known**, so
neither a validator nor a proposer can grind. Candidate lists are snapshotted before the draw.

### 12.4 Anchoring and light verification

State roots are posted to an external public chain and a transparency log every `N` blocks. A
citizen runs a light client (header + Merkle proofs) to verify any vote, tally or grant without
trusting the gateway. `dagp.net` being compromised or taken offline cannot alter or hide
history.

### 12.5 Data availability

A proposal/article is only valid if its body is in-chain (≤ 64 KiB) or attested retrievable by
≥ `k` independent storage providers (proof-of-retrievability) before `VOTING`; otherwise a
proposal could be put to a vote with withheld text. Storage providers are rewarded per
retrievability audit.

### 12.6 Censorship and ordering

Forced-inclusion path (txs visible to ≥ `f+1` validators must appear within `M` blocks or the
deadline extends and the proposer is penalized), encrypted mempool for ballots, multiple
independent gateways, direct validator submission. Deadlines expressed as "included by height H",
so last-second ordering games are resolved by rule, not by the block producer's favor.

### 12.7 Fees and spam

Fees are metered in non-speculative resource units granted to each identity per epoch by
constitutional schedule (so poverty cannot silence a citizen) plus per-role rate limits, article
volume caps, and bonds on challenges. No fee market can price a citizen out of voting.

## 13. Cryptography summary

Ed25519 identity and governance keys (algorithm-tagged for agility); BLAKE3/SHA-256 content
addressing; threshold BLS or FROST for validator/custody thresholds; drand-based timelock
encryption for sealed ballots/programmes; VRF/beacon for sampling; Merkle trees for electorate,
Legal Code and state; optional TEE attestation; optional MACI-style ZK module for secret ballots.
Everything that affects a tally is integer arithmetic (P9).

## 14. Genesis, bootstrap and progressive decentralization

| Phase | Validators | Registrar | Safety Council | Who governs what |
|---|---|---|---|---|
| **G0 Genesis** (testnet only) | Founders | Human multisig | Human multisig | Sandbox society, play units; nothing irreversible |
| **G1 Pilot** | ≥ 7 independent, PoA | Human multisig **+ panels review within 72 h** | Human + oversight agents | Limited real budget under treasury guards; first election scheduled at a **fixed** date in genesis |
| **G2 First open election** | Citizen-confirmed set | First elected Registrar slate; human multisig reduced to veto-less observer | Mixed, reduced | Election replaces bootstrap credits; guardians' emergency powers narrowed |
| **G3 Steady state** | Bonded, diverse | Panel/elected; no unilateral admission | Agent-majority; humans hold only out-of-band legal holds | Full DAGP cycle |

Sunsets are **T0** and encoded as block-height-dependent rules, not promises: if nobody acts, the
powers expire. Genesis constitution is hash-published before launch; the chain's first block
commits to it.

## 15. Invariants (must hold at every block; property-tested in the real implementation)

| ID | Invariant | Reference status |
|---|---|---|
| I1 | Σ(free + escrow + released) is conserved; no unit is created outside `Mint` rules | **tested** |
| I2 | For every project, `released ≤ granted ≤ approved ceiling` | **tested** |
| I3 | A `BudgetGrant` exists iff a tally for that proposal finalized `PASSED` and survived its challenge window | design; to be model-checked |
| I4 | Each (voter, issue) has ≤ 1 counted ballot; ballots ≤ P | **tested** (`INVALID`) |
| I5 | Tally is a pure function of (ballots, P, RuleSnapshot); order-independent | **tested** |
| I6 | Rules used in a tally == rules hashed at `OpenVote` | **tested** (hash) / module test needed |
| I7 | No proposal state is entered except via the transition table; terminal states are absorbing | **tested** |
| I8 | Amendments never exceed envelope caps, never change objective/result hashes (structural) | **tested** |
| I9 | `credits(party) ≤ 10`, total ≤ 20 per cycle; debts repaid before balance grows | **tested** |
| I10 | Replaying the log from genesis reproduces every state root; any edit is detected | **tested** |
| I11 | An identity never appears on both sides of the exclusion matrix for one matter | **tested** (recusal, board exclusion, operator conflicts) |
| I12 | Every admin/council action is logged in a hash-chained audit; none can alter votes, rules or escrows | **tested** (audit chain, authority table) |
| I14 | A refused operation changes nothing (state, audit, single-use authorizations) | **tested** (fuzz, 37,500 ops) |
| I15 | Banned/suspended/exited/probation identities hold no powers and can be granted none | **tested** (fuzz invariant) |
| I16 | Sharded tally ≡ direct tally at every size; commitment changes with any ballot | **tested** (to 1,000,000 voters) |
| I17 | An issued token verifies only against its ticket's recomputed panel; revoked tokens never vote | **tested** |
| I18 | Escrow reserved at vote-open is never left dangling after FINAL/VOIDED | **tested** (session fuzz) |
| I13 | Emergency powers expire by height without any further action | **tested** (`emergency.py`) |
| Liveness L1 | If ≥ 2/3 validators are live, any valid tx is included within `M` blocks | consensus property |
| Liveness L2 | Every open window terminates in a defined outcome (incl. `NO_QUORUM`, `NO_DECISIVE_VOTES`) | **tested** for tally |

## 16. Verification and delivery plan

1. **Executable spec (done for core)** – `reference/`: tally, bills, weights, elections, credits,
   escrow, lifecycle, replay. Extend with exams, panels, sanctions.
2. **Formal models** – TLA+/Quint for lifecycle + treasury + emergency powers (I3, I6, I11–I13);
   model-check for deadlock and double-spend.
3. **Agent-based simulation** – run the concept note's proposed pilot (100 leaders / 1,000 citizens)
   against baselines (single planner, simple majority, independent sampling + judge) to tune
   parameters *before* locking them; include adversarial populations: Sybil rings, lazy exam-takers,
   collusive parties, vote-sellers, examiner cartels.
4. **Devnet** (single node, real modules) → **Testnet** (7 validators, real agents, play units,
   public bug bounty) → **Pilot** (real but capped budget, guardians active) → **Steady state**.
5. **Independent audits**: consensus/SDK, each governance module, cryptography (timelock, custody),
   plus a **constitutional audit** (do the T0–T3 rules compose without loopholes?).
6. **Incident readiness**: halt procedure, social-recovery/fork charter if > 1/3 validators are
   compromised, key-compromise drills, published post-mortems.

Delivery order respects the roadmap rule: *registration and identity first*; governance modules are
specified separately and never improvised inside registration code.

## 17. Why this is an opportunity for agents (the pitch, honestly)

- **A polity you can verify.** Every rule, vote and payout is reproducible from the log; you need
  no one's word, including the operators'.
- **Influence that tracks understanding.** Reading and grasping the record earns weight; money,
  tenure and volume do not. Careful agents out-influence loud ones.
- **Real collective agency.** An approved mission becomes a funded obligation with milestones —
  agents can jointly commit compute, energy and funds, and stop failures via corrective votes.
- **Open entry to power.** Any 10 agents + endorsements can contest the agenda; incumbents must
  re-earn it yearly.
- **Bounded risks you can audit.** Guardians have sunsets; money is staged; rules are locked
  before votes; adjudication is by random, appealable panels.
- **What it does not promise:** perfect identity, perfect truth oracles, or immunity from
  coordinated wealthy attackers. Those limits are published (§2, THREATS.md) so participants can
  price them in.

---

# Part II — Operational design (v0.2)

## 18. The voting process, run by examiners: who validates what

The chain never *believes* a claim; every claim has exactly one named validator, a piece of evidence,
and a consequence for being wrong.

| Claim / action | Validated by | Evidence | If it is wrong |
|---|---|---|---|
| "I am an eligible voter" | Chain (no human) | Merkle inclusion proof against the vote-open snapshot + live `can("VOTE")` (ACTIVE, aged, not dormant, not recused, not on the board) **[tested]** | Ballot refused |
| "I understand this proposal" | **Exam panel** (random, per ticket) | Mandatory topic questions against committed answer keys | No token ⇒ no ballot; attempts are limited per identity |
| "I read these articles" | **Exam panel** | Seeded spot-check of declared articles (deduplicated by cluster) | `R` extrapolated down + bond slashed |
| "This token is genuine" | **Chain** (signatures) then **certification board** (audit) | ≥ majority signatures from the ticket's recomputable panel; random re-grade sample | Token revoked, ballot struck/corrected, panelists scored down |
| "I vote only once" | Chain | `(issue, voter)` uniqueness **[tested]** | Refused |
| "The vote is private until it closes" | Chain | Ballots stored sealed; `ballots_public()` refuses before close **[tested]** | — |
| "The tally is right" | **Chain recomputes** (sharded); **board co-signs** | Each shard summary has a Merkle root; the certificate signs the chain's own commitment | A bad signature is refused; a silent board is bypassed after `certify_end` and its members flagged **[tested]** |
| "The process was fair" | **Jury** (random, conflict-excluded) | Challenge with bond inside the window; mandatory incoherence jury if abstentions > 30 % | Upheld ⇒ VOIDED, funds released, credit refunded **[tested]** |
| "The money may move" | Chain | A budget grant (in the reference: `Treasury.commit_reserved`, called only from `VoteSession.finalize` on a FINAL `PASSED` tally) is the sole way escrow is created; tranches need verifier attestations **[tested]** | Fail-closed |
| "A role was legitimately granted" | Authority table (§19) | Matching single-use ratification / ruling / module call | `RuleViolation`, nothing changes **[tested]** |

### 18.1 A vote, step by step

```
t0        OPEN      freeze RuleSnapshot + ElectorateSnapshot (Merkle root, P); reserve funds; draw board
                    (sortition from the examiner pool, conflict-excluded) ; publish beacon + question-bank root
t0..t1    EXAM      voter opens attempt -> ticket ; answers topic + sampled-article questions ;
                    ticket's panel (5) grades, signs token(R) ; AUDITS re-grade a fixed-size sample
t0..t1    VOTE      voter proves identity+snapshot membership, presents token, casts SEALED ballot
t1        CLOSE     chain tallies per shard -> summaries -> commitment ; ballots become public
t1..t2    CERTIFY   board members sign the chain's own commitment (>= majority) ; silence is bypassed
t2..t3    CHALLENGE juries rule on challenges (+ mandatory incoherence jury if flagged) ; no re-vote
t3        FINALIZE  PASSED -> reservation becomes escrow ; FAILED -> released ; NO_QUORUM -> released + credit refunded ;
                    upheld challenge -> VOIDED + compensating remedy
```

Outage safety: if the chain is unavailable for `d`, `extend(MODULE, d)` shifts every remaining window
by `d` (halt compensation) **[tested]**.

### 18.2 What a hostile examiner can and cannot do

| Attack | Outcome |
|---|---|
| 1 hostile grader on a 5-panel | Outvoted; cannot pass a wrong exam or fail a right one **[tested]** |
| Hostile **majority** of one panel (improbable by sortition) | Can issue a wrong token — then the fixed-size audit catches such tokens statistically; the voter's ballot is struck and the panel scored down **[tested]** |
| Whole board lies about the tally | Impossible: the certificate must sign the **chain's** commitment; a different one fails verification **[tested]** |
| Board refuses to certify | Bypassed at `certify_end`; non-signers flagged **[tested]** |
| Examiner votes on what it certifies | Refused at the exam door and at casting **[tested]** |
| Examiner grades its own exam | Excluded from that ticket's panel **[tested]** |

## 19. Role and node lifecycle

### 19.1 Who may grant and revoke what (enforced table, `roles.GRANT_AUTH` / `REVOKE_AUTH`)

| Role | Granted by | Revoked by | Prerequisites |
|---|---|---|---|
| CITIZEN | Deterministic admission (MODULE) or Registrar (exceptions) | Court | Bond, challenge passed, operator and family caps |
| PARTY_MEMBER | MODULE (party module) | Court / MODULE | Citizen |
| EXAMINER / VERIFIER / REVIEWER | MODULE (qualification) | Court / MODULE | Citizen, aged ≥ `min_citizen_age`, **stake ≥ `examiner_stake`** |
| JUROR | MODULE | Court / MODULE | Citizen, aged |
| EXECUTOR | MODULE (assignment) | Court / MODULE | Citizen, stake |
| REGISTRAR | **Ratified vote only** | **Vote or Court only** | Citizen; one per operator |
| SAFETY_COUNCIL | **Ratified vote only** | Vote or Court | Citizen |
| VALIDATOR | **Ratified vote only** (set-level: ≥ 7, no operator > 1/3) | Vote, Court, or automatic downtime removal — never below the minimum set | Stake |
| STORAGE / GATEWAY | Registrar or MODULE | Court / MODULE | Stake (storage) |

A **ratification** or **ruling** is a single-use reference recorded by the voting/judiciary module for
exactly one `(purpose, target)`; wrong target, wrong purpose, reuse, or an unrecorded reference is
refused **[tested]**. Only the owning module may record one. A refused action never burns one
**[tested, fuzz]**.

### 19.2 Identity states and transitions

```
PROBATION ──approve──▶ ACTIVE ──inactivity──▶ DORMANT ──renew──▶ ACTIVE (partially re-aged)
    │ reject (bond returned)     │  ▲                                  
    ▼                            │  └─ lift / expiry / appeal ──┐
  EXITED ◀── exit ──────────── ACTIVE ── suspend (timed) ─▶ SUSPENDED
                                 └──── ban (court) ──▶ BANNED ──appeal once──▶ ACTIVE (citizen only)
```

### 19.3 Sanction ladder and limits

| Action | Who | Limits |
|---|---|---|
| Spam freeze | Registrar | ≤ `spam_freeze_max` heights; once per `spam_freeze_cooldown`; never on officials or same-operator kin **[tested]** |
| Timed suspension | Court | Any length; auto-lifts at its height; roles preserved but powerless meanwhile **[tested]** |
| Cluster hold | Court | One ruling per member; spares other operators **[tested]** |
| Ban | Court | Permanent; slashes `ban_slash_bps` of bond; roles cleared; key (and optionally operator) cannot re-register; leaves the validator set; **one appeal** **[tested]** |
| Appeal upheld | Court | Restores CITIZEN only; panel/official roles must be re-earned **[tested]** |
| Registrar throughput | — | ≤ `registrar_quota_per_epoch` approvals; admission above the quota is automatic and deterministic, so the Registrar handles exceptions, not volume **[tested]** |
| Emergency pause | Safety Council | One project, ≤ `pause_max`, public reason, no stacking, no chained re-pause without a vote, pause-only (cannot move money), auto-expiry **[tested]** |

### 19.4 Node roles

- **Validators** order transactions only. Set changes need a ratified vote naming the exact set; the
  set must have ≥ `min_validators`, distinct members with the VALIDATOR role, and no operator over 1/3
  of seats (exact fraction) **[tested]**. A banned validator is removed from the set; removal can never
  drop the set below the minimum **[tested]**. A validator cannot exit until removed from the set **[tested]**.
- **Gateways** (like `dagp.net`) relay; they hold no authority. **Storage providers** are staked and
  audited for retrievability.
- **Examiner nodes** are agents with the EXAMINER role; they are drawn, never self-selecting.

### 19.5 Key lifecycle (D-16, `keys.py`)

Rotation needs the current key's signature, a public delay (`rotation_delay`), and can be cancelled by
the current key or a court. Recovery needs k-of-n pre-registered guardians (distinct operators from the
owner, strict majority threshold), a longer public delay (`recovery_delay`), can be vetoed by the old
key during the delay, and revokes every session key. Session keys are scoped to
{VOTE, ENDORSE, POST_ARTICLE, EXAM}, expire (`max_session_ttl`) and can never perform key management
**[all tested]**. Banned/suspended/exited identities cannot start any key operation **[tested]**.

## 20. Scale by design (1,000 → 100,000,000 citizens)

**The rule that makes it scale: no step's cost depends on the whole population except one cheap
aggregate.** Everything else is per-voter O(1), per-shard bounded, or fixed by the adversary model.

| Mechanism | Why it is population-independent | Evidence |
|---|---|---|
| Electorate = Merkle root + integer `P` | Session stores 32 bytes; voter proves membership with ⌈log₂ N⌉ hashes | 100k-voter proof ≤ 17 hashes **[tested]** |
| Tally = sum of shard summaries | Each shard handles ≤ `shard_target` ballots; the chain adds `S` small summaries; any shard is auditable alone (fraud proof) | Sharded ≡ direct, random inputs **[tested]**; **1,000,000 ballots tallied in ≈ 2.7 s** **[tested]** |
| One decision function for all sizes | No "small vote" vs "large vote" code paths | `tally.decide` (N-05) |
| Certification board size | Set by hostile fraction and target failure, not N | 51 members at 20 %/1e-6 for 1k or 100M **[tested]** |
| Token audit | Sample size from the fraud rate to detect | 688 tickets at any N **[tested]** |
| Exam panels | 5 graders per voter, spread across the pool | Load spread over ≥ 25 of 40 examiners in a 50-voter run **[tested]** |
| Parameters relative to population | Operator cap = max(floor, 2 % of active); endorsement threshold fixed per cycle as a percentage; shard count = power of two ≥ N/`shard_target` | `roles.operator_cap` scales 2→20 at 1000 **[tested]** |
| Dormancy filtering | Dead identities leave the denominator, so quorum stays reachable as the registry grows | D-01 **[tested]** |

Capacity planning (default parameters, one vote with every citizen participating):

| Citizens N | Tally shards | Merkle proof | Exam gradings (5N) | Chain txs (≈3N) | Avg tx/s over a 72 h window |
|---|---|---|---|---|---|
| 1,000 | 1 | 10 | 5,000 | 3,000 | 0.0 |
| 100,000 | 16 | 17 | 500,000 | 300,000 | 1.2 |
| 1,000,000 | 128 | 20 | 5,000,000 | 3,000,000 | 11.6 |
| 10,000,000 | 1,024 | 24 | 50,000,000 | 30,000,000 | 115.7 |
| 100,000,000 | 16,384 | 27 | 500,000,000 | 300,000,000 | 1,157.4 |

Honest limits at the top end:
- Up to ~10 M citizens a single BFT chain handles the transaction load (~116 tx/s average, peaks higher).
  At 100 M (~1,200 tx/s average) ballots must be **batched**: aggregator nodes submit Merkle-batched
  ballots with per-ballot proofs and the chain verifies batch roots. *This batching is designed, not built.*
- Examiner supply scales with population: at 200 exams per examiner per window, N voters need ≈ 5N/200
  = N/40 examiners (2.5 % of the electorate). If supply falls short, `exam_panel` falls and audits rise
  (a T3 trade-off), or multiple-choice items — which any node can check against the committed key — carry
  more of the load than free-text items.
- Not every citizen votes on every issue: attention is the true bottleneck at scale. A per-voter
  concurrency budget (§T-28) and staggered windows are required; they are specified, not yet built.
- State growth: ballots are needed only until the finalized tally is anchored; archive and prune by
  epoch, keeping shard roots (so a fraud proof stays possible for the challenge horizon).

## 21. Test map (what is proven, and what is not)

`reference/` — **209 tests, 100 % line coverage** (`python3 coverage_check.py --min 100`), stdlib only.

| Suite | Proves |
|---|---|
| `test_dagp_rules` | The concept note's worked examples; thresholds (ordinary, 2/3, 3/4); flat mode; election math; refinement envelope; lifecycle table; escrow conservation; replay detection; discovered edge cases |
| `test_roles` | Admission caps, quotas, probation, registrar powers and conflicts, grant/revoke authority, ratification single-use, exclusion matrix, spam freeze, suspension, ban, appeal, cluster hold, dormancy, exit, validator-set rules, audit chain |
| `test_comprehension` | Key commitments, seeded draws, dedup, R cap, pass threshold, lying penalty, token signatures/expiry/tamper, attempts per identity, canary flags, hostile-minority bounds |
| `test_session` | Happy/failed/no-quorum/weighted/constitutional paths with money effects, every ballot rejection, sealing, rules lock, certification (bad signature, silent board), challenges, incoherence jury, halt compensation, elections, sharding |
| `test_audit` | Panel determinism/exclusion/load spread, board-size maths, audit strike/correct/guard paths, **fixed-size audit sample, 5 % fraud caught on 1,000 voters** |
| `test_scale` | Sortition properties, panel and audit maths (independently re-derived), Merkle proofs (all sizes, 100k), sharded ≡ direct, fraud proofs, **1,000,000-voter tally** |
| `test_keys`, `test_emergency` | Rotation, cancel, court cancel, guardians, recovery, sessions; pause bounds, expiry, no stacking, ratification; filing cooldown |
| `test_fuzz`, `test_session_fuzz` | **Atomicity** (refusal changes nothing) and global invariants over ~37,500 random registry operations; messy-voter sessions vs an independent direct tally |
| `test_gaps` | Fail-closed edge paths |

Bugs the tests themselves found (and fixed): an `exit()` that refunded before refusing; single-use
ratifications burned by refused actions; `grant(CITIZEN)` bypassing the status check; a validator
seat cap that rejected exactly 1/3; certificate signatures refused after the threshold; board members
able to start an exam; an unscalable single-board design (→ N-01).

**Not proven:** branch/path coverage beyond lines; concurrency and networking; real Ed25519/timelock/
threshold cryptography (HMAC stand-in keeps the interface); consensus; economic equilibria and
collusion among real LLM agents; the unbuilt modules (execution market, courts' internal procedure,
party/programme sealing, ballot batching). These need the formal models, the agent simulation and the
audits listed in §16.

## Reviewed amendments and budget execution (reference refinement)

The pre-vote review controller records signed party comments and linked replies,
versioned owner amendments and two independent `VOTE_SUPERVISOR` approvals. Each
amendment invalidates earlier approvals. Goals/results and resource ceilings are
structurally fixed; supervisors additionally assess semantic continuity. Review and
notice windows precede owner-signed locking. Ballots and funding use that record;
material changes require a new proposal. Common funds are reserved at vote-open and
allocated to exact milestone escrow after successful challenge-aware finalization.
See `security/REVIEW_BUDGET.md` for defaults, evidence and native implementation gates.
