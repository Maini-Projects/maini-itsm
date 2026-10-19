"""The two places the API talks to Supabase Auth, tested against a pretend Supabase (no network).

The request shapes follow Supabase's documented endpoints: GET /auth/v1/user and POST/DELETE
/auth/v1/admin/users. They have NOT been run against a real project yet; the first sign-in on
the deployed service is the real check.
"""
import json
import uuid

import httpx
import pytest

from app import auth
from app.errors import api_error


@pytest.fixture
def supabase(monkeypatch):
    """Point the API at a fake Supabase and record the requests it makes."""
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    from app.config import get_settings
    get_settings.cache_clear()
    state = {"requests": [], "user_status": 200, "user_id": str(uuid.uuid4()), "admin_status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if request.url.path == "/auth/v1/user":
            if state["user_status"] != 200:
                return httpx.Response(state["user_status"], json={"msg": "bad"})
            return httpx.Response(200, json={"id": state["user_id"], "email": "a@b.com"})
        if request.url.path == "/auth/v1/admin/users" and request.method == "POST":
            if state["admin_status"] != 200:
                return httpx.Response(state["admin_status"], json={"msg": "no"})
            return httpx.Response(200, json={"id": state["user_id"]})
        return httpx.Response(200, json={})

    monkeypatch.setattr(auth, "_http", httpx.Client(transport=httpx.MockTransport(handler)))
    auth._cache.clear()
    yield state
    get_settings.cache_clear()
    monkeypatch.setattr(auth, "_http", None)
    auth._cache.clear()


def test_valid_token_returns_user_id_and_sends_both_keys(supabase):
    assert auth.supabase_verify("good-token") == uuid.UUID(supabase["user_id"])
    sent = supabase["requests"][0]
    assert sent.headers["authorization"] == "Bearer good-token" and sent.headers["apikey"] == "anon-key"


def test_verified_tokens_are_cached_briefly(supabase):
    auth.supabase_verify("t1")
    auth.supabase_verify("t1")
    assert len(supabase["requests"]) == 1
    auth.supabase_verify("t2")
    assert len(supabase["requests"]) == 2


def test_rejected_token_is_401_and_not_cached(supabase):
    supabase["user_status"] = 401
    for _ in range(2):
        with pytest.raises(Exception) as e:
            auth.supabase_verify("expired")
        assert e.value.status_code == 401 and e.value.detail["code"] == "invalid_token"
    assert len(supabase["requests"]) == 2


def test_unreachable_login_service_is_503(monkeypatch, supabase):
    def boom(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(auth, "_http", httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(Exception) as e:
        auth.supabase_verify("anything")
    assert e.value.status_code == 503


def test_create_user_sends_service_key_and_confirms_email(supabase):
    new_id = auth.AuthAdmin().create_user("new.hire@company.com", "a-long-password")
    assert new_id == uuid.UUID(supabase["user_id"])
    sent = supabase["requests"][0]
    assert sent.headers["authorization"] == "Bearer service-key" and sent.headers["apikey"] == "service-key"
    assert json.loads(sent.content) == {"email": "new.hire@company.com", "password": "a-long-password",
                                        "email_confirm": True}


@pytest.mark.parametrize("upstream,ours", [(422, 409), (400, 409), (500, 502)])
def test_create_user_failures_map_to_clear_errors(supabase, upstream, ours):
    supabase["admin_status"] = upstream
    with pytest.raises(Exception) as e:
        auth.AuthAdmin().create_user("x@company.com", "a-long-password")
    assert e.value.status_code == ours


def test_missing_supabase_settings_are_reported_not_crashed(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(Exception) as e:
        auth.supabase_verify("anything")
    assert e.value.detail["code"] == "auth_not_configured"
    get_settings.cache_clear()
