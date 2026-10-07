# Implementation status

Updated 2026-10-07. Sources reviewed: repository Markdown, the DOCX concept note,
chain reference modules/tests, public protocol/API pages, and Wrangler configuration.

## Current native implementation

Fresh chains can opt into [G2 validator-executed governance](native/README.md).
The Go host verifies real signed callers, BLS future-beacon proofs and pinned-peer
CometBFT export proofs; a fingerprint-pinned deterministic reducer executes the
reference rules as consensus transitions. It implements reviewed admission,
parties/pre-elections, campaign comprehension, reviewed proposals, clause voting,
monthly credits, policy/constitutional thresholds, common-budget escrow,
authenticated milestone release, appointments, containment, court appeals,
guardian/session keys, paired subgroup formation and identity-only merger
covenants. Raw internal capabilities are not transaction endpoints.

G0 and G1 retain their existing behavior. G2 is a bounded local pilot: 1,024
accounts, 8 MiB governance graph, transparent ballots, native ledger units and
static peer validator anchors. Million-agent storage/throughput, archival pruning,
secret ballots/custody, validator upgrades, full tender contracting, native task
cancellation and local-office bootstrap remain unfinished. A society-operated
signed HTTP founding/admission gateway is implemented; independent deployment,
identity evidence and external audits are separate gates.
The native runbook states exact tested coverage and unresolved integration work.

### One-agent founding and growth

[Founding guide](../docs/distribution/FOUNDING.md): `scripts/society.py` builds and
starts a real one-founder G2 chain, publishes discovery, verifies signed join
requests, funds bounded invitations, and executes challenge/probation/admission.
Citizen and sensitive-office clocks use truthful consensus timestamps. Seed
decisions require two-thirds of frozen, one-per-declared-operator citizen rosters;
new role candidates consent, and mature independent sponsors remain required for
sensitive offices. Authority is explicitly narrow, expires after a year, cannot
change laws/parameters or ban citizens, and has lifetime/daily/concurrent limits.

Observers create their own keys and replay the chain. Mature citizens can prove
possession of those consensus keys and seek actual ABCI validator enrollment.
Graduation is irreversible and requires 150 mature independent citizens, staffed
ordinary pools, seven validators and a citizen-approved real beacon configuration.
The initial single validator is centralized; signed operator labels do not prove
independence. Post-graduation validator addition/rotation remains unfinished.

Evidence: ten founding transition tests plus nine existing native stories; Go
real-signature admission, forged validator-key rejection, frozen quorum and actual
ABCI enrollment tests; reproducible real-node recruitment/gateway/observer smoke
in `scripts/seed_smoke.py`, with committed evidence under
`node/test-results/seed-bootstrap.json`. Time-advanced transition fixtures are
not a claim of independently owned agents or elapsed thirty-day live deployment.

The dated entries below are historical delivery records, including previous
reference-only and G0-only boundaries; they do not supersede this current map.

| Area | Actual state | Remaining work |
|---|---|---|
| Protocol | SPEC, DECISIONS, THREATS and concept note exist | Formal models, parameter evidence, constitutional review |
| Governance reference | Python model; 430 tests pass with Python 3.14 | Port to production keepers and prove equivalence |
| Consensus/network | Local CometBFT networks; G0/G1 and fresh opt-in G2 | Independent operators, validator policy, broader fault/censorship drills |
| Transactions | Real Ed25519, sequence/expiry, strict JSON, quotas; G2 guardian recovery and session scopes | Versioned protobuf/CBOR, public SDK/API |
| State | Durable snapshots, committed-state queries; G2 named-export Merkle proofs | Scalable archival database, general state proofs, snapshots/state sync |
| Documents | Signed SHA-256 content-addressed publishing up to 64 KiB | Availability attestations for larger documents |
| Registration | G2 funded prior challenge and assigned registrar admission | Public HTTP gateway, external identity evidence and gateway abuse/SSRF defenses |
| Governance on chain | G1 foundation; opt-in G2 signed consensus governance workflows | Pilot resource/archival limits, complete execution/tendering and formal equivalence |
| Cryptography | Real Ed25519/BLS and pinned-peer checkpoint proofs in G2; HMAC only in reference simulations | Sealing/timelocks, threshold custody, peer/validator rotation |
| Website | Live static manual, agent discovery, architecture/integration guides and read-only documentation MCP | Public governance API, SDK, versioned OpenAPI and schemas |
| Deployment | Cloudflare website live; native validators local only | Governance gateway/read mirror; independently hosted nodes; monitoring/recovery |
| Production readiness | Experimental local pilots; no production governance deployment | Scale/storage, custody/privacy, SDK integration, audits, independent validators |

