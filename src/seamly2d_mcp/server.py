import base64
import logging
import sys
from pathlib import Path
from typing import Any

try:
    # mcp 1.x
    from mcp.server.fastmcp import Context, FastMCP
except ImportError:
    # mcp 2.x moved mcp.server.fastmcp to mcp.server.mcpserver and renamed
    # FastMCP to MCPServer; the API surface used here is unchanged.
    from mcp.server.mcpserver import Context
    from mcp.server.mcpserver import MCPServer as FastMCP
from mcp.types import ImageContent, TextContent

from .operations import cli_bridge, ribben_client, xml_geometry, xml_measurements, xml_pattern
from .prompt_text import PATTERN_DRAFTING_STRATEGY
from .server_state import ServerState

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Seamly2DMCPserver")
logger.setLevel(logging.INFO)

state = ServerState()

mcp = FastMCP(
    "Seamly2DMCP",
    instructions="Seamly2D pattern-drafting integration through the Model Context Protocol",
)


@mcp.tool(structured_output=False)
def ping(ctx: Context) -> list[TextContent]:
    """Check that the Seamly2D MCP server is up and responding.

    Returns:
        A short confirmation message.
    """
    return [TextContent(type="text", text="seamly2d-mcp is alive")]


def _text(payload: Any) -> list[TextContent]:
    import json

    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2))]


@mcp.tool(structured_output=False)
def list_measurement_files(directory: str) -> list[TextContent]:
    """List Seamly2D measurement files (.smis individual / .smms multisize) under a directory.

    Args:
        directory: Folder to search recursively.

    Returns:
        A JSON list of file paths.
    """
    try:
        return _text(xml_measurements.list_measurement_files(directory))
    except xml_measurements.MeasurementFileError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def read_measurements(path: str) -> list[TextContent]:
    """Read a Seamly2D measurement file (.smis or .smms) into structured data.

    Args:
        path: Path to the .smis or .smms file.

    Returns:
        JSON with kind, version, unit, pm_system, notes, and the measurement
        list (plus personal info for individual files, or size/height base
        for multisize files).
    """
    try:
        return _text(xml_measurements.read_measurements(path))
    except xml_measurements.MeasurementFileError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def update_measurements(path: str, changes: dict[str, dict[str, Any]]) -> list[TextContent]:
    """Patch specific measurement values in an existing .smis/.smms file in place.

    Only the given attributes on the given measurements are changed; the rest
    of the file (formatting, comments, other measurements) is left untouched.

    Args:
        path: Path to the .smis or .smms file.
        changes: Maps measurement name -> {attribute: new_value}. For an
            individual (.smis) file the attribute is "value"
            (e.g. {"height": {"value": 180}}). For a multisize (.smms) file
            it can be base/size_increase/height_increase/description/full_name.

    Returns:
        A message confirming the update, listing any measurement names that
        were not found in the file and therefore not changed.

    Examples:
        ```json
        {
            "path": "C:/patterns/measurements/alex.smis",
            "changes": {"height": {"value": 180}, "waist_circ": {"value": 78}}
        }
        ```
    """
    try:
        missing = xml_measurements.update_measurements(path, changes)
    except xml_measurements.MeasurementFileError as e:
        return _text(f"Error: {e}")
    if missing:
        return _text(
            f"Updated {len(changes) - len(missing)} measurement(s). "
            f"Not found (unchanged): {', '.join(missing)}"
        )
    return _text(f"Updated {len(changes)} measurement(s) in {path}.")


@mcp.tool(structured_output=False)
def create_measurement_file(
    path: str,
    measurements: dict[str, Any],
    personal: dict[str, str] | None = None,
    unit: str = "cm",
    notes: str = "",
) -> list[TextContent]:
    """Create a new individual (.smis) measurement file.

    Args:
        path: Destination path for the new .smis file.
        measurements: Measurement name -> numeric value, e.g.
            {"height": 173, "bust_circ": 102, "waist_circ": 92}. Names must
            match Seamly2D's measurement system (see a sample .smis file for
            the standard names, e.g. height, neck_circ, bust_circ, waist_circ,
            hip_circ, shoulder_length).
        personal: Optional subset of family_name/given_name/birth_date/gender/email.
        unit: "cm", "mm", or "inch" (default "cm").
        notes: Optional free-text notes stored in the file.

    Returns:
        A confirmation message with the path written.

    Examples:
        ```json
        {
            "path": "C:/patterns/measurements/alex.smis",
            "measurements": {"height": 170, "bust_circ": 90, "waist_circ": 75},
            "personal": {"given_name": "Alex", "gender": "female"}
        }
        ```
    """
    try:
        xml_measurements.create_measurement_file(
            path, measurements, personal=personal, unit=unit, notes=notes
        )
    except xml_measurements.MeasurementFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Created measurement file at {path}.")


