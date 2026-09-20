"""Create and extend a Seamly2D pattern's draft geometry -- points, lines,
curves, arcs, and piece outlines.

xml_pattern.py deliberately stops at the "safe" parametric layer
(increments/notes) and stays out of <draftBlock> geometry -- see its
docstring and PROJECT_PLAN.md phase 4. This module is that next layer,
built incrementally rather than covering all ~40 point/curve tool types
Seamly2D has (see src/libs/vtools/tools/ in the Seamly2D source): for now,
the handful of types most drafts actually need.

Grounded directly in the schema Seamly2D itself ships
(src/libs/ifc/schema/pattern/*.xsd in the Seamly2D source tree), in real
sample files, and -- for arcs and pieces, where the bundled sample file
doesn't help enough on its own -- the C++ tools that write them (see each
function's docstring for the exact source file), not guessed:

- "single": an anchor point at explicit (x, y) coordinates -- the only
  point type with no dependencies; every draft needs at least one.
- "endLine": a point at a given length and angle from an existing point.
- "alongLine": a point at a given length along the line from one existing
  point toward another.
- <line>: a plain visual line connecting two existing points.
- <spline type="simpleInteractive">: a cubic-Bezier curve between two
  existing points, each end with its own angle+length tangent handle
  (Seamly2D's "Curve" tool).
- <arc type="simple">: a circular arc around an existing center point, from
  one angle to another (Seamly2D's "Arc" tool).
- <pieces><piece>: a seam-allowance outline built from existing points and
  curves (Seamly2D's "New Piece" tool) -- needed before render_pattern can
  export anything from a from-scratch draft.

Every point, line, arc, spline, modeling entry, and piece in a document
shares ONE global id counter -- confirmed empirically against a real sample
file, where these are interleaved rather than numbered per type. Seamly2D
resolves a draft block's <calculation> children in document order, so new
elements are always appended at the end and may only reference points that
already exist -- which also means dependency ordering takes care of itself
as long as every add_* call here validates its references before writing.

Piece outlines add a wrinkle: a <piece> can't reference <calculation>
geometry directly. Each referenced point/spline/arc first gets a thin
wrapper element in <modeling> (its own id, pointing back at the original via
idObject), and the piece's <nodes> reference those modeling ids instead --
see add_piece's docstring. This mirrors Seamly2D's own internal two-step
"promote, then build the outline" flow, just automated into one call.

Like xml_pattern.py, every write is preceded by a `.bak` backup (except
create_pattern, which is for a path that doesn't exist yet).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lxml import etree

from .xml_pattern import PatternFileError, _backup, _parse, _write

# Characters the real "shortName" schema type forbids in a name (roughly:
# whitespace and formula-operator characters), plus "must not start with a
# digit" -- see the shortName xs:pattern in
# src/libs/ifc/schema/pattern/*.xsd. Not a byte-for-byte port of that regex,
# just enough to catch the mistakes an LLM-driven caller is likely to make
# (spaces, punctuation) with a clear error instead of a cryptic one later.
_INVALID_NAME_CHARS = re.compile(r"""[\s*/&|!<>^\-+.,=?:;'"]""")


def _validate_name(name: str) -> None:
    if not name:
        raise PatternFileError("name must not be empty")
    if name[0].isdigit():
        raise PatternFileError(f"invalid name {name!r}: must not start with a digit")
    if _INVALID_NAME_CHARS.search(name):
        raise PatternFileError(
            f"invalid name {name!r}: must not contain whitespace or formula-operator "
            "characters (*/&|!<>^-+.,=?:;'\")"
        )


def _find_draft_block(root: etree._Element, name: str) -> etree._Element | None:
    for db in root.findall("draftBlock"):
        if db.get("name") == name:
            return db
    return None


def _require_draft_block(path: Path, root: etree._Element, name: str) -> etree._Element:
    draft_block = _find_draft_block(root, name)
    if draft_block is None:
        raise PatternFileError(f"{path}: no draft block named {name!r}")
    return draft_block


def _calculation(draft_block: etree._Element) -> etree._Element:
    calc = draft_block.find("calculation")
    if calc is None:
        raise PatternFileError("draft block has no <calculation> element")
    return calc


def _modeling(draft_block: etree._Element) -> etree._Element:
    modeling = draft_block.find("modeling")
    if modeling is None:
        raise PatternFileError("draft block has no <modeling> element")
    return modeling


def _pieces_container(draft_block: etree._Element) -> etree._Element:
    pieces = draft_block.find("pieces")
    if pieces is None:
        raise PatternFileError("draft block has no <pieces> element")
    return pieces


def _next_id(root: etree._Element) -> int:
    ids = [int(v) for v in root.xpath("//@id") if str(v).isdigit()]
    return (max(ids) if ids else 0) + 1


def _all_points(root: etree._Element) -> list[etree._Element]:
    return root.findall("draftBlock/calculation/point")


def _find_point(root: etree._Element, ref: str) -> etree._Element:
    """Resolves ref (a point's name, or its numeric id as a string/int) to its element."""
    ref_str = str(ref)
    for p in _all_points(root):
        if p.get("name") == ref_str or p.get("id") == ref_str:
            return p
    raise PatternFileError(f"no point named or with id {ref!r}")


def _find_calc_element(root: etree._Element, tag: str, ref: str) -> etree._Element:
    """Resolves ref (numeric id, as a string/int) to a <tag> element in <calculation>.

    Unlike points, lines/splines/arcs have no "name" attribute in Seamly2D's
    schema -- they're only ever referenced by the id add_line/add_spline/
    add_arc returned.
    """
    ref_str = str(ref)
    for el in root.findall(f"draftBlock/calculation/{tag}"):
        if el.get("id") == ref_str:
            return el
    raise PatternFileError(f"no {tag} with id {ref!r}")


def _check_name_free(root: etree._Element, name: str) -> None:
    if any(p.get("name") == name for p in _all_points(root)):
        raise PatternFileError(f"a point named {name!r} already exists")


def create_pattern(
    path: str | Path,
    draft_block_name: str,
    *,
    description: str = "",
    unit: str = "cm",
    measurements_file: str = "",
    version: str = "0.6.8",
) -> None:
    """Create a brand-new pattern file with one empty draft block.

    Unlike the geometry-editing functions below, this does not back up an
    existing file first -- it's meant for a path that doesn't exist yet.
    Follow up with add_point_single (at least once, to get a starting
    anchor point) and then add_point_end_line/add_point_along_line/add_line.

    Args:
        path: Destination .sm2d path. Parent directories are created if missing.
        draft_block_name: Name of the initial draft block (e.g. "Front").
        description: Optional pattern description.
        unit: "cm", "mm", or "inch".
        measurements_file: Optional path (relative to this file, or
            absolute) to a .smis/.smms file. Only needed once a formula
            references a measurement name -- pure-coordinate ("single")
            points and plain-number formulas don't need one.
        version: Pattern format version to declare (matches what current
            Seamly2D itself writes).
    """
    path = Path(path)
    _validate_name(draft_block_name)

    root = etree.Element("pattern")
    root.append(etree.Comment("Pattern created with seamly2d-mcp (https://seamly.io/)."))
    etree.SubElement(root, "version").text = version
    etree.SubElement(root, "unit").text = unit
    etree.SubElement(root, "description").text = description
    etree.SubElement(root, "notes")
    etree.SubElement(root, "measurements").text = measurements_file
    etree.SubElement(root, "increments")
    draft_block = etree.SubElement(root, "draftBlock", name=draft_block_name)
    etree.SubElement(draft_block, "calculation")
    etree.SubElement(draft_block, "modeling")
    etree.SubElement(draft_block, "pieces")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise PatternFileError(f"could not create directory {path.parent}: {e}") from e

    tree = etree.ElementTree(root)
    try:
        tree.write(str(path), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    except OSError as e:
        raise PatternFileError(f"could not write {path}: {e}") from e


def list_points(path: str | Path, draft_block_name: str) -> list[dict[str, Any]]:
    """List the points in one draft block's <calculation>, in creation order.

    Returns each point's raw attributes (id, name, type, and whichever
    type-specific attributes it has -- x/y for "single", basePoint/length/
    angle for "endLine", etc.) so a caller can find a point by name to
    reference in a later add_point_*/add_line call.
    """
    path = Path(path)
    _, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    return [dict(p.attrib) for p in _calculation(draft_block).findall("point")]


def _add_point(
    path: Path,
    draft_block_name: str,
    name: str,
    point_type: str,
    refs: dict[str, str] | None,
    attrs: dict[str, str],
) -> int:
    tree, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    _validate_name(name)
    _check_name_free(root, name)

    resolved_refs = {attr: _find_point(root, ref).get("id") for attr, ref in (refs or {}).items()}

    new_id = _next_id(root)
    _backup(path)
    point = etree.SubElement(_calculation(draft_block), "point")
    point.set("id", str(new_id))
    point.set("name", name)
    point.set("type", point_type)
    for key, value in {**attrs, **resolved_refs}.items():
        point.set(key, value)
    _write(tree, path)
    return new_id


def add_point_single(
    path: str | Path,
    draft_block_name: str,
    name: str,
    x: float,
    y: float,
    *,
    label_offset: tuple[float, float] = (0.0, 0.0),
) -> int:
    """Add an anchor point at explicit (x, y) canvas coordinates.

    Units follow the pattern's own unit (cm/mm/inch). This is the only
    point type with no dependencies -- every draft needs at least one to
    start from.

    Returns:
        The new point's id, for use as a base_point/first_point/second_point
        argument in later add_point_*/add_line calls (its name also works).
    """
    return _add_point(
        Path(path), draft_block_name, name, "single", None,
        {"x": str(x), "y": str(y), "mx": str(label_offset[0]), "my": str(label_offset[1])},
    )


def add_point_end_line(
    path: str | Path,
    draft_block_name: str,
    name: str,
    base_point: str,
    length: str,
    angle: str,
    *,
    line_type: str = "none",
    line_color: str = "black",
    label_offset: tuple[float, float] = (0.0, 0.0),
) -> int:
    """Add a point at a given length and angle from an existing point.

    Args:
        base_point: Name or id of the point to measure from.
        length: Distance, as a Seamly2D formula -- a plain number, an
            increment name (e.g. "#Hemline"), or an expression combining
            them (e.g. "#Hemline/2+1").
        angle: Angle in degrees (0 = along +x, counterclockwise), as a
            plain number or formula.
        line_type: Draws a visible line from base_point to the new point if
            not "none" (e.g. "solidLine", "dashLine", "dotLine").

    Returns:
        The new point's id.
    """
    return _add_point(
        Path(path), draft_block_name, name, "endLine", {"basePoint": base_point},
        {
            "length": length, "angle": angle, "lineType": line_type, "lineColor": line_color,
            "mx": str(label_offset[0]), "my": str(label_offset[1]),
        },
    )


def add_point_along_line(
    path: str | Path,
    draft_block_name: str,
    name: str,
    first_point: str,
    second_point: str,
    length: str,
    *,
    label_offset: tuple[float, float] = (0.0, 0.0),
) -> int:
    """Add a point at a given length along the line from first_point toward
    second_point (length may exceed their distance, extrapolating past
    second_point).

    Args:
        first_point / second_point: Name or id of the two existing points
            defining the line's direction; measured from first_point.
        length: Distance from first_point, as a Seamly2D formula.

    Returns:
        The new point's id.
    """
    return _add_point(
        Path(path), draft_block_name, name, "alongLine",
        {"firstPoint": first_point, "secondPoint": second_point},
        {
            "length": length, "lineType": "none", "lineColor": "black",
            "mx": str(label_offset[0]), "my": str(label_offset[1]),
        },
    )


def add_line(
    path: str | Path,
    draft_block_name: str,
    first_point: str,
    second_point: str,
    *,
    line_type: str = "solidLine",
    line_color: str = "black",
) -> int:
    """Draw a plain visual line connecting two existing points.

    Args:
        first_point / second_point: Name or id of the two points to connect.
        line_type: e.g. "solidLine", "dashLine", "dotLine", "hair".

    Returns:
        The new line's id.
    """
    path = Path(path)
    tree, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    first = _find_point(root, first_point)
    second = _find_point(root, second_point)

    new_id = _next_id(root)
    _backup(path)
    line = etree.SubElement(_calculation(draft_block), "line")
    line.set("id", str(new_id))
    line.set("firstPoint", first.get("id"))
    line.set("secondPoint", second.get("id"))
    line.set("lineType", line_type)
    line.set("lineColor", line_color)
    _write(tree, path)
    return new_id


def add_spline(
    path: str | Path,
    draft_block_name: str,
    first_point: str,
    second_point: str,
    *,
    angle1: str = "0",
    length1: str = "1",
    angle2: str = "0",
    length2: str = "1",
    line_color: str = "black",
) -> int:
    """Draw a cubic-Bezier curve between two existing points (Seamly2D's "Curve" tool).

    Matches the schema's "simpleInteractive" spline type: the curve runs
    from first_point to second_point, and each end has its own tangent
    control handle expressed the same way add_point_end_line expresses a
    new point -- an angle in degrees plus a length -- rather than as raw
    control-point coordinates.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the curve to.
        first_point / second_point: Name or id of the two existing points
            the curve runs between (see list_points).
        angle1: Tangent direction at first_point, in degrees (0 = along
            +x, counterclockwise), as a plain number or formula.
        length1: Tangent handle length at first_point -- bigger pulls the
            curve further before it bends toward second_point.
        angle2: Tangent direction at second_point, same convention as
            angle1.
        length2: Tangent handle length at second_point.
        line_color: e.g. "black", "red", ... (matches Seamly2D's palette).

    Returns:
        The new spline's id.
    """
    path = Path(path)
    tree, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    first = _find_point(root, first_point)
    second = _find_point(root, second_point)

    new_id = _next_id(root)
    _backup(path)
    spline = etree.SubElement(_calculation(draft_block), "spline")
    spline.set("id", str(new_id))
    spline.set("type", "simpleInteractive")
    spline.set("point1", first.get("id"))
    spline.set("point4", second.get("id"))
    spline.set("angle1", str(angle1))
    spline.set("length1", str(length1))
    spline.set("angle2", str(angle2))
    spline.set("length2", str(length2))
    spline.set("color", line_color)
    _write(tree, path)
    return new_id


def add_arc(
    path: str | Path,
    draft_block_name: str,
    center_point: str,
    radius: str,
    angle1: str,
    angle2: str,
    *,
    line_color: str = "black",
) -> int:
    """Draw a circular arc around an existing center point (Seamly2D's "Arc" tool).

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the arc to.
        center_point: Name or id of the existing point to center the arc on.
        radius: Arc radius, as a plain number or formula.
        angle1: Start angle in degrees (0 = along +x, counterclockwise), as
            a plain number or formula.
        angle2: End angle, same convention -- the arc sweeps from angle1 to
            angle2 in the direction of increasing angle.
        line_color: e.g. "black", "red", ... (matches Seamly2D's palette).

    Returns:
        The new arc's id.
    """
    path = Path(path)
    tree, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    center = _find_point(root, center_point)

    new_id = _next_id(root)
    _backup(path)
    arc = etree.SubElement(_calculation(draft_block), "arc")
    arc.set("id", str(new_id))
    arc.set("type", "simple")
    arc.set("center", center.get("id"))
    arc.set("radius", str(radius))
    arc.set("angle1", str(angle1))
    arc.set("angle2", str(angle2))
    arc.set("color", line_color)
    _write(tree, path)
    return new_id


# Node kind -> (calc element tag, piece <node type="...">, modeling element's
# own type="..." attribute). Grounded in the actual C++ tool that writes each
# modeling entry (VNodePoint/VNodeSpline/VNodeArc's AddToFile, in
# src/libs/vtools/tools/nodeDetails/) and the valid <node type> values listed
# in VAbstractPattern (NodePoint/NodeArc/NodeElArc/NodeSpline/NodeSplinePath
# in src/libs/ifc/xml/vabstractpattern.cpp) -- NodeSplinePath/NodeElArc are
# left out here since there's no add_* tool yet for multi-point paths or
# elliptical arcs.
_PIECE_NODE_KINDS: dict[str, tuple[str, str, str]] = {
    "point": ("point", "NodePoint", "modeling"),
    "spline": ("spline", "NodeSpline", "modelingSpline"),
    "arc": ("arc", "NodeArc", "modeling"),
}


def list_pieces(path: str | Path, draft_block_name: str) -> list[dict[str, Any]]:
    """List the pieces (seam-allowance outlines) in one draft block.

    Returns each piece's raw attributes (id, name, seamAllowance, width,
    ...) plus its outline as a list of {type, idObject, reverse} node dicts,
    in outline order.
    """
    path = Path(path)
    _, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    pieces = []
    for piece in _pieces_container(draft_block).findall("piece"):
        outline = [dict(node.attrib) for node in piece.findall("nodes/node")]
        pieces.append({**dict(piece.attrib), "outline": outline})
    return pieces


def add_piece(
    path: str | Path,
    draft_block_name: str,
    name: str,
    outline: list[dict[str, Any]],
    *,
    seam_allowance: bool = True,
    seam_allowance_width: str = "1",
) -> int:
    """Create a piece (seam-allowance outline) from existing draft geometry.

    Mirrors Seamly2D's "New Piece" tool: an outline is an ordered, closed
    sequence of nodes around the piece boundary, where consecutive point
    nodes imply a straight edge between them, and a curve node (spline/arc)
    replaces the straight edge with that curve. Needed before render_pattern
    can export anything from a from-scratch draft -- an empty scene (no
    pieces) is refused.

    Internally, Seamly2D doesn't let a piece reference draft geometry
    directly: each referenced point/spline/arc is first "promoted" into the
    draft block's <modeling> section (a thin wrapper with its own id,
    pointing back at the original via idObject), and the piece's outline
    references those modeling ids instead. This function does that
    promotion step automatically -- callers just reference the same
    point/spline/arc names or ids used with add_point_*/add_spline/add_arc.

    Args:
        path: Path to the .sm2d file.
        draft_block_name: Draft block to add the piece to.
        name: Piece name (e.g. "Front Panel") -- unlike point names, this
            has no character restrictions.
        outline: Ordered list of nodes around the piece boundary, each a
            dict with exactly one of:
              - {"point": ref} -- an existing point (name or id).
              - {"spline": ref, "reverse": bool} -- an existing curve (id,
                as returned by add_spline), optionally walked tail-to-head.
              - {"arc": ref, "reverse": bool} -- an existing arc (id, as
                returned by add_arc), optionally walked end-to-start.
            "reverse" defaults to False and is ignored for point nodes. Must
            have at least 2 entries.
        seam_allowance: Whether the piece has a seam allowance.
        seam_allowance_width: Seam allowance width, as a plain number or
            formula, in the pattern's own unit. Only meaningful if
            seam_allowance is true.

    Returns:
        The new piece's id.
    """
    path = Path(path)
    if len(outline) < 2:
        raise PatternFileError("a piece outline needs at least 2 nodes")

    tree, root = _parse(path)
    draft_block = _require_draft_block(path, root, draft_block_name)
    modeling = _modeling(draft_block)
    pieces = _pieces_container(draft_block)

    resolved: list[tuple[str, str, etree._Element, bool]] = []
    for entry in outline:
        present = [k for k in _PIECE_NODE_KINDS if k in entry]
        if len(present) != 1:
            raise PatternFileError(
                f"each outline entry must have exactly one of point/spline/arc: {entry!r}"
            )
        kind = present[0]
        tag, node_type, modeling_type = _PIECE_NODE_KINDS[kind]
        ref = entry[kind]
        reverse = bool(entry.get("reverse", False))
        calc_el = _find_point(root, ref) if kind == "point" else _find_calc_element(root, tag, ref)
        resolved.append((node_type, modeling_type, calc_el, reverse))

    _backup(path)

    nodes_el = etree.Element("nodes")
    for node_type, modeling_type, calc_el, reverse in resolved:
        modeling_id = _next_id(root)
        modeling_el = etree.SubElement(modeling, calc_el.tag)
        modeling_el.set("id", str(modeling_id))
        modeling_el.set("type", modeling_type)
        modeling_el.set("idObject", calc_el.get("id"))

        node_el = etree.SubElement(nodes_el, "node")
        node_el.set("idObject", str(modeling_id))
        node_el.set("type", node_type)
        if node_type != "NodePoint":
            node_el.set("reverse", "1" if reverse else "0")

    piece_id = _next_id(root)
    piece = etree.SubElement(pieces, "piece")
    piece.set("id", str(piece_id))
    piece.set("name", name)
    piece.set("version", "2")
    piece.set("closed", "1")
    piece.set("seamAllowance", "1" if seam_allowance else "0")
    if seam_allowance:
        piece.set("width", seam_allowance_width)
    piece.append(nodes_el)

    _write(tree, path)
    return piece_id
