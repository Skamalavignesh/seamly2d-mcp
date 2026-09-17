"""Read and edit Seamly2D pattern files (.sm2d).

.sm2d is XML. This module deliberately only touches the "safe" parametric
layer of a pattern -- increments (named formulas that drive the whole draft)
and metadata (description/notes) -- not the <draftBlock> point/line/curve
geometry, which is a much larger parametric-CAD surface to model correctly
(see PROJECT_PLAN.md phase 4).

Any write is preceded by a `.bak` backup of the original file so a bad edit
is always recoverable.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from lxml import etree

PATTERN_ROOT = "pattern"


class PatternFileError(Exception):
    """Raised when a .sm2d file can't be parsed or written as expected."""


def _parse(path: Path) -> tuple[etree._ElementTree, etree._Element]:
    try:
        tree = etree.parse(str(path))
    except OSError as e:
        raise PatternFileError(f"could not open {path}: {e}") from e
    except etree.XMLSyntaxError as e:
        raise PatternFileError(f"{path} is not valid XML: {e}") from e
    root = tree.getroot()
    if root.tag != PATTERN_ROOT:
        raise PatternFileError(f"{path}: unrecognized root element <{root.tag}> (expected <pattern>)")
    return tree, root


def _backup(path: Path) -> Path:
    """Copy ``path`` to a ``.bak`` sibling before mutating it, overwriting any
    previous backup. Returns the backup path."""
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, backup)
    except OSError as e:
        raise PatternFileError(f"could not write backup {backup}: {e}") from e
    return backup


def _write(tree: etree._ElementTree, path: Path) -> None:
    try:
        tree.write(str(path), xml_declaration=True, encoding="UTF-8")
    except OSError as e:
        raise PatternFileError(f"could not write {path}: {e}") from e


def _find_increment(root: etree._Element, name: str) -> etree._Element | None:
    # Iterate rather than build an XPath predicate from `name`, since a name
    # containing a quote character would otherwise break or misdirect the query.
    for inc in root.findall("increments/increment"):
        if inc.get("name") == name:
            return inc
    return None


def read_pattern(path: str | Path) -> dict[str, Any]:
    """Parse a .sm2d file's metadata and parametric layer (not the geometry).

    Returns version, unit, description, notes, the linked measurement file
    path, the list of increments ({name, formula, description}), and the
    names of the pattern's draft blocks (pieces/sections), so the caller
    knows what geometry exists without pulling in the full point/line/curve
    detail.
    """
    path = Path(path)
    tree, root = _parse(path)

    def text(tag: str) -> str:
        el = root.find(tag)
        return (el.text or "") if el is not None else ""

    increments = [
        {
            "name": inc.get("name"),
            "formula": inc.get("formula"),
            "description": inc.get("description", ""),
        }
        for inc in root.findall("increments/increment")
    ]

    draft_blocks = [db.get("name") for db in root.findall("draftBlock")]

    return {
        "version": text("version"),
        "unit": text("unit"),
        "description": text("description"),
        "notes": text("notes"),
        "measurements_file": text("measurements"),
        "increments": increments,
        "draft_blocks": draft_blocks,
    }


def list_increments(path: str | Path) -> list[dict[str, Any]]:
    """List a pattern's increments (name/formula/description)."""
    return read_pattern(path)["increments"]


def update_increment(
    path: str | Path,
    name: str,
    formula: str,
    description: str | None = None,
) -> None:
    """Update one increment's formula (and optionally its description) in place.

    Backs up the original file to ``<path>.bak`` first. Raises PatternFileError
    if no increment with that name exists -- this never creates a new one, to
    avoid silently introducing an undefined variable other formulas can't see.
    """
    if not formula or not formula.strip():
        raise PatternFileError("formula must be a non-empty string")
    path = Path(path)
    tree, root = _parse(path)
    inc = _find_increment(root, name)
    if inc is None:
        raise PatternFileError(f"{path}: no increment named {name!r}")
    _backup(path)
    inc.set("formula", formula)
    if description is not None:
        inc.set("description", description)
    _write(tree, path)


def set_pattern_notes(path: str | Path, text: str) -> None:
    """Set a pattern's <notes> text in place. Backs up the original file first."""
    path = Path(path)
    tree, root = _parse(path)
    notes = root.find("notes")
    if notes is None:
        raise PatternFileError(f"{path}: no <notes> element")
    _backup(path)
    notes.text = text
    _write(tree, path)
