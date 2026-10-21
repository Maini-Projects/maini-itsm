"""Sign in, refresh a session, change a password. The front end only ever talks to this API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..auth import AuthAdmin, AuthClient, get_auth_admin, get_auth_client
from ..db import fetch_one, get_conn
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
def login(body: LoginIn, auth: AuthClient = Depends(get_auth_client), conn=Depends(get_conn)):
    """Exchange email + password for a session: {access_token, refresh_token, expires_in}."""
    session = auth.login(body.email, body.password)
    if session is None:
        raise api_error(401, "invalid_credentials", "Incorrect email or password.")
    # the password is right: tell people who have no profile yet why they cannot come in
    email = body.email.strip().lower()
    if fetch_one(conn, "select 1 from profiles where lower(email) = %(e)s", {"e": email}) is None:
        req = fetch_one(conn, "select status from signup_requests where lower(email) = %(e)s order by created_at desc limit 1",
                        {"e": email})
        if req and req["status"] == "pending":
            raise api_error(403, "account_pending", "Your sign-up request is waiting for Administrator approval.")
        if req and req["status"] == "rejected":
            raise api_error(403, "account_rejected", "Your sign-up request was not approved.")
    return session


class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=72)


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, conn=Depends(get_conn), auth_admin: AuthAdmin = Depends(get_auth_admin)):
    """Self sign-up. The login is created but cannot use the portal until an Administrator approves the request
    (and chooses the role and team)."""
    email = str(body.email).lower()
    if fetch_one(conn, "select id from profiles where lower(email) = %(e)s", {"e": email}) or fetch_one(
            conn, "select id from signup_requests where lower(email) = %(e)s and status = 'pending'", {"e": email}):
        raise api_error(409, "login_exists", "A login with that email already exists or is waiting for approval.")
    login_id = auth_admin.create_user(email, body.password)
    try:
        conn.execute("delete from signup_requests where lower(email) = %(e)s and status = 'rejected'", {"e": email})
        conn.execute("insert into signup_requests(id, email, full_name) values (%(id)s, %(e)s, %(n)s)",
                     {"id": login_id, "e": email, "n": body.full_name.strip()})
    except Exception:
        auth_admin.delete_user(login_id)  # do not leave a login with no request
        raise
    return {"status": "pending_approval"}


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
