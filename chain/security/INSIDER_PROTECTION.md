# Coordinated insider protection

## Delayed citizenship and office activation

Production reference defaults add mandatory gates to prevent rushed enrollment and
privilege escalation. These are protected security parameters, outside the ordinary
parameter-vote allowlist; the production `Params` constructor also rejects weakening
the minimum durations or increasing the appointment ceilings.

| Gate | Default |
|---|---|
| Citizenship warmup after admission | 3 rolling days before civic powers become effective |
| Citizenship tenure before sensitive office appointment | At least 30 rolling days |
| Delay after appointment | 2 rolling days before office powers become effective |
| Appointments sponsored by one admin | At most 5 in any rolling 24 hours |
| Appointments sponsored by one operator, across keys | At most 5 in any rolling 24 hours |
| All sensitive office appointments combined | At most 20 in any rolling 24 hours |

Sensitive offices are admin, registrar, safety council and vote supervisor. All
four share the same appointment budget: switching the role name does not create
another allowance. An admin **cannot appoint officials unilaterally**. Appointment
still requires an unused matching governance ratification. A sponsoring admin is
recorded on that immutable ratification, must be effective and uncontained when
it is executed, and cannot sponsor another identity controlled by the same operator.
Trusted voting-module decisions without an individual admin sponsor consume the
same global budget; they are not an externally callable admin bypass.

Pending grants record a public activation height in the audit and `role_ready`
state. Effective-authority checks enforce the delay on registrar admission, court
issuance/execution, safety pauses, vote supervision and council membership. A pending
admin does not enter the oversight denominator. Council snapshots require an explicit
current committed height when created or refreshed. Citizenship voting rights remain
separate from the extra office delay once citizenship itself has matured.

A ratified revocation can cancel a pending appointment. Revocation and reappointment
start a fresh full activation delay and do not refund the rolling appointment budget.
Duplicate grants fail without spending authorization, stake or budget. Backdated
appointments fail. Citizenship re-grants restart citizenship age; ban appeals restore
citizenship with a fresh warmup and require other offices to be re-earned. Revoking
citizenship also suppresses dependent office authority until tenure is met again.
Liveness renewal and key rotation do not mint new appointment allowances.

The reference uses `protection_day_blocks = 14,400` abstract blocks per model day:
3-day warmup = 43,200; 30-day tenure = 432,000; 2-day office delay = 28,800.
**Native governance keepers must use committed consensus timestamps and elapsed
86,400-second days**, never client timestamps or an assumed fixed block cadence.
Thirty days is an elapsed-duration policy, not a calendar-month boundary. The main
community and insider simulations explicitly compress a model day to one height
while preserving the 3/30/2-day rules. Historical unit fixtures use a test-only
`HistoricalParams` subclass to preserve earlier timing for unrelated rules;
`test_privilege_gates.py` uses unmodified production defaults and adversarial cases.
There is no runtime genesis exemption from these gates in the reference registry.

Validation of this refinement: 376 reference tests, including 18 dedicated
production-default privilege tests; six community-simulation tests; and the
47-check coordinated-insider scenario. The fresh v8 seed-7 community run covers
1,000 citizens plus 100 leaders in both WEIGHTED and FLAT modes, with 338 scenario
checks and 27,658 hash-chained events. Run and verify with:

```sh
PYTHONPATH=chain/reference python3 -m unittest discover -s chain/reference/tests -q
python3 chain/simulation/community.py --seeds 7 --output /tmp/dagp-privilege-v8
python3 chain/simulation/verify.py /tmp/dagp-privilege-v8 --replay
python3 chain/simulation/insider_abuse.py --output /tmp/dagp-insider-gates.json
```

These rules execute in the Python governance reference. G0 currently anchors signed
documents and reports; it does not yet enforce citizenship or administrative roles.
Delays and quotas bound privilege growth, but do not establish independent identity,
prove good intentions, or replace the planned native keeper implementation and audit.

## Threat model

Fifty elected administrators exist; ten coordinate to freeze citizens, purge honest
officials, reject applicants, pause every project or disable the validators. Their
accounts are valid but intentions are hostile. Limits apply to successful state
changes, and changing account, ruling reference or role must not erase the budget.

Admins are not superusers. `ADMIN` enables peer oversight; registrar and safety
council powers remain separately assigned. A registrar cannot ban citizens or remove their voting, case-filing or key-custody
rights through a spam freeze. Courts can impose a full suspension, including upgrading
an existing spam freeze; a registrar freeze cannot shield a target from judicial review. A peer
vote cannot confiscate funds, ban citizenship, erase votes or stop validators.

## Enforced reference defaults

| Boundary | Default |
|---|---|
| Combined suspensions, bans and role revocations | 2 per accountable official per rolling model day |
| Shared operator | Same combined limit of 2, across that operator's accounts |
| System-wide sanctions | At most 20; also limited to 2% of the frozen cohort's active citizen population, with a small-network floor of 3 |
| Permanent bans | At most 5 across the system, within the combined budgets |
| Registrar admission/rejection decisions | 50 per official/operator and 250 system-wide per rolling model day, plus existing epoch approval quota |
| Unratified project pauses | 2 per official/operator, 10 system-wide per rolling model day |
| Simultaneously paused funded projects | At most ceil(20% of funded nonempty escrows), minimum 1 |
| Peer containment | 25 independent approvals for a frozen 50-admin roster |
| Containment vote expiry / hold | 100 / 300 blocks |
| Repeated containment of same target | No new request until 600 blocks after the preceding containment |

