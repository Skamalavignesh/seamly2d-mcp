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


def test_add_spline_between_existing_points(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    xg.add_point_single(path, "Front", "A2", 10, 0)
    spline_id = xg.add_spline(
        path, "Front", "A1", "A2", angle1="30", length1="2", angle2="150", length2="2"
    )
    assert spline_id == 3


def test_add_spline_defaults_and_xml_shape(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    xg.add_point_single(path, "Front", "A2", 10, 0)
    xg.add_spline(path, "Front", "A1", "A2")
    _, root = xg._parse(path)
    spline = root.find("draftBlock/calculation/spline")
    assert spline.get("type") == "simpleInteractive"
    assert spline.get("point1") == "1"
    assert spline.get("point4") == "2"
    assert spline.get("angle1") == "0"
    assert spline.get("length1") == "1"
    assert spline.get("color") == "black"


def test_add_spline_unknown_reference_raises(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    with pytest.raises(PatternFileError, match="no point named or with id"):
        xg.add_spline(path, "Front", "A1", "does-not-exist")


def test_add_arc_around_existing_point(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    arc_id = xg.add_arc(path, "Front", "A1", "5", "0", "180")
    assert arc_id == 2


def test_add_arc_xml_shape(tmp_path):
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A1", 0, 0)
    xg.add_arc(path, "Front", "A1", "5", "0", "180")
    _, root = xg._parse(path)
    arc = root.find("draftBlock/calculation/arc")
    assert arc.get("type") == "simple"
    assert arc.get("center") == "1"
    assert arc.get("radius") == "5"
    assert arc.get("angle1") == "0"
    assert arc.get("angle2") == "180"
    assert arc.get("color") == "black"


def test_add_arc_unknown_center_raises(tmp_path):
    path = _new_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="no point named or with id"):
        xg.add_arc(path, "Front", "does-not-exist", "5", "0", "180")


def test_spline_and_arc_share_global_id_counter_with_points_and_lines(tmp_path):
    path = _new_pattern(tmp_path)
    p1 = xg.add_point_single(path, "Front", "A1", 0, 0)
    p2 = xg.add_point_single(path, "Front", "A2", 10, 0)
    line_id = xg.add_line(path, "Front", "A1", "A2")
    spline_id = xg.add_spline(path, "Front", "A1", "A2")
    arc_id = xg.add_arc(path, "Front", "A1", "5", "0", "180")
    assert sorted([p1, p2, line_id, spline_id, arc_id]) == [1, 2, 3, 4, 5]


def _square_pattern(tmp_path):
    """A. B. C. D square (0,0)-(10,0)-(10,10)-(0,10), all straight edges."""
    path = _new_pattern(tmp_path)
    xg.add_point_single(path, "Front", "A", 0, 0)
    xg.add_point_single(path, "Front", "B", 10, 0)
    xg.add_point_single(path, "Front", "C", 10, 10)
    xg.add_point_single(path, "Front", "D", 0, 10)
    return path


def test_add_piece_all_point_nodes(tmp_path):
    path = _square_pattern(tmp_path)
    piece_id = xg.add_piece(
        path, "Front", "Square",
        [{"point": "A"}, {"point": "B"}, {"point": "C"}, {"point": "D"}],
    )
    pieces = xg.list_pieces(path, "Front")
    assert len(pieces) == 1
    piece = pieces[0]
    assert piece["id"] == str(piece_id)
    assert piece["name"] == "Square"
    assert piece["seamAllowance"] == "1"
    assert piece["closed"] == "1"
    assert len(piece["outline"]) == 4
    assert all(node["type"] == "NodePoint" for node in piece["outline"])


def test_add_piece_promotes_referenced_points_into_modeling(tmp_path):
    path = _square_pattern(tmp_path)
    xg.add_piece(path, "Front", "Square", [{"point": "A"}, {"point": "B"}, {"point": "C"}, {"point": "D"}])
    _, root = xg._parse(path)
    modeling_points = root.findall("draftBlock/modeling/point")
    assert len(modeling_points) == 4
    a_id = xg._find_point(root, "A").get("id")
    assert any(p.get("idObject") == a_id and p.get("type") == "modeling" for p in modeling_points)


def test_add_piece_with_curve_nodes(tmp_path):
    path = _square_pattern(tmp_path)
    spline_id = xg.add_spline(path, "Front", "A", "B", angle1="30", angle2="150")
    arc_id = xg.add_arc(path, "Front", "C", "5", "0", "90")
    piece_id = xg.add_piece(
        path, "Front", "Curvy",
        [
            {"point": "A"},
            {"spline": spline_id, "reverse": False},
            {"point": "B"},
            {"point": "C"},
            {"arc": arc_id, "reverse": True},
            {"point": "D"},
        ],
    )
    piece = xg.list_pieces(path, "Front")[0]
    assert piece["id"] == str(piece_id)
    outline = piece["outline"]
    assert [n["type"] for n in outline] == ["NodePoint", "NodeSpline", "NodePoint", "NodePoint", "NodeArc", "NodePoint"]
    assert outline[1]["reverse"] == "0"
    assert outline[4]["reverse"] == "1"


def test_add_piece_without_seam_allowance_omits_width(tmp_path):
    path = _square_pattern(tmp_path)
    xg.add_piece(
        path, "Front", "Square",
        [{"point": "A"}, {"point": "B"}, {"point": "C"}, {"point": "D"}],
        seam_allowance=False,
    )
    piece = xg.list_pieces(path, "Front")[0]
    assert piece["seamAllowance"] == "0"
    assert "width" not in piece


def test_add_piece_rejects_too_few_nodes(tmp_path):
    path = _square_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="at least 2 nodes"):
        xg.add_piece(path, "Front", "Square", [{"point": "A"}])


def test_add_piece_rejects_ambiguous_node(tmp_path):
    path = _square_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="exactly one of point/spline/arc"):
        xg.add_piece(path, "Front", "Square", [{"point": "A"}, {"point": "B", "arc": "1"}])


def test_add_piece_unknown_point_reference_raises(tmp_path):
    path = _square_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="no point named or with id"):
        xg.add_piece(path, "Front", "Square", [{"point": "A"}, {"point": "does-not-exist"}])


def test_add_piece_unknown_spline_reference_raises(tmp_path):
    path = _square_pattern(tmp_path)
    with pytest.raises(PatternFileError, match="no spline with id"):
        xg.add_piece(path, "Front", "Square", [{"point": "A"}, {"spline": "999"}])


def test_add_piece_ids_continue_global_counter(tmp_path):
    path = _square_pattern(tmp_path)  # points 1-4
    piece_id = xg.add_piece(
        path, "Front", "Square",
        [{"point": "A"}, {"point": "B"}, {"point": "C"}, {"point": "D"}],
    )
    # 4 modeling wrappers (ids 5-8) + the piece itself (id 9)
    assert piece_id == 9