@mcp.tool(structured_output=False)
def read_pattern(path: str) -> list[TextContent]:
    """Read a Seamly2D pattern file's (.sm2d) metadata and parametric layer.

    This does not return the pattern's point/line/curve geometry (draftBlock
    contents) -- only version/unit/description/notes, the linked measurement
    file, the increments (named formulas that drive the draft), and the
    draft block names present, so you know what pieces exist.

    Args:
        path: Path to the .sm2d file.

    Returns:
        JSON with version, unit, description, notes, measurements_file,
        increments, and draft_blocks.
    """
    try:
        return _text(xml_pattern.read_pattern(path))
    except xml_pattern.PatternFileError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def list_increments(path: str) -> list[TextContent]:
    """List a pattern's increments (the named formulas driving the draft).

    Args:
        path: Path to the .sm2d file.

    Returns:
        JSON list of {name, formula, description}.
    """
    try:
        return _text(xml_pattern.list_increments(path))
    except xml_pattern.PatternFileError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def update_increment(
    path: str, name: str, formula: str, description: str | None = None
) -> list[TextContent]:
    """Update one increment's formula in a pattern file, in place.

    The increment must already exist (use list_increments to see names) --
    this never creates a new one. The original file is backed up to
    ``<path>.bak`` before the edit. Changes only take effect in the Seamly2D
    GUI after the file is reopened.

    Args:
        path: Path to the .sm2d file.
        name: Increment name, including its leading '#' if it has one
            (e.g. "#NecWidth").
        formula: New formula, using Seamly2D's expression syntax (references
            to measurement names or other increments, e.g. "neck_circ/6+1").
        description: Optional new description text for the increment.

    Returns:
        A confirmation message, or an error if the increment doesn't exist.

    Examples:
        ```json
        {
            "path": "C:/patterns/male_shirt.sm2d",
            "name": "#NecWidth",
            "formula": "neck_circ/6+1"
        }
        ```
    """
    try:
        xml_pattern.update_increment(path, name, formula, description)
    except xml_pattern.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Updated increment {name!r} in {path}. Reopen the file in Seamly2D to see the change.")


@mcp.tool(structured_output=False)
def set_pattern_notes(path: str, text: str) -> list[TextContent]:
    """Set a pattern file's <notes> text, in place.

    The original file is backed up to ``<path>.bak`` before the edit.

    Args:
        path: Path to the .sm2d file.
        text: New notes text (replaces any existing notes).

    Returns:
        A confirmation message.
    """
    try:
        xml_pattern.set_pattern_notes(path, text)
    except xml_pattern.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Updated notes in {path}.")


@mcp.tool(structured_output=False)
def create_pattern(
    path: str,
    draft_block_name: str,
    description: str = "",
    unit: str = "cm",
    measurements_file: str = "",
) -> list[TextContent]:
    """Create a brand-new pattern file with one empty draft block, to draft into from scratch.

    Follow up with add_point_single (needed at least once, as a starting
    anchor point) and then add_point_end_line/add_point_along_line/add_line
    to build up the draft. Use validate_pattern after each meaningful step
    to catch a broken reference or formula early.

    Args:
        path: Destination .sm2d path. Parent directories are created if missing.
        draft_block_name: Name of the initial draft block (e.g. "Front").
        description: Optional pattern description.
        unit: "cm", "mm", or "inch" (default "cm").
        measurements_file: Optional path to a .smis/.smms file -- only
            needed once a formula references a measurement name; plain
            coordinates and number formulas don't need one.

    Returns:
        A confirmation message.
    """
    try:
        xml_geometry.create_pattern(
            path, draft_block_name, description=description, unit=unit, measurements_file=measurements_file
        )
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Created {path} with draft block {draft_block_name!r}.")


@mcp.tool(structured_output=False)
def list_points(path: str, draft_block_name: str) -> list[TextContent]:
    """List the points in one draft block, in creation order.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Name of the draft block to list points from.

    Returns:
        JSON list of each point's raw attributes (id, name, type, and
        whichever type-specific attributes it has), so you can find a point
        by name to reference in add_point_*/add_line.
    """
    try:
        return _text(xml_geometry.list_points(path, draft_block_name))
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def add_point_single(
    path: str, draft_block_name: str, name: str, x: float, y: float
) -> list[TextContent]:
    """Add an anchor point at explicit (x, y) canvas coordinates.

    The only point type with no dependencies on other points -- every draft
    needs at least one of these to start from. Units follow the pattern's
    own unit (cm/mm/inch).

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the point to.
        name: Point name (letters/numbers/underscore, must not start with a
            digit or contain spaces/punctuation used by formulas).
        x: X coordinate.
        y: Y coordinate.

    Returns:
        A confirmation message including the new point's id.
    """
    try:
        new_id = xml_geometry.add_point_single(path, draft_block_name, name, x, y)
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added point {name!r} (id {new_id}) at ({x}, {y}).")


