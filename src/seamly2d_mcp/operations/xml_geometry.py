"""Create and extend a Seamly2D pattern's draft geometry -- points and lines.

xml_pattern.py deliberately stops at the "safe" parametric layer
(increments/notes) and stays out of <draftBlock> geometry -- see its
docstring and PROJECT_PLAN.md phase 4. This module is that next layer,
built incrementally rather than covering all ~40 point tool types Seamly2D
has (see src/libs/vtools/tools/ in the Seamly2D source): for now, the
handful of types most drafts actually start from.

Grounded directly in the schema Seamly2D itself ships
(src/libs/ifc/schema/pattern/*.xsd in the Seamly2D source tree) and in real
sample files, not guessed:

- "single": an anchor point at explicit (x, y) coordinates -- the only
  point type with no dependencies; every draft needs at least one.
- "endLine": a point at a given length and angle from an existing point.
- "alongLine": a point at a given length along the line from one existing
  point toward another.
- <line>: a plain visual line connecting two existing points.

Every point, line, arc, and spline in a document shares ONE global id
counter -- confirmed empirically against a real sample file, where line/
spline ids are interleaved with point ids rather than numbered per type.
Seamly2D resolves a draft block's <calculation> children in document order,
so new elements are always appended at the end and may only reference
points that already exist -- which also means dependency ordering takes
care of itself as long as every add_* call here validates its references
before writing.

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
