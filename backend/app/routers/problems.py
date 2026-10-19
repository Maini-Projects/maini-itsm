"""Problems: investigate recurring incidents, record root cause, workaround and permanent fix.

  employee - raises problems and sees/edits (while Identified) the ones they raised
  manager  - works their team's problems: owner, all fields, workflow, linking incidents
  admin    - no restrictions
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..activity import timeline
from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, can_manage, current_user, require_roles, visibility
from . import incidents as incident_module

router = APIRouter(tags=["problems"])

Priority = Literal["P1", "P2", "P3", "P4"]
FINISHED = "('Resolved','Closed')"

SELECT = """
select p.id, p.number, p.title, p.description, p.status, p.priority::text as priority,
       p.service_id, s.name as service_name, p.team_id, t.name as team_name,
       p.raised_by, rb.full_name as raised_by_name,
       p.owner_id, ow.full_name as owner_name, p.owner_id as assignee_id,
       p.root_cause, p.workaround, p.permanent_solution, p.created_at, p.updated_at,
       (select count(*) from problem_incidents pi where pi.problem_id = p.id) as related_incidents
from problems p
left join services s on s.id = p.service_id
left join teams t on t.id = p.team_id
join profiles rb on rb.id = p.raised_by
left join profiles ow on ow.id = p.owner_id
"""


def _vis(user: Principal) -> tuple[str, dict]:
    return visibility(user, alias="p", owner_col="raised_by", assignee_col="owner_id")


def load(conn, user: Principal, problem_id: UUID) -> dict:
    vis, params = _vis(user)
    row = fetch_one(conn, SELECT + f" where p.id = %(id)s and {vis}", {"id": problem_id, **params})
    if row is None:
        raise api_error(404, "not_found", "Problem not found.")
    return row


def _linked_incidents(conn, user: Principal, problem_id: UUID) -> list[dict]:
    vis, params = visibility(user)
    return fetch_all(
        conn,
        f"""select i.id, i.number, i.short_description, i.priority::text as priority, i.status
              from problem_incidents pi join incidents i on i.id = pi.incident_id
             where pi.problem_id = %(p)s and {vis} order by i.number""",
        {"p": problem_id, **params},
    )


def _detail(conn, user: Principal, problem_id: UUID) -> dict:
    prob = load(conn, user, problem_id)
    prob["can_manage"] = can_manage(user, prob)
    prob["incidents"] = _linked_incidents(conn, user, problem_id)
    prob["related_incidents"] = len(prob["incidents"])  # only what this user may see
    return prob


# ---- list / read ---------------------------------------------------------------------------

@router.get("/problems")
def list_problems(
    status: str | None = None,
    priority: Priority | None = None,
    q: str | None = Query(default=None, description="matches the number or the title"),
    open_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Principal = Depends(current_user),
    conn=Depends(get_conn),
):
    vis, vp = _vis(user)
    where = f"""{vis}
        and (%(status)s::text is null or p.status = %(status)s)
        and (%(priority)s::text is null or p.priority::text = %(priority)s)
        and (%(q)s::text is null or p.number ilike %(q)s or p.title ilike %(q)s)
        and (not %(open_only)s or p.status not in {FINISHED})"""
    params = {**vp, "status": status, "priority": priority, "q": f"%{q}%" if q else None,
              "open_only": open_only, "limit": limit, "offset": offset}
    total = fetch_one(conn, f"select count(*) as n from problems p where {where}", params)["n"]
    items = fetch_all(conn, SELECT + f" where {where} order by p.created_at desc, p.id limit %(limit)s offset %(offset)s",
                      params)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/problems/{problem_id}")
def get_problem(problem_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    return _detail(conn, user, problem_id)


@router.get("/problems/{problem_id}/activity")
def problem_activity(problem_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    load(conn, user, problem_id)
    return timeline(conn, "problems", problem_id, owner_key="owner_id")


# ---- create / edit -------------------------------------------------------------------------

class ProblemIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    service_id: UUID | None = None
    priority: Priority | None = Field(default=None, description="staff only; defaults to P3")


class ProblemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    service_id: UUID | None = None
    priority: Priority | None = None
    root_cause: str | None = Field(default=None, max_length=10000)
    workaround: str | None = Field(default=None, max_length=10000)
    permanent_solution: str | None = Field(default=None, max_length=10000)


STAFF_ONLY_FIELDS = {"priority", "root_cause", "workaround", "permanent_solution"}


@router.post("/problems", status_code=201)
def create_problem(body: ProblemIn, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    if body.priority and user.role == "employee":
        raise api_error(403, "forbidden", "Only staff can set the priority of a problem.")
    row = fetch_one(
        conn,
        """insert into problems(title, description, service_id, priority, raised_by, updated_by)
           values (%(t)s, %(d)s, %(svc)s, coalesce(%(p)s::priority_level, 'P3'), %(uid)s, %(uid)s) returning id""",
        {"t": body.title, "d": body.description, "svc": body.service_id, "p": body.priority, "uid": user.id},
    )
    return _detail(conn, user, row["id"])


@router.patch("/problems/{problem_id}")
def update_problem(problem_id: UUID, body: ProblemPatch, user: Principal = Depends(current_user),
                   conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    prob = load(conn, user, problem_id)
    if prob["status"] == "Closed":
        raise api_error(409, "problem_closed", "A closed problem cannot be edited.")
    own_while_new = (prob["raised_by"] == user.id and prob["status"] == "Identified"
                     and not (set(changes) & STAFF_ONLY_FIELDS))
    if not (can_manage(user, prob) or own_while_new):
        raise api_error(403, "forbidden", "You can only edit your own problem while it is Identified, "
                                          "and only its title, description and service.")
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    conn.execute(f"update problems set {sets}, updated_by = %(uid)s where id = %(id)s",
                 {**changes, "uid": user.id, "id": problem_id})
    return _detail(conn, user, problem_id)


# ---- owner / workflow ----------------------------------------------------------------------

class AssignIn(BaseModel):
    owner_id: UUID


@router.post("/problems/{problem_id}/assign")
def assign_problem(problem_id: UUID, body: AssignIn, user: Principal = Depends(require_roles("admin", "manager")),
                   conn=Depends(get_conn)):
    prob = load(conn, user, problem_id)
    if not can_manage(user, prob):
        raise api_error(403, "forbidden", "You can only assign problems of your own team.")
    if prob["status"] == "Closed":
        raise api_error(409, "problem_closed", "A closed problem cannot be reassigned.")
    target = fetch_one(conn, "select id, role, team_id from profiles where id = %(id)s and status = 'active'",
                       {"id": body.owner_id})
    if target is None or target["role"] not in ("manager", "admin"):
        raise api_error(422, "invalid_assignee", "A problem can only be owned by an active manager or admin.")
    if user.role == "manager" and target["role"] == "manager" and target["team_id"] != user.team_id:
        raise api_error(422, "invalid_assignee", "You can only assign to your own team's manager or to an admin.")
    conn.execute("update problems set owner_id = %(o)s, updated_by = %(uid)s where id = %(id)s",
                 {"o": body.owner_id, "uid": user.id, "id": problem_id})
    return _detail(conn, user, problem_id)


class TransitionIn(BaseModel):
    to_status: Literal["Investigating", "Root Cause Identified", "Fix Planned", "Resolved", "Closed"]


@router.post("/problems/{problem_id}/transition")
def transition_problem(problem_id: UUID, body: TransitionIn, user: Principal = Depends(require_roles("admin", "manager")),
                       conn=Depends(get_conn)):
    """Identified -> Investigating -> Root Cause Identified -> Fix Planned -> Resolved -> Closed (or back to
    Investigating). Invalid moves are refused by the database."""
    prob = load(conn, user, problem_id)
    if not can_manage(user, prob):
        raise api_error(403, "forbidden", "You can only move problems of your own team.")
    if body.to_status == "Root Cause Identified" and not (prob["root_cause"] or "").strip():
        raise api_error(422, "root_cause_required", "Record the root cause before marking it identified.")
    conn.execute("update problems set status = %(to)s, updated_by = %(uid)s where id = %(id)s",
                 {"to": body.to_status, "uid": user.id, "id": problem_id})
    return _detail(conn, user, problem_id)


# ---- linked incidents ----------------------------------------------------------------------

class LinkIn(BaseModel):
    incident_id: UUID


def _check_link_rights(conn, user: Principal, problem_id: UUID) -> dict:
    prob = load(conn, user, problem_id)
    if not can_manage(user, prob):
        raise api_error(403, "forbidden", "You can only link incidents to problems of your own team.")
    if prob["status"] == "Closed":
        raise api_error(409, "problem_closed", "A closed problem cannot be changed.")
    return prob


@router.post("/problems/{problem_id}/incidents", status_code=201)
def link_incident(problem_id: UUID, body: LinkIn, user: Principal = Depends(require_roles("admin", "manager")),
                  conn=Depends(get_conn)):
    _check_link_rights(conn, user, problem_id)
    incident_module.load(conn, user, body.incident_id)  # 404 unless the user may see that incident
    conn.execute("insert into problem_incidents(problem_id, incident_id) values (%(p)s, %(i)s) "
                 "on conflict do nothing", {"p": problem_id, "i": body.incident_id})
    conn.execute("update problems set updated_by = %(uid)s where id = %(p)s", {"uid": user.id, "p": problem_id})
    return _detail(conn, user, problem_id)


@router.delete("/problems/{problem_id}/incidents/{incident_id}")
def unlink_incident(problem_id: UUID, incident_id: UUID, user: Principal = Depends(require_roles("admin", "manager")),
                    conn=Depends(get_conn)):
    _check_link_rights(conn, user, problem_id)
    done = fetch_one(conn, "delete from problem_incidents where problem_id = %(p)s and incident_id = %(i)s "
                           "returning incident_id", {"p": problem_id, "i": incident_id})
    if done is None:
        raise api_error(404, "not_found", "That incident is not linked to this problem.")
    return _detail(conn, user, problem_id)
