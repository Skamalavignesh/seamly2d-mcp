# Seamly2D MCP — Project Plan

## 1. Goal

Build a Model Context Protocol (MCP) server that lets Claude (and, where possible,
ChatGPT) drive **Seamly2D** — the open-source pattern-drafting app installed at
`C:\Program Files (x86)\Seamly2D`. An LLM should be able to: inspect/create body
measurement files, inspect and tweak pattern files (increments, formulas, notes),
and render a pattern to SVG/PDF/PNG/DXF for the user to view — all through
natural-language requests, without the user hand-editing XML or clicking through
the Seamly2D GUI.

## 2. What we confirmed about Seamly2D (grounds this plan)

- **No live scripting API / no Python bindings.** Seamly2D is a Qt6 C++ desktop
  app (`seamly2d.exe` = pattern editor, `seamlyme.exe` = measurement editor).
  There is no macro console like FreeCAD's. Source: [Seamly2D API issue #178](https://github.com/FashionFreedom/Seamly2D/issues/178) (still open/requested, not implemented).
- **Two integration surfaces exist instead:**
  1. **File format** — pattern (`.sm2d`) and measurement (`.smis` individual /
     `.smms` multisize) files are plain, human-editable **XML**. Verified against
     the bundled samples in `Seamly2D\samples\`. This is the primary integration
     point: an MCP tool can read/write these files directly with no app running.
  2. **Headless CLI export** — `seamly2d.exe [options] <file>` supports batch
     export to 34+ formats (SVG, PDF, PNG, DXF variants, OBJ, EPS, PS) with page
     size, margins, rotation, and detail-filtering flags, with no GUI interaction
     needed. Source: [Seamly wiki – Command Line](https://wiki.seamly.io/wiki/Command_Line).
     This is how the MCP will produce a visual result (e.g. a PNG/PDF) for a
     pattern after editing it.
- **File format is not officially schema'd** — there's community demand for this
  too ([forum thread](https://forum.seamly.io/t/looking-for-official-documentation-or-xml-schema-for-sm2d-files/15403)),
  so we'll reverse-engineer the schema we need from real sample files as we go,
  rather than trying to cover 100% of the format up front.

**Implication:** this MCP is fundamentally a *file-and-process* integration
(read/write XML, shell out for rendering), not a live in-app RPC integration.
That's simpler to build and more robust (no dependency on Seamly2D's internal
IPC), but it means edits only show up in the GUI when the user re-opens the file.

## 3. Architecture

```
Claude / ChatGPT
      │  (MCP protocol, stdio or HTTP)
      ▼
Seamly2D MCP Server  (Python, FastMCP)
      │
      ├─ XML layer  → read/write .sm2d, .smis, .smms directly (lxml)
      ├─ CLI layer  → subprocess calls to seamly2d.exe for headless export
      └─ (stretch)  → seamlyme.exe for measurement-side operations, if it has
                       an equivalent CLI (unconfirmed — check when we get there)
