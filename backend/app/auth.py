"""Login. The front end signs in with Supabase Auth and sends the token as 'Authorization: Bearer ...'.

This module only answers one question: which user id does this token belong to? It is a
dependency, so tests (or another identity provider later) can replace it without touching
the rest of the API.
"""
import time
from typing import Callable
from uuid import UUID

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .errors import api_error

TokenVerifier = Callable[[str], UUID]

_cache: dict[str, tuple[UUID, float]] = {}
_http: httpx.Client | None = None


def _client() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=10)
    return _http


def supabase_verify(token: str) -> UUID:
    """Ask Supabase Auth who owns the token (works for any Supabase signing-key setup)."""
    settings = get_settings()
    now = time.monotonic()
    hit = _cache.get(token)
    if hit and hit[1] > now:
        return hit[0]
    if not settings.supabase_url:
        raise api_error(500, "auth_not_configured", "SUPABASE_URL is not set.")
    try:
        resp = _client().get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key},
        )
    except httpx.HTTPError:
        raise api_error(503, "auth_unavailable", "The login service could not be reached.")
    if resp.status_code != 200:
        raise api_error(401, "invalid_token", "Your session has expired. Please sign in again.")
    user_id = UUID(resp.json()["id"])
    if len(_cache) > 2000:
        _cache.clear()
    _cache[token] = (user_id, now + settings.token_cache_seconds)
    return user_id


def get_token_verifier() -> TokenVerifier:
    return supabase_verify


_bearer = HTTPBearer(auto_error=False, description="The access token from signing in with Supabase Auth")


def bearer_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """Declared as a security scheme so the /docs page shows an Authorize button."""
    if credentials is None or not credentials.credentials.strip():
        raise api_error(401, "missing_token", "Sign in to use this service.")
    return credentials.credentials.strip()


def verified_user_id(token: str = Depends(bearer_token), verify: TokenVerifier = Depends(get_token_verifier)) -> UUID:
    return verify(token)


# ---- creating logins (admin only; needs the Supabase service-role key) -----------------------

class AuthAdmin:
    """Creates and removes Supabase logins. Replaced by a fake in tests."""

    def create_user(self, email: str, password: str) -> UUID:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise api_error(500, "auth_not_configured", "Supabase keys are not set on the server.")
        key = settings.supabase_service_role_key
        try:
            resp = _client().post(
                f"{settings.supabase_url}/auth/v1/admin/users",
                headers={"Authorization": f"Bearer {key}", "apikey": key},
                json={"email": email, "password": password, "email_confirm": True},
            )
        except httpx.HTTPError:
            raise api_error(503, "auth_unavailable", "The login service could not be reached.")
        if resp.status_code in (400, 409, 422):
            raise api_error(409, "login_exists", "A login with that email already exists or the password is too weak.")
        if resp.status_code >= 300:
            raise api_error(502, "auth_error", "The login service rejected the request.")
        return UUID(resp.json()["id"])

    def delete_user(self, user_id: UUID) -> None:
        settings = get_settings()
        key = settings.supabase_service_role_key
        try:
            _client().delete(
                f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
                headers={"Authorization": f"Bearer {key}", "apikey": key},
            )
        except httpx.HTTPError:
            pass


def get_auth_admin() -> AuthAdmin:
    return AuthAdmin()
