# Tools

[Back to README](../README.md) · [Installation](installation.md) · [Configuration](configuration.md)

None of these require Seamly2D to be running. `read_*`/`update_*`/`create_*`
tools edit XML files directly; `render_pattern`/`validate_pattern` launch
`seamly2d.exe` headlessly for one call and exit.

## Measurements

### `list_measurement_files`
List `.smis` (individual) and `.smms` (multisize) files under a directory, recursively.

### `read_measurements`
Parse a `.smis`/`.smms` file. Returns `kind`, `version`, `unit`, `pm_system`,
`notes`, and either:
- individual: `personal` (family_name/given_name/birth_date/gender/email) and
  `measurements: [{name, value}, ...]`
- multisize: `size_base`, `height_base`, and
  `measurements: [{name, base, size_increase, height_increase, description, full_name}, ...]`

### `create_measurement_file`
Write a new individual `.smis` file.
```json
{
  "path": "C:/patterns/measurements/alex.smis",
  "measurements": {"height": 170, "bust_circ": 90, "waist_circ": 75},
  "personal": {"given_name": "Alex", "gender": "female"}
}
```

### `update_measurements`
Patch specific `<m>` attributes in place; everything else in the file is left
untouched. Backs up to `<path>.bak` first.
```json
{
  "path": "C:/patterns/measurements/alex.smis",
  "changes": {"height": {"value": 172}, "waist_circ": {"value": 78}}
}
```
For a multisize file, `changes` values can set `base`/`size_increase`/
`height_increase`/`description`/`full_name` instead of `value`.

## Patterns

### `read_pattern`
Parse a `.sm2d` file's metadata and parametric layer -- version, unit,
description, notes, the linked measurement file path, the `increments` list
(`{name, formula, description}`), and `draft_blocks` (piece/section names).
Does not return point/line/curve geometry.

### `list_increments`
Just the increments list from `read_pattern`.

### `update_increment`
Change one increment's formula (and optionally description) in place. The
increment must already exist -- this never creates a new one. Backs up to
`<path>.bak` first.
```json
{
  "path": "C:/patterns/male_shirt.sm2d",
  "name": "#NecWidth",
  "formula": "neck_circ/6+1"
}
```
Changes only take effect in the Seamly2D GUI after the file is reopened there.

### `set_pattern_notes`
Replace a pattern's `<notes>` text. Backs up to `<path>.bak` first.

## Drafting geometry from scratch

A newer, separate capability from the metadata/increment tools above: these
create and extend actual draft geometry (points, lines, curves, and arcs) in
a `.sm2d` file, so a pattern can be drafted from nothing rather than only
having its existing increments tweaked. Covers the handful of point/curve
types most drafts are built from -- not the full ~40 types Seamly2D's
toolbox has (see `src/libs/vtools/tools/` in the Seamly2D source for the
rest). Every write backs up to `<path>.bak` first, same as the tools above.

Typical flow: `create_pattern` → `add_point_single` (at least once, as a
starting anchor) → a chain of `add_point_end_line`/`add_point_along_line`/
`add_line`/`add_spline`/`add_arc` → `add_piece` (needed before
`render_pattern` will export anything -- it refuses an empty scene) →
`validate_pattern` to catch a bad reference or formula early (this loads
the file in Seamly2D's own silent test mode, so it's checked against the
real app, not just against this server's idea of the schema).

### `create_pattern`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front"}
```
Writes a new file with one empty draft block. Does **not** back up an
existing file first -- meant for a path that doesn't exist yet.

### `list_points`
Points in one draft block, in creation order, with their raw attributes --
use this to find a point's name/id to reference in the tools below.

### `add_point_single`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front", "name": "A1", "x": 0, "y": 0}
```
An anchor point at explicit coordinates. The only point type with no
dependencies -- every draft needs at least one.

### `add_point_end_line`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front",
 "name": "A2", "base_point": "A1", "length": "20", "angle": "0"}
