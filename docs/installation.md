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
initialize/tools-list handshake over curl, not just "the port opens"),
behind a **required bearer token** -- every request without a matching
`Authorization: Bearer <token>` header gets a 401, verified with real HTTP
requests (correct/missing/wrong token) in `tests/test_http_auth.py`:

```bash
uv run seamly2d-mcp --transport http --host 127.0.0.1 --port 8000 --http-token <a-secret-you-choose>
```

Omit `--http-token` and the server generates a random one and prints it once
at startup instead of refusing to start -- convenient for a quick local
test, but pass your own for anything you'll leave running.

**Why the token is required, not optional:** once this endpoint sits behind
a public tunnel (below), the tunnel URL is not itself a secret -- it can
leak through browser history, logs, or the tunnel provider's own status
pages. Every tool here is reachable through this transport, including the
ones that write pattern files anywhere on disk, shell out to `seamly2d.exe`,
and drive a live, open Seamly2D via the Ribben addon. Without the token,
anyone who finds the URL could do all of that.

This serves the MCP endpoint at `http://127.0.0.1:8000/mcp`. To connect
ChatGPT (or any other remote MCP client) to it, the endpoint needs to be
reachable over HTTPS from wherever that client runs -- for a machine behind
NAT/a home network, that means a tunnel (e.g. `ngrok http 8000` or
Cloudflare Tunnel) or an actual public deployment; `127.0.0.1` by itself is
only reachable from this machine. Keep the live addon's own advantages by
tunneling *from* this machine rather than redeploying the server elsewhere
-- the Ribben addon only ever accepts loopback connections, so the MCP
server has to stay on the same box as the running Seamly2D to reach it.

**A tunnel needs one more flag.** The transport has its own separate
DNS-rebinding defense (from the MCP SDK) that only accepts `127.0.0.1`/
`localhost` as a request's `Host` header by default -- every request
arriving through a tunnel gets `421 Misdirected Request` / "Invalid Host
header" until you allowlist the tunnel's hostname:

```bash
uv run seamly2d-mcp --transport http --host 127.0.0.1 --port 8000 \
  --http-token <a-secret-you-choose> \
  --public-host my-tunnel-name.trycloudflare.com
```

`--public-host` can be repeated if the tunnel's hostname changes between
runs (a `cloudflared tunnel --url http://localhost:8000` "quick tunnel"
gets a new random hostname every time it starts, unless you set up a named
tunnel). Verified against a real `cloudflared` quick tunnel end-to-end: a
real MCP `initialize` handshake over the public HTTPS URL, with the correct
bearer token and hostname both required.

As of ChatGPT's current Developer Mode (Plus/Pro plans, Settings > Security
and login > Developer mode > Plugins > connect your server URL), it also
needs a server URL, the same as any other remote MCP client -- there's no
separate "local" path even from the ChatGPT desktop app. Register the
tunnel's HTTPS URL there, and provide the bearer token as that connector's
auth. That part is on ChatGPT's side and outside this project, and its
exact steps are subject to change -- see OpenAI's own docs for the current
UI.

Claude Desktop should keep using the stdio transport (the default, no flags
needed) shown above -- there's no reason to add the network hop, or the
token, locally.
