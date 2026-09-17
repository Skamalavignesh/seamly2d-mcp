import shutil
from pathlib import Path

import pytest

from seamly2d_mcp.operations import xml_measurements as xm

FIXTURES = Path(__file__).parent / "fixtures"


def test_list_measurement_files():
    files = xm.list_measurement_files(FIXTURES)
    names = {Path(f).name for f in files}
    assert "male_shirt.smis" in names
    assert "gost_man_ru.smms" in names


def test_read_individual_measurements():
    data = xm.read_measurements(FIXTURES / "male_shirt.smis")
    assert data["kind"] == "individual"
    assert data["unit"] == "cm"
    assert data["pm_system"] == "998"
    by_name = {m["name"]: m["value"] for m in data["measurements"]}
    assert by_name["height"] == "173"
    assert by_name["bust_circ"] == "102"
    assert data["personal"]["gender"] == "unknown"


def test_read_multisize_measurements():
    data = xm.read_measurements(FIXTURES / "gost_man_ru.smms")
    assert data["kind"] == "multisize"
    assert data["unit"] == "mm"
    assert data["size_base"] == "500"
    assert data["height_base"] == "1760"
    by_name = {m["name"]: m for m in data["measurements"]}
    assert by_name["height"]["base"] == "1760"
    assert by_name["bust_circ"]["size_increase"] == "38"


def test_read_missing_file_raises():
    with pytest.raises(xm.MeasurementFileError):
        xm.read_measurements(FIXTURES / "does_not_exist.smis")


def test_read_invalid_root_raises(tmp_path):
    bad = tmp_path / "bad.smis"
    bad.write_text("<?xml version='1.0'?><notsmis/>", encoding="utf-8")
    with pytest.raises(xm.MeasurementFileError):
        xm.read_measurements(bad)


def test_update_individual_measurements_round_trip(tmp_path):
    target = tmp_path / "male_shirt.smis"
    shutil.copy(FIXTURES / "male_shirt.smis", target)
    original_text = target.read_text(encoding="utf-8")

    missing = xm.update_measurements(target, {"height": {"value": "180"}})
    assert missing == []

    data = xm.read_measurements(target)
    by_name = {m["name"]: m["value"] for m in data["measurements"]}
    assert by_name["height"] == "180"
    # untouched measurement stays exactly as it was
    assert by_name["bust_circ"] == "102"

    new_text = target.read_text(encoding="utf-8")
    assert new_text != original_text
    # only the one changed value differs; everything else in the file is intact
    assert 'name="neck_circ" value="41"' in new_text


def test_update_unknown_measurement_reports_missing(tmp_path):
    target = tmp_path / "male_shirt.smis"
    shutil.copy(FIXTURES / "male_shirt.smis", target)
    missing = xm.update_measurements(target, {"not_a_real_measurement": {"value": "1"}})
    assert missing == ["not_a_real_measurement"]


def test_update_multisize_measurement_attribute(tmp_path):
    target = tmp_path / "gost_man_ru.smms"
    shutil.copy(FIXTURES / "gost_man_ru.smms", target)
    missing = xm.update_measurements(target, {"height": {"base": "1800"}})
    assert missing == []
    data = xm.read_measurements(target)
    by_name = {m["name"]: m for m in data["measurements"]}
    assert by_name["height"]["base"] == "1800"


def test_create_measurement_file_round_trip(tmp_path):
    target = tmp_path / "new_person.smis"
    xm.create_measurement_file(
        target,
        {"height": 170, "bust_circ": 90, "waist_circ": 75},
        personal={"given_name": "Alex", "gender": "female"},
        notes="test profile",
    )
    assert target.exists()

    data = xm.read_measurements(target)
    assert data["kind"] == "individual"
    assert data["notes"] == "test profile"
    assert data["personal"]["given_name"] == "Alex"
    by_name = {m["name"]: m["value"] for m in data["measurements"]}
    assert by_name["height"] == "170"
    assert by_name["bust_circ"] == "90"


def test_create_measurement_file_rejects_invalid_unit(tmp_path):
    with pytest.raises(xm.MeasurementFileError):
        xm.create_measurement_file(tmp_path / "bad.smis", {"height": 170}, unit="furlongs")


def test_create_measurement_file_rejects_empty_measurements(tmp_path):
    with pytest.raises(xm.MeasurementFileError):
        xm.create_measurement_file(tmp_path / "bad.smis", {})
