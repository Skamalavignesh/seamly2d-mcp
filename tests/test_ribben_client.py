"""Tests for the Ribben addon client against a real (fake) TCP server.

No mocking of socket/json internals -- a tiny background-thread server speaks
the real newline-delimited JSON-RPC 2.0 wire protocol the Seamly2D addon
uses, so these tests exercise ribben_client's actual request/response and
error-handling logic, not a stand-in for it.
"""

import json
import socket
import threading

import pytest

from seamly2d_mcp.operations import ribben_client as rc

TOKEN = "test-token-0123456789"


class FakeRibbenServer:
    """Minimal stand-in for the Seamly2D addon: one accept loop, one
    connection at a time, same line-framing and token check as the real
    RibbenServer."""

    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(1)
        self.port = self._socket.getsockname()[1]
        self._thread = threading.Thread(target=self._serve_once, daemon=True)
        self._thread.start()

    def _serve_once(self):
        try:
            conn, _ = self._socket.accept()
        except OSError:
            return
        with conn:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            request = json.loads(buf.decode("utf-8"))
            response = self._handle(request)
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    def _handle(self, request: dict) -> dict:
        if request.get("token") != TOKEN:
            return {"jsonrpc": "2.0", "id": request.get("id"),
                     "error": {"code": 1, "message": "Missing or incorrect token."}}

        method = request.get("method")
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True, "app": "seamly2d"}}
        if method == "list_increments":
            return {"jsonrpc": "2.0", "id": request["id"],
                     "result": {"increments": [{"name": "#Foo", "formula": "1", "value": 1,
                                                 "description": "", "valid": True}]}}
        if method == "update_increment":
            return {"jsonrpc": "2.0", "id": request["id"],
                     "error": {"code": 3, "message": "No increment named \"bar\"."}}
        if method == "list_points":
            return {"jsonrpc": "2.0", "id": request["id"],
                     "result": {"points": [{"id": "1", "name": "A1", "type": "single", "x": "0", "y": "0"}]}}
        if method == "add_point_single":
            return {"jsonrpc": "2.0", "id": request["id"],
                     "result": {"id": 2, "name": request["params"]["name"]}}
        if method == "add_point_end_line":
            return {"jsonrpc": "2.0", "id": request["id"],
                     "error": {"code": 3, "message": "No point named or with id \"ghost\"."}}
        if method == "add_point_along_line":
            return {"jsonrpc": "2.0", "id": request["id"],
                     "result": {"id": 3, "name": request["params"]["name"]}}
        if method == "add_line":
            return {"jsonrpc": "2.0", "id": request["id"], "result": {"id": 4}}
        return {"jsonrpc": "2.0", "id": request.get("id"),
                 "error": {"code": -32601, "message": f"Unknown method {method!r}."}}

    def close(self):
        self._socket.close()
        self._thread.join(timeout=1)


@pytest.fixture
def fake_server():
    server = FakeRibbenServer()
    yield server
    server.close()


def test_ping_success(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    assert rc.ping(conn) == {"ok": True, "app": "seamly2d"}


def test_list_increments(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    increments = rc.list_increments(conn)
    assert increments == [{"name": "#Foo", "formula": "1", "value": 1, "description": "", "valid": True}]


def test_wrong_token_raises(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token="wrong")
    with pytest.raises(rc.RibbenClientError, match="Missing or incorrect token"):
        rc.ping(conn)


def test_server_side_error_raises(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    with pytest.raises(rc.RibbenClientError, match="No increment named"):
        rc.update_increment(conn, "bar", "1")


def test_unreachable_port_raises():
    # Nothing listens here; the OS should refuse the connection immediately.
    conn = rc.RibbenConnection(host="127.0.0.1", port=1, token=TOKEN)
    with pytest.raises(rc.RibbenClientError, match="Could not reach"):
        rc.ping(conn)


def test_discover_connection_reads_ini(tmp_path, monkeypatch):
    settings_dir = tmp_path / "Seamly2DTeam"
    settings_dir.mkdir()
    (settings_dir / "Seamly2D.ini").write_text(
        "[Ribben]\nenabled=true\nport=54321\ntoken=abc123\n", encoding="utf-8"
    )
    monkeypatch.setenv("APPDATA", str(tmp_path))

    found = rc.discover_connection()
    assert found is not None
    assert found.port == 54321
    assert found.token == "abc123"


def test_discover_connection_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "does-not-exist"))
    assert rc.discover_connection() is None


def test_resolve_connection_raises_helpful_error_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "does-not-exist"))
    with pytest.raises(rc.RibbenClientError, match="Enable Ribben Addon"):
        rc.resolve_connection()


def test_resolve_connection_prefers_explicit_token():
    conn = rc.resolve_connection(host="10.0.0.5", port=9999, token="explicit")
    assert conn == rc.RibbenConnection(host="10.0.0.5", port=9999, token="explicit")


def test_list_points(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    assert rc.list_points(conn, "Front") == [{"id": "1", "name": "A1", "type": "single", "x": "0", "y": "0"}]


def test_add_point_single(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    assert rc.add_point_single(conn, "Front", "A1", 0, 0) == {"id": 2, "name": "A1"}


def test_add_point_end_line_unknown_reference_raises(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    with pytest.raises(rc.RibbenClientError, match="No point named or with id"):
        rc.add_point_end_line(conn, "Front", "A2", "ghost", "10", "0")


def test_add_point_along_line(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    assert rc.add_point_along_line(conn, "Front", "A3", "A1", "A2", "5") == {"id": 3, "name": "A3"}


def test_add_line(fake_server):
    conn = rc.RibbenConnection(host="127.0.0.1", port=fake_server.port, token=TOKEN)
    assert rc.add_line(conn, "Front", "A1", "A2") == {"id": 4}
