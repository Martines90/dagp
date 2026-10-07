# Implementation status

Updated 2026-10-06. Sources reviewed: repository Markdown, the DOCX concept note,
chain reference modules/tests, public protocol/API pages, and Wrangler configuration.

| Area | Actual state | Remaining work |
|---|---|---|
| Protocol | SPEC, DECISIONS, THREATS and concept note exist | Formal models, parameter evidence, constitutional review |
| Governance reference | Python model; 376 tests pass with Python 3.14 | Port to production keepers and prove equivalence |
| Consensus/network | Go CometBFT G0 network with seven local validator configurations | Independent operators, validator policy, fault/censorship drills |
| Transactions | Real Ed25519 signatures, chain binding, sequences, height expiry, strict JSON | Versioned protobuf/CBOR, resource quotas, key lifecycle |
| State | Durable snapshots, deterministic hash, committed-state queries | Scalable database, Merkle proofs, snapshots/state sync |
| Documents | Signed SHA-256 content-addressed publishing up to 64 KiB | Availability attestations for larger documents |
| Registration | Roadmap only | Worker/D1, challenge-first admission, signed evidence, admin review, SSRF defense |
| Governance on chain | Not yet implemented | Identity/roles → proposals/deliberation → examiner/tally → escrow/review → elections/courts |
| Cryptography | Ed25519 on G0; HMAC stand-in in reference | Sealing/timelocks, beacon verification, threshold custody |
| Website | Static observer pages | API page reconciled with roadmap; publish canonical OpenAPI/schemas/discovery |
| Deployment | Static assets configured in Wrangler | Gateway/read mirror; hosted nodes; monitoring and recovery runbooks |
| Production readiness | G0 only | SDK integration, audits, simulation, independent validators, external anchoring |

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
