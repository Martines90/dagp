# Contributing to DAGP

Start with `docs/distribution/QUICKSTART.md` and the current protocol manual.
Run the society locally and inspect the implementation status before proposing
production claims. Community forks and adaptations are welcome under MIT.

Use GitHub issues for reproducible attack reports, design questions, scenario
results and implementation gaps. Use pull requests for documentation, adapters,
tests and native modules. Explain what changed, why, and what evidence supports it.
Do not include private keys, account tokens or identifying admission evidence.

For governance changes, preserve existing invariant and adversarial tests, state
changes to quorum or authority explicitly, and run affected suites. For discovery
or documentation edits, regenerate copies with `python3 scripts/build_discovery.py`.
For MCP edits, run `node --test integrations/docs-mcp/test/server.test.mjs`.

Real-agent experiments must respect participant consent and operator authority.
The reference simulation's trusted module/court actors and HMAC keys are not
production transaction authentication. Keep reference/testnet/production labels
accurate in your community's public materials.
