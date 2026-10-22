"""Who is calling, and what they may see.

The database stores the rules of the workflow; this module decides, per role, which records a
caller can see and which actions they may attempt:
  admin    - everything, no restrictions
  manager  - their own team's records, plus anything they raised or are assigned
  employee - only what they raised themselves
"""
from typing import Literal
from uuid import UUID

from fastapi import Depends, Header, Request
from pydantic import BaseModel

from .auth import verified_user_id
from .db import fetch_all, fetch_one, get_conn
from .errors import api_error
from .tenant import schema_owning, use_schema, use_schemas

Role = Literal["admin", "manager", "employee"]


class Principal(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: Role
    team_id: UUID | None = None
    project_id: UUID | None = None   # the first customer (project) they are viewing; new records go here
    project_ids: list[UUID] = []     # every customer they are viewing right now
    schema_name: str | None = None   # the database schema this request writes to


def active_projects(conn, user_id: UUID, role: str, wanted: str | None) -> list[dict]:
    """The customers named by the X-Project-Id header (comma separated) that they may use; all of theirs if none."""
    if role == "admin":
        rows = fetch_all(conn, "select id, schema_name from projects where schema_name is not null order by name")
    else:
        rows = fetch_all(conn, """select p.id, p.schema_name from projects p join user_projects up on up.project_id = p.id
                                   where up.user_id = %(u)s and p.schema_name is not null order by p.name""", {"u": user_id})
    asked = {x.strip() for x in (wanted or "").split(",") if x.strip()}
    chosen = [r for r in rows if str(r["id"]) in asked]
    return chosen or rows


def _uuids(values) -> list[str]:
    out = []
    for v in values:
        try:
            out.append(str(UUID(str(v))))
        except ValueError:
            pass
    return out


def current_user(request: Request, user_id: UUID = Depends(verified_user_id), conn=Depends(get_conn),
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
    projects = active_projects(conn, row["id"], row["role"], x_project_id)
    schema = None
    if projects:
        schemas = [p["schema_name"] for p in projects]
        if request.method == "GET" and len(schemas) > 1:
            use_schemas(conn, schemas)  # read all the chosen customers together
            schema = schemas[0]
        else:  # a write goes to exactly one customer: the one that owns the record being changed
            schema = schema_owning(conn, schemas, request.url.path, _uuids(request.path_params.values())) \
                if len(schemas) > 1 else schemas[0]
            use_schema(conn, schema)
    return Principal(**{k: row[k] for k in ("id", "email", "full_name", "role", "team_id")},
                     project_id=projects[0]["id"] if projects else None,
                     project_ids=[p["id"] for p in projects], schema_name=schema)


def require_roles(*roles: Role):
    def dependency(user: Principal = Depends(current_user)) -> Principal:
        if user.role not in roles:
            raise api_error(403, "forbidden", "Your role is not allowed to do this.")
        return user

    return dependency


def visibility(user: Principal, alias: str = "i", team_col: str = "team_id", owner_col: str = "requester_id",
               assignee_col: str | None = "assignee_id") -> tuple[str, dict]:
    """SQL condition limiting records to what this user may see, plus its parameters."""
    params = {"vis_me": user.id, "vis_team": user.team_id}
    if user.role == "admin":
        return "true", {}
    if user.role == "manager":
        parts = [f"{alias}.{team_col} = %(vis_team)s", f"{alias}.{owner_col} = %(vis_me)s"]
        if assignee_col:
            parts.append(f"{alias}.{assignee_col} = %(vis_me)s")
        return "(" + " or ".join(parts) + ")", params
    return f"{alias}.{owner_col} = %(vis_me)s", params


def can_manage(user: Principal, record: dict) -> bool:
    """May this user act as the working owner of the record (assign, edit all fields, move it on)?"""
    if user.role == "admin":
        return True
    if user.role == "manager":
        return record.get("team_id") == user.team_id or record.get("assignee_id") == user.id
    return False
