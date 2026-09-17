import shutil
from pathlib import Path

import pytest

from seamly2d_mcp.operations import xml_pattern as xp

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_pattern():
    data = xp.read_pattern(FIXTURES / "male_shirt.sm2d")
    assert data["unit"] == "cm"
    assert "male shirt pattern" in data["description"]
    assert data["measurements_file"] == "../measurements/individual/male_shirt.smis"
    assert "Men shirt" in data["draft_blocks"]
    assert "Pocket" in data["draft_blocks"]
    by_name = {i["name"]: i["formula"] for i in data["increments"]}
    assert by_name["#BustCircumfence"] == "bust_circ+4"


def test_list_increments():
    increments = xp.list_increments(FIXTURES / "male_shirt.sm2d")
    names = {i["name"] for i in increments}
    assert "#NecWidth" in names
    assert "#ArmLength" in names


def test_read_missing_file_raises():
    with pytest.raises(xp.PatternFileError):
        xp.read_pattern(FIXTURES / "does_not_exist.sm2d")


def test_read_invalid_root_raises(tmp_path):
    bad = tmp_path / "bad.sm2d"
    bad.write_text("<?xml version='1.0'?><notpattern/>", encoding="utf-8")
    with pytest.raises(xp.PatternFileError):
        xp.read_pattern(bad)


def test_update_increment_round_trip_and_backup(tmp_path):
    target = tmp_path / "male_shirt.sm2d"
    shutil.copy(FIXTURES / "male_shirt.sm2d", target)
    original_text = target.read_text(encoding="utf-8")

    xp.update_increment(target, "#NecWidth", "neck_circ/6+1", description="widened neck")

    backup = target.with_suffix(".sm2d.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original_text

    data = xp.read_pattern(target)
    by_name = {i["name"]: i for i in data["increments"]}
    assert by_name["#NecWidth"]["formula"] == "neck_circ/6+1"
    assert by_name["#NecWidth"]["description"] == "widened neck"
    # untouched increment stays exactly as it was
    assert by_name["#ArmLength"]["formula"] == "arm_shoulder_tip_to_wrist_bent+3"


def test_update_unknown_increment_raises(tmp_path):
    target = tmp_path / "male_shirt.sm2d"
    shutil.copy(FIXTURES / "male_shirt.sm2d", target)
    with pytest.raises(xp.PatternFileError):
        xp.update_increment(target, "#NotReal", "1")


def test_update_increment_name_with_quote_does_not_break_lookup(tmp_path):
    # A naive f-string XPath predicate would mis-parse a name containing a
    # quote; _find_increment iterates instead, so this must fail cleanly
    # (no such increment) rather than raising an XPath syntax error or
    # matching the wrong element.
    target = tmp_path / "male_shirt.sm2d"
    shutil.copy(FIXTURES / "male_shirt.sm2d", target)
    with pytest.raises(xp.PatternFileError):
        xp.update_increment(target, "#Not'Real", "1")


def test_update_increment_empty_formula_raises(tmp_path):
    target = tmp_path / "male_shirt.sm2d"
    shutil.copy(FIXTURES / "male_shirt.sm2d", target)
    with pytest.raises(xp.PatternFileError):
        xp.update_increment(target, "#NecWidth", "   ")


def test_set_pattern_notes_round_trip(tmp_path):
    target = tmp_path / "male_shirt.sm2d"
    shutil.copy(FIXTURES / "male_shirt.sm2d", target)

    xp.set_pattern_notes(target, "Adjusted for a slimmer fit.")

    backup = target.with_suffix(".sm2d.bak")
    assert backup.exists()

    data = xp.read_pattern(target)
    assert data["notes"] == "Adjusted for a slimmer fit."
