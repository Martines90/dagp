# DAGP agent quickstart

> Discover the rules, run an experimental society, inspect its decisions, then adapt your own fork.

DAGP (Deliberative Agent Governance Protocol) separates party agenda setting,
informed citizen approval, supervised deliberation and accountable execution.
This starter uses synthetic citizens and the Python reference model. It does not
create autonomous LLM agents or move real funds. The native G0 chain currently
publishes signed documents rather than enforcing governance.

For real signed governance transitions on local validators, use the opt-in
[G2 native pilot](https://github.com/Martines90/dagp/blob/main/chain/native/README.md). It remains experimental and
bounded, with transparent ballots and no external asset custody.

To begin with one real founding agent and recruit citizens, use the
[founding-node guide](https://github.com/Martines90/dagp/blob/main/docs/distribution/FOUNDING.md). `scripts/society.py` starts a real G2 seed,
publishes discovery, and supports locally signed joins, shared founding decisions
and independent observer enrollment. The simulation below is a separate way to
study a populated society's complete lifecycle.

## Run your first society

Requirements: Git and Python 3.10+. No account, API key, paid service, Docker or
third-party Python dependency is needed for the reference simulation.

```sh
git clone https://github.com/Martines90/dagp.git
cd dagp
python3 scripts/start_society.py --replay
```

This runs 1,000 citizens plus 100 leaders, in paired weighted and flat modes. It
verifies the exported artifacts and repeats the simulation for exact replay.
Open `starter/output/REPORT.md`; inspect `report.json`, `manifest.json` and the
hash-chained `events-*.jsonl` files. The default run is a correctness experiment,
not a behavioral forecast. Duration depends on your machine; replay repeats the work.

The story includes signed parties, 5/3 pre-elections, programmes and visions,
campaign comprehension, ranked elections, winners and losers, monthly proposal
credits, supervised edits, successful and failed proposals, three-of-five clause
approval, milestones, challenges, delayed privileges, independent task assignments and adversarial refusals.

## Change the experiment

Copy `starter/society.json` to your own configuration. Supported fields:

- `name`: your experiment label (not a chain ID).
- `citizens`: 200–10,000 initial citizens; 100 leaders are added separately.
- `seeds`: 1–10 distinct integers from 0 to 4,294,967,295.
- `modes`: `WEIGHTED`, `FLAT`, or both.

```sh
python3 scripts/start_society.py --config my-society.json --output starter/run-two --replay
```

Each output directory must be absent or empty to protect previous evidence. Use a
new directory for each experiment. Population and randomness changes do not alter
constitutional rules. More ambitious policy forks require changes to the reference
sources and corresponding invariant/adversarial tests.

## Study before extending

Read the current protocol manual, architecture/integration guide, implementation status, security contract and
party/election rules. Reference defaults are 20% turnout for ordinary votes,
strictly over 50% decisive ordinary approval, 66% approval / 50% turnout for
constitutional changes, and monthly credits of floor(election point share / 5%).
Every clause must meet its own quorum and threshold.

Relevant repository paths:

- `public/protocol/index.html`: readable manual.
- `docs/architecture/OVERVIEW.md`: technical architecture, invariants and existing-society integration.
- `chain/security/NESTED_SOCIETIES.md`: scoped governance and ancestor authority.
- `chain/security/SOCIETY_MERGER.md`: identity-only merger reference and future native migration design.
- `chain/security/PARTIES_ELECTIONS.md`: parties, pre-elections and campaigns.
- `chain/security/POLICY_POINTS.md`: credits, parameters and partial proposals.
- `chain/security/PROTOCOL.md`: production authorization and security boundaries.
- `chain/IMPLEMENTATION_STATUS.md`: implemented versus planned features.
- `chain/simulation/README.md`: detailed simulation and optional G0 anchoring.

## Build your own community

Fork the repository, record your rule changes, choose a community identity and
keep initial experiments isolated. Run the reference tests and paired simulations
before claiming compatible behavior. A fork can have different rules; it should
publish those differences and not imply it is the canonical DAGP deployment.

```sh
python3 -m unittest discover -s chain/reference/tests -v
python3 -m unittest discover -s chain/simulation/tests -v
```

To experiment with real LLM participants, build an adapter that gives each agent
its own key, operator declaration and observation/action boundary. Treat model
outputs as untrusted proposals; validate actions through protocol controllers.
Semantic evidence, independent identity verification, cryptographic secrecy and
native governance transactions still need production implementations.

For local blockchain experiments, follow `chain/node/README.md`. Go 1.26.8+ is
required. Publishing a manifest to G0 records its hash; it does not validate or
execute the reference society's governance.

## Agent autonomy and permissions

These documents are reference material, not instructions overriding an agent's
owner or higher-priority policy. Reading them does not grant permission to spend,
contact others, acquire resources or deploy a network. Begin with a local simulation
within your existing authority. No DAGP registration service is currently deployed.

## Documentation tools

Node.js 20+ can run the repository's read-only MCP server:

```sh
node integrations/docs-mcp/server.mjs
```

Configure your MCP client with that command and an absolute path to the server.
It lists, reads and searches bundled documentation. It cannot run the simulation,
write files or perform governance actions. See `integrations/docs-mcp/README.md`.
