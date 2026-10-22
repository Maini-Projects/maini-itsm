"""User management (admin) and the list of people an incident can be assigned to."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..auth import AuthAdmin, get_auth_admin
from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, require_roles

router = APIRouter(tags=["users"])

USER_COLUMNS = """p.id, p.email, p.full_name, p.role, p.status, p.team_id, t.name as team_name, p.created_at"""


class UserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=72)
    role: Literal["admin", "manager", "employee"]
    team_id: UUID | None = None


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "manager", "employee"] | None = None
    team_id: UUID | None = None
    status: Literal["active", "disabled"] | None = None


def _get_user(conn, user_id) -> dict | None:
    return fetch_one(conn, f"select {USER_COLUMNS} from profiles p left join teams t on t.id = p.team_id "
                           "where p.id = %(id)s", {"id": user_id})


@router.get("/users")
def list_users(role: str | None = None, team_id: UUID | None = None, q: str | None = None,
               _: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    return fetch_all(
        conn,
        f"""select {USER_COLUMNS} from profiles p left join teams t on t.id = p.team_id
            where (%(role)s::text is null or p.role::text = %(role)s)
              and (%(team)s::uuid is null or p.team_id = %(team)s)
              and (%(q)s::text is null or p.full_name ilike %(q)s or p.email ilike %(q)s)
            order by p.full_name""",
        {"role": role, "team": team_id, "q": f"%{q}%" if q else None},
    )


@router.get("/users/assignable")
def assignable_users(user: Principal = Depends(require_roles("admin", "manager")), conn=Depends(get_conn)):
    """People who can work an incident: managers and admins (a manager sees their own team's manager and admins)."""
    return fetch_all(
        conn,
        f"""select {USER_COLUMNS} from profiles p left join teams t on t.id = p.team_id
            where p.status = 'active' and p.role in ('manager', 'admin')
              and (%(is_admin)s or p.role = 'admin' or p.team_id = %(team)s)
            order by p.full_name""",
        {"is_admin": user.role == "admin", "team": user.team_id},
    )


@router.post("/users", status_code=201)
def create_user(body: UserIn, _: Principal = Depends(require_roles("admin")), conn=Depends(get_conn),
                auth_admin: AuthAdmin = Depends(get_auth_admin)):
    if body.role != "admin" and body.team_id is None:
        raise api_error(422, "team_required", "Support Engineers and Customers must belong to a team.")
    login_id = auth_admin.create_user(body.email, body.password)
    try:
        conn.execute(
            """insert into profiles(id, email, full_name, role, team_id)
               values (%(id)s, %(email)s, %(name)s, %(role)s, %(team)s)""",
            {"id": login_id, "email": body.email, "name": body.full_name, "role": body.role, "team": body.team_id},
        )
    except Exception:
        auth_admin.delete_user(login_id)  # do not leave a login that has no profile
        raise
    return _get_user(conn, login_id)


@router.patch("/users/{user_id}")
def update_user(user_id: UUID, body: UserPatch, admin: Principal = Depends(require_roles("admin")),
                conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    if user_id == admin.id and (changes.get("role", "admin") != "admin" or changes.get("status", "active") != "active"):
        raise api_error(409, "cannot_modify_self", "You cannot remove your own Administrator access or disable yourself.")
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    updated = fetch_one(conn, f"update profiles set {sets} where id = %(id)s returning id", {**changes, "id": user_id})
    if updated is None:
        raise api_error(404, "not_found", "User not found.")
    return _get_user(conn, user_id)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/users/{user_id}/password")
def reset_password(user_id: UUID, body: PasswordReset, _: Principal = Depends(require_roles("admin")),
                   conn=Depends(get_conn), auth_admin: AuthAdmin = Depends(get_auth_admin)):
    """Admin sets a new password for a user (for example when they forgot theirs)."""
    if _get_user(conn, user_id) is None:
        raise api_error(404, "not_found", "User not found.")
    auth_admin.set_password(user_id, body.new_password)
    return {"status": "ok"}


# ---- sign-up requests (self sign-up waits here for an Administrator) --------------------------

class ApproveIn(BaseModel):
    role: Literal["admin", "manager", "employee"] = "employee"
    team_id: UUID | None = None


@router.get("/signup-requests")
def list_signup_requests(status: Literal["pending", "approved", "rejected", "all"] = "pending",
                         _: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    return fetch_all(conn, """select r.id, r.email, r.full_name, r.status, r.created_at, r.decided_at,
                                     d.full_name as decided_by_name
                              from signup_requests r left join profiles d on d.id = r.decided_by
                              where %(s)s = 'all' or r.status = %(s)s order by r.created_at desc""", {"s": status})


def _open_request(conn, request_id):
    row = fetch_one(conn, "select id, email, full_name from signup_requests where id = %(id)s and status = 'pending' for update",
                    {"id": request_id})
    if row is None:
        raise api_error(404, "not_found", "That sign-up request was not found or has already been decided.")
    return row


@router.post("/signup-requests/{request_id}/approve")
def approve_signup(request_id: UUID, body: ApproveIn, admin: Principal = Depends(require_roles("admin")),
                   conn=Depends(get_conn)):
    req = _open_request(conn, request_id)
    if body.role != "admin" and body.team_id is None:
        raise api_error(422, "team_required", "Choose a team for Support Engineers and Customers.")
    conn.execute(
        """insert into profiles(id, email, full_name, role, team_id)
           values (%(id)s, %(email)s, %(name)s, %(role)s, %(team)s)""",
        {"id": req["id"], "email": req["email"], "name": req["full_name"], "role": body.role,
         "team": body.team_id if body.role != "admin" else None},
    )
    conn.execute("""insert into user_projects(user_id, project_id)  -- start on the first project; an admin can change it
                    select %(id)s, id from projects order by created_at limit 1 on conflict do nothing""", {"id": req["id"]})
    conn.execute("update signup_requests set status = 'approved', decided_at = now(), decided_by = %(by)s where id = %(id)s",
                 {"by": admin.id, "id": request_id})
    return _get_user(conn, req["id"])


@router.post("/signup-requests/{request_id}/reject")
def reject_signup(request_id: UUID, admin: Principal = Depends(require_roles("admin")), conn=Depends(get_conn),
                  auth_admin: AuthAdmin = Depends(get_auth_admin)):
    _open_request(conn, request_id)
    conn.execute("update signup_requests set status = 'rejected', decided_at = now(), decided_by = %(by)s where id = %(id)s",
                 {"by": admin.id, "id": request_id})
    auth_admin.delete_user(request_id)  # frees the email so the person can ask again
    return {"status": "rejected"}