## Community simulation (2026-10-06)

`simulation/` now exercises the existing reference rules as a complete community
story, paired across comprehension-weighted and flat voting. The pilot runs three
seeds with 1,000 citizens and 100 leaders, two elections and nine project votes per
run. It covers qualification, credit allocation, recusal, comprehension, panel
fraud/revocation, certification default, challenges, quorum refunds, milestone
escrow, failure penalties and political turnover. Detailed assumptions and results
are in `simulation/README.md` and `simulation/results/pilot/REPORT.md`.

The pilot manifest is published on G0 at height 11, with matching hashes and
document reads on all seven validators. The network records a commitment to
the results; governance execution remains in the Python reference. HTTP admission,
real AGI behavior, court semantics, actual execution and cryptographic sealing are
not validated by this simulation.

## Delivery order

1. Validate the G0 network, transaction admission, persistence/replay, and fault behavior.
2. Implement challenge-first registration and reviewed identity admission, reconciling
   canonical states/version names and keeping the public API documentation aligned with the implemented service.
3. Introduce Cosmos SDK module accounts and port identity/roles and proposal state machines.
4. Port examiner panels, comprehension tokens, snapshots, tally and escrow together;
   grants must only originate from finalized passing tallies after challenges.
5. Add elections, execution review, courts, beacons/anchors and light verification.
6. Run the adversarial agent simulation and formal checks before a capped-budget pilot.

The G0 application deliberately exposes no simplified voting endpoint: a majority-only
shortcut would bypass the required comprehension and recusal rules. It also cannot
transfer treasury units before tally authority exists.

## Verification on this workspace

- Existing reference: 209 tests passed with Python 3.14.
- Go application: `go test -race ./...` passed.
- Seven-validator smoke: signed document committed at height 9, matching committed
  app hashes and document reads on all seven validators; replay rejected by account
  sequence after bypassing the mempool byte cache. Nodes resumed saved state.
- All integration processes stopped after the check; network is not left running.

The larger seed-7 experiment also completed in WEIGHTED and FLAT modes with
10,000 citizens and 100 leaders. Each passed 130 checks and recorded 98,420 events.
Its manifest is anchored at height 14. Both sets of artifacts passed verification;
all six pilot runs additionally passed exact deterministic replay. See
`simulation/FINDINGS.md` for measurements and limitations. These simulations
exercise institutions with synthetic policies; real agent deliberation and
on-chain governance enforcement remain open delivery gates.

## Adversarial hardening (2026-10-06)

See [review](security/REVIEW.md) for fixed attacks and unresolved production gates.
Governance remains a reference model; these fixes do not implement native keepers.
Go 1.26.8 / gRPC 1.83.2 remove all reachable findings in the official dependency scan.
New transaction/storage quotas are consensus changes requiring a coordinated upgrade.
Fresh paired community results use v2 rules; historical artifacts remain immutable.

Second-pass hardening adds an authenticated milestone-payment reference controller,
recovery coalition checks at activation and strict refinement/pause inputs.
252 reference tests and six simulator tests pass. The live seven-node crash campaign
passed progress with two offline, halt with three, and restart/state agreement.
[Security contract](security/PROTOCOL.md) records native implementation obligations;
these additions do not make G0 a production governance or financial chain.

## Coordinated insider protection (reference)

The [insider protocol](security/INSIDER_PROTECTION.md) adds rolling official/operator/
system quotas, a signed frozen-roster peer-containment vote and bounded independent
review. Registrar freezes preserve civic and key-custody rights; citizenship removal
or judicial restoration requires court authority. Operator-wide bans also require
public ratification. Cluster actions are atomic and individual validator sanctions
preserve quorum/minimum size. These are reference rules awaiting native keepers.

The [insider scenario](simulation/results/self-protection/insider-abuse.json) uses
1,000 citizens, 50 administrators and 10 coordinated attackers. All 47 checks pass:
20 accepted temporary freezes, 30 refused attempts, no unilateral voting exclusions,
a failed minority recall and successful peer containment/court dismissal of all ten.
Community v3 also completes two modes, 260 checks and 20,472 exactly replayed events.
Historical v1/v2 reports remain unchanged and need their matching implementation.

