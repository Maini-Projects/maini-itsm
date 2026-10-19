"""Releases: group changes, get admin approval, deploy and validate.

  manager  - raises releases; edits and moves their team's releases (edit only while Planned)
  admin    - no restrictions (may edit until Closed)
  employee - no access
The approval step (Under Review -> Approved / Planned) is done only through /approvals/{id}/decision.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..activity import timeline
from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, can_manage, require_roles, visibility
from . import changes as change_module

router = APIRouter(tags=["releases"])
staff_only = require_roles("admin", "manager")

Environment = Literal["Production", "UAT"]

SELECT = """
select r.id, r.number, r.name, r.environment::text as environment, r.status,
       r.service_id, s.name as service_name, r.team_id, t.name as team_name,
       r.owner_id, ow.full_name as owner_name, r.owner_id as assignee_id,
       r.scope, r.rollback_plan, r.deployment_at, r.created_at, r.updated_at
from releases r
left join services s on s.id = r.service_id
left join teams t on t.id = r.team_id
join profiles ow on ow.id = r.owner_id
"""


def _vis(user: Principal) -> tuple[str, dict]:
    return visibility(user, alias="r", owner_col="owner_id", assignee_col=None)


def load(conn, user: Principal, release_id: UUID) -> dict:
    vis, params = _vis(user)
    row = fetch_one(conn, SELECT + f" where r.id = %(id)s and {vis}", {"id": release_id, **params})
    if row is None:
        raise api_error(404, "not_found", "Release not found.")
    return row


def _detail(conn, user: Principal, release_id: UUID) -> dict:
    rel = load(conn, user, release_id)
    rel["can_manage"] = can_manage(user, rel)
    rel["changes"] = fetch_all(
        conn, """select c.id, c.number, c.title, c.risk::text as risk, c.status
                   from release_changes rc join changes c on c.id = rc.change_id
                  where rc.release_id = %(id)s order by c.number""", {"id": release_id})
    rel["approvals"] = fetch_all(
        conn, """select a.id, a.status, a.created_at, a.decided_at, a.comment, a.decided_by,
                        d.full_name as decided_by_name
                   from approvals a left join profiles d on d.id = a.decided_by
                  where a.record_type = 'release' and a.record_id = %(id)s order by a.created_at desc, a.id""",
        {"id": release_id})
    return rel


# ---- list / read ---------------------------------------------------------------------------

@router.get("/releases")
def list_releases(
    status: str | None = None,
    environment: Environment | None = None,
    q: str | None = Query(default=None, description="matches the number or the name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Principal = Depends(staff_only),
    conn=Depends(get_conn),
):
    vis, vp = _vis(user)
    where = f"""{vis}
        and (%(status)s::text is null or r.status = %(status)s)
        and (%(env)s::text is null or r.environment::text = %(env)s)
        and (%(q)s::text is null or r.number ilike %(q)s or r.name ilike %(q)s)"""
    params = {**vp, "status": status, "env": environment, "q": f"%{q}%" if q else None,
              "limit": limit, "offset": offset}
    total = fetch_one(conn, f"select count(*) as n from releases r where {where}", params)["n"]
    items = fetch_all(conn, SELECT + f" where {where} order by r.created_at desc, r.id limit %(limit)s offset %(offset)s",
                      params)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/releases/{release_id}")
def get_release(release_id: UUID, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    return _detail(conn, user, release_id)


@router.get("/releases/{release_id}/activity")
def release_activity(release_id: UUID, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    load(conn, user, release_id)
    return timeline(conn, "releases", release_id)


# ---- create / edit -------------------------------------------------------------------------

class ReleaseIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    environment: Environment = "Production"
    service_id: UUID | None = None
    scope: str | None = Field(default=None, max_length=10000)
    rollback_plan: str | None = Field(default=None, max_length=10000)
    deployment_at: datetime | None = None


class ReleasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    environment: Environment | None = None
    service_id: UUID | None = None
    scope: str | None = Field(default=None, max_length=10000)
    rollback_plan: str | None = Field(default=None, max_length=10000)
    deployment_at: datetime | None = None


@router.post("/releases", status_code=201)
def create_release(body: ReleaseIn, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    row = fetch_one(
        conn,
        """insert into releases(name, environment, service_id, scope, rollback_plan, deployment_at, owner_id, updated_by)
           values (%(name)s, %(environment)s, %(service_id)s, %(scope)s, %(rollback_plan)s, %(deployment_at)s,
                   %(uid)s, %(uid)s) returning id""",
        {**body.model_dump(), "uid": user.id},
    )
    return _detail(conn, user, row["id"])


def _check_editable(rel: dict, user: Principal) -> None:
    if not can_manage(user, rel):
        raise api_error(403, "forbidden", "You can only change releases of your own team.")
    if rel["status"] == "Closed":
        raise api_error(409, "release_closed", "A closed release cannot be changed.")
    if rel["status"] != "Planned" and user.role != "admin":
        raise api_error(409, "release_locked", "A release can only be changed while it is Planned.")


@router.patch("/releases/{release_id}")
def update_release(release_id: UUID, body: ReleasePatch, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    rel = load(conn, user, release_id)
    _check_editable(rel, user)
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    conn.execute(f"update releases set {sets}, updated_by = %(uid)s where id = %(id)s",
                 {**changes, "uid": user.id, "id": release_id})
    return _detail(conn, user, release_id)


# ---- workflow ------------------------------------------------------------------------------

class TransitionIn(BaseModel):
    # Approved / back to Planned happen only through an approval decision.
    to_status: Literal["Under Review", "Ready to Deploy", "Deployment", "Validated", "Closed"]


@router.post("/releases/{release_id}/transition")
def transition_release(release_id: UUID, body: TransitionIn, user: Principal = Depends(staff_only),
                       conn=Depends(get_conn)):
    rel = load(conn, user, release_id)
    if not can_manage(user, rel):
        raise api_error(403, "forbidden", "You can only move releases of your own team.")
    if rel["status"] == "Under Review":
        raise api_error(409, "awaiting_approval", "This release is waiting for an admin's decision.")
    if body.to_status == "Under Review":
        missing = [label for key, label in (("scope", "scope"), ("rollback_plan", "rollback plan"),
                                            ("deployment_at", "deployment date"))
                   if not (rel[key].strip() if isinstance(rel[key], str) else rel[key])]
        if missing:
            raise api_error(422, "incomplete_release", f"Add the {', '.join(missing)} before sending for review.")
    conn.execute("update releases set status = %(to)s, updated_by = %(uid)s where id = %(id)s",
                 {"to": body.to_status, "uid": user.id, "id": release_id})
    return _detail(conn, user, release_id)


# ---- changes inside a release --------------------------------------------------------------

class ChangeLinkIn(BaseModel):
    change_id: UUID


@router.post("/releases/{release_id}/changes", status_code=201)
def add_change(release_id: UUID, body: ChangeLinkIn, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    rel = load(conn, user, release_id)
    _check_editable(rel, user)
    change_module.load(conn, user, body.change_id)  # 404 unless the user may see that change
    conn.execute("insert into release_changes(release_id, change_id) values (%(r)s, %(c)s) on conflict do nothing",
                 {"r": release_id, "c": body.change_id})
    conn.execute("update releases set updated_by = %(uid)s where id = %(r)s", {"uid": user.id, "r": release_id})
    return _detail(conn, user, release_id)


@router.delete("/releases/{release_id}/changes/{change_id}")
def remove_change(release_id: UUID, change_id: UUID, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    rel = load(conn, user, release_id)
    _check_editable(rel, user)
    done = fetch_one(conn, "delete from release_changes where release_id = %(r)s and change_id = %(c)s "
                           "returning change_id", {"r": release_id, "c": change_id})
    if done is None:
        raise api_error(404, "not_found", "That change is not part of this release.")
    return _detail(conn, user, release_id)
