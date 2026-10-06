# Implementation status

Updated 2026-10-05. Sources reviewed: repository Markdown, the DOCX concept note,
chain reference modules/tests, public protocol/API pages, and Wrangler configuration.

| Area | Actual state | Remaining work |
|---|---|---|
| Protocol | SPEC, DECISIONS, THREATS and concept note exist | Formal models, parameter evidence, constitutional review |
| Governance reference | Python model; 209 tests pass with Python 3.14 | Port to production keepers and prove equivalence |
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
