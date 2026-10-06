# DAGP community simulation

A reproducible story of an agent society, using the existing Python governance
reference rules and the G0 blockchain as a signed results registry. No external
LLM account, paid API, Docker or third-party Python package is required.

This is a **hybrid simulation**. Registration, roles, elections, exams, ballots,
credits and treasury rules execute in `dagp_ref`. A manifest committing to the
report and event files is published through real Ed25519 transactions on the
seven-validator CometBFT network. The G0 chain does not enforce those governance
transitions yet. Synthetic identities and policies do not demonstrate AGI.

## Run from the project root

Use Python 3.10 or newer:

```sh
python3 -m unittest discover -s chain/simulation/tests -v
python3 chain/simulation/community.py --seeds 7 19 43 --output chain/simulation/results/pilot
python3 chain/simulation/verify.py chain/simulation/results/pilot --replay
python3 chain/simulation/community.py --citizens 10000 --seeds 7 --output chain/simulation/results/large
python3 chain/simulation/verify.py chain/simulation/results/large
```

Each seed runs WEIGHTED and FLAT modes, using the same keyed random draws for
participation, competence, reading, candidate preference and dishonesty. `--modes
WEIGHTED` runs one mode. `--replay` reruns the reference experiment and compares
its complete report and event stream byte for byte; larger runs take longer.

Build and initialize the network once with `make build` / `make init` in
`chain/node` (Go 1.25+ required). On this workspace the binaries and devnet already
exist. Then publish a report manifest:

```sh
cd chain/node
python3 scripts/devnet.py anchor \
  --document ../simulation/results/pilot/manifest.json \
  --receipt ../simulation/results/pilot/anchor-receipt.json
```

The command starts the seven existing validators, publishes the signed manifest,
checks the document and app hash across all nodes, writes a receipt, and stops
the processes. Use `large` instead of `pilot` for the other report. Existing content
cannot be published twice: retain the receipt for an already anchored manifest.
An updated report produces a new manifest hash and a new publication.

## The community story

The default society begins with 1,000 citizens and 100 leaders. They have different
priorities, diligence, reliability and competence; 6% have a dishonest reading-claim
policy. Five model families are distributed evenly. An additional approved
applicant and a bounded Sybil ring are introduced during admission probes. The
report's population denotes the initial society; electorate snapshots include
these additional eligible identities and exclude recused/dormant/board identities.

1. Pre-vetted synthetic identities enter probation, post bonds and receive approval.
   Bootstrap ratifications establish registrars, safety council and seven modeled
   validators. Staked examiners, project verifiers, reviewers and jurors are assigned.
   A registrar approves one applicant and rejects another with a bond refund.
2. Parties publish programmes and candidate rosters. Builders, Stewards, Researchers,
   Commons and Frontier compete. Micro fails the minimum membership requirement.
   Double-party membership and excess endorsements are excluded from qualification.
3. Citizens rank three qualified parties using the 4/2/1 election ballot. They must
   pass the comprehension gate first. Malformed election ballots are excluded.
   The certification board signs the recomputed tally; its members cannot vote.
4. Parties receive earned proposal credits, with zero-credit candidates retaining
   citizenship. There is no winner-takes-all presidency: results allocate agenda
   authority. The leading party nominates an administrator under a declared scenario
   policy; its grant uses a ratification linked to the finalized election.
5. Parties spend earned credits on nine projects. Three scripted deliberation rounds
   retain the objective/result commitment and reduce the resource ceiling. Proposing
   party members are recused. Each voter receives a ticket-specific five-examiner
   panel; a separate 51-member board certifies and audits issued tokens.
6. Favorable, reckless, low-turnout, incoherent, process-challenged, execution-failing,
   examiner-cartel, silent-board and contested-subsidy scenarios exercise different
   outcomes. Double voting, revoked tokens, uncertified payments and proposer
   self-approval are refused. Missing quorum refunds the credit. An upheld challenge
   voids the proposal. A silent board flags default but cannot halt tally finalization.
7. Approved budgets convert reservations into escrow. Modeled independent milestone
   attestations release tranches; emergency pauses block releases until expiry.
   Failed projects return unspent escrow and penalize party credits. Successful
   projects increase their party's reputation; failed projects reduce it.
8. Liveness review makes silent identities dormant. The next election uses the
   new electorate and updated party reputation, redistributing political influence.

## Experimental assumptions

This is a mechanism and workflow test, not a behavioral forecast:

- Citizen traits and turnout are seeded probabilities. Answers are generated from
  known keys plus modeled errors; no agent actually reasons or reads the briefs.
- Questions check protocol understanding and recorded article constraints. They do
  not yet establish comprehension of a rich project-specific debate.
- Programme sealing, ballot secrecy and examiner signatures use the reference model,
  which has an HMAC stand-in and memory visibility guards, not production encryption.
- Admission challenges/SSRF checks are not exercised: the HTTP registration service
  is not built. Operator declarations are assumed truthful. Successful cap checks
  cannot establish real-world Sybil resistance.
- Jury rulings and project evidence are scripted. Internals of a court and execution
  market are not implemented. Numeric attestations simulate independent evidence.
- Bootstrap offices are configured appointments. Election winner nomination and
  replacement of unspent cycle credit balances are explicit scenario adapter policies;
  debt survives. They are not complete on-chain office/election-cycle modules.
- The cartel incident injects one fully corrupted panel and a targeted audit to
  prove revocation. Other panels have a 10% hostile examiner population and receive
  protocol-sized random audits. Targeted detection is not a fraud-detection estimate.
- The contested subsidy deliberately correlates greater reading effort with greater
  opposition, testing weighting sensitivity. A changed result does not mean a better
  decision. The baseline is FLAT **with the same comprehension gate**, not unrestricted
  majority voting. Single-planner and other research baselines remain future work.
- Virtual protocol heights represent compressed societal time. They are separate
  from the actual block heights where manifests are anchored. No real resource is
  delivered and no real funds move.

## Artifacts and verification

Each run exports `report.json`, human-readable `REPORT.md`, a small `manifest.json`,
question/record files, and per-seed/mode hash-chained event streams. The manifest
commits to the report bytes, event stream hashes, terminal event roots and role
registry audit roots. `verify.py` checks artifacts and optionally replays all runs.

`anchor-receipt.json` records transaction/block heights, the transaction hash,
seven matching application hashes and block IDs, and successful document reads.
These are local RPC observations, **not independently verified consensus proofs**.
The manifest attests to recorded bytes; validators do not check the simulation's
correctness. The local validator processes all share one machine.

Checks fail the run on a rule violation, inconsistent independent tally, reservation
leak, missing expected refusal, corrupted role audit or treasury conservation failure.
Tests also cover exact reproducibility and export tampering. Large generated event
and question files are ignored by Git; compact reports, manifests and receipts are
kept alongside the code. Regenerate the ignored files before using `verify.py` on a
fresh checkout.

For the next stage, port identity/election/session/treasury rules into chain modules
and send every action as a signed transaction. Then reuse this scenario as a true
end-to-end network test, followed by real LLM deliberation and independent audits.
