"""Incidents: raise, view, edit, assign, move through the workflow, comment, activity timeline.

The database enforces the workflow itself (allowed moves, resolution notes, SLA clocks). Incidents of
every priority close directly from Resolved; there is no approval step. This module decides who may
attempt what:
  employee - raises incidents, edits their own while still New, comments, and confirms (closes) or
             reopens their own resolved incident
  manager  - works their team's incidents: assign, edit everything, move through the workflow
  admin    - no restrictions
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..activity import attachment_events
from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, can_manage, current_user, require_roles, visibility

router = APIRouter(tags=["incidents"])

Level = Literal["High", "Medium", "Low"]
Priority = Literal["P1", "P2", "P3", "P4"]
# The screens pick a priority directly (shown as Critical / High / Medium / Low). The database still works the
# priority out from impact and urgency, so a chosen priority is stored as the pair that gives exactly that priority.
PRIORITY_LEVELS = {"P1": ("High", "High"), "P2": ("High", "Medium"), "P3": ("Medium", "Medium"), "P4": ("Low", "Low")}
NOT_OPEN = "('Resolved','Closed')"  # work finished

SELECT = f"""
select i.id, i.number, i.short_description, i.description, i.status, i.priority, i.impact, i.urgency,
       i.major_incident, i.resolution_notes,
       i.service_id, s.name as service_name,
       i.team_id, t.name as team_name,
       i.requester_id, rq.full_name as requester_name,
       i.assignee_id, asg.full_name as assignee_name,
       i.response_due, i.resolution_due, i.responded_at, i.resolved_at, i.closed_at,
       i.created_at, i.updated_at,
       case when i.status in {NOT_OPEN} then null
            else floor(extract(epoch from (i.resolution_due - now())) / 60)::int end as minutes_to_resolution_due,
       (i.status not in {NOT_OPEN} and i.resolution_due < now()) as sla_breached
