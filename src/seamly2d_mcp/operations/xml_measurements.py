"""Read and write Seamly2D measurement files (.smis individual / .smms multisize).

Both formats are plain XML. We use lxml so that targeted edits (update_measurements)
only touch the specific attributes being changed and leave everything else in the
file — comments, whitespace, unrelated elements — exactly as it was.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from lxml import etree

INDIVIDUAL_ROOT = "smis"
MULTISIZE_ROOT = "smms"

_PERSONAL_FIELDS = ("family-name", "given-name", "birth-date", "gender", "email")


class MeasurementFileError(Exception):
    """Raised when a .smis/.smms file can't be parsed or written as expected."""


def _detect_kind(root: etree._Element, path: Path) -> str:
    if root.tag == INDIVIDUAL_ROOT:
        return "individual"
    if root.tag == MULTISIZE_ROOT:
        return "multisize"
    raise MeasurementFileError(
        f"{path}: unrecognized root element <{root.tag}> (expected <smis> or <smms>)"
    )


_VALID_UNITS = ("cm", "mm", "inch")

def _backup(path: Path) -> Path:
    """Copy ``path`` to a ``.bak`` sibling before mutating it, overwriting any
    previous backup. Returns the backup path."""
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, backup)
    except OSError as e:
        raise MeasurementFileError(f"could not write backup {backup}: {e}") from e
    return backup


def _write(tree: etree._ElementTree, path: Path, **kwargs: Any) -> None:
    try:
        tree.write(str(path), xml_declaration=True, encoding="UTF-8", **kwargs)
    except OSError as e:
        raise MeasurementFileError(f"could not write {path}: {e}") from e


def _parse(path: Path) -> tuple[etree._ElementTree, etree._Element, str]:
    try:
        tree = etree.parse(str(path))
    except OSError as e:
        raise MeasurementFileError(f"could not open {path}: {e}") from e
    except etree.XMLSyntaxError as e:
        raise MeasurementFileError(f"{path} is not valid XML: {e}") from e
    root = tree.getroot()
    return tree, root, _detect_kind(root, path)


def list_measurement_files(directory: str | Path) -> list[str]:
    """List .smis/.smms files under ``directory`` (recursive)."""
    directory = Path(directory)
    if not directory.is_dir():
        raise MeasurementFileError(f"{directory} is not a directory")
    files = sorted(directory.rglob("*.smis")) + sorted(directory.rglob("*.smms"))
    return [str(p) for p in files]


def read_measurements(path: str | Path) -> dict[str, Any]:
    """Parse a .smis or .smms file into a plain dict.

    Common keys: kind ("individual"/"multisize"), version, unit, pm_system, notes.

    Individual files additionally have:
      - personal: {family_name, given_name, birth_date, gender, email}
      - measurements: [{name, value}, ...]

    Multisize files additionally have:
      - size_base, height_base
      - measurements: [{name, base, size_increase, height_increase, description, full_name}, ...]
    """
    path = Path(path)
    tree, root, kind = _parse(path)

    def text(tag: str) -> str:
        el = root.find(tag)
        return (el.text or "") if el is not None else ""

    result: dict[str, Any] = {
        "kind": kind,
        "version": text("version"),
        "unit": text("unit"),
        "pm_system": text("pm_system"),
        "notes": text("notes"),
    }

    bm = root.find("body-measurements")
    measurements: list[dict[str, Any]] = []

    if kind == "individual":
        personal_el = root.find("personal")
        personal = {}
        if personal_el is not None:
            for field in _PERSONAL_FIELDS:
                el = personal_el.find(field)
                personal[field.replace("-", "_")] = el.text if el is not None and el.text else ""
        result["personal"] = personal
        if bm is not None:
            for m in bm.findall("m"):
                measurements.append({"name": m.get("name"), "value": m.get("value")})
    else:
        size_el = root.find("size")
        height_el = root.find("height")
        result["size_base"] = size_el.get("base") if size_el is not None else None
        result["height_base"] = height_el.get("base") if height_el is not None else None
        if bm is not None:
            for m in bm.findall("m"):
                measurements.append(
                    {
                        "name": m.get("name"),
                        "base": m.get("base"),
                        "size_increase": m.get("size_increase"),
                        "height_increase": m.get("height_increase"),
                        "description": m.get("description", ""),
                        "full_name": m.get("full_name", ""),
                    }
                )

    result["measurements"] = measurements
    return result


def update_measurements(path: str | Path, changes: dict[str, dict[str, Any]]) -> list[str]:
    """Patch specific <m> elements in place.

    ``changes`` maps measurement name -> {attribute: new_value}. For an
    individual (.smis) file the only meaningful attribute is "value". For a
    multisize (.smms) file it can be any of base/size_increase/
    height_increase/description/full_name.

    Only the touched attributes are modified; the rest of the file (formatting,
    comments, other measurements) is left as-is.

    Returns the list of measurement names in ``changes`` that were not found
    in the file (and therefore not updated).
    """
    path = Path(path)
    tree, root, kind = _parse(path)
    bm = root.find("body-measurements")
    if bm is None:
        raise MeasurementFileError(f"{path}: no <body-measurements> element")

    by_name = {m.get("name"): m for m in bm.findall("m")}
    missing: list[str] = []
    for name, attrs in changes.items():
        el = by_name.get(name)
        if el is None:
            missing.append(name)
            continue
        for attr, value in attrs.items():
            el.set(attr, str(value))

    _backup(path)
    _write(tree, path)
    return missing


def create_measurement_file(
    path: str | Path,
    measurements: dict[str, Any],
    *,
    personal: dict[str, str] | None = None,
    unit: str = "cm",
    pm_system: str = "998",
    notes: str = "",
    version: str = "0.3.4",
) -> None:
    """Write a new individual (.smis) measurement file.

    ``measurements`` maps measurement name -> numeric value (e.g.
    {"height": 173, "bust_circ": 102}). ``personal`` may set any of
    family_name/given_name/birth_date/gender/email; unset fields are left empty,
    matching what SeamlyMe writes for a blank profile.
    """
    if unit not in _VALID_UNITS:
        raise MeasurementFileError(f"unit must be one of {_VALID_UNITS}, got {unit!r}")
    if not measurements:
        raise MeasurementFileError("measurements must contain at least one entry")

    path = Path(path)
    personal = personal or {}

    root = etree.Element(INDIVIDUAL_ROOT)
    root.append(etree.Comment(f"Measurements created with seamly2d-mcp (https://seamly.io/)."))
    etree.SubElement(root, "version").text = version
    etree.SubElement(root, "read-only").text = "false"
    notes_el = etree.SubElement(root, "notes")
    if notes:
        notes_el.text = notes
    etree.SubElement(root, "unit").text = unit
    etree.SubElement(root, "pm_system").text = pm_system

    personal_el = etree.SubElement(root, "personal")
    etree.SubElement(personal_el, "family-name").text = personal.get("family_name") or None
    etree.SubElement(personal_el, "given-name").text = personal.get("given_name") or None
    etree.SubElement(personal_el, "birth-date").text = personal.get("birth_date") or "1800-01-01"
    etree.SubElement(personal_el, "gender").text = personal.get("gender") or "unknown"
    etree.SubElement(personal_el, "email").text = personal.get("email") or None

    bm_el = etree.SubElement(root, "body-measurements")
    for name, value in measurements.items():
        etree.SubElement(bm_el, "m", name=name, value=str(value))

    tree = etree.ElementTree(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MeasurementFileError(f"could not create directory {path.parent}: {e}") from e
    _write(tree, path, pretty_print=True)
