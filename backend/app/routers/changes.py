"""Change requests. Managers raise them, an admin approves them (see approvals.py).

  everyone - can read every change (list, detail, activity) so the whole organisation sees what is planned
  manager  - raises changes; edits and moves their own team's changes (edit only while Draft)
  admin    - no restrictions (may edit until Closed)
  employee - read-only
The database enforces the workflow; the approval step (Approval Pending -> Scheduled / Draft) is
done only through /approvals/{id}/decision.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..activity import timeline
from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, can_manage, current_user, require_roles

router = APIRouter(tags=["changes"])
staff_only = require_roles("admin", "manager")

Level = Literal["High", "Medium", "Low"]
ChangeType = Literal["Standard", "Normal", "Emergency"]

SELECT = """
select c.id, c.number, c.title, c.type::text as type, c.risk::text as risk, c.status,
       c.service_id, s.name as service_name, c.team_id, t.name as team_name,
       c.requester_id, rq.full_name as requester_name, c.requester_id as assignee_id,
       c.implementation_plan, c.test_plan, c.backout_plan, c.planned_start, c.planned_end,
       c.created_at, c.updated_at
from changes c
left join services s on s.id = c.service_id
left join teams t on t.id = c.team_id
join profiles rq on rq.id = c.requester_id
"""


def _vis(user: Principal) -> tuple[str, dict]:
    """Reading is open to the whole organisation; changing is limited by can_manage and staff_only."""
    return "true", {}


def load(conn, user: Principal, change_id: UUID) -> dict:
    vis, params = _vis(user)
    row = fetch_one(conn, SELECT + f" where c.id = %(id)s and {vis}", {"id": change_id, **params})
    if row is None:
        raise api_error(404, "not_found", "Change not found.")
    return row


def _detail(conn, user: Principal, change_id: UUID) -> dict:
    chg = load(conn, user, change_id)
    chg["can_manage"] = can_manage(user, chg)
    chg["releases"] = fetch_all(
        conn, """select r.id, r.number, r.name from release_changes rc join releases r on r.id = rc.release_id
                  where rc.change_id = %(id)s order by r.number""", {"id": change_id})
    chg["approvals"] = fetch_all(
        conn, """select a.id, a.status, a.created_at, a.decided_at, a.comment, a.decided_by,
                        d.full_name as decided_by_name
                   from approvals a left join profiles d on d.id = a.decided_by
                  where a.record_type = 'change' and a.record_id = %(id)s order by a.created_at desc, a.id""",
        {"id": change_id})
    return chg


# ---- list / read ---------------------------------------------------------------------------

@router.get("/changes")
def list_changes(
    status: str | None = None,
    type: ChangeType | None = None,
    risk: Level | None = None,
    q: str | None = Query(default=None, description="matches the number or the title"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Principal = Depends(current_user),
    conn=Depends(get_conn),
):
    vis, vp = _vis(user)
    where = f"""{vis}
        and (%(status)s::text is null or c.status = %(status)s)
        and (%(type)s::text is null or c.type::text = %(type)s)
        and (%(risk)s::text is null or c.risk::text = %(risk)s)
        and (%(q)s::text is null or c.number ilike %(q)s or c.title ilike %(q)s)"""
    params = {**vp, "status": status, "type": type, "risk": risk, "q": f"%{q}%" if q else None,
              "limit": limit, "offset": offset}
    total = fetch_one(conn, f"select count(*) as n from changes c where {where}", params)["n"]
    items = fetch_all(conn, SELECT + f" where {where} order by c.created_at desc, c.id limit %(limit)s offset %(offset)s",
                      params)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/changes/{change_id}")
def get_change(change_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    return _detail(conn, user, change_id)


@router.get("/changes/{change_id}/activity")
def change_activity(change_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    load(conn, user, change_id)
    return timeline(conn, "changes", change_id)


# ---- create / edit -------------------------------------------------------------------------

class ChangeIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    type: ChangeType = "Normal"
    risk: Level = "Medium"
    service_id: UUID | None = None
    implementation_plan: str | None = Field(default=None, max_length=10000)
    test_plan: str | None = Field(default=None, max_length=10000)
    backout_plan: str | None = Field(default=None, max_length=10000)
    planned_start: datetime | None = None
    planned_end: datetime | None = None


class ChangePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    type: ChangeType | None = None
    risk: Level | None = None
    service_id: UUID | None = None
    implementation_plan: str | None = Field(default=None, max_length=10000)
    test_plan: str | None = Field(default=None, max_length=10000)
    backout_plan: str | None = Field(default=None, max_length=10000)
    planned_start: datetime | None = None
    planned_end: datetime | None = None


def _check_dates(start, end) -> None:
    if start and end and end < start:
        raise api_error(422, "invalid_dates", "The planned end cannot be before the planned start.")


@router.post("/changes", status_code=201)
def create_change(body: ChangeIn, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    _check_dates(body.planned_start, body.planned_end)
    row = fetch_one(
        conn,
        """insert into changes(title, type, risk, service_id, implementation_plan, test_plan, backout_plan,
                               planned_start, planned_end, requester_id, updated_by)
           values (%(title)s, %(type)s, %(risk)s, %(service_id)s, %(implementation_plan)s, %(test_plan)s,
                   %(backout_plan)s, %(planned_start)s, %(planned_end)s, %(uid)s, %(uid)s) returning id""",
        {**body.model_dump(), "uid": user.id},
    )
    return _detail(conn, user, row["id"])


@router.patch("/changes/{change_id}")
def update_change(change_id: UUID, body: ChangePatch, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    chg = load(conn, user, change_id)
    if not can_manage(user, chg):
        raise api_error(403, "forbidden", "You can only edit changes of your own team.")
    if chg["status"] == "Closed":
        raise api_error(409, "change_closed", "A closed change cannot be edited.")
    if chg["status"] != "Draft" and user.role != "admin":
        raise api_error(409, "change_locked", "A change can only be edited while it is a Draft.")
    _check_dates(changes.get("planned_start", chg["planned_start"]), changes.get("planned_end", chg["planned_end"]))
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    conn.execute(f"update changes set {sets}, updated_by = %(uid)s where id = %(id)s",
                 {**changes, "uid": user.id, "id": change_id})
    return _detail(conn, user, change_id)


# ---- workflow ------------------------------------------------------------------------------

class TransitionIn(BaseModel):
    # Scheduled / back to Draft happen only through an approval decision.
    to_status: Literal["Submitted", "Under Review", "Approval Pending", "Implementation", "Implemented", "Closed"]


@router.post("/changes/{change_id}/transition")
def transition_change(change_id: UUID, body: TransitionIn, user: Principal = Depends(staff_only),
                      conn=Depends(get_conn)):
    chg = load(conn, user, change_id)
    if not can_manage(user, chg):
        raise api_error(403, "forbidden", "You can only move changes of your own team.")
    if chg["status"] == "Approval Pending":
        raise api_error(409, "awaiting_approval", "This change is waiting for an admin's decision.")
    if body.to_status == "Approval Pending":
        missing = [label for key, label in (("implementation_plan", "implementation plan"),
                                            ("backout_plan", "backout plan"), ("planned_start", "planned start"))
                   if not (chg[key].strip() if isinstance(chg[key], str) else chg[key])]
        if missing:
            raise api_error(422, "incomplete_change", f"Add the {', '.join(missing)} before sending for approval.")
    conn.execute("update changes set status = %(to)s, updated_by = %(uid)s where id = %(id)s",
                 {"to": body.to_status, "uid": user.id, "id": change_id})
    return _detail(conn, user, change_id)
