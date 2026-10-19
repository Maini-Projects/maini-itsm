"""Sign in, refresh a session, change a password. The front end only ever talks to this API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import AuthAdmin, AuthClient, get_auth_admin, get_auth_client
from ..errors import api_error
from ..rbac import Principal, current_user

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)  # Supabase checks the address itself
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/auth/login")
def login(body: LoginIn, auth: AuthClient = Depends(get_auth_client)):
    """Exchange email + password for a session: {access_token, refresh_token, expires_in}."""
    session = auth.login(body.email, body.password)
    if session is None:
        raise api_error(401, "invalid_credentials", "Incorrect email or password.")
    return session


@router.post("/auth/refresh")
def refresh(body: RefreshIn, auth: AuthClient = Depends(get_auth_client)):
    session = auth.refresh(body.refresh_token)
    if session is None:
        raise api_error(401, "invalid_token", "Your session has expired. Please sign in again.")
    return session


@router.post("/auth/password")
def change_password(body: PasswordIn, user: Principal = Depends(current_user),
                    auth: AuthClient = Depends(get_auth_client), auth_admin: AuthAdmin = Depends(get_auth_admin)):
    """Change your own password; the current one must be right."""
    if auth.login(user.email, body.current_password) is None:
        raise api_error(422, "wrong_password", "The current password is not correct.")
    if body.new_password == body.current_password:
        raise api_error(422, "same_password", "Choose a password different from the current one.")
    auth_admin.set_password(user.id, body.new_password)
    return {"status": "ok"}