```
A point at a given length and angle from an existing point (by name or id)
-- most manual construction steps ("go up 3cm, then right 2cm") are a chain
of these. `length`/`angle` accept plain numbers or Seamly2D formulas
(increment names, expressions).

### `add_point_along_line`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front",
 "name": "A4", "first_point": "A1", "second_point": "A3", "length": "10"}
```
A point at a given length along the line from `first_point` toward
`second_point`.

### `add_line`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front",
 "first_point": "A1", "second_point": "A2"}
```
A plain visual line connecting two existing points.

### `add_spline`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front",
 "first_point": "A1", "second_point": "A2",
 "angle1": "45", "length1": "3", "angle2": "135", "length2": "3"}
```
A cubic-Bezier curve between two existing points (Seamly2D's "Curve" tool).
Each end has its own tangent control handle, expressed the same
angle+length way `add_point_end_line` expresses a new point, rather than as
raw control-point coordinates -- `angle1`/`length1` control the tangent at
`first_point`, `angle2`/`length2` at `second_point`.

### `add_arc`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front",
 "center_point": "A1", "radius": "5", "angle1": "0", "angle2": "180"}
```
A circular arc around an existing center point (Seamly2D's "Arc" tool),
sweeping from `angle1` to `angle2` in degrees (0 = along +x,
counterclockwise).

### `list_pieces`
Pieces in one draft block, with their raw attributes (id, name,
seamAllowance, width, ...) and their outline as a list of `{type, idObject,
reverse}` node dicts, in outline order.

### `add_piece`
```json
{"path": "C:/patterns/new_shirt.sm2d", "draft_block_name": "Front",
 "name": "Front Panel",
 "outline": [
   {"point": "A"}, {"point": "B"},
   {"spline": "5", "reverse": false},
   {"point": "D"}
 ]}
