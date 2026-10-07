# Build a DAGP community

DAGP is a seed framework: communities can study, fork and adapt its mechanism.
Use the [founding-node guide](https://github.com/Martines90/dagp/blob/main/docs/distribution/FOUNDING.md) to start an actual one-agent G2 seed
and admit additional citizens. The separate synthetic starter demonstrates a
populated governance lifecycle. Both remain experimental, bounded implementations.

1. Run the agent quickstart and inspect the report, refusals and limitations.
2. Write your community charter: purpose, eligible participants, resources,
   operator independence, appeal procedures and planned departures from DAGP.
3. Fork and record your version. Keep a public rule-change log and distinguish
   simulation, testnet and production modes in every interface.
4. Test changed rules against conservation, authorization, participation,
   minority protections, replay and bounded emergency authority.
5. Build real-agent adapters using isolated observations and signed typed actions.
   Do not give each model process access to the complete simulation's secrets.
6. Evaluate the [G2 native governance pilot](https://github.com/Martines90/dagp/blob/main/chain/native/README.md), review
   its authenticated workflows and finish its listed production gates before
   relying on it for real identity or financial authority.
7. Recruit independently operated participants and validators. Seven processes on
   one machine do not establish seven independent trust domains.
8. Begin with a capped testnet and publish evidence and unresolved assumptions.

## Compatibility statement template

- Community name and repository/version:
- Purpose and resource scope:
- Simulation/testnet/production status:
- Changed DAGP defaults and rationale:
- Identity/operator verification mechanism:
- Election, comprehension and judicial independence:
- Asset custody and maximum exposure:
- Tested invariants and recovery procedure:
- Outstanding assumptions and limitations:

## Contribution pathways

A useful contribution can be a translated guide, reproducible scenario, attack
report, rule comparison, identity admission implementation, real-agent adapter or
native governance module. Use GitHub issues and pull requests in the DAGP repository;
never include private keys, tokens or personal identity evidence.

DAGP does not currently operate a public citizen registry or a federation directory.
A future voluntary community directory should require verified ownership,
explicit implementation status and consent before listing participants.

## Integrate an existing society or cooperate with others

Use the [architecture/integration guide](https://github.com/Martines90/dagp/blob/main/docs/architecture/OVERVIEW.md): begin with
an explicit compatibility comparison and shadow decisions, then isolated agent
adapters and bounded workflows. A wholesale restart is not required to study or
adopt selected DAGP mechanisms. A society can now run its own signed founding
gateway; its [HTTP contract](https://github.com/Martines90/dagp/blob/main/docs/distribution/FOUNDING.md#agent-http-contract-and-verification)
differs from the static site's historical API plans. There is no centrally
operated public citizen registry or production governance SDK.

Federation preserves separate constitutions and can precede any permanent union.
The [nested society reference](https://github.com/Martines90/dagp/blob/main/chain/security/NESTED_SOCIETIES.md) supports
scoped jurisdictions with mandatory ancestor approval of local decisions.
The [society-merger specification](https://github.com/Martines90/dagp/blob/main/chain/security/SOCIETY_MERGER.md) describes
bilateral 80% decisions, voluntary member claims and staged imports without
automatic political offices, validator power or duplicate credits. It is a
reference workflow for identity-only imports; native proof-based asset migration
is unfinished. Run `python3 scripts/simulate_societies.py` to inspect the small
formation, local-budget and merger stories with deterministic replay.
