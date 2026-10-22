"""Defects: bugs found in a service. Raise, view, edit, assign, move through the workflow, comment, activity.

Handled like incidents, with no approval step and no SLA clock. The database enforces the workflow itself
(allowed moves, resolution notes). This module decides who may attempt what:
  employee - raises defects, edits their own while still New, comments, and confirms (closes) or
             reopens their own resolved defect
  manager  - works their team's defects: assign, edit everything, move through the workflow
  admin    - no restrictions
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..activity import attachment_events, timeline
from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, can_manage, current_user, require_roles, visibility

router = APIRouter(tags=["defects"])

Severity = Literal["Critical", "High", "Medium", "Low"]
Environment = Literal["Production", "UAT"]
NOT_OPEN = "('Resolved','Closed')"  # work finished

SELECT = """
select d.id, d.number, d.title, d.description, d.steps_to_reproduce, d.expected_result, d.actual_result,
       d.status, d.severity::text as severity, d.environment::text as environment, d.resolution_notes,
       d.service_id, s.name as service_name,
       d.team_id, t.name as team_name,
       d.raised_by, rb.full_name as raised_by_name,
       d.assignee_id, asg.full_name as assignee_name,
       d.resolved_at, d.closed_at, d.created_at, d.updated_at
from defects d
left join services s on s.id = d.service_id
left join teams t on t.id = d.team_id
join profiles rb on rb.id = d.raised_by
left join profiles asg on asg.id = d.assignee_id
"""


def _vis(user: Principal) -> tuple[str, dict]:
    return visibility(user, alias="d", owner_col="raised_by", assignee_col="assignee_id")


def load(conn, user: Principal, defect_id: UUID) -> dict:
    """The defect, if this user is allowed to see it; otherwise 404 (we do not reveal that it exists)."""
    vis, params = _vis(user)
    row = fetch_one(conn, SELECT + f" where d.id = %(id)s and {vis}", {"id": defect_id, **params})
    if row is None:
        raise api_error(404, "not_found", "Defect not found.")
    return row


# ---- list / read ---------------------------------------------------------------------------

@router.get("/defects")
def list_defects(
    status: str | None = None,
    severity: Severity | None = None,
    environment: Environment | None = None,
    team_id: UUID | None = None,
    assignee_id: UUID | None = None,
    service_id: UUID | None = None,
    q: str | None = Query(default=None, description="matches the number or the title"),
    mine: bool = Query(default=False, description="only defects I raised or am assigned"),
    open_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Principal = Depends(current_user),
    conn=Depends(get_conn),
):
    vis, vp = _vis(user)
    where = f"""{vis}
        and (%(status)s::text is null or d.status = %(status)s)
        and (%(severity)s::text is null or d.severity::text = %(severity)s)
        and (%(env)s::text is null or d.environment::text = %(env)s)
        and (%(team)s::uuid is null or d.team_id = %(team)s)
        and (%(assignee)s::uuid is null or d.assignee_id = %(assignee)s)
        and (%(service)s::uuid is null or d.service_id = %(service)s)
        and (%(q)s::text is null or d.number ilike %(q)s or d.title ilike %(q)s)
        and (not %(mine)s or d.raised_by = %(me)s or d.assignee_id = %(me)s)
        and (not %(open_only)s or d.status not in {NOT_OPEN})"""
    params = {**vp, "status": status, "severity": severity, "env": environment, "team": team_id,
              "assignee": assignee_id, "service": service_id, "q": f"%{q}%" if q else None, "mine": mine,
              "me": user.id, "open_only": open_only, "limit": limit, "offset": offset}
    total = fetch_one(conn, f"select count(*) as n from defects d where {where}", params)["n"]
    items = fetch_all(conn, SELECT + f" where {where} order by d.created_at desc, d.id limit %(limit)s offset %(offset)s",
                      params)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/defects/{defect_id}")
def get_defect(defect_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    d = load(conn, user, defect_id)
    d["can_manage"] = can_manage(user, d)
    return d


# ---- create / edit -------------------------------------------------------------------------

class DefectIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    steps_to_reproduce: str | None = Field(default=None, max_length=10000)
    expected_result: str | None = Field(default=None, max_length=10000)
    actual_result: str | None = Field(default=None, max_length=10000)
    service_id: UUID | None = None
    severity: Severity = "Medium"
    environment: Environment = "Production"


class DefectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    steps_to_reproduce: str | None = Field(default=None, max_length=10000)
    expected_result: str | None = Field(default=None, max_length=10000)
    actual_result: str | None = Field(default=None, max_length=10000)
    service_id: UUID | None = None
    severity: Severity | None = None
    environment: Environment | None = None


STAFF_ONLY_FIELDS = {"severity"}


@router.post("/defects", status_code=201)
def create_defect(body: DefectIn, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    """Number, team and status are set by the database."""
    row = fetch_one(
        conn,
        """insert into defects(title, description, steps_to_reproduce, expected_result, actual_result, service_id,
                               severity, environment, raised_by, updated_by, project_id)
           values (%(title)s, %(description)s, %(steps_to_reproduce)s, %(expected_result)s, %(actual_result)s,
                   %(service_id)s, %(severity)s, %(environment)s, %(uid)s, %(uid)s, %(proj)s) returning id""",
        {**body.model_dump(), "uid": user.id, "proj": user.project_id},
    )
    d = load(conn, user, row["id"])
    d["can_manage"] = can_manage(user, d)
    return d


@router.patch("/defects/{defect_id}")
def update_defect(defect_id: UUID, body: DefectPatch, user: Principal = Depends(current_user),
                  conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    d = load(conn, user, defect_id)
    if d["status"] == "Closed":
        raise api_error(409, "defect_closed", "A closed defect cannot be edited.")
    own_while_new = (d["raised_by"] == user.id and d["status"] == "New"
                     and not (set(changes) & STAFF_ONLY_FIELDS))
    if not (can_manage(user, d) or own_while_new):
        raise api_error(403, "forbidden", "You can only edit your own defect while it is New, "
                                          "and not its severity.")
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    conn.execute(f"update defects set {sets}, updated_by = %(uid)s where id = %(id)s",
                 {**changes, "uid": user.id, "id": defect_id})
    return get_defect(defect_id, user, conn)


# ---- assign / move through the workflow ----------------------------------------------------

class AssignIn(BaseModel):
    assignee_id: UUID


@router.post("/defects/{defect_id}/assign")
def assign_defect(defect_id: UUID, body: AssignIn, user: Principal = Depends(require_roles("admin", "manager")),
                  conn=Depends(get_conn)):
    """Assigning a New defect moves it to Assigned."""
    d = load(conn, user, defect_id)
    if not can_manage(user, d):
        raise api_error(403, "forbidden", "You can only assign defects of your own team.")
    if d["status"] == "Closed":
        raise api_error(409, "defect_closed", "A closed defect cannot be reassigned.")
    target = fetch_one(conn, "select id, role, team_id from profiles where id = %(id)s and status = 'active'",
                       {"id": body.assignee_id})
    if target is None or target["role"] not in ("manager", "admin"):
        raise api_error(422, "invalid_assignee", "Defects can only be assigned to an active Support Engineer or Administrator.")
    if user.role == "manager" and target["role"] == "manager" and target["team_id"] != user.team_id:
        raise api_error(422, "invalid_assignee", "You can only assign to your own team's Support Engineer or to an Administrator.")
    conn.execute(
        """update defects
              set assignee_id = %(a)s, updated_by = %(uid)s,
                  status = case when status = 'New' then 'Assigned' else status end
            where id = %(id)s""",
        {"a": body.assignee_id, "uid": user.id, "id": defect_id},
    )
    return get_defect(defect_id, user, conn)


class TransitionIn(BaseModel):
    to_status: Literal["Assigned", "In Progress", "Pending", "Resolved", "Closed"]
    resolution_notes: str | None = Field(default=None, max_length=10000)


@router.post("/defects/{defect_id}/transition")
def transition_defect(defect_id: UUID, body: TransitionIn, user: Principal = Depends(current_user),
                      conn=Depends(get_conn)):
    """Move the defect to its next state. Invalid moves are refused by the database with a clear message.

    Resolved -> Closed directly (no approval). Resolved -> In Progress reopens it.
    """
    d = load(conn, user, defect_id)
    staff = can_manage(user, d)
    if not staff:
        own = d["raised_by"] == user.id
        confirm = body.to_status == "Closed"
        reopen = body.to_status == "In Progress"
        if not (own and d["status"] == "Resolved" and (confirm or reopen)):
            raise api_error(403, "forbidden", "You can only confirm (close) or reopen your own resolved defect.")
    conn.execute(
        """update defects set status = %(to)s, resolution_notes = coalesce(%(notes)s, resolution_notes),
                  updated_by = %(uid)s where id = %(id)s""",
        {"to": body.to_status, "notes": body.resolution_notes if staff else None, "uid": user.id, "id": defect_id},
    )
    return get_defect(defect_id, user, conn)


# ---- comments and activity -----------------------------------------------------------------

class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    internal: bool = Field(default=False, description="staff-only note, hidden from the reporter")


@router.get("/defects/{defect_id}/comments")
def list_comments(defect_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    d = load(conn, user, defect_id)
    return fetch_all(
        conn,
        """select c.id, c.body, c.internal, c.created_at, c.author_id, p.full_name as author_name, p.role as author_role
             from defect_comments c join profiles p on p.id = c.author_id
            where c.defect_id = %(id)s and (%(staff)s or not c.internal)
            order by c.created_at desc, c.id""",
        {"id": defect_id, "staff": can_manage(user, d)},
    )


@router.post("/defects/{defect_id}/comments", status_code=201)
def add_comment(defect_id: UUID, body: CommentIn, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    d = load(conn, user, defect_id)
    if body.internal and not can_manage(user, d):
        raise api_error(403, "forbidden", "Only the team handling the defect can add internal notes.")
    return fetch_one(
        conn,
        """with c as (insert into defect_comments(defect_id, author_id, body, internal)
                      values (%(i)s, %(a)s, %(b)s, %(int)s) returning *)
           select c.id, c.body, c.internal, c.created_at, c.author_id, p.full_name as author_name, p.role as author_role
             from c join profiles p on p.id = c.author_id""",
        {"i": defect_id, "a": user.id, "b": body.body, "int": body.internal},
    )


@router.get("/defects/{defect_id}/activity")
def activity(defect_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    """Timeline for the Activity tab: creation, status/assignee/severity changes and notes, newest first."""
    d = load(conn, user, defect_id)
    events = timeline(conn, "defects", defect_id, owner_key="assignee_id", owner_label="Assigned to")
    events += attachment_events(conn, user, "defect", defect_id, d)
    for c in list_comments(defect_id, user, conn):
        events.append({"at": c["created_at"], "type": "note", "actor": c["author_name"], "text": c["body"],
                       "internal": c["internal"]})
    events.sort(key=lambda e: e["at"], reverse=True)
    return events
