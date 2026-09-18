# Seamly2D MCP

Model Context Protocol server that connects [Seamly2D](https://seamly.io/) pattern
files to Claude — read and write body measurements, read and adjust a pattern's
parametric increments, and headlessly render a pattern to SVG/PDF/PNG/DXF and
more, all through natural-language requests.

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for architecture and why it's built this
way (no live scripting API in Seamly2D, so this works by editing `.sm2d`/`.smis`/
`.smms` XML directly and shelling out to `seamly2d.exe`'s own headless export
mode), and [TODO.md](TODO.md) for build progress.

## Requirements

- [Seamly2D](https://seamly.io/) installed (tested against `seamly2d.exe` v0.6.8).
- Python 3.12+ and [uv](https://docs.astral.sh/uv/).

## Quick start

Clone or copy this project, then from its directory:

```bash
uv sync
uv run seamly2d-mcp
```

### Connect Claude Desktop

Add this to Claude Desktop's `claude_desktop_config.json`, replacing the path
with this project's absolute path:

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

Restart Claude Desktop after editing the config. See
[docs/installation.md](docs/installation.md) for where that file lives and
[docs/configuration.md](docs/configuration.md) for the `--seamly2d-exe` flag
(only needed if Seamly2D isn't in one of the default install locations).

## Tools

See [docs/tools.md](docs/tools.md) for the full list with arguments and
examples. Summary:

| Tool | Purpose |
| --- | --- |
| `list_measurement_files` | Find `.smis`/`.smms` files under a folder. |
| `read_measurements` | Parse a measurement file into structured data. |
| `create_measurement_file` | Write a new individual (`.smis`) measurement file. |
| `update_measurements` | Patch specific measurement values in place. |
| `read_pattern` | Parse a pattern's metadata, increments, and piece names. |
| `list_increments` | List a pattern's named parametric formulas. |
| `update_increment` | Edit one increment's formula in place. |
| `set_pattern_notes` | Set a pattern's notes text. |
| `create_pattern` / `add_point_single` / `add_point_end_line` / `add_point_along_line` / `add_line` / `list_points` | Draft new geometry from scratch into a `.sm2d` file — see [Drafting geometry](#drafting-geometry-from-scratch) below. |
| `render_pattern` | Headlessly export a pattern's layout (SVG/PDF/PNG/DXF/...). |
| `validate_pattern` | Silently load a pattern to check it rebuilds cleanly. |
| `validate_measurements` | Silently load a measurement file (via SeamlyMe) to check it parses cleanly. |
| `ping` | Health check. |
| `live_ping` / `live_status` / `live_read_pattern` / `live_list_increments` / `live_update_increment` / `live_set_pattern_notes` | Same as the tools above, but live against a *running* Seamly2D via its Ribben addon instead of a file on disk — see [Live connection](#live-connection-ribben-addon) below. |

All file-mutating tools (`update_measurements`, `update_increment`,
`set_pattern_notes`) back up the original file to `<path>.bak` before writing.

## Drafting geometry from scratch

`create_pattern` + `add_point_single`/`add_point_end_line`/`add_point_along_line`/
`add_line` write real draft geometry (points/lines) into a `.sm2d` file, so
a pattern can be built from nothing instead of only having an existing
one's increments tweaked. Grounded directly in Seamly2D's own schema
(`src/libs/ifc/schema/pattern/*.xsd` in the Seamly2D source) and verified
against the real, officially-installed `seamly2d.exe` -- a pattern drafted
purely through these tools loads and validates cleanly, and its geometry
renders correctly when opened. Covers the handful of point types most
drafts are built from, not the full ~40 Seamly2D's toolbox has; see
[docs/tools.md](docs/tools.md#drafting-geometry-from-scratch) for the
details and TODO.md for what's still ahead (curves, arcs, piece outlines).

## Live connection (Ribben addon)

The `live_*` tools talk to a *running* Seamly2D instance instead of a file on
disk, over a small embedded JSON-RPC server called the Ribben addon (a local
fork of Seamly2D at `E:\seamly2d-ribben` — see its own `RIBBEN.md` for how
that side works). Enable it in that Seamly2D build via **Utilities > Enable
Ribben Addon (Live MCP Server)**, then the `live_*` tools "just work" — the
connection's port and token are auto-discovered from Seamly2D's own settings
file, no configuration needed on this side. The advantage over the file-based
tools: edits (e.g. `live_update_increment`) recompute the pattern's geometry
immediately, visible in the open window right away, instead of needing the
file reopened.

## Status

Core tool surface (measurements, pattern increments, headless render) is built,
tested, and verified live against Claude Desktop — see [TODO.md](TODO.md).
A Streamable HTTP transport (`--transport http`) is available for ChatGPT/remote
clients — see [docs/installation.md](docs/installation.md#remote--chatgpt-streamable-http-transport).
A live connection into a running Seamly2D (via the Ribben addon, see above) is
also available for pattern metadata/increments/notes.
Drafting new geometry from scratch (points/lines) is now available -- see
above -- covering a subset of Seamly2D's point types. Not yet done: curves/
arcs, piece outlines (so render_pattern has something to export), a live
(addon-backed) version of geometry creation, and live render/measurement
tools (the addon doesn't expose those yet).

## Development

```bash
uv sync
uv run pytest
uv run seamly2d-mcp
```

Tests run real assertions against bundled Seamly2D sample files under
`tests/fixtures/`, plus a few that shell out to the real installed
`seamly2d.exe` (skipped automatically if it isn't found on the machine).