from incidents i
left join services s on s.id = i.service_id
left join teams t on t.id = i.team_id
join profiles rq on rq.id = i.requester_id
left join profiles asg on asg.id = i.assignee_id
"""


def load(conn, user: Principal, incident_id: UUID) -> dict:
    """The incident, if this user is allowed to see it; otherwise 404 (we do not reveal that it exists)."""
    vis, params = visibility(user)
    row = fetch_one(conn, SELECT + f" where i.id = %(id)s and {vis}", {"id": incident_id, **params})
    if row is None:
        raise api_error(404, "not_found", "Incident not found.")
    return row


# ---- list / read ---------------------------------------------------------------------------

@router.get("/incidents")
def list_incidents(
    status: str | None = None,
    priority: Priority | None = None,
    team_id: UUID | None = None,
    assignee_id: UUID | None = None,
    service_id: UUID | None = None,
    q: str | None = Query(default=None, description="matches the number or the short description"),
    mine: bool = Query(default=False, description="only incidents I raised or am assigned"),
    open_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Principal = Depends(current_user),
    conn=Depends(get_conn),
):
    vis, vp = visibility(user)
    where = f"""{vis}
        and (%(status)s::text is null or i.status = %(status)s)
        and (%(priority)s::text is null or i.priority::text = %(priority)s)
        and (%(team)s::uuid is null or i.team_id = %(team)s)
        and (%(assignee)s::uuid is null or i.assignee_id = %(assignee)s)
        and (%(service)s::uuid is null or i.service_id = %(service)s)
        and (%(q)s::text is null or i.number ilike %(q)s or i.short_description ilike %(q)s)
        and (not %(mine)s or i.requester_id = %(me)s or i.assignee_id = %(me)s)
        and (not %(open_only)s or i.status not in {NOT_OPEN})"""
    params = {**vp, "status": status, "priority": priority, "team": team_id, "assignee": assignee_id,
              "service": service_id, "q": f"%{q}%" if q else None, "mine": mine, "me": user.id,
              "open_only": open_only, "limit": limit, "offset": offset}
    total = fetch_one(conn, f"select count(*) as n from incidents i where {where}", params)["n"]
    items = fetch_all(conn, SELECT + f" where {where} order by i.created_at desc, i.id limit %(limit)s offset %(offset)s",
                      params)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    inc = load(conn, user, incident_id)
    inc["can_manage"] = can_manage(user, inc)
    return inc


# ---- create / edit -------------------------------------------------------------------------

class IncidentIn(BaseModel):
    short_description: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    service_id: UUID | None = None
    priority: Priority | None = Field(default=None, description="P1 Critical, P2 High, P3 Medium (default), P4 Low")
    impact: Level | None = Field(default=None, description="optional; only used when priority is not given")
    urgency: Level | None = Field(default=None, description="optional; only used when priority is not given")
    requester_id: UUID | None = Field(default=None, description="admin only: raise on someone else's behalf")


class IncidentPatch(BaseModel):
    short_description: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    service_id: UUID | None = None
    priority: Priority | None = None
    impact: Level | None = None
    urgency: Level | None = None
    major_incident: bool | None = None


STAFF_ONLY_FIELDS = {"priority", "impact", "urgency", "major_incident"}


@router.post("/incidents", status_code=201)
def create_incident(body: IncidentIn, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    """Team, number and SLA deadlines are set by the database. Send `priority` (default P3 Medium)."""
    requester = body.requester_id or user.id
    if requester != user.id and user.role != "admin":
        raise api_error(403, "forbidden", "Only an Administrator can raise an incident for someone else.")
    impact, urgency = PRIORITY_LEVELS[body.priority] if body.priority else (body.impact or "Medium", body.urgency or "Medium")
    row = fetch_one(
        conn,
        """insert into incidents(short_description, description, service_id, impact, urgency, requester_id, updated_by, project_id)
           values (%(sd)s, %(d)s, %(svc)s, %(imp)s, %(urg)s, %(req)s, %(uid)s, %(proj)s) returning id""",
        {"sd": body.short_description, "d": body.description, "svc": body.service_id, "imp": impact,
         "urg": urgency, "req": requester, "uid": user.id, "proj": user.project_id},
    )
    return load(conn, user, row["id"])


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: UUID, body: IncidentPatch, user: Principal = Depends(current_user),
                    conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    inc = load(conn, user, incident_id)
    if inc["status"] == "Closed":
        raise api_error(409, "incident_closed", "A closed incident cannot be edited.")
    own_while_new = (inc["requester_id"] == user.id and inc["status"] == "New"
                     and not (set(changes) & STAFF_ONLY_FIELDS))
    if not (can_manage(user, inc) or own_while_new):
        raise api_error(403, "forbidden", "You can only edit your own incident while it is New, "
                                          "and only its description and service.")
    if "priority" in changes:  # a chosen priority is stored as the impact/urgency pair that gives it
        chosen = changes.pop("priority")
        if chosen:
            changes["impact"], changes["urgency"] = PRIORITY_LEVELS[chosen]
        if not changes:
            return load(conn, user, incident_id)
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    conn.execute(f"update incidents set {sets}, updated_by = %(uid)s where id = %(id)s",
                 {**changes, "uid": user.id, "id": incident_id})
    return load(conn, user, incident_id)


# ---- assign / move through the workflow ----------------------------------------------------

class AssignIn(BaseModel):
    assignee_id: UUID


@router.post("/incidents/{incident_id}/assign")
def assign_incident(incident_id: UUID, body: AssignIn, user: Principal = Depends(require_roles("admin", "manager")),
                    conn=Depends(get_conn)):
    """Assigning a New incident moves it to Assigned."""
    inc = load(conn, user, incident_id)
    if not can_manage(user, inc):
        raise api_error(403, "forbidden", "You can only assign incidents of your own team.")
    if inc["status"] == "Closed":
        raise api_error(409, "incident_closed", "A closed incident cannot be reassigned.")
    target = fetch_one(conn, "select id, role, team_id from profiles where id = %(id)s and status = 'active'",
                       {"id": body.assignee_id})
    if target is None or target["role"] not in ("manager", "admin"):
        raise api_error(422, "invalid_assignee", "Incidents can only be assigned to an active Support Engineer or Administrator.")
    if user.role == "manager" and target["role"] == "manager" and target["team_id"] != user.team_id:
        raise api_error(422, "invalid_assignee", "You can only assign to your own team's Support Engineer or to an Administrator.")
    conn.execute(
        """update incidents
              set assignee_id = %(a)s, updated_by = %(uid)s,
                  status = case when status = 'New' then 'Assigned' else status end
            where id = %(id)s""",
        {"a": body.assignee_id, "uid": user.id, "id": incident_id},
    )
    return load(conn, user, incident_id)


class TransitionIn(BaseModel):
    to_status: Literal["Assigned", "In Progress", "Pending", "Resolved", "Closed"]
    resolution_notes: str | None = Field(default=None, max_length=10000)


@router.post("/incidents/{incident_id}/transition")
def transition_incident(incident_id: UUID, body: TransitionIn, user: Principal = Depends(current_user),
                        conn=Depends(get_conn)):
    """Move the incident to its next state. Invalid moves are refused by the database with a clear message.

    Every priority: Resolved -> Closed directly (no approval). Resolved -> In Progress reopens it.
    """
    inc = load(conn, user, incident_id)
    staff = can_manage(user, inc)
    if not staff:
        own = inc["requester_id"] == user.id
        confirm = body.to_status == "Closed"
        reopen = body.to_status == "In Progress"
        if not (own and inc["status"] == "Resolved" and (confirm or reopen)):
            raise api_error(403, "forbidden", "You can only confirm (close) or reopen your own resolved incident.")
    conn.execute(
        """update incidents set status = %(to)s, resolution_notes = coalesce(%(notes)s, resolution_notes),
                  updated_by = %(uid)s where id = %(id)s""",
        {"to": body.to_status, "notes": body.resolution_notes if staff else None, "uid": user.id, "id": incident_id},
    )
    return load(conn, user, incident_id)


# ---- comments and activity -----------------------------------------------------------------

class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    internal: bool = Field(default=False, description="staff-only note, hidden from the requester")


@router.get("/incidents/{incident_id}/comments")
def list_comments(incident_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    inc = load(conn, user, incident_id)
    return fetch_all(
        conn,
        """select c.id, c.body, c.internal, c.created_at, c.author_id, p.full_name as author_name, p.role as author_role
             from incident_comments c join profiles p on p.id = c.author_id
            where c.incident_id = %(id)s and (%(staff)s or not c.internal)
            order by c.created_at desc, c.id""",
        {"id": incident_id, "staff": can_manage(user, inc)},
    )


@router.post("/incidents/{incident_id}/comments", status_code=201)
def add_comment(incident_id: UUID, body: CommentIn, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    inc = load(conn, user, incident_id)
    if body.internal and not can_manage(user, inc):
        raise api_error(403, "forbidden", "Only the team handling the incident can add internal notes.")
    return fetch_one(
        conn,
        """with c as (insert into incident_comments(incident_id, author_id, body, internal)
                      values (%(i)s, %(a)s, %(b)s, %(int)s) returning *)
           select c.id, c.body, c.internal, c.created_at, c.author_id, p.full_name as author_name, p.role as author_role
             from c join profiles p on p.id = c.author_id""",
        {"i": incident_id, "a": user.id, "b": body.body, "int": body.internal},
    )


@router.get("/incidents/{incident_id}/activity")
def activity(incident_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    """Timeline for the Activity tab: creation, status/assignee/priority changes and notes, newest first."""
    inc = load(conn, user, incident_id)
    audit = fetch_all(
        conn,
        """select a.at, a.action, p.full_name as actor_name,
                  a.old_values ->> 'status' as old_status,     a.new_values ->> 'status' as new_status,
                  a.old_values ->> 'assignee_id' as old_assignee, a.new_values ->> 'assignee_id' as new_assignee,
                  a.old_values ->> 'priority' as old_priority, a.new_values ->> 'priority' as new_priority
             from audit_log a left join profiles p on p.id = a.actor_id
            where a.table_name = 'incidents' and a.record_id = %(id)s
            order by a.id desc""",
        {"id": incident_id},
    )
    ids = {r[k] for r in audit for k in ("old_assignee", "new_assignee") if r[k]}
    names = {}
    if ids:
        names = {str(r["id"]): r["full_name"] for r in
                 fetch_all(conn, "select id, full_name from profiles where id = any(%(ids)s::uuid[])",
                           {"ids": list(ids)})}
    events = []
    for r in audit:
        who = r["actor_name"] or "System"
        if r["action"] == "INSERT":
            events.append({"at": r["at"], "type": "created", "actor": who, "text": "Incident created"})
            continue
        if r["old_status"] != r["new_status"]:
            events.append({"at": r["at"], "type": "status", "actor": who,
                           "text": f"Status changed from {r['old_status']} to {r['new_status']}"})
        if r["old_assignee"] != r["new_assignee"]:
            events.append({"at": r["at"], "type": "assignment", "actor": who,
                           "text": f"Assigned to {names.get(r['new_assignee'], 'nobody')}"})
        if r["old_priority"] != r["new_priority"]:
            events.append({"at": r["at"], "type": "priority", "actor": who,
                           "text": f"Priority changed from {r['old_priority']} to {r['new_priority']}"})
    for c in list_comments(incident_id, user, conn):
        events.append({"at": c["created_at"], "type": "note", "actor": c["author_name"], "text": c["body"],
                       "internal": c["internal"]})
    events += attachment_events(conn, user, "incident", incident_id, inc)
    events.sort(key=lambda e: e["at"], reverse=True)
    return events