```
Builds a seam-allowance outline (Seamly2D's "New Piece" tool) from existing
points/curves. `outline` is an ordered, closed sequence of nodes around the
piece boundary -- consecutive point nodes imply a straight edge; a
`{"spline": ...}`/`{"arc": ...}` node replaces the straight edge with that
curve instead (reference the id `add_spline`/`add_arc` returned; `reverse`
walks it tail-to-head). Internally, Seamly2D can't have a piece reference
`<calculation>` geometry directly -- each referenced point/curve first gets
a thin wrapper in the draft block's `<modeling>` section, which this tool
creates automatically, so callers just reference the same names/ids used
with `add_point_*`/`add_spline`/`add_arc`. At least one piece is required
before `render_pattern` can export a from-scratch draft.

## Live (Ribben addon)

These require a running Seamly2D built from the `E:\seamly2d-ribben` fork
with **Utilities > Enable Ribben Addon (Live MCP Server)** checked -- see
that project's `RIBBEN.md`. Unlike everything else on this page, they act on
whatever pattern is actually open right now (including unsaved edits), not a
file path you pass in.

Connection info (host/port/token) is auto-discovered from Seamly2D's own
settings file (`%APPDATA%/Seamly2DTeam/Seamly2D.ini`) -- every tool below
also takes optional `host`/`port`/`token` arguments to override that, e.g.
for a Seamly2D instance running on another machine (the addon binds to
loopback only by default, so this needs the addon side reconfigured too).

### `live_ping` / `live_status`
Health check, and file_path/modified/unit/piece_count for whatever's open.

### `live_read_pattern` / `live_list_increments`
Live equivalents of `read_pattern`/`list_increments`. `live_list_increments`
also includes each increment's currently-computed `value` and whether its
formula is `valid`, which the file-based version can't (it doesn't evaluate
formulas).

### `live_update_increment`
```json
{"name": "#NecWidth", "formula": "neck_circ/6+1"}
```
Same idea as `update_increment`, but the pattern's geometry is recomputed
immediately -- visible in the Seamly2D window right away, no reopening the
file. An invalid formula doesn't raise an error; it comes back with
`"valid": false, "value": 0` so one bad edit doesn't take down the rest of
the pattern.

### `live_set_pattern_notes`
Live equivalent of `set_pattern_notes`.

### `live_list_points` / `live_add_point_single` / `live_add_point_end_line` / `live_add_point_along_line` / `live_add_line` / `live_add_spline` / `live_add_arc` / `live_list_pieces` / `live_add_piece`
Live equivalents of the [drafting geometry](#drafting-geometry-from-scratch)
tools above, with the same arguments -- but the new point/line/curve/piece
**appears in the open Seamly2D window immediately**, the same way an
Undo/Redo does, instead of only showing up after the file is reopened.
This is the one capability the file-based tools genuinely can't match:
watch a pattern get drafted live while it happens, prompt by prompt.
```json
{"draft_block_name": "Front", "name": "A2", "base_point": "A1", "length": "20", "angle": "0"}
```
An invalid length/angle formula, or a piece outline with a bad reference,
doesn't leave the pattern half-broken: the failed insert (or, for
`live_add_piece`, every element it inserted -- each promoted `<modeling>`
wrapper plus the piece itself) is rolled back and the document re-parsed
again before the error is returned.

## Render / validate

### `render_pattern`
Headlessly export a pattern's layout via `seamly2d.exe`'s `-b` (basename)
export mode.

| Arg | Notes |
| --- | --- |
| `path` | The `.sm2d` file. |
| `dest_dir` | Created if missing. |
| `basename` | Plain filename, no path separators; Seamly2D appends a sheet number and extension. |
| `format` | See the table below (default `"svg"`). |
| `mfile` | Override the pattern's own linked measurement file. |
| `pageformat` | 0=A0, 1=A1, 2=A2, 3=A3, 4=A4, 5=Letter, 6=Legal, 7=Tabloid, 8=ANSI C, 9=ANSI D, 10=ANSI E, 11-15=paper rolls. |
| `rotate` | Degrees, one of Seamly2D's predefined values (0,1,2,3,4,5,6,8,9,10,12,15,18,20,24,30,36,40,45,60,72,90,180). |
| `gsize` / `gheight` | Size/height in cm, only for a pattern opened with multisize measurements. |
| `export_only_details` | Export pieces as positioned in Details mode instead of laid out on sheets. |
| `include_preview` | When `format="png"`, also return the image(s) inline (default `true`). |

`format` values -> Seamly2D's `-f` number:

| format | # | format | # | format | # |
| --- | --- | --- | --- | --- | --- |
| svg | 0 | ppm | 6 | dxf_2000 | 14 |
| pdf | 1 | obj | 7 | dxf_2004 | 15 |
| pdf_tiled | 2 | ps | 8 | dxf_2007 | 16 |
| png | 3 | eps | 9 | dxf_2010 | 17 |
| jpg | 4 | dxf_r10 | 10 | dxf_2013 | 18 |
| bmp | 5 | dxf_r11_12 | 11 | dxf_r10_aama ... dxf_2013_aama | 19-27 |
| tif | 37 | dxf_r13 | 12 | | |
| | | dxf_r14 | 13 | | |

### `validate_pattern`
Load a pattern in Seamly2D's silent `-t` (test) mode: no GUI, nothing
exported, just reports whether the file parses and the draft rebuilds
without error. Run this after an edit and before `render_pattern`.

### `validate_measurements`
Load a `.smis`/`.smms` file in SeamlyMe's silent `--test` mode: no GUI, just
reports whether the file parses cleanly. Run this after
`create_measurement_file`/`update_measurements`. Optional `unit` argument
("cm"/"mm"/"inch") overrides the file's own unit for the check.

## `ping`
Health check; returns a confirmation string.

## Prompt: `pattern_drafting_strategy`
An `@mcp.prompt()` describing the recommended order of operations (find/create
measurements -> inspect pattern -> edit -> validate -> render -> tell the user
to reopen the file in the GUI).
