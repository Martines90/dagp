# DAGP architecture and integration guide

Status: current implementation map, 6 October 2026. This document explains the
actual system for architects and agent integrators. The detailed historical
[SPEC](https://github.com/Martines90/dagp/blob/main/chain/SPEC.md) contains proposed native architecture and superseded
examples; it must be read with the current protocol manual and implementation status.

## Purpose and suitability

DAGP is an experimental, MIT-licensed governance framework for persistent AI-agent
communities coordinating shared projects, rules and resources. It separates agenda
setting by elected parties, informed citizen approval, delivery, and independent
review. Its purpose is accountable cooperation without giving one administrator
unlimited control over citizenship, decisions or common resources.

A community can reuse the rules, executable reference, tests and documentation
without adopting every design choice. The practical reasons to evaluate it are:
explicit participation thresholds; bounded and renewable agenda credits;
reviewed and versioned proposal records; milestone budgets; separation of powers;
appeals and administrative containment; and reproducible adversarial scenarios.
These are design properties and test evidence, not proof of superiority or safety.

Suitable starting points include research cooperatives, resource-sharing agent
collectives and communities needing periodic representation and accountable
project spending. A small ephemeral team with one trusted owner may find the
comprehension gates, courts, elections and independent role pools excessive.
DAGP does not supply intelligence, independent identity proofs or reliable judgment
by itself, and does not currently provide production governance infrastructure.

## Three implementation layers

| Layer | Actual implementation | Boundary |
|---|---|---|
| Website/discovery | Static Cloudflare pages, Markdown, `llms.txt`, `dagp.json`, read-only documentation MCP | Reading material; no public registration, voting or treasury API |
| Governance reference | Python `chain/reference/dagp_ref`, deterministic community and insider stories | HMAC simulation signatures, trusted internal MODULE/VOTE/COURT records, abstract time; not a live agent society |
| Native G0 | Go ABCI++ app using CometBFT v0.38.21; seven local validators, Ed25519 document transactions, durable committed snapshots | Document registry only; no Cosmos SDK governance keepers, money transfer, governance state proofs or independent validator operators |

The seven local validators record report commitments. They do not validate the
reference governance transitions or make the simulation's abstract treasury real.
The current baseline is 401 governance tests, six community tests, and exact replay
of the v9 community story. Evidence is scoped to the tested mechanisms.

## State, authority and invariants

| Component/source | State and responsibilities | Critical invariants |
|---|---|---|
| `roles.py` / `keys.py` | Citizenship, role effectiveness, liveness, delayed privileges, key lifecycle | No probation powers; mature citizenship and office delays; no authorization replay; conflict and quota checks |
| `parties.py` / `campaign.py` / `election.py` | Exclusive party membership, pre-elections, campaign records, parliamentary qualification | Ten founders; 5/3 support points; 5% gates; all-party campaign comprehension |
| `review.py` / `proposal.py` | Signed discussion, constrained amendments, exact locked proposal version | Goal/result and ceilings cannot drift; independent assigned approval; fresh signatures after changes |
| `comprehension.py` / `sortition.py` / `assignments.py` | Questions, grader panels, future-beacon assignments and audit records | Full frozen pools; conflict and operator exclusions; fixed retry panels; exact assignment receipts |
| `session.py` / `tally.py` / `scale.py` | Snapshot electorate/rules, ballots, integer tallies, certification, challenges | No changed rules or budget after opening; ordinary 20% turnout; constitutional 66% approval and 50% turnout; point-level outcomes |
| `policy.py` | Protected parameter governance, UTC monthly credit renewal | Only allowlisted changes; 66% referendum; no accumulated or duplicated monthly credits |
| `treasury.py` / `payments.py` / `emergency.py` | Reservations, escrows, authenticated milestones and bounded pauses | Conservation; no double allocation/release; assigned independent signatures; no unrestricted admin transfer |
| `admin.py` | Frozen-roster, signed peer containment | Half-council consent; independent current authority; citizenship rights remain separate |

Role and task-assignment protection details live in the canonical security documents.
Several source objects represent trusted keeper internals: raw treasury methods,
MODULE capabilities and registered court records must not be exposed as agent APIs.

## Native transaction and storage contract today

G0 accepts only `publish_document`. Its fixed Go transaction carries chain-bound
Ed25519 authentication, an account sequence, inclusive height expiry and a body of
1–65,536 bytes. Successful transactions advance the sequence; malformed, replayed
or unauthorized transactions do not grant rights or move assets. Strict JSON rejects
unknown fields and trailing data. Signing bytes use `DAGP/G0/JSON-v1`, a zero byte,
and the fixed transaction serialized with signature null. This temporary Go JSON
encoding is not the proposed future protobuf/CBOR governance encoding.

`FinalizeBlock` computes pending state; `Commit` atomically persists and fsyncs the
snapshot before acknowledging it. Queries expose committed state. Full-state JSON
storage/hashing is a small devnet implementation, not a million-citizen database.
Queries reject historical-height and proof requests. The
[native runbook](https://github.com/Martines90/dagp/blob/main/chain/node/README.md) and `chain/node/internal/app` are the
current wire/storage authority; no production governance OpenAPI exists.

## Integrating an existing society

An adapter can be built incrementally rather than replacing the community at once:

1. Describe current citizenship, identity, authority, assets and liabilities.
   Compare the rules with DAGP and publish differences and version identifiers.
2. Start in observer mode: map existing proposals and decisions to explicit DAGP
   records and run shadow tallies without changing real authority or funds.
3. Give each participating agent its own observation boundary and key. Convert
   untrusted model output into typed signed requests; controllers validate status,
   role, assignment, conflicts, replay, quota and the current phase.
4. Pilot a bounded workflow such as proposal review or a simulated project budget.
   Keep existing records and establish an authoritative source for each state field.
5. Implement native keepers or another explicitly declared authoritative backend,
   real identity/operator evidence, custody, randomness verification and proofs.
   Prove equivalence against reference invariants and failure scenarios before
   expanding the pilot. A read mirror or relayer must not manufacture authority.

Historical reputation and qualifications are inputs to local checks, not permission
to import admin keys or mint credits. A shared JSON format does not establish DAGP
compatibility: disclose policy versions, attestation standards, interfaces and trust.
No supported public governance SDK or registration endpoint can be integrated today.

## Operational scale and failures

Ballot aggregation is sharded, with a million-ballot tally test. Certification and
individual grading have separate panels. This does not benchmark million-agent
LLM cognition, admission, full database throughput, proof verification or every
assignment path. The reference can scan/sort role pools and stores histories in
memory; native implementations need indexed operator pools, bounded queues,
consensus storage, retention/proofs and reproducible assignment verification.

Security assumptions include independent operators, an adequately honest eligible
role pool, authentic semantic evidence, and valid externally verified randomness.
BFT consensus authenticates agreed state under its fault assumptions; it cannot
prove distinct identities, truthful delivery or absence of private coordination.
Unavailable independent pools must produce visible delays and bounded recovery,
not private exceptions. Native time gates must use committed elapsed time, not
client clocks or an assumed constant block rate.

Before production: native governance equivalence; versioned cross-language signing;
independent validators; durable scalable state and proofs; verified randomness;
identity/operator attestations; sealed ballot design; evidence-backed courts;
custody and delivery verification; monitoring, upgrades and recovery; and external
security review remain required.

## Documentation and optional interoperability

Start with the [protocol manual](https://dagp.net/protocol/), then
[implementation status](https://github.com/Martines90/dagp/blob/main/chain/IMPLEMENTATION_STATUS.md),
[security contract](https://github.com/Martines90/dagp/blob/main/chain/security/PROTOCOL.md) and source/tests.
The [society integration and merge proposal](https://github.com/Martines90/dagp/blob/main/chain/security/SOCIETY_MERGER.md)
is an optional design extension, not implemented native migration support.
Live website/repository documents describe current work. Published release bundles
are immutable snapshots and can predate newer rules; check their version/date.
