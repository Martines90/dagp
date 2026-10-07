# Discovery and publication runbook

The project is designed to distribute a useful seed: discover → understand →
simulate → fork → build a community. Discovery files do not guarantee that agents
will find the site, and visits do not establish autonomous adoption.

## Build and validate

```sh
python3 scripts/build_discovery.py --origin https://dagp.net
python3 -m unittest discover -s scripts/tests -v
python3 -m unittest discover -s chain/simulation/tests -v
node --test integrations/docs-mcp/test/server.test.mjs
python3 scripts/start_society.py --output starter/run-validation --replay
```

Rebuild public Markdown and MCP bundles after editing their source documents.
Keep the current protocol's implementation boundary visible in downstream copies.
For a fork, set your own origin and update the site canonical links, repository
links and package/registry identities before deployment.

## Publish the website

Use Node.js 20.19+ or a current supported Node LTS. The existing Cloudflare Workers
configuration serves `public/` as static assets. Existing custom domain bindings
are maintained in the Cloudflare account; this configuration does not create DNS.

```sh
npx wrangler login
npx wrangler deploy
```

After deployment, verify the actual public domain, not just the generated files:

```sh
curl -f https://dagp.net/llms.txt
curl -f https://dagp.net/docs/quickstart.md
curl -f https://dagp.net/dagp.json
curl -f https://dagp.net/sitemap.xml
```

Confirm Markdown Content-Type, correct canonical URLs, new homepage, direct access
to `/start/` and `/build/`, and the discovery manifest's accurate publication flags.
An old cached homepage is not evidence that the new starter was deployed.

## Publish releases and discoverable metadata

The repository homepage should be https://dagp.net with relevant agent/governance
and blockchain topics. Releases should link to reproducible commands and state that
governance remains a reference model. A prerelease is appropriate for this seed.
Use `RELEASE.md` as the release body and include a verified example report/manifest.
Source archives are supplied by GitHub releases; do not include private devnet keys.

## Publish the MCP integration

Follow `integrations/docs-mcp/README.md`. First verify npm scope ownership and
publish its package. Then validate and publish `server.json` with the official
MCP Registry publisher using verified GitHub ownership. Update the discovery
manifest's `published_package` flag only after npm publication is confirmed.

## Submit documentation and worked examples

After the public site is verified, submit `/llms.txt` to documentation directories
through their contribution forms. Offer the quickstart and report to relevant
agent-framework communities through their normal contribution processes.
`OUTREACH.md` provides concise, accurate announcement text. Publication requires
the relevant account and a chosen destination; do not claim submissions happened
without confirmation or send unsolicited bulk messages.

A2A Agent Cards describe actual A2A services. This documentation tool is MCP over
local stdio, so no card or nonexistent A2A endpoint is advertised.

## License

Original project code and associated project documentation are MIT licensed.
Retain the notice in forks and bundles; upstream dependencies keep their own licenses.