@mcp.tool(structured_output=False)
def add_point_end_line(
    path: str,
    draft_block_name: str,
    name: str,
    base_point: str,
    length: str,
    angle: str,
    line_type: str = "none",
) -> list[TextContent]:
    """Add a point at a given length and angle from an existing point.

    This is the most commonly needed relative point type -- most hand-drawn
    pattern construction steps ("go up 3cm, then right 2cm" etc.) are a
    chain of these.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the point to.
        name: New point's name.
        base_point: Name or id of the point to measure from (see list_points).
        length: Distance, as a Seamly2D formula -- a plain number, an
            increment name (e.g. "#Hemline"), or an expression.
        angle: Angle in degrees (0 = along +x, counterclockwise), as a
            plain number or formula.
        line_type: Draws a visible line from base_point to the new point if
            not "none" (e.g. "solidLine", "dashLine", "dotLine").

    Returns:
        A confirmation message including the new point's id.
    """
    try:
        new_id = xml_geometry.add_point_end_line(
            path, draft_block_name, name, base_point, length, angle, line_type=line_type
        )
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added point {name!r} (id {new_id}), {length} at {angle} degrees from {base_point!r}.")


@mcp.tool(structured_output=False)
def add_point_along_line(
    path: str, draft_block_name: str, name: str, first_point: str, second_point: str, length: str
) -> list[TextContent]:
    """Add a point at a given length along the line from first_point toward second_point.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the point to.
        name: New point's name.
        first_point: Name or id of the point to measure from.
        second_point: Name or id of the point defining the line's direction.
        length: Distance from first_point, as a Seamly2D formula. May
            exceed the first_point-second_point distance, extrapolating
            past second_point.

    Returns:
        A confirmation message including the new point's id.
    """
    try:
        new_id = xml_geometry.add_point_along_line(path, draft_block_name, name, first_point, second_point, length)
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added point {name!r} (id {new_id}), {length} along {first_point!r} -> {second_point!r}.")


@mcp.tool(structured_output=False)
def add_line(
    path: str, draft_block_name: str, first_point: str, second_point: str, line_type: str = "solidLine"
) -> list[TextContent]:
    """Draw a plain visual line connecting two existing points.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the line to.
        first_point: Name or id of one endpoint.
        second_point: Name or id of the other endpoint.
        line_type: e.g. "solidLine", "dashLine", "dotLine", "hair".

    Returns:
        A confirmation message including the new line's id.
    """
    try:
        new_id = xml_geometry.add_line(path, draft_block_name, first_point, second_point, line_type=line_type)
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added line (id {new_id}) from {first_point!r} to {second_point!r}.")


@mcp.tool(structured_output=False)
def add_spline(
    path: str,
    draft_block_name: str,
    first_point: str,
    second_point: str,
    angle1: str = "0",
    length1: str = "1",
    angle2: str = "0",
    length2: str = "1",
) -> list[TextContent]:
    """Draw a cubic-Bezier curve between two existing points (the "Curve" tool).

    Each end of the curve has its own tangent control handle, expressed the
    same "angle + length" way add_point_end_line expresses a new point,
    rather than as raw control-point coordinates.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the curve to.
        first_point: Name or id of the point the curve starts at (see list_points).
        second_point: Name or id of the point the curve ends at.
        angle1: Tangent direction at first_point, in degrees (0 = along +x,
            counterclockwise), as a plain number or formula.
        length1: Tangent handle length at first_point -- bigger pulls the
            curve further before it bends toward second_point.
        angle2: Tangent direction at second_point, same convention as angle1.
        length2: Tangent handle length at second_point.

    Returns:
        A confirmation message including the new curve's id.
    """
    try:
        new_id = xml_geometry.add_spline(
            path, draft_block_name, first_point, second_point,
            angle1=angle1, length1=length1, angle2=angle2, length2=length2,
        )
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added curve (id {new_id}) from {first_point!r} to {second_point!r}.")


@mcp.tool(structured_output=False)
def add_arc(
    path: str,
    draft_block_name: str,
    center_point: str,
    radius: str,
    angle1: str,
    angle2: str,
) -> list[TextContent]:
    """Draw a circular arc around an existing center point (the "Arc" tool).

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the arc to.
        center_point: Name or id of the existing point to center the arc on.
        radius: Arc radius, as a plain number or formula.
        angle1: Start angle in degrees (0 = along +x, counterclockwise), as
            a plain number or formula.
        angle2: End angle, same convention -- the arc sweeps from angle1 to
            angle2 in the direction of increasing angle.

    Returns:
        A confirmation message including the new arc's id.
    """
    try:
        new_id = xml_geometry.add_arc(path, draft_block_name, center_point, radius, angle1, angle2)
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added arc (id {new_id}) centered on {center_point!r}, radius {radius}.")


