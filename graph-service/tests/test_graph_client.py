import json

import httpx

from app.auth.graph_client import GraphClient
from app.config import Settings


def _client(handler) -> GraphClient:
    return GraphClient(Settings(azure_tenant_id="", azure_client_id=""), transport=httpx.MockTransport(handler))


def test_missing_token_does_not_invent_a_profile():
    call = _client(lambda request: httpx.Response(500)).get_me(None)
    assert call.ok is False
    assert call.error_code == "not_authenticated"
    assert call.body is None
    assert call.attempts == 0


def test_get_retries_throttle_then_returns_the_real_body():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "throttled", "message": "slow down"}})
        return httpx.Response(200, json={"id": "real-user", "displayName": "Real Person"})

    call = _client(handler).get_me("secret-token")
    assert call.ok is True
    assert call.attempts == 2
    assert call.body["displayName"] == "Real Person"


def test_post_is_not_retried_after_throttle():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"code": "throttled", "message": "slow down"}})

    call = _client(handler).create_event("secret-token", {"subject": "probe"})
    assert calls["n"] == 1
    assert call.ok is False
    assert call.error_code == "throttled"
    assert call.body is None


def test_graph_error_message_is_truncated_and_token_is_not_echoed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "ErrorAccessDenied", "message": "no access_token=should-not-matter " + ("x" * 500)}})

    call = _client(handler).list_messages("secret-token")
    assert call.error_code == "graph_access_denied"
    assert "secret-token" not in call.message
    assert len(call.message) <= 300
    assert "secret-token" not in json.dumps(call.safe_metadata)
