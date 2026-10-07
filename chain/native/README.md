# G2 validator-executed governance pilot

G2 is an opt-in consensus runtime for fresh local chains. It executes governance
transitions during CometBFT proposal validation and finalization, and commits the
resulting governance state. It does not merely anchor simulation reports.
Existing G0 and G1 networks retain their wire format and state hashing.

**This is an experimental bounded pilot, not a production financial network.**
The native ledger uses charter-issued units. A society can run its own
[founding gateway](../../docs/distribution/FOUNDING.md) for signed recruitment and
admission. No global public registry, external asset custody, independent
validator deployment or external audit is provided by this implementation.

## One-agent founding stage

`python3 scripts/society.py init --home ./my-society` and then `start` create a
fresh one-founder G2 chain. An explicit SEED charter provides finite authority
for recruitment, consented qualification, candidate-proven validator enrollment
and irreversible graduation. Frozen citizen rosters require two-thirds approval,
with one seat per declared operator; authority becomes shared as citizens mature.
The founder's tenure is truthful. Normal warmup, office tenure and activation
delays apply, apart from the explicitly chartered initial founding roles.

The seed cannot enact laws, spend project budgets, ban citizens or change protocol
parameters. It has a 6,000-unit lifetime budget, daily and concurrent-case limits,
and a nonrenewable one-year deadline. Graduation requires 150 mature independent
citizens, staffed governance pools, seven validators and a citizen-approved valid
collective beacon. Exact roles, limits, HTTP/signing contracts and commands are in
the [founding guide](../../docs/distribution/FOUNDING.md). Synthetic transition
fixtures test time gates; live admission uses real consensus time.

## Authority boundary

The Go application verifies the real Ed25519 transaction signature, chain,
sequence, height expiry and delegated session scope. It supplies the authenticated
caller and committed UTC consensus time to a pinned Python reducer. Transactions
cannot supply a MODULE, COURT or VOTE capability, arbitrary Python method, object
graph, code path or authority flag. Internal single-use capabilities are created
only after the corresponding authorized workflow succeeds.

The reducer reuses the reference state machines. Its `Receipts` record actions
already authenticated by Go; they are not HMAC simulation signatures. Question
answers require individual transactions from three of five assigned examiners.
Question banks, role effects and exact budgets are bound to the reviewed proposal
digest. Refinement clears prior approvals. Invalid transactions discard the entire
write set and consume neither sequence nor quota.

State serialization is canonical, bounded JSON with an explicit class allowlist,
references and shared object identity. It uses no pickle or client-selected import.
Validators execute the same pinned code and Python implementation/version
(major/minor/patch); startup checks the fingerprint and
reconstructs committed state. Runtime infrastructure failures stop validation
rather than being treated as a locally chosen failed transaction.

## Implemented transaction families

Every action uses type `protocol`, with body `{"operation":"…","args":{…}}`.
The signing domain is `DAGP/G2/JSON-v1` followed by a zero byte and the fixed Go
transaction struct with signature null. Bodies are base64 in the outer envelope.
The exact field sets are enforced in `dagp_native/engine.py` and `merger.py`.

| Family | Native behavior |
|---|---|
| `wallet.transfer` | Conserved native ledger units; bounded citizen sponsorship of new accounts |
| `identity.*` | Prefunded prior challenge, key possession, assigned registrar review, probation, three-day civic warmup, heartbeat, exit and bounded temporary freezes |
| `beacon.publish` | Collective BLS proof verification, frozen future-round schedule and jurisdiction-specific assignments |
| `party.*` | Ten individual founder consents, exclusive membership, internal frozen-roster sanctions |
| `pre.*`, `campaign.*`, `election.open` | 5/3 support points, 5% qualification, committed candidate programs and visions, mandatory campaign comprehension |
| `proposal.*` | Independent supervisors, signed party discussion, versioned refinement, fresh approval, locking, reviewed budget reservation |
| `exam.*`, `vote.*` | Independent per-voter grading, certification-board audits, electorate/rule snapshots, weighted ballots, quorum, challenges, finalization and independent clause outcomes |
| `role.accept`, `role.apply` | Candidate consent, finalized referendum authority, current tenure, activation delay, shared sponsoring-operator and global appointment quotas |
| Parameter and constitutional ballots | Protected allowlist; 66% parameter approval with general quorum; 66% constitutional approval with 50% participation; next-month parameter activation |
| Monthly agenda credits | Elected parties only; floor(vote share / governed credit step), UTC monthly replacement, existing debt/refund protections |
| `milestone.approve`, `treasury.pause` | Actual assigned verifier approvals; exact funded tranche, deadline and conservation checks; bounded emergency pause |
| `admin.*`, `court.*` | Frozen-roster council containment; voted roster refresh; independent jury and subsequent court-administrator assignment; quotas, sanctions and appeals |
| `key.*` | Real new-key possession, delayed rotation, independent guardian recovery and limited expiring session keys |
| `society.*` | Founder consent, mandatory ancestor review, paired parent/cohort formation ballots, cooling-off, inherited constraints, local political state and parent-reserved budgets |
| `merger.*` | Bilateral 80% participation/approval mandates, notice/cooling-off, verified peer exports, voluntary source exit, identity-only import, warmup, replay protection and unclaimed-export recovery |

