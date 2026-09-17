import base64
import logging
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

from .operations import cli_bridge, ribben_client, xml_measurements, xml_pattern
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
        logger.info(f"Serving Streamable HTTP on http://{args.host}:{args.port}/mcp")
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