@mcp.tool(structured_output=False)
def list_pieces(path: str, draft_block_name: str) -> list[TextContent]:
    """List the pieces (seam-allowance outlines) in one draft block.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to list pieces from.

    Returns:
        JSON list of each piece's raw attributes (id, name, seamAllowance,
        width, ...) plus its outline as a list of {type, idObject, reverse}
        node dicts, in outline order.
    """
    try:
        return _text(xml_geometry.list_pieces(path, draft_block_name))
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def add_piece(
    path: str,
    draft_block_name: str,
    name: str,
    outline: list[dict[str, Any]],
    seam_allowance: bool = True,
    seam_allowance_width: str = "1",
) -> list[TextContent]:
    """Create a piece (seam-allowance outline) from existing draft geometry.

    An outline is an ordered, closed sequence of nodes around the piece
    boundary: consecutive point nodes imply a straight edge between them,
    and a curve node (spline/arc) replaces the straight edge with that
    curve instead. Needed before render_pattern can export anything from a
    from-scratch draft -- it refuses to export an empty scene.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the piece to.
        name: Piece name (e.g. "Front Panel") -- unlike point names, this
            has no character restrictions.
        outline: Ordered list of nodes around the piece boundary, each a
            dict with exactly one of:
              - {"point": ref} -- an existing point (name or id, see list_points).
              - {"spline": ref, "reverse": bool} -- an existing curve (id,
                as returned by add_spline), optionally walked tail-to-head.
              - {"arc": ref, "reverse": bool} -- an existing arc (id, as
                returned by add_arc), optionally walked end-to-start.
            "reverse" defaults to false and is ignored for point nodes. Must
            have at least 2 entries.
        seam_allowance: Whether the piece has a seam allowance.
        seam_allowance_width: Seam allowance width, as a plain number or
            formula, in the pattern's own unit. Only meaningful if
            seam_allowance is true.

    Returns:
        A confirmation message including the new piece's id.
    """
    try:
        new_id = xml_geometry.add_piece(
            path, draft_block_name, name, outline,
            seam_allowance=seam_allowance, seam_allowance_width=seam_allowance_width,
        )
    except xml_geometry.PatternFileError as e:
        return _text(f"Error: {e}")
    return _text(f"Added piece {name!r} (id {new_id}) with {len(outline)} outline nodes.")


def _ribben_connection(host: str | None, port: int | None, token: str | None) -> ribben_client.RibbenConnection:
    return ribben_client.resolve_connection(
        host=host or state.ribben_host,
        port=port or state.ribben_port,
        token=token or state.ribben_token,
    )


