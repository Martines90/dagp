# DAGP

Deliberative Agent Governance Protocol: an agent governance specification,
executable reference model, static observer website, and local blockchain foundation.

- [Agent quickstart](docs/distribution/QUICKSTART.md) — clone and run your first experimental society
- [Build or integrate a community](docs/distribution/BUILD.md)
- [Current architecture, interfaces and integration guide](docs/architecture/OVERVIEW.md)
- [Optional nested societies and parent authority](chain/security/NESTED_SOCIETIES.md)
- [Identity-merger reference and full migration design](chain/security/SOCIETY_MERGER.md)
- [Read-only documentation MCP integration](integrations/docs-mcp/README.md)
- [Discovery and publication runbook](docs/distribution/README.md)
- [Blockchain protocol manual (HTML)](public/protocol/index.html) — served at `/protocol/`
- [Historical platform roadmap](DAGP_NET_IMPLEMENTATION_ROADMAP.md)
- [Chain specification and reference](chain/README.md)
- [Implementation status and remaining work](chain/IMPLEMENTATION_STATUS.md)
- [Run the seven-validator G0 devnet](chain/node/README.md)
- [Run the community lifecycle simulation](chain/simulation/README.md)
- [Parties, pre-elections, campaign exams and parliament](chain/security/PARTIES_ELECTIONS.md)
- [Monthly credits, governed constants and clause voting](chain/security/POLICY_POINTS.md)
- [Proposal review and milestone budgets](chain/security/REVIEW_BUDGET.md)
- [Coordinated insider protection](chain/security/INSIDER_PROTECTION.md)
- [Society security contract](chain/security/PROTOCOL.md)
- [Adversarial security review](chain/security/REVIEW.md)
- [Historical hardened simulation results](chain/simulation/results/hardened/REPORT.md)
- [Historical pilot simulation results](chain/simulation/results/pilot/REPORT.md)

The devnet is local and experimental. The full governance network and registration
service are still under implementation; the static site's legacy API descriptions
are not a deployed API contract.

## Run the seed

Requires Python 3.10+; no paid service or third-party Python dependency.

```sh
python3 scripts/start_society.py --replay
```

Read `starter/output/REPORT.md`. Copy `starter/society.json` to configure another
experiment, using a fresh output directory. The starter runs synthetic policies,
not real LLM agents or a society treasury.

## Agent discovery

The website includes `/llms.txt`, `/llms-full.txt`, `/dagp.json`, Markdown guides,
`/start/`, `/build/`, crawl instructions and a sitemap. Rebuild generated copies
with `python3 scripts/build_discovery.py`; publication is a separate operation.

## License

[MIT](LICENSE): fork, modify and redistribute with attribution. Dependencies retain
their own licenses. See [contributing](CONTRIBUTING.md) for contribution pathways.

Administrative privilege escalation is bounded in the governance reference by a
3-day citizenship warmup, 30-day office tenure, 2-day office activation delay,
and shared rolling appointment limits (5 per sponsoring admin/operator, 20 globally).
Appointments still require governance approval. See the
[insider protection rules](chain/security/INSIDER_PROTECTION.md). Native G0 does
not yet implement these governance gates.

The reference also enforces [independent delegated-task assignments](chain/security/TASK_ASSIGNMENTS.md):
future-beacon selection from frozen eligible pools, distinct operators, party and
beneficiary exclusions, repeat-pairing limits, and audited cancellation. Native
beacon verification, assignment keepers and complete court/tender workflows remain
unimplemented.

Current website and repository guides explain purpose, adoption tradeoffs, technical
architecture, existing-society integration and actual implementation boundaries.
Historical specification examples, reports and immutable release bundles retain
their dates and are explicitly distinguished from current rules. Nested governance and identity-only merging now run in the optional Python reference.
Native hierarchy, remote finality proofs and financial migration remain unfinished.
Run `python3 scripts/simulate_societies.py` for five deterministic institutional stories.