The genesis identity/operator/family labels and prior tenure remain charter trust
assumptions. Random assignments make declared insider coordination harder; they
cannot detect secretly shared ownership. Human-quality comprehension, truthful
grading and actual project delivery are not established by cryptography alone.

## Randomness and remote checkpoints

Randomness uses `pedersen-bls-unchained`: one charter-pinned collective G1 public
key, a G2 BLS signature over SHA-256 of the absolute round encoded as eight
big-endian bytes, and SHA-256(signature) as the seed. Each pool commits before its
scheduled future round. A signed early, wrong-round or forged proof is refused.
Jurisdictions share the authenticated external beacon, with separate local rounds.

G2 application roots are CometBFT Merkle roots over metadata, governance graph,
accounts, documents and named exports. `/export`, with the export key as request
data, returns `{value,proof}` at committed application height H. A signed header
and commit at H+1 authenticate that application root. Proof JSON is returned in
the value; it is not an ABCI `ProofOps` response. Historical export queries and
general state-sync/light-client services remain unsupported.

`receipt/<account>` exports the account's latest accepted protocol result and
transaction digest, including challenge/ticket/assignment identifiers. Clients
must match the expected digest: the next accepted action replaces that receipt.

Peer chains must be declared in genesis with their expected code hash and seven
or more distinct Ed25519 validators. Incoming proofs require the exact chain,
pinned current/next validator-set hashes, a real greater-than-two-thirds commit,
the exact export Merkle leaf and its chain/code commitment. Remote validators are
a trust anchor, not a proof that their software is honest. Validator rotation and
dynamic peer admission require a coordinated upgrade; no user transaction can
replace the trust anchors.

Merger admission imports citizenship only. Source offices, parties, agenda
credits, treasury assets, debts and contracts do not migrate. A source citizen
exits before a receiving claim; the claim needs receiving-key possession and a
funded receiving bond. Imported citizenship warms up for three days, and offices
must be earned again. An unclaimed exit can be restored only after the receiving
deadline has closed and an authenticated claim-tree proof establishes non-claim.

## Running and verification

Use Python 3.10+ with the same interpreter version on every validator, Go 1.26.8,
and fresh genesis/state directories. Build the node tools in `chain/node`:

```sh
go build -o bin/dagpd ./cmd/dagpd
go build -o bin/dagp-key ./cmd/dagp-key
go build -o bin/cometbft ./cmd/cometbft
python3 scripts/governance_devnet.py --home /tmp/dagp-g2-fresh
```

The runner refuses to overwrite its home, launches seven local validators with
100 citizens and 50 charter admins, signs founder consents and pre-election
ballots, rejects replay/raw authority calls, compares committed roots, and stops
its processes. Its beacon generator key is a public test fixture. It does not
deploy a production randomness service. Evidence is saved to
`chain/node/test-results/g2-governance.json`; private keys remain outside Git.

```sh
PYTHONPATH=chain/native:chain/reference python3 -m unittest discover -s chain/native/tests -q
PYTHONPATH=chain/reference python3 -m unittest discover -s chain/reference/tests -q
cd chain/node
go test -race -count=1 ./...
```

Native adapter stories cover elections, a five-clause 3/5 funded outcome and
milestone release, admission gates, court/appeal separation, paired subgroup
formation, monthly parameter activation with a live council case, suspension
expiry and bilateral merger/failed-claim recovery. Their trusted-host inputs
are explicit fixtures. Go tests independently use real Ed25519/BLS signatures
and real CometBFT checkpoint verification, plus persistence/restart and
cross-process hash agreement. Long day/month phases use advanced committed-time
fixtures, not shortened protocol thresholds.

Go's test cache cannot track external Python source changes; use `-count=1` for
these integrated checks. The node Makefile does this automatically.

## Pilot limits and unfinished engineering

Accounts are capped at 1,024, object graphs at 8 MiB/50,000 nodes, exports at 1 MiB, transaction
bodies at 64 KiB and blocks at 128 transactions/2 MiB. The reducer currently
starts a process and serializes its graph for each invocation. Audit/receipt
history consumes graph capacity; there is no archival database or pruning yet.
These bounds prevent unbounded input but do not establish sustainable production
throughput or million-member operation.

New account funding requires an eligible citizen, at least bond+one unit, at most
five new accounts per operator and forty globally per rolling day. A challenge
consumes one unit into the common pool. Signing accounts are retained rather
than silently reused. Reaching pilot capacity requires an explicit migration.

Ballots are transparent consensus state. API phase restrictions do **not** provide
cryptographic secrecy; committed question-answer receipts are also observable.
Timelock encryption, secret ballots, threshold custody, large-document
availability, formal equivalence, upgrade/validator governance, scalable indexed
storage and state sync remain unfinished. Entrenched `CORE` votes, governed task
cancellation and full tender/execution contracting are not exposed as native
actions. Constitutional ballots are a distinct implemented kind.

Small cohorts retain safety thresholds: formation is possible using the parent
professional pool, but later local votes need sufficient local qualifications
and independent officials. Offices do not flow down automatically. A cell with
too few examiners cannot replace the 51-member board with insiders. Local-office
bootstrap and campaign parent-permission UX need further integration work.
Do not treat the experimental structural handlers as a production merger bridge.