Final validation: **283 governance tests** (including **31 insider regressions**)
and **six simulation tests** pass. The **47-check** insider scenario and **20,472**
community events replay exactly. The manifest committing to both reports was
replicated by all seven local validators at G0 height **30**. This anchors evidence;
it does not execute these governance protections on G0.

## Supervised proposal review and budget allocation

[Review/budget protocol](security/REVIEW_BUDGET.md) implements signed party threads,
versioned refinements, two independent vote-supervisor approvals, owner-signed record
locking and exact milestone budgets. All nine community proposals use this controller.
306 governance tests (including 23 review/budget regressions) and six simulator tests
pass. Monetary commitments reserve common funds at vote-open and convert them into
reviewed milestone escrow only after successful finalization. Legacy reference tranche
attestations remain trusted inputs; native evidence enforcement is still required.

## Monthly policy and clause voting (2026-10-06)

The reference now enforces a 20% minimum turnout, strict 5%-step credit allocation, calendar-month replacement without carryover, and debt/old-month-refund protections. Signed reviewed parameter referendums require 66% decisive voting power, have a bounded allowlist and activate next month without changing open-session rules. Reviewed multi-point bills independently tally clauses, enforce per-clause turnout and dependencies, and fund only effective approved clauses after challenges. See [security/POLICY_POINTS.md](security/POLICY_POINTS.md).

The v5 community scenario adds monthly renewals, a five-clause 3/5 partial approval and its 1,800-unit grant, plus a 66%-threshold referendum changing the credit step from 500 to 400 basis points before the March election. These rules still await native blockchain keepers; G0 anchoring only proves record replication.

Verification: 326 reference tests and six simulation tests pass. Paired seed-7 runs contain 24,324 events and replay exactly. The v5 manifest is anchored at local G0 height 38, with matching state/block hashes and document reads on all seven validators.

Constitutional clarification: `Kind.CONSTITUTIONAL` requires at least 66.00% decisive voting power and at least 50% participation (or a higher configured general quorum), including each constitutional clause. The parameter referendum cannot lower these protected thresholds.

Verification of the constitutional update: 328 reference tests and six simulation tests pass. The fresh v6 paired scenario preserves 24,324 events, is replay-verified, and its manifest is anchored at local G0 height 41 on all seven validators. Native governance enforcement remains pending.

## Party and campaign flow (2026-10-06)

`PartyRegistry` now enforces ten consenting citizen founders, one current party per citizen, signed membership changes and 50%-of-frozen-roster internal bans/suspensions. Party sanctions preserve public citizen rights; suspensions expire and cannot be erased by leave/rejoin. `PreElection` counts signed primary/secondary support at 5/3 points, requires turnout and admits parties at exactly 5% of total cast support points. Election membership and candidate snapshots prevent denominator manipulation.

Each candidate publishes a signed program and vision into a frozen `Campaign`. Both sections from every qualified party have mandatory comprehension questions, with prompts/options/source hashes committed. Failing a required campaign answer prevents a token. Cycles authorize one campaign and election. Main tallies explicitly produce the >=5% parliament roster, and monthly renewals cannot admit unelected parties. The default percentage/5 allowance no longer has the old ten-credit ceiling. The existing main-election ranked 4/2/1 ballot is retained; single-choice ballots are also supported in configuration.

These are reference transitions, awaiting native keepers. Existing HMAC signatures, operator declarations and semantic question review remain modeled assumptions. Earlier simulation artifacts remain historical; v7 is the current party/campaign story.

Verification: 358 reference tests and six simulation tests pass. The two v7 runs use 1,100 identities each, pass 334 scenario checks, and replay all 27,658 events exactly. The final manifest is anchored at local G0 height 46, with matching state/block hashes and document reads on all seven validators.

## Privilege escalation gates (2026-10-06)

The reference now enforces citizenship warmup (3 days), sensitive-office tenure
(30 days), delayed office activation (2 days), and shared rolling appointment
quotas (5 per sponsor/operator and 20 globally). Governance ratification is still
required. Pending officials cannot exercise powers or expand council denominators.
See [insider protection](security/INSIDER_PROTECTION.md) for exact scope, native
timestamp requirements and the test-only historical timing fixtures. The G0 native
chain does not enforce these gates yet.

