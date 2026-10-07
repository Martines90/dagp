# Publication status — 6 October 2026

## Published

- Website: https://dagp.net/
- Agent starter: https://dagp.net/start/
- Community build guide: https://dagp.net/build/
- Agent index: https://dagp.net/llms.txt
- Full Markdown bundle: https://dagp.net/llms-full.txt
- Discovery metadata: https://dagp.net/dagp.json
- Sitemap: https://dagp.net/sitemap.xml
- GitHub repository description, homepage and agent/governance/blockchain topics.
- MIT license and read-only MCP source in the public repository.

Cloudflare Worker version: `a8917be9-5e66-4474-9cd1-4f06a85fafee`.
Public homepage, starter, llms.txt and discovery metadata were compared against
local files; Markdown Content-Type and the oversized PDF redirect were verified.
Mobile/desktop browser checks passed at 390 and 1,440 pixels.

## Submitted for review

llms.txt Hub directory listing:
https://github.com/thedaviddias/llms-txt-hub/pull/1896

Submission is not acceptance. Other directories require contact information or
account login; no submission to them is claimed.

## Release

The `v0.1.0-seed.1` GitHub prerelease packages the starter source, full verified
example society, downloadable documentation MCP package and SHA-256 checksums.
Check the release page for confirmation and attachments:
https://github.com/Martines90/dagp/releases/tag/v0.1.0-seed.1

## MCP distribution

The standalone `dagp-docs-mcp-0.1.0.mcpb` bundle is published in the seed release;
its public download matches registry SHA-256 metadata. The official MCP Registry
entry `io.github.Martines90/dagp-docs`, version 0.1.0, is published with verified
GitHub namespace ownership. The bundle manifest passes the official validator,
and a fresh extraction successfully initializes and reads the quickstart.

The optional npm package `@marcipan9019/dagp-docs-mcp` is not published: npm
rejected publication because two-factor publishing authorization is required.
Registry discovery uses the published MCPB artifact, independently of npm.
The discovery manifest distinguishes bundle, registry and npm publication flags.

## Evidence

Default seed 7, paired WEIGHTED/FLAT: 334 scenario checks, 27,658 verified events,
100,000 abstract treasury units conserved per run, exact deterministic replay.
Six MCP boundary tests, two starter boundary tests and six existing simulation
tests pass. These checks do not establish production governance readiness.
