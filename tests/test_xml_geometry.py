import pytest

from seamly2d_mcp.operations import xml_geometry as xg
from seamly2d_mcp.operations.xml_pattern import PatternFileError


def _new_pattern(tmp_path):
    path = tmp_path / "new.sm2d"
    xg.create_pattern(path, "Front", description="test")
    return path


def test_create_pattern_has_one_empty_draft_block(tmp_path):
    path = _new_pattern(tmp_path)
    assert xg.list_points(path, "Front") == []


def test_add_point_single(tmp_path):
    path = _new_pattern(tmp_path)
    new_id = xg.add_point_single(path, "Front", "A1", 1.5, 2.5)
    assert new_id == 1
    points = xg.list_points(path, "Front")
    assert points == [{"id": "1", "name": "A1", "type": "single", "x": "1.5", "y": "2.5", "mx": "0.0", "my": "0.0"}]


def test_add_point_end_line_references_base_by_name(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    new_id = xg.add_point_end_line(path, "Front", "A2", "A1", "10", "90")
    assert new_id == 2
    points = {p["name"]: p for p in xg.list_points(path, "Front")}
    assert points["A2"]["basePoint"] == "1"
    assert points["A2"]["length"] == "10"
    assert points["A2"]["angle"] == "90"


def test_add_point_end_line_references_base_by_id(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    new_id = xg.add_point_end_line(path, "Front", "A2", "1", "10", "90")
    assert new_id == 2


def test_add_point_along_line(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    xg.add_point_single(path, "Front", "A2", 10, 0)
    new_id = xg.add_point_along_line(path, "Front", "A3", "A1", "A2", "5")
    points = {p["name"]: p for p in xg.list_points(path, "Front")}
    assert points["A3"]["firstPoint"] == "1"
    assert points["A3"]["secondPoint"] == "2"
    assert new_id == 3


def test_add_line_between_existing_points(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    xg.add_point_single(path, "Front", "A2", 10, 0)
    line_id = xg.add_line(path, "Front", "A1", "A2", line_type="dashLine")
    assert line_id == 3


def test_ids_are_globally_unique_across_points_and_lines(tmp_path):
    path = _new_pattern(tmp_path)
    p1 = xg.add_point_single(path, "Front", "A1", 0, 0)
    p2 = xg.add_point_single(path, "Front", "A2", 10, 0)
    line_id = xg.add_line(path, "Front", "A1", "A2")
    p3 = xg.add_point_along_line(path, "Front", "A3", "A1", "A2", "5")
    assert sorted([p1, p2, line_id, p3]) == [1, 2, 3, 4]


def test_add_point_unknown_reference_raises(tmp_path):
    path = _new_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="no point named or with id"):
        xg.add_point_end_line(path, "Front", "A2", "does-not-exist", "10", "0")


def test_add_point_unknown_draft_block_raises(tmp_path):
    path = _new_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="no draft block named"):
        xg.add_point_single(path, "NotARealBlock", "A1", 0, 0)


def test_duplicate_point_name_raises(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    with pytest.raises(PatternFileError, match="already exists"):
        xg.add_point_single(path, "Front", "A1", 5, 5)


@pytest.mark.parametrize("bad_name", ["1A", "A 1", "A-1", "A.1", "A*1"])
def test_invalid_point_name_raises(tmp_path, bad_name):
    path = _new_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="invalid name"):
        xg.add_point_single(path, "Front", bad_name, 0, 0)


def test_add_point_backs_up_file_first(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    backup = path.with_suffix(path.suffix + ".bak")
    assert backup.exists()
    # backup reflects the state before this add (no points yet)
    assert xg.list_points(backup, "Front") == []


def test_create_pattern_rejects_invalid_draft_block_name(tmp_path):
    with pytest.raises(PatternFileError, match="invalid name"):
        xg.create_pattern(tmp_path / "bad.sm2d", "Not Valid")
