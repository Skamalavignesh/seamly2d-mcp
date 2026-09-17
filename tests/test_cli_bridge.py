from pathlib import Path

import pytest

from seamly2d_mcp.operations import cli_bridge as cb

FIXTURES = Path(__file__).parent / "fixtures"
PATTERN = FIXTURES / "male_shirt.sm2d"
MFILE = FIXTURES / "male_shirt.smis"
MSMS_FILE = FIXTURES / "gost_man_ru.smms"

pytestmark = pytest.mark.skipif(
    cb.detect_seamly2d_exe() is None,
    reason="seamly2d.exe not found on this machine",
)


def test_detect_seamly2d_exe():
    assert cb.detect_seamly2d_exe() is not None


def test_validate_pattern_success():
    result = cb.validate_pattern(PATTERN, mfile=MFILE, timeout=60)
    assert result["success"] is True
    assert result["returncode"] == 0


def test_validate_missing_file_raises():
    with pytest.raises(cb.CliBridgeError):
        cb.validate_pattern(FIXTURES / "does_not_exist.sm2d")


def test_render_pattern_svg(tmp_path):
    result = cb.render_pattern(
        PATTERN, tmp_path, "male_shirt", format="svg", mfile=MFILE, timeout=60
    )
    assert result["success"] is True
    assert result["exported_files"], "expected at least one exported layout file"
    for f in result["exported_files"]:
        assert Path(f).exists()
        assert Path(f).suffix == ".svg"


def test_render_pattern_unknown_format_raises(tmp_path):
    with pytest.raises(cb.CliBridgeError):
        cb.render_pattern(PATTERN, tmp_path, "male_shirt", format="not_a_format")


def test_render_pattern_rejects_basename_with_path_separator(tmp_path):
    with pytest.raises(cb.CliBridgeError):
        cb.render_pattern(PATTERN, tmp_path, "../escape", format="svg")


def test_render_pattern_relative_paths_are_resolved(tmp_path, monkeypatch):
    # seamly2d.exe cannot resolve relative filename arguments against the
    # process cwd, so cli_bridge must absolutize everything before invoking it.
    monkeypatch.chdir(FIXTURES)
    result = cb.render_pattern(
        Path("male_shirt.sm2d"),
        tmp_path,
        "male_shirt",
        format="svg",
        mfile=Path("male_shirt.smis"),
        timeout=60,
    )
    assert result["success"] is True


def test_detect_seamlyme_exe():
    assert cb.detect_seamlyme_exe() is not None


def test_validate_measurements_individual():
    result = cb.validate_measurements(MFILE, timeout=30)
    assert result["success"] is True
    assert result["returncode"] == 0


def test_validate_measurements_multisize():
    result = cb.validate_measurements(MSMS_FILE, timeout=30)
    assert result["success"] is True


def test_validate_measurements_missing_file_raises():
    with pytest.raises(cb.CliBridgeError):
        cb.validate_measurements(FIXTURES / "does_not_exist.smis")


def test_validate_measurements_invalid_unit_raises():
    with pytest.raises(cb.CliBridgeError):
        cb.validate_measurements(MFILE, unit="furlongs")
