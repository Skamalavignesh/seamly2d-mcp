from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerState:
    """Configuration shared across tool calls for one server process."""

    seamly2d_exe: Path | None = None  # path to seamly2d.exe; None = auto-detect
    seamlyme_exe: Path | None = None  # path to seamlyme.exe; None = auto-detect
    default_output_dir: Path | None = None  # where render_pattern writes by default

    # Ribben addon (live JSON-RPC into a running Seamly2D) connection
    # overrides; None on any of these means auto-detect from Seamly2D's own
    # settings file -- see operations/ribben_client.py.
    ribben_host: str | None = None
    ribben_port: int | None = None
    ribben_token: str | None = None
