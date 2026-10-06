# Adversarial review — 2026-10-06

Baseline committed and pushed as `6a87852` before this review. This is an internal
code and mechanism review, not an independent audit or a production security certification.
Governance still runs in a Python reference model; G0 records signed documents only.

## Findings fixed

| Attacker / failure | Prior damage | Hardened behavior |
|---|---|---|
| Party submits negative, fractional or boolean credits/budgets | Credit inflation, corrupt escrow | Integer bounds; validate before mutation; prevent duplicate grants |
| Project administrator omits pause height or supplies zero verifier threshold | Release paused/unverified funds | Require explicit height after a pause and positive threshold |
| Voter searches secrets or retries for a colluding panel | Offline examiner selection grinding | Panel derived from issue, beacon and identity; stable across retries; exclude same operator |
| Voter grinds ticket secrets to evade audit | Selective audit avoidance | Audit ordering uses identity and attempt number rather than secret |
| Examiner replays grading or fabricates an attempt | Repeated slashing/scores; forged eligibility | Stored attempt binding; one successful grade; issued-token record required |
| Voter presents old token after audit correction | Excess vote weight | Authoritative corrected reading caps weight; ballot commitment updated |
| Record author mutates question content after opening | Change comprehension rules mid-vote | Full question-record commitment checked on open actions |
| Recovery coalition replays cancelled recovery | Hijack after cancellation | Consumed recovery nonce; known, exclusive target key; guardian operator diversity |
| Malicious transaction fails after partial application | Corrupt state/history | Pending-state application and defensive copies; complete replay verification |
| Challenge filer or unavailable court stalls forever | Locked treasury reservations | One case per identity; bounded grounds; grace timeout voids and releases reservation |
| Shard publisher supplies negative counts or invented weights | Impossible election/tally | Per-shard and aggregate integer/count/weight conservation checks |
| RPC submitter uses ambiguous JSON, oversized transactions or floods publications | Decoder disagreement; memory/disk exhaustion | Exact fields, duplicate rejection, depth/size/block limits, account epoch quotas and bounded store |
| Corrupt snapshot/genesis key | Signature panic or invalid persisted state | Bounded snapshot loading; key/document validation; atomic initialization |
| Dependency vulnerabilities | Reachable vulnerable library paths | Go 1.26.8 and gRPC 1.83.2; official govulncheck reports zero reachable vulnerabilities |

Regression evidence: `../reference/tests/test_security.py` and
`../node/internal/app/security_test.go`. Limits in `security.go` are consensus rules;
all nodes must upgrade together. Historical G0 snapshots remain readable, but new
publication counters change state hashes after the first upgraded transaction.

## Remaining attack surface and design requirements

- **Sybil/operator capture:** operator declarations and admission are trusted inputs.
  Require independently verifiable identity/operator evidence, appeals, registrar
  diversity and periodic recertification. Bonds alone cannot prove independence.
- **Oracle/examiner collusion:** cryptography authenticates graders, not truth.
  Reference signatures are simulated HMACs. Native governance needs real signatures,
  signed exam transcripts, independent regrading and enforceable evidence/slashing.
  Public answers in the simulator are not secure comprehension assessments.
- **Randomness:** fixed public beacons can permit identity/registration timing attacks;
  attempt number still affects audit selection. Freeze identities/pools before fresh
  unpredictable round randomness, use independently generated audit randomness after
  token issuance, and prove beacon availability and resistance to withholding.
- **Courts/challenge denial:** timeout prevents permanent fund locks but can still let
  meritless challenges void projects when courts are unavailable. Add evidence-based
  admissibility, calibrated bonds, independent juries and appeals before production.
- **Treasury oracle:** numerical milestone attestations are trusted test inputs.
  Require distinct authorized verifier signatures bound to project, milestone,
  amount and expiry; prove conflicts and prevent replay before real funds.
- **Shards:** structural conservation is not a proof that inputs were eligible or
  honest. Native aggregation must bind summaries to electorate and ballot roots,
  verified inclusion and uniqueness, and an effective fraud-proof window.
- **Consensus:** seven local validators share one machine/operator. This review does
  not test Byzantine equivocation, partitions, stolen validator keys or independent
  infrastructure. CometBFT's security assumptions require less than one third faulty
  voting power; governance cannot remove that requirement.
- **Availability:** finite storage and account quotas bound resource consumption but
  approved actors can exhaust global capacity. Production needs metering, fees,
  pruning/archive commitments, RPC rate limits and upgrade/capacity procedures.
- **Capture/coercion:** public votes permit bribery and coercion; declared family and
  operator diversity can be dishonest. Model coordinated coalitions, wealth and
  censorship, and specify privacy and credible dispute evidence before deployment.
- **Recovery:** runtime operator changes and pending operations require policy-bound
  rechecks in native keepers. Guardian diversity at registration is insufficient alone.
- **Bootstrap authority:** modeled module authority is trusted. Enforce expiring,
  narrowly scoped genesis privileges and finalized, evidence-bound role ratification.

## Reproduction

Run Python reference and simulation unittest discovery, Go `go test -race ./...`,
`go test ./internal/app -run '^$' -fuzz FuzzExecuteAtomic -fuzztime=20s -parallel=2`,
and `govulncheck ./...`. The scan also reports five advisories in required modules
that this code does not appear to call; zero reachable findings is not a guarantee
against unknown vulnerabilities. See the [official Go vulnerability guidance](https://go.dev/doc/security/vuln/).

`../simulation/results/hardened/` contains a fresh seed-7, 1,100-identity paired
run under hardened v2 rules. Historical pilot/large artifacts are retained unchanged;
exact replay of those v1 artifacts requires commit `6a87852`.

## Validation results

- Python reference: **238 tests passed**, including 29 attack regressions.
- Community simulator: **6 tests passed**.
- Go: race-enabled suite passed; **260,645 fuzz executions** without failure.
- Hardened paired community run: **260 checks**, **20,472 events**, exact replay passed.
- Rebuilt seven-validator smoke: document committed at height **17**, all nodes
  agreed and replay was refused.
- Dependency scan: **zero reachable findings**, five module-only advisories.

These are local correctness and attack-regression results, not proof against all
adversaries. No crash/partition/equivocation chaos campaign was performed here.
