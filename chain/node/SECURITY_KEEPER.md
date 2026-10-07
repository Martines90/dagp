# Native G1 identity security keeper

G1 is an **experimental, opt-in native security foundation**, not a finished
DAGP governance chain. The Go validator executes these transitions inside
CometBFT proposal validation and block finalization. No Python/HMAC reference
runtime, report anchoring or trusted client assertions authorize them.

## Activation and trust boundary

Existing G0 snapshots, document transaction signatures and hashes keep their
encoding. G1 requires a fresh, explicitly approved genesis with `governance`:
`version: 1`, `time` equal to genesis UTC Unix seconds, `identities` covering exactly
the genesis accounts, empty `freezes`, `complaints`, `cases`, `rosters` and `rotations`.
Every identity has an immutable `operator` and positive `citizen_since`; an
optional positive `admin_since` designates a **genesis-charter administrator**.
There are no runtime registration, citizenship issuance or appointment endpoints.
Operator independence and historical tenure are genesis trust assumptions;
cryptography cannot establish that two declared operators are actually independent.

A citizen must have thirty days' tenure before the charter grants administrator
status, and administrative powers activate two days after that grant. Block times
come from CometBFT, never the host wall clock or transaction payload. Unix-second
values may repeat within a second but cannot decrease. These checks do not yet
implement citizenship issuance or the three-day new-citizen activation workflow.

## Transactions

The existing seven-field transaction envelope remains strict: chain ID, account,
sequence, expiry height, type, base64 body and Ed25519 signature. Document signing
uses the existing G0 domain. All security messages use
`DAGP/G1/JSON-v1\0`. Message bodies are JSON objects with **exactly** the fields
below; extra properties, duplicate keys and upper-case aliases are refused.
Invalid actions consume neither sequence nor quota and cannot partially change
state. Bodies are capped at 4 KiB; existing block and account limits apply. G1 governance
state is capped at 8 MiB, with shared hash-addressed council rosters, and G1
snapshots at 56 MiB. G0 retains its 48 MiB snapshot bound. Security messages copy
only their write set, so stored document bytes are not copied for every action.

| Type | Exact body fields | Authority and effect |
|---|---|---|
| `freeze_identity` | `target`, `evidence` | Mature administrator; a different operator; lowercase 64-hex evidence hash; 24-hour hold |
| `open_containment` | `target`, `evidence` | Mature administrator; another operator's administrator; opens one-hour council case |
| `approve_containment` | `case` | One real signature per eligible frozen council member; half the roster temporarily contains the target |
| `schedule_key_rotation` | `key`, `proof` | Current account signature plus new-key possession signature; activation after two days |
| `cancel_key_rotation` | none | Current account key cancels its pending change |
| `activate_key_rotation` | none | Current key authorizes activation after the delay; preserves sequence and identity |

A freeze suspends the target's ability to issue further freezes. It **does not**
ban the citizen, erase identity, prohibit document publication/key maintenance,
remove council voting rights or shrink the council denominator. Admission/review
workflows that will eventually consume these holds are not implemented yet.

Freeze quotas are rolling 24-hour windows: at most two per administrator/operator,
and at most `min(20, max(3, floor(population * 0.02)))` globally. There are no permanent
ban or validator-removal transactions.

Council case rosters include all mature charter administrators, including temporarily
frozen or contained administrators in the denominator. The roster must contain at
least five administrators with distinct declared operators. The target cannot vote
for its own containment; contained administrators cannot exercise council powers.
At least `ceil(roster / 2)` eligible distinct members must approve within one hour.
The resulting administrative hold lasts six hours and cannot be extended by the
same case. Complaints themselves never suspend anyone. Duplicate target cases are
refused until expiry. One complaint per operator per rolling day and a council-sized
global allowance bound storage without letting a small minority exhaust complaint
capacity. All cases are bounded by the account limit (1,024).

The new-key possession message is the fixed JSON encoding of `{chain, account, key}`
prefixed by `DAGP/G1/KEY-POSSESSION-v1\0`; `RotationProofBytes` exposes those exact
bytes. `key` and `proof` are base64 byte strings. Pending keys are globally reserved;
current or pending duplicates, cross-chain proofs and premature activation fail.
Activation requires the current key, so **lost-key recovery is not implemented**.
Freezes and containment cannot seize keys.

## Local verification

```sh
cd chain/node
make build
make test
python3 scripts/security_devnet.py --home /tmp/dagp-g1-fresh
```

Choose a fresh directory; the runner refuses overwrite and stops every process it
starts. It creates seven local validators, 100 citizens and fifty charter admins.
It executes actual signed freezes and council transactions, tests the two-action
operator quota and three-action population cap, rejects replay and duplicate
approvals, verifies ten approvals cannot contain an admin and twenty-five can,
and compares app hashes across all seven validators. Reports are local RPC/snapshot
observations, **not independently verified light-client proofs**. Unit tests also
cover a 1,000-citizen/50-admin/10-attacker scenario, tenure, key possession,
rotation/cancellation, proposal consistency, committed-only reads, persistence,
restart and independent replay. Private devnet keys never belong in the repository.

`dagp-key --type TYPE --document message.json` signs a message using the same chain,
account, sequence and expiry flags as document publication. `/governance` queries
return committed keeper state; historical queries and proof requests remain refused.

## Remaining native engineering

This section records the G1 boundary. A fresh-chain
[G2 governance runtime](../native/README.md) now implements the broader signed
workflow under validator consensus. Read its exact coverage and pilot limits;
G1 remains unchanged and is not implicitly upgraded.

This foundation does not implement randomized assignment/beacon verification,
reviewed admission, governed role appointments, parties, campaign comprehension,
elections, proposals, clause voting, policy changes, courts, credits, milestone
payments, nested governance or remote society mergers. Those still run in the
reference model. Their full authorization chains must be ported together; there is
no simplified majority-vote or arbitrary treasury/role grant endpoint. Database
scaling, state-sync proofs, guardian recovery and independent validator upgrades
also remain engineering work. External audits, independent deployment and real
agent identity evidence remain separate release requirements.

Recorded verification: [seven-validator result](test-results/g1-security.json).
The full Go race-tested suite passes with eleven new G1 regression tests.