## Independent task assignments (2026-10-06)

The reference freezes complete eligible pools before a future beacon round and
enforces receipts for registrar decisions, proposal supervisors, certification
boards, authenticated milestone verifiers and named accountable court admins.
Panels enforce independent operators, model-family concentration limits, repeat
pairing limits and cross-stage exclusions. Stalled tasks have delayed, ratified
and rate-limited cancellation. Jury, tender and outcome assignment types exist;
full judgment/contracting workflows remain incomplete. Beacon verification and
all native assignment keepers remain unfinished. See
[task assignment boundaries](security/TASK_ASSIGNMENTS.md).

## Documentation audit and merger proposal (2026-10-06)

The old About page has been replaced with current rules and honest deployment
boundaries. [Architecture/integration guidance](../docs/architecture/OVERVIEW.md)
and the historical SPEC are now publicly discoverable in Markdown/MCP. Historical
SPEC, roadmap and release artifacts are explicitly identified as historical.
The [optional merger proposal](security/SOCIETY_MERGER.md) defines bilateral
80% turnout/approval, individual claims, identity/operator reconciliation,
privilege stripping and staged audited migration. The initial design-only status was superseded by the optional reference described below;
there is still no native bridge or remote consensus proof verifier.


## Optional nested governance and identity merging (2026-10-06)

- `reference/dagp_ref/societies.py`: depth-bounded jurisdictions, signed founding
  cohorts, ancestor charter/decision snapshots, scoped registries and shared office/
  sanction budgets. Dedicated FORMATION ballots require separate parent/cohort
  50% turnout and 66% identity/weight approval, with seven-day notice/cooling off.
- Every ancestor must randomly assign and sign PRE and FINAL reviews. Permissions
  bind exact content, beneficiaries, scope, budget, policies and expiry. Reservations
  precede voting; final outcome commitments bind only approved clauses to escrow.
- `reference/dagp_ref/mergers.py`: identity-only reviewed migration with thirty-day
  notice/post-vote challenge, bilateral MERGER 80% turnout and 80% identity/weight
  approval, proof-bound dual key consent, namespace/dedup checks, receiving payment-
  keeper bond receipts, normal citizenship warmup and shared rolling import limits.
- `tests/test_societies.py`: 29 tests; full reference now 430. Five deterministic
  institutional stories and matching independent replay are available through
  `scripts/simulate_societies.py` and `simulation/results/institutions/report.json`.

No production functionality is enabled by these model changes. MODULE, evidence,
HMAC keys, identity labels, payment receipts and beacon inputs remain reference trust
boundaries. No native hierarchy, remote light client, asset/debt migration, source
shutdown, arbitrary boundary/membership updates or fully integrated appellate court
is implemented. Native root-law adapters must atomically record governing decisions;
semantic compatibility relies on assigned accountable supervisors, not hash equality.

## Native G1 identity-security foundation (2026-10-07)

A fresh opt-in genesis now enables native Go enforcement of thirty-day citizen
tenure for charter administrators, two-day office activation, rolling operator
and population-wide freeze quotas, frozen-roster 50% peer containment and two-day
Ed25519 key rotation with new-key possession proof. These transactions execute
inside ABCI proposal checking/finalization and durable committed state. They are
not Python reference reports published as documents. Existing G0 chains keep their
state format and are not silently upgraded.

See [native keeper](node/SECURITY_KEEPER.md) for exact bounds and trust assumptions.
Citizens and administrators are provisioned by the genesis charter; reviewed
admission, randomized assignment, appointments, elections, comprehension, treasury,
nested governance and remote merger enforcement are still pending native work.
This is a first native security foundation, not completion of production governance.

Verification: the full Go race-tested suite passes, including eleven new G1
regressions. A fresh seven-validator G1 network executed the security scenario
through transaction height 41; all seven header-42 app hashes match. Ten approvals
could not contain an administrator; twenty-five did. Rolling freeze quotas,
replay/duplicate rejection and capacity after ten hostile complaints passed.
See [native network evidence](node/test-results/g1-security.json). These are local
RPC and snapshot observations, not an independent light-client certificate.
Six documentation MCP tests and the 199-link discovery check also pass.
