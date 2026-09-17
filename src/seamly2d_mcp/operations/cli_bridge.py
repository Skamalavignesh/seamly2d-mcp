"""Headless export/validation via the seamly2d.exe CLI.

Seamly2D has no live scripting API, but its CLI supports a genuine headless
export mode (``-b/--basename`` enables it) and a silent load-and-quit test
mode (``-t/--test``) that never shows the GUI. Both are verified here against
the real, installed ``seamly2d.exe --help`` output (v0.6.8), not just the
wiki docs, since flags can drift between versions.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

_COMMON_PATHS = [
    r"C:\Program Files (x86)\Seamly2D\seamly2d.exe",
    r"C:\Program Files\Seamly2D\seamly2d.exe",
]

_COMMON_PATHS_SEAMLYME = [
    r"C:\Program Files (x86)\Seamly2D\seamlyme.exe",
    r"C:\Program Files\Seamly2D\seamlyme.exe",
]

_VALID_UNITS = ("cm", "mm", "inch")

# Matches the -f/--format numbers from `seamly2d.exe --help`.
FORMAT_NUMBERS = {
    "svg": 0,
    "pdf": 1,
    "pdf_tiled": 2,
    "png": 3,
    "jpg": 4,
    "bmp": 5,
    "ppm": 6,
    "obj": 7,
    "ps": 8,
    "eps": 9,
    "dxf_r10": 10,
    "dxf_r11_12": 11,
    "dxf_r13": 12,
    "dxf_r14": 13,
    "dxf_2000": 14,
    "dxf_2004": 15,
    "dxf_2007": 16,
    "dxf_2010": 17,
    "dxf_2013": 18,
    "dxf_r10_aama": 19,
    "dxf_r11_12_aama": 20,
    "dxf_r13_aama": 21,
    "dxf_r14_aama": 22,
    "dxf_2000_aama": 23,
    "dxf_2004_aama": 24,
    "dxf_2007_aama": 25,
    "dxf_2010_aama": 26,
    "dxf_2013_aama": 27,
    "tif": 37,
}


class CliBridgeError(Exception):
    """Raised for setup problems (missing exe, missing file, bad args) --
    distinct from a subprocess run that completes but fails, which is
    reported in the returned dict instead."""


def detect_seamly2d_exe() -> Path | None:
    """Find seamly2d.exe: PATH first, then common Windows install locations."""
    for name in ("seamly2d", "seamly2d.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for candidate in _COMMON_PATHS:
        if Path(candidate).exists():
            return Path(candidate)
    return None


def _resolve_exe(seamly2d_exe: str | Path | None) -> Path:
    exe = Path(seamly2d_exe) if seamly2d_exe else detect_seamly2d_exe()
    if exe is None or not exe.exists():
        raise CliBridgeError(
            "seamly2d.exe not found. Pass seamly2d_exe explicitly, or install "
            "Seamly2D / put it on PATH."
        )
    return exe


def detect_seamlyme_exe() -> Path | None:
    """Find seamlyme.exe: PATH first, then common Windows install locations."""
    for name in ("seamlyme", "seamlyme.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for candidate in _COMMON_PATHS_SEAMLYME:
        if Path(candidate).exists():
            return Path(candidate)
    return None


def _resolve_seamlyme_exe(seamlyme_exe: str | Path | None) -> Path:
    exe = Path(seamlyme_exe) if seamlyme_exe else detect_seamlyme_exe()
    if exe is None or not exe.exists():
        raise CliBridgeError(
            "seamlyme.exe not found. Pass seamlyme_exe explicitly, or install "
            "Seamly2D / put it on PATH."
        )
    return exe


def _run(argv: list[str], timeout: float) -> dict[str, Any]:
    if not math.isfinite(timeout) or timeout <= 0:
        raise CliBridgeError("timeout must be a positive finite number")
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        out = "\n".join(part for part in (e.stdout, e.stderr) if part)
        return {
            "success": False,
            "timed_out": True,
            "error": f"seamly2d did not finish within {timeout:g}s",
            "output": out,
        }
    except OSError as e:
        return {"success": False, "error": f"could not start seamly2d: {e}"}

    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    result: dict[str, Any] = {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": output.strip(),
    }
    if proc.returncode != 0:
        result["error"] = f"seamly2d exited with code {proc.returncode}"
    return result


def render_pattern(
    pattern_path: str | Path,
    dest_dir: str | Path,
    basename: str,
    format: str = "svg",
    mfile: str | Path | None = None,
    pageformat: int | None = None,
    rotate: int | None = None,
    gsize: int | None = None,
    gheight: int | None = None,
    export_only_details: bool = False,
    timeout: float = 120,
    seamly2d_exe: str | Path | None = None,
) -> dict[str, Any]:
    """Headlessly export a pattern's layout via ``seamly2d.exe -b ...``.

    Returns a dict with success/returncode/output, and on success
    ``exported_files`` -- the files written to ``dest_dir`` matching
    ``basename``.
    """
    if not basename or any(sep in basename for sep in ("/", "\\")):
        raise CliBridgeError(f"basename must be a plain filename with no path separators, got {basename!r}")

    exe = _resolve_exe(seamly2d_exe)
    pattern_path = Path(pattern_path)
    if not pattern_path.exists():
        raise CliBridgeError(f"pattern file not found: {pattern_path}")
    pattern_path = pattern_path.resolve()
    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise CliBridgeError(f"could not create destination directory {dest_dir}: {e}") from e
    dest_dir = dest_dir.resolve()

    fmt_num = FORMAT_NUMBERS.get(format.lower())
    if fmt_num is None:
        raise CliBridgeError(f"unknown format {format!r}; valid: {sorted(FORMAT_NUMBERS)}")

    # seamly2d.exe fails to resolve a relative filename argument (it does not
    # use the process's working directory the way most CLIs do), so every
    # path handed to it must be absolute.
    argv = [str(exe), "-b", basename, "-d", str(dest_dir), "-f", str(fmt_num)]
    if mfile:
        argv += ["-m", str(Path(mfile).resolve())]
    if pageformat is not None:
        argv += ["-p", str(pageformat)]
    if rotate is not None:
        argv += ["-r", str(rotate)]
    if gsize is not None:
        argv += ["-x", str(gsize)]
    if gheight is not None:
        argv += ["-e", str(gheight)]
    if export_only_details:
        argv.append("--exportOnlyDetails")
    argv.append(str(pattern_path))

    result = _run(argv, timeout)
    if result["success"]:
        result["exported_files"] = sorted(str(p) for p in dest_dir.glob(f"{basename}*"))
    return result


def validate_pattern(
    pattern_path: str | Path,
    mfile: str | Path | None = None,
    timeout: float = 60,
    seamly2d_exe: str | Path | None = None,
) -> dict[str, Any]:
    """Load a pattern in Seamly2D's silent test mode (``-t``) and quit.

    No GUI is shown and nothing is exported. A clean (success) exit means the
    file parses and the draft rebuilds without error -- a good sanity check
    right after an XML edit, before handing the file back to the user.
    """
    exe = _resolve_exe(seamly2d_exe)
    pattern_path = Path(pattern_path)
    if not pattern_path.exists():
        raise CliBridgeError(f"pattern file not found: {pattern_path}")
    pattern_path = pattern_path.resolve()

    argv = [str(exe), "-t"]
    if mfile:
        argv += ["-m", str(Path(mfile).resolve())]
    argv.append(str(pattern_path))
    return _run(argv, timeout)


def validate_measurements(
    path: str | Path,
    unit: str | None = None,
    timeout: float = 60,
    seamlyme_exe: str | Path | None = None,
) -> dict[str, Any]:
    """Load a measurement file in SeamlyMe's silent test mode (``--test``) and quit.

    No GUI is shown. A clean (success) exit means the file parses as valid
    Seamly2D measurements -- a good sanity check right after
    create_measurement_file/update_measurements.
    """
    exe = _resolve_seamlyme_exe(seamlyme_exe)
    path = Path(path)
    if not path.exists():
        raise CliBridgeError(f"measurement file not found: {path}")
    path = path.resolve()

    argv = [str(exe), "--test"]
    if unit is not None:
        if unit not in _VALID_UNITS:
            raise CliBridgeError(f"unit must be one of {_VALID_UNITS}, got {unit!r}")
        argv += ["-u", unit]
    argv.append(str(path))
    return _run(argv, timeout)