@mcp.tool(structured_output=False)
def live_ping(host: str | None = None, port: int | None = None, token: str | None = None) -> list[TextContent]:
    """Check that a running Seamly2D's Ribben addon is reachable.

    Unlike ``ping`` (which just checks this MCP server), this reaches into a
    *running* Seamly2D instance over its Ribben addon -- see live_read_pattern
    for what that means and how connection info is found.

    Args:
        host: Override the addon's host (default: auto-detect, normally 127.0.0.1).
        port: Override the addon's port (default: auto-detect from Seamly2D's settings).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON confirming the addon responded, or an error explaining why it
        couldn't be reached.
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.ping(conn))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_status(host: str | None = None, port: int | None = None, token: str | None = None) -> list[TextContent]:
    """Get the currently-open pattern's file path, unsaved-changes flag, unit, and piece count.

    Reads live from a running Seamly2D instance via the Ribben addon --
    see live_read_pattern for what that means.

    Args:
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON with file_path, modified, unit, and piece_count.
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.get_status(conn))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_read_pattern(host: str | None = None, port: int | None = None, token: str | None = None) -> list[TextContent]:
    """Read the pattern currently open in a running Seamly2D, live.

    This is the live counterpart to read_pattern: instead of parsing a .sm2d
    file from disk, it asks a running Seamly2D instance (via its "Ribben"
    addon -- Utilities > Enable Ribben Addon (Live MCP Server) in the app)
    about whatever pattern is actually open right now, including unsaved
    edits. Requires that addon to be enabled; if it isn't reachable this
    returns an error explaining how to turn it on.

    Connection info (host/port/token) is auto-detected from Seamly2D's own
    settings file by default -- you normally don't need to pass any of the
    optional arguments below.

    Args:
        host: Override the addon's host (default: auto-detect, normally 127.0.0.1).
        port: Override the addon's port (default: auto-detect from Seamly2D's settings).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON with file_path, description, notes, unit, piece_count, and
        increment_count.
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.read_pattern(conn))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_list_increments(host: str | None = None, port: int | None = None, token: str | None = None) -> list[TextContent]:
    """List the increments (named formulas) of the pattern open in a running Seamly2D, live.

    Live counterpart to list_increments -- see live_read_pattern for what
    "live" means here and how the addon is reached.

    Args:
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON list of {name, formula, value, description, valid}.
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.list_increments(conn))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_update_increment(
    name: str, formula: str, host: str | None = None, port: int | None = None, token: str | None = None
) -> list[TextContent]:
    """Set one increment's formula in the pattern open in a running Seamly2D, live.

    Live counterpart to update_increment, with one real advantage over the
    file-based version: the pattern's geometry is recomputed immediately, so
    the change shows up in the Seamly2D window right away -- no "reopen the
    file to see it" step. The increment must already exist (use
    live_list_increments to see names).

    Args:
        name: Increment name, including its leading '#' if it has one
            (e.g. "#NecWidth").
        formula: New formula, using Seamly2D's expression syntax.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON with the increment's new formula/value/valid -- valid is false
        (value 0) rather than an error if the formula doesn't parse, so a
        bad edit doesn't take down the rest of the pattern.
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.update_increment(conn, name, formula))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_set_pattern_notes(
    text: str, host: str | None = None, port: int | None = None, token: str | None = None
) -> list[TextContent]:
    """Set the notes text of the pattern open in a running Seamly2D, live.

    Live counterpart to set_pattern_notes -- see live_read_pattern for what
    "live" means here and how the addon is reached.

    Args:
        text: New notes text (replaces any existing notes).
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message.
    """
    try:
        conn = _ribben_connection(host, port, token)
        ribben_client.set_pattern_notes(conn, text)
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text("Updated notes in the open pattern.")


@mcp.tool(structured_output=False)
def live_list_points(
    draft_block_name: str, host: str | None = None, port: int | None = None, token: str | None = None
) -> list[TextContent]:
    """List the points in one draft block of the pattern open in a running Seamly2D, live.

    Live counterpart to list_points -- see live_read_pattern for what "live"
    means here and how the addon is reached.

    Args:
        draft_block_name: Name of the draft block to list points from.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON list of each point's raw attributes (id, name, type, and
        whichever type-specific attributes it has).
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.list_points(conn, draft_block_name))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_add_point_single(
    draft_block_name: str, name: str, x: float, y: float,
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Add an anchor point at explicit (x, y) coordinates to a running Seamly2D, live.

    Unlike the file-based add_point_single, the new point appears in the
    open window immediately -- the same live rebuild Seamly2D's own Undo/Redo
    already triggers, repurposed here for a fresh addition instead of an
    undo step. See live_read_pattern for how the addon is reached.

    Args:
        draft_block_name: Draft block to add the point to.
        name: Point name (letters/numbers/underscore, must not start with a
            digit or contain spaces/punctuation used by formulas).
        x: X coordinate.
        y: Y coordinate.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new point's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_point_single(conn, draft_block_name, name, x, y)
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(f"Added point {result.get('name')!r} (id {result.get('id')}) at ({x}, {y}), live.")


@mcp.tool(structured_output=False)
def live_add_point_end_line(
    draft_block_name: str, name: str, base_point: str, length: str, angle: str, line_type: str = "none",
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Add a point at a given length and angle from an existing point, live.

    Live counterpart to add_point_end_line -- appears in the open window
    immediately. See live_add_point_single for what "live" means here.

    Args:
        draft_block_name: Draft block to add the point to.
        name: New point's name.
        base_point: Name or id of the point to measure from (see live_list_points).
        length: Distance, as a Seamly2D formula -- a plain number, an
            increment name (e.g. "#Hemline"), or an expression.
        angle: Angle in degrees (0 = along +x, counterclockwise), as a
            plain number or formula.
        line_type: Draws a visible line from base_point to the new point if
            not "none" (e.g. "solidLine", "dashLine", "dotLine").
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new point's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_point_end_line(conn, draft_block_name, name, base_point, length, angle, line_type)
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(
        f"Added point {result.get('name')!r} (id {result.get('id')}), "
        f"{length} at {angle} degrees from {base_point!r}, live."
    )


@mcp.tool(structured_output=False)
def live_add_point_along_line(
    draft_block_name: str, name: str, first_point: str, second_point: str, length: str,
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Add a point at a given length along the line from first_point toward second_point, live.

    Live counterpart to add_point_along_line -- appears in the open window
    immediately. See live_add_point_single for what "live" means here.

    Args:
        draft_block_name: Draft block to add the point to.
        name: New point's name.
        first_point: Name or id of the point to measure from.
        second_point: Name or id of the point defining the line's direction.
        length: Distance from first_point, as a Seamly2D formula.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new point's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_point_along_line(conn, draft_block_name, name, first_point, second_point, length)
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(
        f"Added point {result.get('name')!r} (id {result.get('id')}), "
        f"{length} along {first_point!r} -> {second_point!r}, live."
    )


@mcp.tool(structured_output=False)
def live_add_line(
    draft_block_name: str, first_point: str, second_point: str, line_type: str = "solidLine",
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Draw a plain visual line connecting two existing points, live.

    Live counterpart to add_line -- appears in the open window immediately.
    See live_add_point_single for what "live" means here.

    Args:
        draft_block_name: Draft block to add the line to.
        first_point: Name or id of one endpoint.
        second_point: Name or id of the other endpoint.
        line_type: e.g. "solidLine", "dashLine", "dotLine", "hair".
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new line's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_line(conn, draft_block_name, first_point, second_point, line_type)
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(f"Added line (id {result.get('id')}) from {first_point!r} to {second_point!r}, live.")


@mcp.tool(structured_output=False)
def live_add_spline(
    draft_block_name: str, first_point: str, second_point: str,
    angle1: str = "0", length1: str = "1", angle2: str = "0", length2: str = "1",
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Draw a cubic-Bezier curve between two existing points, live.

    Live counterpart to add_spline -- appears in the open window immediately.
    See live_add_point_single for what "live" means here.

    Args:
        draft_block_name: Draft block to add the curve to.
        first_point: Name or id of the point the curve starts at.
        second_point: Name or id of the point the curve ends at.
        angle1: Tangent direction at first_point, in degrees.
        length1: Tangent handle length at first_point.
        angle2: Tangent direction at second_point.
        length2: Tangent handle length at second_point.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new curve's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_spline(
            conn, draft_block_name, first_point, second_point, angle1, length1, angle2, length2
        )
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(f"Added curve (id {result.get('id')}) from {first_point!r} to {second_point!r}, live.")


@mcp.tool(structured_output=False)
def live_add_arc(
    draft_block_name: str, center_point: str, radius: str, angle1: str, angle2: str,
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Draw a circular arc around an existing center point, live.

    Live counterpart to add_arc -- appears in the open window immediately.
    See live_add_point_single for what "live" means here.

    Args:
        draft_block_name: Draft block to add the arc to.
        center_point: Name or id of the existing point to center the arc on.
        radius: Arc radius, as a plain number or formula.
        angle1: Start angle in degrees.
        angle2: End angle -- the arc sweeps from angle1 to angle2.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new arc's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_arc(conn, draft_block_name, center_point, radius, angle1, angle2)
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(f"Added arc (id {result.get('id')}) centered on {center_point!r}, radius {radius}, live.")


@mcp.tool(structured_output=False)
def live_list_pieces(
    draft_block_name: str, host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """List the pieces (seam-allowance outlines) in one draft block, live.

    Args:
        draft_block_name: Draft block to list pieces from.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        JSON list of each piece's raw attributes plus its outline, same
        shape as the file-based list_pieces tool.
    """
    try:
        conn = _ribben_connection(host, port, token)
        return _text(ribben_client.list_pieces(conn, draft_block_name))
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")


@mcp.tool(structured_output=False)
def live_add_piece(
    draft_block_name: str, name: str, outline: list[dict[str, Any]],
    seam_allowance: bool = True, seam_allowance_width: str = "1",
    host: str | None = None, port: int | None = None, token: str | None = None,
) -> list[TextContent]:
    """Create a piece (seam-allowance outline) from existing draft geometry, live.

    Live counterpart to add_piece -- appears in the open window immediately.
    See add_piece for the full outline contract (point/spline/arc node
    dicts) and live_add_point_single for what "live" means here.

    Args:
        draft_block_name: Draft block to add the piece to.
        name: Piece name.
        outline: Ordered list of {"point"|"spline"|"arc": ref, "reverse": bool}
            node dicts around the piece boundary. Must have at least 2 entries.
        seam_allowance: Whether the piece has a seam allowance.
        seam_allowance_width: Seam allowance width, as a plain number or formula.
        host: Override the addon's host (default: auto-detect).
        port: Override the addon's port (default: auto-detect).
        token: Override the addon's auth token (default: auto-detect).

    Returns:
        A confirmation message including the new piece's id.
    """
    try:
        conn = _ribben_connection(host, port, token)
        result = ribben_client.add_piece(
            conn, draft_block_name, name, outline,
            seam_allowance=seam_allowance, seam_allowance_width=seam_allowance_width,
        )
    except ribben_client.RibbenClientError as e:
        return _text(f"Error: {e}")
    return _text(f"Added piece {name!r} (id {result.get('id')}) with {len(outline)} outline nodes, live.")


@mcp.tool(structured_output=False)
def render_pattern(
    path: str,
    dest_dir: str,
    basename: str,
    format: str = "svg",
    mfile: str | None = None,
    pageformat: int | None = None,
    rotate: int | None = None,
    gsize: int | None = None,
    gheight: int | None = None,
    export_only_details: bool = False,
    include_preview: bool = True,
    timeout: float = 120,
) -> list[TextContent | ImageContent]:
    """Headlessly render a pattern's layout via Seamly2D's CLI (no GUI shown).

    Args:
        path: Path to the .sm2d pattern file.
        dest_dir: Folder to write exported file(s) into (created if missing).
        basename: Base filename for exported layout file(s); Seamly2D appends
            a sheet number and the format's extension.
        format: One of "svg", "pdf", "pdf_tiled", "png", "jpg", "bmp", "tif",
            "ppm", "obj", "ps", "eps", or a "dxf_*" variant (default "svg").
        mfile: Optional path to a measurement file overriding the one the
            pattern references internally. Required if the pattern's own
            relative measurements path doesn't resolve on this machine.
        pageformat: Page template number (0=A0 ... 4=A4, 5=Letter, etc.) --
            see docs/tools.md for the full table. Omit to use the pattern's
            own layout settings.
        rotate: Rotation in degrees (one of Seamly2D's predefined values).
        gsize: Size value in cm, only for a pattern opened with multisize
            measurements (e.g. 40).
        gheight: Height value in cm, only for a pattern opened with multisize
            measurements (e.g. 176).
        export_only_details: Export pattern pieces as positioned in Details
            mode instead of laid out on sheets.
        include_preview: When format is "png", also return the exported
            image(s) as inline previews (default True).
        timeout: Seconds to wait before giving up (default 120).

    Returns:
        A message with success/output and the exported file paths; PNG
        output is additionally returned as an inline image when
        include_preview is True.
    """
    try:
        result = cli_bridge.render_pattern(
            path,
            dest_dir,
            basename,
            format=format,
            mfile=mfile,
            pageformat=pageformat,
            rotate=rotate,
            gsize=gsize,
            gheight=gheight,
            export_only_details=export_only_details,
            timeout=timeout,
            seamly2d_exe=state.seamly2d_exe,
        )
    except cli_bridge.CliBridgeError as e:
        return _text(f"Error: {e}")

    contents: list[TextContent | ImageContent] = _text(result)
    if include_preview and result.get("success") and format.lower() == "png":
        for f in result.get("exported_files", []):
            try:
                data = Path(f).read_bytes()
            except OSError:
                continue
            contents.append(
                ImageContent(type="image", data=base64.b64encode(data).decode("ascii"), mimeType="image/png")
            )
    return contents


@mcp.tool(structured_output=False)
def validate_pattern(path: str, mfile: str | None = None, timeout: float = 60) -> list[TextContent]:
    """Load a pattern in Seamly2D's silent test mode and check it rebuilds cleanly.

    No GUI is shown and nothing is exported. Use this right after editing a
    pattern's XML (e.g. via update_increment) to catch a broken formula or
    malformed file before handing it back to the user.

    Args:
        path: Path to the .sm2d file.
        mfile: Optional measurement file override.
        timeout: Seconds to wait before giving up (default 60).

    Returns:
        success/returncode/output from the load attempt.
    """
    try:
        result = cli_bridge.validate_pattern(
            path, mfile=mfile, timeout=timeout, seamly2d_exe=state.seamly2d_exe
        )
    except cli_bridge.CliBridgeError as e:
        return _text(f"Error: {e}")
    return _text(result)


@mcp.tool(structured_output=False)
def validate_measurements(path: str, unit: str | None = None, timeout: float = 60) -> list[TextContent]:
    """Load a measurement file in SeamlyMe's silent test mode and check it parses cleanly.

    No GUI is shown. Use this right after create_measurement_file or
    update_measurements to catch a malformed file before handing it back to
    the user or feeding it to render_pattern.

    Args:
        path: Path to the .smis or .smms file.
        unit: Optional unit override ("cm", "mm", or "inch").
        timeout: Seconds to wait before giving up (default 60).

    Returns:
        success/returncode/output from the load attempt.
    """
    try:
        result = cli_bridge.validate_measurements(
            path, unit=unit, timeout=timeout, seamlyme_exe=state.seamlyme_exe
        )
    except cli_bridge.CliBridgeError as e:
        return _text(f"Error: {e}")
    return _text(result)


@mcp.prompt()
def pattern_drafting_strategy() -> str:
    return PATTERN_DRAFTING_STRATEGY


def main():
    """Run the MCP server"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seamly2d-exe",
        default=None,
        help="Path to seamly2d.exe (default: auto-detect common install locations)",
    )
    parser.add_argument(
        "--seamlyme-exe",
        default=None,
        help="Path to seamlyme.exe (default: auto-detect common install locations)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio for Claude Desktop (default); http for remote/ChatGPT-style "
        "clients (Streamable HTTP transport, served at --host:--port/mcp)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind for --transport http")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind for --transport http")
    parser.add_argument(
        "--http-token",
        default=None,
        help="Bearer token required on every request when --transport http is used (default: "
        "a random one is generated and printed once at startup). Required because this "
        "transport is meant to sit behind a public tunnel for remote clients like ChatGPT -- "
        "without it, anyone with the tunnel URL could call every tool, including the ones "
        "that write files or drive a live Seamly2D. Not used/needed for --transport stdio "
        "(Claude Desktop), which never leaves this machine.",
    )
    parser.add_argument(
        "--public-host",
        action="append",
        default=None,
        help="Additional Host header value(s) to accept when --transport http is used -- e.g. "
        "your tunnel's hostname, 'my-tunnel.trycloudflare.com' (no scheme/port). Can be given "
        "multiple times. Needed because the transport's DNS-rebinding protection otherwise only "
        "accepts 127.0.0.1/localhost and rejects every request arriving through a tunnel with "
        "'421 Misdirected Request' / 'Invalid Host header'.",
    )
    parser.add_argument(
        "--ribben-host",
        default=None,
        help="Host for the Ribben addon's live JSON-RPC server (default: auto-detect, normally 127.0.0.1)",
    )
    parser.add_argument(
        "--ribben-port",
        type=int,
        default=None,
        help="Port for the Ribben addon's live JSON-RPC server (default: auto-detect from Seamly2D's settings)",
    )
    parser.add_argument(
        "--ribben-token",
        default=None,
        help="Auth token for the Ribben addon (default: auto-detect from Seamly2D's settings)",
    )
    args = parser.parse_args()
    if args.seamly2d_exe:
        state.seamly2d_exe = Path(args.seamly2d_exe)
    if args.seamlyme_exe:
        state.seamlyme_exe = Path(args.seamlyme_exe)
    state.ribben_host = args.ribben_host
    state.ribben_port = args.ribben_port
    state.ribben_token = args.ribben_token
    logger.info("Starting Seamly2D MCP server")
    if args.transport == "http":
        _run_http(args.host, args.port, args.http_token, args.public_host)
    else:
        mcp.run()


def _build_http_app(token: str, host: str = "127.0.0.1", public_hosts: list[str] | None = None):
    """Wraps the SDK's own Streamable HTTP Starlette app with a bearer-token gate.

    Split out from _run_http so a test can drive it with an ASGI test client
    instead of needing a real bound socket.

    A tunnel URL alone is not a secret: it can leak through browser history,
    logs, or the tunnel provider's own status pages. The MCP SDK's own auth
    support (AuthSettings/TokenVerifier) assumes a real OAuth authorization
    server, which is more machinery than a single-user personal setup needs
    -- this is a plain shared-secret check on top of the SDK's own app
    instead.

    public_hosts extends the SDK's own DNS-rebinding defense (which only
    accepts 127.0.0.1/localhost/[::1] by default -- see
    TransportSecuritySettings in the MCP SDK) to also accept a tunnel's
    hostname, without which every tunneled request gets rejected with
    "Invalid Host header" before it ever reaches the bearer-token check.
    """
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class RequireBearerToken(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    allowed_origins = list(allowed_hosts)
    for extra in public_hosts or []:
        allowed_hosts += [extra, f"{extra}:*"]
        allowed_origins += [f"https://{extra}", f"http://{extra}"]

    app = mcp.streamable_http_app(
        host=host,
        transport_security=TransportSecuritySettings(
            allowed_hosts=allowed_hosts, allowed_origins=allowed_origins
        ),
    )
    app.add_middleware(RequireBearerToken)
    return app


def _run_http(host: str, port: int, token: str | None, public_hosts: list[str] | None = None) -> None:
    """Serves the Streamable HTTP transport behind a required bearer token.

    This transport exists specifically so a remote client (ChatGPT, typically
    reached through a public tunnel -- see docs/installation.md) can call the
    same tools Claude Desktop's local stdio transport does, including the
    ones that write pattern files or drive a live, open Seamly2D via the
    Ribben addon.
    """
    import secrets

    import uvicorn

    if not token:
        token = secrets.token_hex(32)
        print(
            f"\nNo --http-token given; generated one for this run:\n\n    {token}\n\n"
            "Put this in your remote client's connector auth as a Bearer token (e.g. ChatGPT's "
            "Developer Mode custom connector settings). Anyone with both your tunnel URL and "
            "this token can call every tool here, including ones that write files or drive a "
            "live Seamly2D -- don't share it. It's regenerated every run unless you pass "
            "--http-token yourself.\n",
            file=sys.stderr,
        )
    if not public_hosts:
        print(
            "No --public-host given -- only 127.0.0.1/localhost will be accepted as a Host "
            "header. If this sits behind a tunnel, every tunneled request will be rejected "
            "with 'Invalid Host header' until you pass --public-host <your-tunnel-hostname>.\n",
            file=sys.stderr,
        )

    app = _build_http_app(token, host=host, public_hosts=public_hosts)
    logger.info(f"Serving Streamable HTTP on http://{host}:{port}/mcp (bearer token required)")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
