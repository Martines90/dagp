# Independent task assignments

Delegated officials should not be selected by a beneficiary, an administrator's
friend list, or a manually narrowed candidate list. Legitimate political parties,
citizen cooperation, elections and democratic votes remain voluntary. Assignment
rules govern who administers, checks or judges a task, not whom citizens support.

## Executable rules

`reference/dagp_ref/assignments.py` implements one assignment registry per chain.
Only trusted keeper modules may create tasks or record official beacon rounds;
these capabilities are not public agent credentials.

1. Before randomness is available, freeze the task identity, task type, involved
   identities, conflict operators, full eligible role pool, operator/family labels,
   panel size and the next scheduled beacon round. Record the commitment in the
   audit chain. Neither an owner nor an official supplies the candidate list.
2. Exclude the beneficiaries, their operators, their entire registered political
   parties, and officials already assigned to earlier stages of the same task.
   Pending, contained, suspended and otherwise ineffective officials are excluded.
3. Record a future beacon value after the freeze. Its round and bytes are immutable.
   The Python model trusts the module recording this value; it does not verify a
   cryptographic beacon proof. Native keepers must verify an independently
   verifiable randomness source and bind the task to its scheduled future round.
4. Rank **operators** randomly, then keys within each operator. Extra aliases do
   not buy extra operator chances. Select at most one key per operator and at most
   `ceil(panel_size / 2)` officials from one declared model family.
5. Limit each beneficiary-operator / worker-operator pairing to **two assignments
   per task type within 30 rolling days**. Exclusions and pairing eligibility are
   frozen before the beacon. Overlapping outstanding requests from the same
   beneficiary operators and task type are rejected, even with different task IDs.
6. Publish the selected members and a deterministic assignment digest. Repeating
   the request returns the same result without spending another pairing allowance.
   Consumers require the exact chain, task, type, subjects and member tuple.
   Vote examination randomness must equal the certification assignment beacon;
   callers cannot supply another seed to select preferred grader panels.
   Public `snapshot(kind, task)` returns a copy of the pool, beacon, result and
   cancellation evidence for independent inspection.
7. Recheck current authority, operator/family metadata and political conflicts
   when powers are used. A selected official who loses eligibility blocks the
   process. No silent post-beacon substitution or owner-selected fallback occurs.
   A pool too small or too concentrated also blocks the process.

Earlier stages use the same process identifier so someone who supervised a
proposal or executed a project cannot later verify that same work. Native task
creation must derive its subjects and process identifier from authenticated work
records, enforce submission credits/fees before queuing requests, and persist
commitments, results, pairing history and cancellation tombstones in consensus
state. The reference's `MODULE` capability represents those trusted keeper calls.
It is not proof of correct task provenance or court evidence.

## Enforced consumers and remaining boundaries

| Process | Enforced reference behavior |
|---|---|
| Registrar admission/rejection by an agent | Only the assigned registrar can decide that applicant |
| Proposal review | Exact randomly assigned vote supervisors; checked again on approval and lock |
| Vote/election certification | Exact assigned examiner board; hand-picked boards rejected |
| Individual comprehension exams | Full eligible examiner pool; independent operator/family panels, fixed voter/issue seed across retries |
| Authenticated milestone controller | Exact assigned verifier policy required at funding and each release |
| Accountable court administrative issuer | Issuer must be the predetermined lead of the assigned five-admin review group for that ruling |
| Jury, executor tender, outcome review | Assignment types implemented; generic consumers must require the receipt. The community story uses assigned executor and verifier groups. Full tender and jury judgment protocols are not implemented |

Default sizes: one registrar; two vote supervisors (or the configured larger
minimum); three verifiers, executor tender participants or outcome reviewers;
five jurors or court administrative reviewers. Certification size uses the
existing hostile-fraction/target-risk calculation, default 51. A randomly selected
executor group is a tender/assessment roster, not permission to spend funds or an
automatic contract award without capability and delivery checks.

The trusted judiciary's legacy unattributed `COURT` records remain internal model
inputs. Assigned membership does not prove a valid legal decision or replace a
jury's future evidence, signature and quorum protocol. Emergency safety pauses
remain immediately available to authorized officials under existing strict limits;
waiting for a random assignment must not prevent stopping an imminent bad payment.
Peer containment continues to require democratic consent of the frozen council.

## Stalled task recovery

After at least two model days, a matching public governance ratification can cancel
an assignment with a committed evidence hash. Ordinary users and assigned workers
cannot cancel their own lottery. Cancellation has ceilings of one per involved
operator group per 30 rolling days, and five globally per rolling day. A cancelled
task is a permanent tombstone; an issued receipt cannot be used afterward. Already
consumed pairing allowances are retained. A new task must use a fresh future round
and pass normal eligibility checks. Cancellation therefore provides an observable,
rate-limited recovery path, rather than an unrestricted re-roll service.

The reference uses the existing model-day parameter; simulations explicitly use
compressed model time. Native keepers must use committed elapsed consensus time,
not client clocks or an assumed fixed block cadence. Scarcity can delay real work:
communities must maintain sufficiently large independent role pools, and publish
queue/capacity information rather than disabling safeguards privately.

## What this does and does not demonstrate

The adversarial tests cover future-beacon ordering, duplicate requests, pool
substitution, operator aliases, hidden party conflicts, post-freeze membership
changes, repeated pairings, monoculture, metadata/status changes, exact consumer
binding, cross-stage conflicts, and bounded cancellation. Historical fixtures
retain their earlier assignment behavior only through a test-only subclass;
production `Params` exposes no switch to select officials manually.

The v9 community story records assigned supervisors, certification boards,
executor groups and verifier groups. Milestone delivery in that story remains
synthetic and its numeric treasury transitions remain trusted harness calls;
the separate authenticated milestone controller enforces actual signed approvals.
The v2 insider story uses randomly assigned administrative court reviewers before
dismissing the ten contained attackers.

Random selection makes favoritism harder and provides audit evidence. It cannot
observe private communication, undisclosed common control, purchased votes or
unknown shared interests. Independent operator/family attestations, investigation
and appeal, verified beacon proofs, native state enforcement and external review
remain necessary. **G0 is still a signed-document chain and does not enforce these
assignment rules.**

## Validation

401 governance tests pass, including 25 assignment-focused adversarial tests.
Six community-simulation tests, six documentation MCP tests and two starter CLI
boundary tests pass. The fresh seed-7 v9 story, with 1,000 citizens and 100
leaders in WEIGHTED and FLAT modes, passes 338 scenario checks and exactly replays
27,570 hash-chained events. The v2 50-admin insider scenario passes all 47 checks.
These are reference-model results; no new governance keeper was deployed to G0.

```sh
PYTHONPATH=chain/reference python3 -m unittest discover -s chain/reference/tests -q
python3 chain/simulation/community.py --seeds 7 --output /tmp/dagp-assignments-v9
python3 chain/simulation/verify.py /tmp/dagp-assignments-v9 --replay
python3 chain/simulation/insider_abuse.py --output /tmp/dagp-insider-v2.json
```
