"""Tests for the bearer-token gate on the Streamable HTTP transport.

This transport is meant to sit behind a public tunnel for remote clients
(ChatGPT); without a token check, anyone with the tunnel URL could call
every tool, including ones that write files or drive a live Seamly2D. These
tests hit the real Starlette app _build_http_app constructs (via an ASGI
test client, no real socket needed), not a re-implementation of the check.
"""

from starlette.testclient import TestClient

from seamly2d_mcp.server import _build_http_app

TOKEN = "test-secret-token"


def _client():
    app = _build_http_app(TOKEN)
    # base_url matters here, not just style: the SDK's own DNS-rebinding
    # protection checks the Host header against an allowed-hosts pattern
    # like "127.0.0.1:*" (see TransportSecurityMiddleware._validate_host),
    # which requires a port -- TestClient's default Host ("testserver") and
    # a bare "127.0.0.1" (no port) both fail that check.
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_missing_token_rejected():
    response = _client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401


def test_wrong_token_rejected():
    response = _client().post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_correct_token_reaches_mcp_handshake():
    # The MCP session manager initializes its task group from the ASGI
    # lifespan startup event, which only fires when TestClient is used as a
    # context manager (a plain .post() on a bare instance skips it).
    with _client() as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200
    assert "Seamly2DMCP" in response.text
