# DAGP read-only documentation MCP server

A dependency-free Node.js 20+ stdio server supporting MCP protocol version
2025-06-18 (and 2025-03-26 / 2024-11-05 negotiation). It exposes documentation
resources plus `list_documents`, `read_document` and `search_documents` tools.
It has no write, network, execution, identity, voting or treasury capability.

## Use from the repository

```json
{
  "mcpServers": {
    "dagp-docs": {
      "command": "node",
      "args": ["/ABSOLUTE/PATH/TO/dagp/integrations/docs-mcp/server.mjs"]
    }
  }
}
```

The client launches the process and completes MCP initialization. Stdout contains
only JSON-RPC messages. IDs are fixed; unknown IDs, filesystem paths, URIs and tools
fail. Search is literal and bounded. No runtime secrets or credentials are needed.

## Standalone MCP bundle

The seed release distributes a self-contained `.mcpb` ZIP with a manifest, server
and documentation. Install it through a host supporting MCPB, or extract it and
configure `node` with an absolute path to the extracted `server.mjs`.

Release: https://github.com/Martines90/dagp/releases/tag/v0.1.0-seed.1
Bundle: https://github.com/Martines90/dagp/releases/download/v0.1.0-seed.1/dagp-docs-mcp-0.1.0.mcpb

Compare the bundle's SHA-256 with the release checksums / registry metadata before
installation. The bundle is unsigned; the checksum authenticates consistency with
the publication source, not independent author identity. A supporting host still
needs a compatible Node runtime. No client-specific installation claim is made.

## Build and test

From the repository root:

```sh
python3 scripts/build_discovery.py
node --test integrations/docs-mcp/test/server.test.mjs
python3 scripts/pack_docs_mcp.py --output /tmp/dagp-docs.mcpb
```

Rebuild documentation after source edits. The packer uses a fixed ZIP timestamp
and an explicit file allowlist. It excludes keys, environment files and dependencies.
Test a newly extracted bundle before distributing it. Publishing a new bundle
requires a new immutable release URL and version plus its own SHA-256 metadata.

## MCP Registry

Registry name: `io.github.Martines90/dagp-docs`. `server.json` describes the release
bundle and its exact hash; use the official publisher:

```sh
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
```

The registry hosts discovery metadata; GitHub hosts the bundle. Presence of a
metadata file alone is not proof of publication. The website discovery manifest
and distribution publication record report confirmed publication states.

## Optional npm distribution

The authenticated npm scope is `@marcipan9019`; the prepared package is
`@marcipan9019/dagp-docs-mcp`. npm currently requires account two-factor publishing
authorization. The package is not available until publication is confirmed.
`server.npm.json` is alternative registry metadata for that future distribution.

```sh
cd integrations/docs-mcp
npm test
npm pack --dry-run
npm publish --access public
```

After confirmed publication, clients can use `npx -y @marcipan9019/dagp-docs-mcp@0.1.0`.
Keep the current release-bundle registry entry until a separately versioned update
adds the verified npm package. There is no A2A service or Agent Card.
