"""Client for the Ribben addon's live JSON-RPC server.

Unlike the rest of this package (which reads/writes .sm2d/.smis/.smms files
directly, since Seamly2D has no live scripting API -- see PROJECT_PLAN.md),
this module talks to a *running* Seamly2D instance over a loopback TCP
socket, via the "Ribben" addon added to the Seamly2D fork at
https://github.com/FashionFreedom/Seamly2D (see RIBBEN.md there): a
checkable "Utilities > Enable Ribben Addon" menu action that starts a
newline-delimited JSON-RPC 2.0 server on 127.0.0.1, guarded by a token.

Because it's live, edits here are reflected immediately in the open window
(no "reopen the file to see the change" caveat the file-based update_increment
carries), and reads reflect whatever's currently open, even if unsaved.

Connection info (port + token) is normally auto-discovered from the same ini
file Seamly2D itself stores the addon's settings in
(``%APPDATA%/Seamly2DTeam/Seamly2D.ini`` on Windows, under a ``[Ribben]``
group) -- there is deliberately no need to copy a port/token around by hand
for the common case of "the MCP server and Seamly2D run on the same machine".
"""

from __future__ import annotations

import configparser
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RibbenClientError(Exception):
    """Raised when the Ribben addon can't be reached, rejects a request, or
    returns an error response."""


@dataclass
class RibbenConnection:
    host: str
    port: int
    token: str


def _settings_path() -> Path:
    """Where Seamly2D stores the addon's settings (same file as its other
    preferences -- see RibbenSettings in the Seamly2D fork's ribben library).
    """
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Seamly2DTeam" / "Seamly2D.ini"


def discover_connection(host: str | None = None) -> RibbenConnection | None:
    """Reads port/token out of Seamly2D's own settings file.

    Returns None (rather than raising) if the file, the [Ribben] group, or a
    token isn't there yet -- that just means the addon has never been
    enabled, which callers turn into a helpful error message rather than a
    raw "file not found".
    """
    path = _settings_path()
    if not path.is_file():
        return None

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return None

    if not parser.has_section("Ribben"):
        return None
    section = parser["Ribben"]

    token = section.get("token", "").strip().strip('"')
    if not token:
        return None

    try:
        port = int(section.get("port", "51230").strip().strip('"'))
    except ValueError:
        port = 51230

    return RibbenConnection(host=host or "127.0.0.1", port=port, token=token)


def resolve_connection(
    host: str | None = None, port: int | None = None, token: str | None = None
) -> RibbenConnection:
    """Fills in whatever wasn't explicitly given from auto-discovery.

    Raises RibbenClientError with a pointed message if a token is neither
    given nor discoverable -- that's the one piece that can't be defaulted.
    """
    if token:
        return RibbenConnection(host=host or "127.0.0.1", port=port or 51230, token=token)

    discovered = discover_connection(host=host)
    if discovered is None:
        raise RibbenClientError(
            "Could not find the Ribben addon's connection info at "
            f"{_settings_path()}. In Seamly2D, check Utilities > Enable "
            "Ribben Addon (Live MCP Server) at least once, or pass "
            "host/port/token explicitly."
        )
    if port:
        discovered.port = port
    return discovered


def _call(
    method: str, params: dict[str, Any] | None, conn: RibbenConnection, timeout: float = 5.0
) -> dict[str, Any]:
    """Sends one newline-delimited JSON-RPC 2.0 request and reads one response.

    Opens a fresh connection per call rather than keeping one open across
    tool invocations -- simpler, and matches how the rest of this server's
    tools are stateless per-call.
    """
    request: dict[str, Any] = {"id": 1, "method": method, "token": conn.token}
    if params is not None:
        request["params"] = params

    try:
        with socket.create_connection((conn.host, conn.port), timeout=timeout) as sock:
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            sock.settimeout(timeout)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except OSError as e:
        raise RibbenClientError(
            f"Could not reach the Ribben addon at {conn.host}:{conn.port} ({e}). "
            "Make sure Seamly2D is running with Utilities > Enable Ribben "
            "Addon (Live MCP Server) checked."
        ) from e

    if not buf:
        raise RibbenClientError("Connection to the Ribben addon closed with no response.")

    try:
        response = json.loads(buf.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RibbenClientError(f"Malformed response from the Ribben addon: {e}") from e

    if "error" in response:
        err = response["error"] or {}
        raise RibbenClientError(f"Ribben addon error {err.get('code')}: {err.get('message')}")

    return response.get("result", {})


def ping(conn: RibbenConnection) -> dict[str, Any]:
    return _call("ping", None, conn)


def get_status(conn: RibbenConnection) -> dict[str, Any]:
    return _call("get_status", None, conn)


def read_pattern(conn: RibbenConnection) -> dict[str, Any]:
    return _call("read_pattern", None, conn)


def list_increments(conn: RibbenConnection) -> list[dict[str, Any]]:
    return _call("list_increments", None, conn).get("increments", [])


def update_increment(conn: RibbenConnection, name: str, formula: str) -> dict[str, Any]:
    return _call("update_increment", {"name": name, "formula": formula}, conn)


def set_pattern_notes(conn: RibbenConnection, text: str) -> dict[str, Any]:
    return _call("set_pattern_notes", {"text": text}, conn)