A model day is `protection_day_blocks=14400`, an abstract reference window, not a
claim about actual wall-clock time on this devnet. **Native implementation must use
committed monotonic consensus timestamps and a rolling 24-hour interval.** Windows
roll continuously, so crossing midnight does not double an attacker's allowance.
The live sanction cohort freezes its population denominator; citizen removals do
not opportunistically lower it, and admissions cannot inflate an existing cohort.
The floor is explicitly a bootstrap compromise: percentage guarantees do not hold
for very small populations. All parameters are public, immutable snapshots with
positive-integer validation. Court-ordered suspensions and bans remain judicial
inputs; new limits do not prove that a court ruling was fair.

A court ruling records its accountable official at issuance. Its action/target and
reference are immutable; execution rechecks that official's current authority.
Legacy unattributed internal court inputs share one budget instead of receiving a
new allowance for each reference. `MODULE` inputs are trusted harness capabilities,
not an API an administrator may call. Operator-wide exclusion additionally needs
public vote ratification: a court ban of one identity cannot alone blacklist an
operator's future applicants.

## Contain, review, restore

`AdminCouncil` accepts signed evidence-bound complaints and approvals with a chain
domain, unique case identifier, frozen roster version and deadline. Repeated approvals,
self/operator-conflicted votes, forged signatures and expired cases do not count.
Approval counts distinct current operators and rechecks supporter authority. Removing,
suspending or containing members does not reduce the frozen denominator. Roster
refresh requires a separate public ratification and cannot occur during open cases.

At threshold the target temporarily loses admin, registrar, safety-council, grading,
verification, review, jury and execution powers. Citizenship, ordinary voting, case
filing and validator operation remain. This prevents a recall vote from creating a
citizenship purge or a network shutdown. A 10/50 faction cannot trigger containment.
A 25/50 coalition can; evidence is committed but its truth is not evaluated by this
reference controller. Independent review remains essential against majority abuse.

A court can restore a mistaken hold. A matching independent court ruling can also
permanently dismiss a contained official's operational roles. Review has a separate
bounded budget, so exhausting the citizen-sanction allowance cannot protect attackers
from dismissal. Dismissal does not ban citizenship, slash the citizen's funds or remove
a validator. Reappointment requires ordinary governance; peers cannot unilaterally
restore privileges. A court ruling needs real independent adjudication in production,
not simply another admin's approval or a caller-supplied reference.

## Other bypasses closed

- Citizenship-role removal or judicial restoration requires a court; registrar
  admission creates citizenship only from probation. All role revocations consume sanction budget; stripping a citizen/registrar/examiner
  role is not a way around the suspension limit. Dependent roles stop functioning when
  the citizenship prerequisite is removed.
- Cluster suspensions validate all member rulings and aggregate quota before applying
  any member. Invalid batch authorization cannot leave the first citizen suspended.
- Individual validator suspension, ban and removal check remaining quorum; ban/removal
  also preserve the minimum set size. Whole-set replacement remains a ratified vote.
  The reference uses equal seats; native code must check actual voting power and CometBFT
  update semantics. This does not stop operators physically switching their servers off.
- Pauses share counters in the registry, so creating a new Emergency controller does
  not reset allowances. Concurrent project holds are bounded and expire automatically.
- Rejected operations do not consume authorizations, quota or partially change state.

## Evidence

Run from the repository root:

```sh
PYTHONPATH=chain/reference python3 -m unittest tests.test_admin_abuse
python3 chain/simulation/insider_abuse.py --output /tmp/insider-abuse.json
python3 chain/simulation/community.py --seeds 7 --output /tmp/community-v3
python3 chain/simulation/verify.py /tmp/community-v3 --replay
```

The [insider scenario](../simulation/results/self-protection/insider-abuse.json)
uses 1,000 citizens and 50 admins. Ten attackers attempt 50 freezes: 20 succeed and
30 are refused. Victims recover automatically. The hostile 10 cannot contain an
honest admin; 25 honest peers contain all ten attackers, then courts dismiss their
powers without banning their citizenship. All **47 scenario checks** pass.

The **31 targeted regression tests** also cover shared operators, cross-chain signing, midnight
bursts, reference replacement, quota exhaustion, minority recalls, administrative
restoration, safe validator sanctions and full-project shutdown attempts. Community
v3 distributes legitimate emergency work across three independent safety officials;
it preserves the limits instead of disabling them for the story.

These mechanisms are executable in the Python reference. **G0 still publishes
signed documents; it does not enforce these governance transitions on-chain.**
Production needs native keepers, authenticated court evidence, real signatures,
key versions, evidence availability, independent identity/operator attestations and
external review. Collusion controlling half the council, dishonest operator labels,
captured courts and physical infrastructure attacks remain separate trust risks.

Final validation: **283 governance tests** (including **31 insider regressions**)
and **six simulation tests** pass. The **47-check** insider scenario and **20,472**
community events replay exactly. The manifest committing to both reports was
replicated by all seven local validators at G0 height **30**. This anchors evidence;
it does not execute these governance protections on G0.
