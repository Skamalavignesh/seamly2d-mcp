# Seamly2D MCP — Build Checklist

Tracks progress against [PROJECT_PLAN.md](PROJECT_PLAN.md). Check items off as
they're completed; each is small enough to verify before moving on.

## Milestone 0 — Scaffold
- [x] `pyproject.toml` + `.python-version` + `uv` env (mirrors freecad-mcp packaging)
- [x] Package skeleton: `src/seamly2d_mcp/{__init__.py, server.py, server_state.py}`
- [x] `operations/` package: empty `xml_measurements.py`, `xml_pattern.py`, `cli_bridge.py`
- [x] `server.py` boots a `FastMCP("Seamly2DMCP")` with one trivial `ping` tool
- [x] Confirm the server connects from Claude Desktop — config wired up in Milestone 4; final live check is the same step as Milestone 4's end-to-end test

## Milestone 1 — Measurements (`.smis` / `.smms`)
- [x] `xml_measurements.py`: parse a `.smis` file into structured JSON (personal + body-measurements) — also handles `.smms` multisize
- [x] Unit test against bundled sample `male_shirt.smis` (+ `gost_man_ru.smms`)
- [x] `read_measurements(path)` tool wired into `server.py`
- [x] `create_measurement_file(path, personal, measurements)` — write a new `.smis`
- [x] `update_measurements(path, changes)` — patch specific `<m>` values, preserve everything else
- [x] `list_measurement_files(dir)` tool
- [x] Tests for create/update round-trip (write then re-read, values match)

## Milestone 2 — Patterns (`.sm2d`) read + increment edits
- [x] `xml_pattern.py`: parse a `.sm2d` — description, unit, linked measurement file, increments, notes
- [x] Unit test against bundled sample `male_shirt.sm2d`
- [x] `read_pattern(path)` tool
- [x] `list_increments(path)` tool
- [x] `update_increment(path, name, formula)` — edit one increment's formula, preserve rest of file byte-for-byte otherwise
- [x] `set_pattern_notes(path, text)` tool
- [x] Backup-before-write safeguard (copy original before any file mutation) — also retrofitted onto Milestone 1's `update_measurements`

## Milestone 3 — Headless render
- [x] `cli_bridge.py`: subprocess wrapper around `seamly2d.exe` (mirrors `headless.py`'s timeout + exit-code handling pattern)
- [x] Confirm exact CLI flags against the real installed `seamly2d.exe` (ran `--help` live — matches wiki, v0.6.8/build 2026.9.14)
- [x] `render_pattern(path, format, dest, page, ...)` tool — returns exported file, and PNG as `ImageContent` when possible
- [x] Manual test: render `male_shirt.sm2d` to SVG and PNG via real `seamly2d.exe`, confirmed output files + inline PNG preview
- [x] `validate_pattern(path)` — uses Seamly2D's own `-t`/test-mode silent load+quit as the sanity check

## Milestone 4 — Polish
- [x] Error handling for malformed/unexpected XML (clear messages, no silent corruption) — also fixed an XPath-injection-shaped bug in `update_increment` name lookup, added unit/empty-input/path-separator validation; 5 new regression tests (27 total)
- [x] `@mcp.prompt()` — pattern-drafting strategy prompt (order of operations for the model)
- [x] `README.md` — install steps + how to point Claude Desktop at this server
- [x] `docs/{installation,configuration,tools}.md`
- [x] Wired into `claude_desktop_config.json` (`C:\Users\91959\AppData\Roaming\claude\claude_desktop_config.json`) alongside the existing `freecad` entry; launch command verified to start cleanly
- [x] End-to-end manual test from Claude Desktop — live-called `ping`, `read_pattern`, and `render_pattern` through the real MCP connection; rendered `male_shirt.sm2d` to PNG and got actual pattern-piece images back inline. Found and documented two environment quirks (Program Files write permissions; this client requires optional args passed as explicit `null`) in docs/configuration.md#known-client-quirks — neither is a server bug (verified our JSON Schema is spec-correct)

## Milestone 5 — Stretch (not blocking v1)
- [x] ChatGPT-compatible HTTP transport — `mcp==2.2.0`'s `MCPServer` has Streamable HTTP built in (`mcp.run(transport="streamable-http", ...)`), no separate OpenAPI wrapper needed. Added `--transport {stdio,http}` + `--host`/`--port` flags. Verified with a real JSON-RPC initialize -> initialized -> tools/list handshake over curl (not just "port opens"), then confirmed clean shutdown. Actually reaching it from ChatGPT still needs the endpoint exposed over public HTTPS (tunnel or deployment) — that part is outside this project, documented in docs/installation.md
- [ ] Point/piece-level geometry edit tools (needs deeper `.sm2d` schema work)
- [x] `seamlyme.exe` CLI investigation — ran `--help` live: no export/format flags (measurement-editor GUI only), but it does have a `--test` silent-load mode symmetric to `seamly2d.exe -t`. Added `validate_measurements` tool + `detect_seamlyme_exe`/`--seamlyme-exe` flag on top of it. Verified against real `.smis` and `.smms` fixtures. 32/32 tests passing.

## Milestone 6 — Live connection via the Ribben addon
The file-based limitation from PROJECT_PLAN.md ("no live scripting API") is no
longer entirely true: a separate fork of Seamly2D
(`E:\seamly2d-ribben`, https://github.com/FashionFreedom/Seamly2D upstream +
a local addon — see its `RIBBEN.md`) adds an embedded, opt-in JSON-RPC server
(`Utilities > Enable Ribben Addon`) into the running app itself. This
milestone wires this server up to that addon instead of/alongside file edits.
- [x] `operations/ribben_client.py` — newline-delimited JSON-RPC 2.0 client
  over a loopback TCP socket, with connection info (port/token)
  auto-discovered from Seamly2D's own settings file
  (`%APPDATA%/Seamly2DTeam/Seamly2D.ini`) so nothing needs to be copied
  around by hand for the common same-machine case
- [x] `live_ping`, `live_status`, `live_read_pattern`, `live_list_increments`,
  `live_update_increment`, `live_set_pattern_notes` tools in `server.py`,
  each with optional host/port/token overrides
- [x] `--ribben-host`/`--ribben-port`/`--ribben-token` CLI flags
- [x] 9 tests against a real fake TCP server (real wire protocol, not mocked
  socket calls) — auth failure, server-side error, unreachable port, and ini
  auto-discovery all covered
- [x] Manual end-to-end verification against the real running `seamly2d.exe`
  with the addon enabled: live ping/status/list_increments/update_increment
  all confirmed working through the actual MCP tool functions, not just the
  client module
- [ ] `live_render`/live measurement tools (the addon only exposes pattern
  metadata + increments + notes so far — see the addon's own RIBBEN.md TODO)

---
**Check-in convention:** after finishing an item, mark it `[x]` here and say so
in chat before moving to the next one — no silent batch-completing a whole
milestone without a check-in.
