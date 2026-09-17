# Installation

[Back to README](../README.md) · [Configuration](configuration.md) · [Tools](tools.md)

## Prerequisites

- [Seamly2D](https://seamly.io/) installed. This project was built and tested
  against `seamly2d.exe` v0.6.8 at `C:\Program Files (x86)\Seamly2D\seamly2d.exe`
  on Windows; other install locations work too as long as `seamly2d.exe` is on
  `PATH` or passed explicitly (see [configuration.md](configuration.md)).
- Python 3.12+ and [uv](https://docs.astral.sh/uv/guides/tools/).

## Install the server

```bash
git clone <this-repo> "seamly2d MCP"
cd "seamly2d MCP"
uv sync
```

`uv sync` creates a local `.venv` and installs `mcp`, `lxml`, and the dev/test
dependencies.

Verify it runs:

```bash
uv run seamly2d-mcp --help
uv run pytest
```

## Connect Claude Desktop

Claude Desktop reads its MCP server list from `claude_desktop_config.json`:

| Platform | Path |
| --- | --- |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

If the file doesn't exist yet, create it. Add (or merge into) an
`mcpServers` entry, replacing the path with this project's absolute path:

```json
{
  "mcpServers": {
    "seamly2d": {
      "command": "uv",
      "args": [
        "--directory",
        "E:/new begin/seamly2d MCP",
        "run",
        "seamly2d-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop after editing the config. Seamly2D itself doesn't need
to be running -- every tool here either edits pattern/measurement files
directly or shells out to `seamly2d.exe` for a one-off headless export (see
[PROJECT_PLAN.md](../PROJECT_PLAN.md)).

## Remote / ChatGPT (Streamable HTTP transport)

The server can also run over HTTP instead of stdio, using the MCP SDK's
built-in Streamable HTTP transport (verified with a real JSON-RPC
initialize/tools-list handshake over curl, not just "the port opens"):

```bash
uv run seamly2d-mcp --transport http --host 127.0.0.1 --port 8000
```

This serves the MCP endpoint at `http://127.0.0.1:8000/mcp`. To connect
ChatGPT (or any other remote MCP client) to it, the endpoint needs to be
reachable over HTTPS from wherever that client runs -- for a machine behind
NAT/a home network, that means a tunnel (e.g. `ngrok http 8000` or
Cloudflare Tunnel) or an actual public deployment; `127.0.0.1` by itself is
only reachable from this machine. ChatGPT's own connector setup UI is where
you'd register the resulting HTTPS URL -- that part is on the ChatGPT side
and outside this project.

Claude Desktop should keep using the stdio transport (the default, no flags
needed) shown above -- there's no reason to add the network hop locally.
