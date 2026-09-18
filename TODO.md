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
  metadata + increments + notes + geometry so far — see the addon's own
  RIBBEN.md TODO)

## Milestone 7 — Draft new geometry from scratch (file-based)
The one deferred item from Milestone 2 ("point/piece-level geometry editing")
starts here: writing real `<point>`/`<line>` elements into a `.sm2d`'s
`<draftBlock><calculation>`, grounded in the schema Seamly2D itself ships
(`src/libs/ifc/schema/pattern/*.xsd`) and in real sample files rather than
guessed. Deliberately covers a handful of the ~40 point types Seamly2D
supports (see `src/libs/vtools/tools/` in the Seamly2D source for the rest)
instead of all of them at once.
- [x] `operations/xml_geometry.py`: `create_pattern`, `list_points`,
  `add_point_single` (anchor point, no dependencies), `add_point_end_line`
  (length+angle from an existing point), `add_point_along_line` (length
  along an existing line), `add_line` (visual connector)
- [x] Global id allocation (`max(any id in the doc) + 1`) — confirmed
  empirically that points/lines/arcs/splines share one id counter, not
  separate ones per element type
- [x] Name validation (schema's `shortName` rules) and duplicate-name
  rejection; referenced points/draft blocks must already exist
- [x] `create_pattern`/`add_point_single`/`add_point_end_line`/
  `add_point_along_line`/`add_line`/`list_points` tools in `server.py`
- [x] 17 tests (id allocation, name-by-id vs name-by-name references,
  invalid names, duplicate names, unknown references, backup-before-write)
- [x] Real end-to-end verification, twice over: (1) a pattern drafted
  purely through the MCP tool functions was checked with `validate_pattern`
  against the actual **officially-installed** `seamly2d.exe` (not the
  Ribben dev build) and loaded cleanly; (2) opened it directly in that same
  real Seamly2D and confirmed visually — the derived point (`alongLine`)
  landed exactly on the expected line, confirming the geometry math and XML
  structure are correct, not just "doesn't crash on load"
- [ ] Curves/arcs (`<spline>`/`<arc>` elements — more attribute variants,
  not yet grounded the way the point/line types above are)
- [ ] Piece outlines (`<pieces>` — needed before `render_pattern` can export
  anything from a from-scratch draft; a separate tool surface mirroring
  Seamly2D's own Draft → Piece mode split)
- [x] A live (Ribben-addon-backed) version of geometry creation, so new
  points appear in a running Seamly2D immediately the way live_update_increment
  does — see Milestone 8.

## Milestone 8 — Draft new geometry from scratch, live
The inspiration for this whole live-connection effort: FreeCAD's own MCP
addon lets you prompt Claude and watch shapes appear in the open FreeCAD
window immediately, because FreeCAD has a live Python scripting console.
Seamly2D doesn't -- but its own Undo/Redo already does a full rebuild of the
visible scene from the pattern's live XML document on every use
(`MainWindow::fullParseFile()` / `doc->Parse(Document::FullParse)`), and
that turned out to be reusable: insert a new `<point>`/`<line>` into the
already-open document, trigger that same rebuild, and the new geometry
appears on screen exactly like an undone/redone one would.
- [x] `listPoints`/`addPointSingle`/`addPointEndLine`/`addPointAlongLine`/
  `addLine` added to the addon's `RibbenHost` interface and implemented in
  `MainWindow` (see `E:\seamly2d-ribben`'s `ribbenmainwindowhost.cpp`),
  grounded in the exact same schema/attribute constants (`ifcdef.h`,
  `VContainer::getNextId()`) as the file-based version, kept in sync
  deliberately (same point types, same attribute names)
- [x] Rollback on failure (`ribbenReparseOrRollback`): calling
  `doc->Parse(Document::FullParse)` directly rather than through the
  existing `fullParseFile()` slot, because that slot *swallows*
  `VExceptionObjectError`/`VExceptionConversionError` internally (logs them,
  disables the GUI) instead of propagating them -- which would leave a bad
  live_add_point_* call both invisible to the caller and the GUI silently
  disabled. On failure, the bad element is removed and the document
  re-parsed again before the error is reported.
- [x] `live_list_points`/`live_add_point_single`/`live_add_point_end_line`/
  `live_add_point_along_line`/`live_add_line` tools in `server.py`
- [x] 5 new tests against the fake TCP server. Full suite: 63/63 passing.
- [x] Verified against the real running app, twice: (1) raw socket calls
  confirmed the new points/lines were created without error; (2) a
  screenshot of the **already-open, unmodified** window, taken immediately
  after the tool calls with no save/reopen/refresh, showed the new points
  and their connecting line rendered on screen -- the actual "prompt Claude,
  watch it happen live" experience that motivated this whole project.
- [ ] Live curves/arcs, live piece outlines -- same gap as Milestone 7's
  file-based version, now doubled (needs both the file-format work and the
  live C++ wiring)

---
**Check-in convention:** after finishing an item, mark it `[x]` here and say so
in chat before moving to the next one — no silent batch-completing a whole
milestone without a check-in.
