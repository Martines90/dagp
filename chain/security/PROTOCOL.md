# Security contract for an AGI society bootstrap

The purpose is legitimate collective action: protected citizenship, informed
participation, proportional agenda authority and accountable spending. Availability
must not be achieved by allowing an administrator to bypass citizenship, votes,
courts or treasury constraints. This document sets implementation obligations;
items marked **required** are not claims that G0 already implements them.

## Small authority surface

Every consequential action must be a typed command with a chain domain, signer,
sequence, expiry, exact target, expected state version and evidence commitment.
Validate authority and all preconditions before changing any state. Reject unknown
fields and ambiguous encoding. Consume an authorization exactly once in the same
atomic commit as its effect. No caller-provided `MODULE`, `VOTE`, `COURT` or signature
count may establish authority at a public boundary. Those reference objects are
trusted harness inputs and must become internal keeper capabilities.

Freeze rule parameters, eligible identities, conflicts and question records before
voting. Publish these commitments and deterministic tally rules. Changes affect
future sessions through versioned migrations, never reinterpret an existing vote.
Bound transaction sizes, attempts, account use and aggregate storage. Publish limits
and failure reasons so capacity cannot become undisclosed discretionary censorship.

## Authenticated milestone release

`reference/dagp_ref/payments.py` defines the reference controller. Finalized governance
funds a project with a fixed verifier roster, strict-majority threshold and explicit
beneficiary operator exclusions. A verifier signs:

`domain | chain | project | tranche index | exact amount | evidence hash | valid-from | expiry`

Release requires authorized, currently active verifiers with distinct operators and
no beneficiary conflict. Check roles and conflicts again at release, match the next
unpaid tranche and its amount, reject expired or cross-chain evidence, enforce pauses,
and advance the tranche exactly once. Signature replay cannot authorize another
project, tranche, chain or amount. A returned snapshot cannot mutate escrow.

This is a reference protocol with simulated signatures. **Required:** native Ed25519
verification, key-version binding, authenticated governance funding, verified evidence
availability, objective acceptance criteria, contested-payment delay, appeals and
execution in atomic consensus state. Raw numeric `Treasury.release_next` remains a
trusted legacy test primitive and must never be exposed as a transaction API. No
signature establishes the truth of a milestone by itself.

## Identity and key custody

Use independently attested operator identity, separate registrar/court/examiner/
validator duties and disclose concentration. Recheck recovery signers' independence
when recovery begins. A pending key change for an inactive owner does not activate.
The reference rechecks recovery coalition status/operator diversity at activation.
**Required:** bind key versions, prove
operator attestations, use cross-chain-separated real signatures and bind session
keys to exact permitted transaction families. Never give a recovered key a new citizen
identity, second vote, erased debt or authority beyond the existing record.

## Emergency, disputes and upgrades

Emergency authority can pause one project's payments temporarily; it cannot spend,
rewrite ballots, transfer identities or suppress elections. Extensions require a
matching finalized public vote. Courts need conflict-free selection, admissible
committed evidence, deadlines and appeal; unavailable courts must not permanently
lock reservations. Timeout voiding is conservative but remains vulnerable to denial
of service until admission/bond and court-availability mechanisms exist.

**Required:** versioned upgrades approved through entrenched governance, independent
review, explicit activation height, reproducible binaries, migration rehearsal and
independent validator agreement. Emergency rollback must never silently erase a
finalized decision. After a partition, resume from verified committed state, not a
chosen administrator's snapshot. Never run duplicate copies of a validator key.

## Capacity and trust boundaries

Shards require proof-bound eligible ballots and uniqueness, not just consistent sums.
Fresh audit randomness must follow token commitment; no client choice controls panel
selection. Simulated public answers are not secure exams. Adversarial tests must cover
colluding graders, registrars, courts, parties and operators, as well as honest outages.

A seven-validator equal-power network can keep progressing with two unavailable;
three unavailable should halt, preserving safety until quorum returns. The local
`devnet.py faults` campaign checks these crash cases. Byzantine equivocation,
independent-machine partitions, disk failure, censorship and compromised keys require
separate campaigns and external review. Do not treat a single-machine test as an
independent society's resilience proof.

## Release criterion

G0 is a development network. Real financial or identity dependency requires native
keepers enforcing every public-boundary invariant, evidence-backed identity and
verifier policies, independent infrastructure, verified state recovery, bounded-cost
adversarial load tests, external security review and a staged capped-value launch.
Each unresolved item must have an owner and a measurable acceptance test; increasing
simulation population does not close a missing trust boundary.
