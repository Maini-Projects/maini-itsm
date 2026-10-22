"""Who is calling, and what they may see.

The database stores the rules of the workflow; this module decides, per role, which records a
caller can see and which actions they may attempt:
  admin    - everything, no restrictions
  manager  - their own team's records, plus anything they raised or are assigned
  employee - only what they raised themselves
"""
from typing import Literal
from uuid import UUID

from fastapi import Depends, Header
from pydantic import BaseModel

from .auth import verified_user_id
from .db import fetch_all, fetch_one, get_conn
from .errors import api_error

Role = Literal["admin", "manager", "employee"]


class Principal(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: Role
    team_id: UUID | None = None
    project_id: UUID | None = None  # where new records go: the first project they are viewing
    project_ids: list[UUID] = []  # every project they are viewing right now


def active_projects(conn, user_id: UUID, role: str, wanted: str | None) -> list[UUID]:
    """The projects named by the X-Project-Id header (comma separated) that they may use, else their first one."""
    if role == "admin":
        rows = fetch_all(conn, "select id from projects order by name")
    else:
        rows = fetch_all(conn, """select p.id from projects p join user_projects up on up.project_id = p.id
                                   where up.user_id = %(u)s order by p.name""", {"u": user_id})
    ids = [r["id"] for r in rows]
    asked = {x.strip() for x in (wanted or "").split(",") if x.strip()}
    chosen = [i for i in ids if str(i) in asked]
    return chosen or ids  # nothing chosen yet: show all of their projects


def _scope_projects(conn, row, wanted) -> dict:
    ids = active_projects(conn, row["id"], row["role"], wanted)
    return {"project_id": ids[0] if ids else None, "project_ids": ids}


def current_user(user_id: UUID = Depends(verified_user_id), conn=Depends(get_conn),
                 x_project_id: str | None = Header(default=None)) -> Principal:
    row = fetch_one(
        conn,
        "select id, email, full_name, role, team_id, status from profiles where id = %(id)s",
        {"id": user_id},
    )
    if row is None:
        raise api_error(403, "no_profile", "This login has no profile in the portal. Ask an Administrator.")
    if row["status"] != "active":
        raise api_error(403, "account_not_active", "This account is not active.")
    return Principal(**{k: row[k] for k in ("id", "email", "full_name", "role", "team_id")},
                     **_scope_projects(conn, row, x_project_id))


def require_roles(*roles: Role):
    def dependency(user: Principal = Depends(current_user)) -> Principal:
        if user.role not in roles:
            raise api_error(403, "forbidden", "Your role is not allowed to do this.")
        return user

    return dependency


def visibility(user: Principal, alias: str = "i", team_col: str = "team_id", owner_col: str = "requester_id",
               assignee_col: str | None = "assignee_id") -> tuple[str, dict]:
    """SQL condition limiting records to what this user may see, plus its parameters."""
    params = {"vis_me": user.id, "vis_team": user.team_id, "vis_proj": user.project_ids}
    in_project = f"{alias}.project_id = any(%(vis_proj)s)"
    if user.role == "admin":
        return in_project, params
    if user.role == "manager":
        parts = [f"{alias}.{team_col} = %(vis_team)s", f"{alias}.{owner_col} = %(vis_me)s"]
        if assignee_col:
            parts.append(f"{alias}.{assignee_col} = %(vis_me)s")
        return f"{in_project} and (" + " or ".join(parts) + ")", params
    return f"{in_project} and {alias}.{owner_col} = %(vis_me)s", params


def can_manage(user: Principal, record: dict) -> bool:
    """May this user act as the working owner of the record (assign, edit all fields, move it on)?"""
    if user.role == "admin":
        return True
    if user.role == "manager":
        return record.get("team_id") == user.team_id or record.get("assignee_id") == user.id
    return False
