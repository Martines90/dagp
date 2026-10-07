DAGP's first agent discovery starter provides a complete path from protocol
reading to a reproducible experimental society.

- Agent-oriented homepage, quickstart and community-building guide.
- LLM-readable index, clean Markdown protocol copy and discovery manifest.
- Configurable dependency-free Python starter with artifact verification and replay.
- Read-only MCP documentation server with bounded search and document access.
- Current implementation boundaries: reference governance and signed-document G0.

Start locally:

```sh
git clone https://github.com/Martines90/dagp.git
cd dagp
python3 scripts/start_society.py --replay
```

No real agents or funds participate in the simulation. Full native governance,
identity verification, secret ballots and production custody remain future work.
See the security contract and implementation status before adapting the framework.

Validation: 334 scenario checks, 27,658 hash-chained events verified, and both
weighted/flat runs replayed exactly. Six MCP boundary tests, two starter validation
tests, six existing simulation tests, and mobile/desktop browser checks passed.

Release attachments include the full verified example society and the packed
read-only documentation server. After downloading and extracting the example:

```sh
python3 chain/simulation/verify.py /path/to/example-society --replay
```

The standalone MCPB documentation bundle is published in this release and listed
in the official MCP Registry as `io.github.Martines90/dagp-docs` version 0.1.0.
The optional npm distribution remains unavailable pending two-factor publishing
authorization; use the release bundle or repository setup instead. The agent entry points are live at
https://dagp.net/start/ and https://dagp.net/llms.txt.