```

- **Language/SDK:** Python + the official `mcp` Python SDK (FastMCP). Reasoning:
  XML handling and subprocess orchestration are both easy in Python, and it
  matches the pattern already used by the `freecad-mcp` project sitting next to
  this one in `E:\new begin`, so conventions can be reused.
- **Transport:** start with **stdio** (what Claude Desktop expects for local
  MCP servers — simplest, zero networking). Add a **Streamable HTTP** mode later
  if we need remote/ChatGPT access.
- **ChatGPT caveat:** ChatGPT does not run local stdio MCP servers the way
  Claude Desktop does. Practical path is either (a) OpenAI's newer MCP connector
  support for Custom GPTs/Apps, which needs the server exposed over HTTP(S), or
  (b) an OpenAPI-Actions shim in front of the same tool functions. We'll design
  the tool functions transport-agnostic so either wrapper is a thin addition —
  but full ChatGPT parity is a **phase-3, not phase-1** goal.

## 4. Proposed tools (MCP tool surface)

**Phase 1 — Measurements (read/write, low risk, high value)**
- `list_measurement_files(dir)` — find `.smis`/`.smms` files
- `read_measurements(path)` — parse a `.smis`/`.smms` into structured JSON
- `create_measurement_file(path, personal, measurements)` — write a new `.smis`
- `update_measurements(path, changes)` — patch specific `<m>` values

**Phase 2 — Patterns (read + safe edits)**
- `read_pattern(path)` — parse a `.sm2d`: description, unit, linked measurement
  file, increments (name/formula/description), notes
- `list_increments(path)` / `update_increment(path, name, formula)` — the
  parametric "variables" that drive the whole draft (safest lever for an LLM to
  pull — no geometry math required, just formula edits)
- `set_pattern_notes(path, text)`

**Phase 3 — Render / export (headless CLI)**
- `render_pattern(path, format, dest, page, ...)` — shells out to `seamly2d.exe`
  to export SVG/PDF/PNG so the result can be shown to the user
- `validate_pattern(path)` — round-trip open+export as a sanity/lint check

**Phase 4 — stretch**
- Point/piece-level geometry edits (much higher complexity — real parametric
  CAD semantics; only attempt once phases 1–3 are solid and we understand more
  of the `.sm2d` point/piece schema from real files)
- ChatGPT-facing HTTP/OpenAPI wrapper

## 5. Repo layout (proposed)

```
seamly2d MCP/
  PROJECT_PLAN.md
  pyproject.toml
  src/seamly2d_mcp/
    server.py           # FastMCP entrypoint, tool registration
    xml_pattern.py       # .sm2d read/write helpers
    xml_measurements.py  # .smis/.smms read/write helpers
    cli_bridge.py         # subprocess wrapper around seamly2d.exe
    schema/               # notes/examples on the XML shape as we learn it
  tests/
    fixtures/             # copies of the bundled sample files
    test_xml_pattern.py
    test_xml_measurements.py
  README.md               # setup + how to point Claude Desktop at this server
```

## 6. Milestones

1. **Scaffold** — Python package, FastMCP server that boots and exposes a
   trivial `ping` tool; confirm it connects from Claude Desktop.
2. **Measurements read/write** — phase 1 tools, tested against the bundled
   sample `.smis` files.
3. **Pattern read + increment edits** — phase 2 tools, tested against bundled
   sample `.sm2d` files (start with `male_shirt.sm2d`, simplest sample).
4. **Headless render** — phase 3, produce a PNG/SVG from a pattern + measurement
   pair and hand it back to the user.
5. **Polish** — error handling for malformed XML, backup-before-write, README.
6. **(Stretch)** ChatGPT-compatible HTTP wrapper; deeper geometry tools.

## 7. Open decisions (flag if you want something different)

- Defaulting to **Python + FastMCP** and **stdio transport** for v1 — say the
  word if you'd rather do Node/TypeScript or start with HTTP instead.
- Defaulting to **file-based editing + CLI render**, not attempting to control a
  *running* Seamly2D window (no accessible API for that exists today).
- Treating **ChatGPT support as phase 3+**, since Claude Desktop's MCP support
  is native and ChatGPT's isn't a drop-in match.

## Sources

- [Seamly2D API issue #178 — API with SeamlyCloud](https://github.com/FashionFreedom/Seamly2D/issues/178)
- [Seamly wiki — API documentation](https://wiki.seamly.io/wiki/API_documentation)
- [Seamly wiki — Command Line](https://wiki.seamly.io/wiki/Command_Line)
- [Seamly forum — sm2d XML schema question](https://forum.seamly.io/t/looking-for-official-documentation-or-xml-schema-for-sm2d-files/15403)
- [FashionFreedom/Seamly2D on GitHub](https://github.com/FashionFreedom/Seamly2D)
