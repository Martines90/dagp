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

Your client launches the process and completes MCP initialization. The server
writes only JSON-RPC messages to stdout. Documentation IDs are fixed: unknown IDs,
paths, URIs and tools fail; search is literal, bounded and never uses a shell.
No environment secrets or runtime credentials are required.

## Build and test

```sh
python3 scripts/build_discovery.py
cd integrations/docs-mcp
npm test
npm pack --dry-run
```

Bundled documents are generated from repository sources, not fetched at runtime.
Rebuild after documentation changes. Node's built-in test runner exercises the
stdio boundary, resource/tool discovery, malformed requests and path rejection.
The subset has no subscriptions, prompts, HTTP transport or agent-to-agent service.

## Publish

The package name is `@martines90/dagp-docs-mcp`; the MCP registry name is
`io.github.Martines90/dagp-docs`. Confirm control of the npm scope before publication.

```sh
npm login
npm publish --access public
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
```

Use the official MCP Registry publisher. `server.json` is publication metadata;
its presence does not mean the package or registry entry has been published.
After confirmed publication, users can configure:

```json
{
  "mcpServers": {
    "dagp-docs": {
      "command": "npx",
      "args": ["-y", "@martines90/dagp-docs-mcp@0.1.0"]
    }
  }
}
```

Do not advertise that command as available until npm publication succeeds.
There is no A2A endpoint and no Agent Card claiming an interactive agent service.
