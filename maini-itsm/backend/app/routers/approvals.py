"""Approval queue: P1/P2 incident sign-off (team manager or admin), changes and releases (admin).

The database decides who may approve what and moves the record on in the same transaction;
this module lists the queue and records the decision.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, require_roles

router = APIRouter(tags=["approvals"])

SELECT = """
select a.id, a.record_type, a.record_id, a.record_number, a.approver_role,
       a.team_id, t.name as team_name, a.status,
       a.requested_by, rb.full_name as requested_by_name,
       a.decided_by, db.full_name as decided_by_name, a.comment, a.created_at, a.decided_at,
       coalesce(i.short_description, c.title, r.name) as title,
       i.priority::text as priority, c.risk::text as risk, c.type::text as change_type,
       r.environment::text as environment
from approvals a
left join teams t on t.id = a.team_id
join profiles rb on rb.id = a.requested_by
left join profiles db on db.id = a.decided_by
left join incidents i on a.record_type = 'incident' and i.id = a.record_id
left join changes   c on a.record_type = 'change'   and c.id = a.record_id
left join releases  r on a.record_type = 'release'  and r.id = a.record_id
"""


def _scope(user: Principal) -> tuple[str, dict]:
    """Admins see every approval; managers see their team's incident approvals and their own requests."""
    if user.role == "admin":
        return "true", {}
    return ("((a.approver_role = 'manager' and a.team_id = %(team)s) or a.requested_by = %(me)s)",
            {"team": user.team_id, "me": user.id})


def _decorate(user: Principal, row: dict) -> dict:
    if user.role == "admin":
        row["can_decide"] = row["status"] == "pending"
    else:
        row["can_decide"] = (row["status"] == "pending" and row["approver_role"] == "manager"
                             and row["team_id"] == user.team_id and row["requested_by"] != user.id)
    return row


@router.get("/approvals")
def list_approvals(status: Literal["pending", "approved", "rejected", "all"] = "pending",
                   user: Principal = Depends(require_roles("admin", "manager")), conn=Depends(get_conn)):
    scope, params = _scope(user)
    rows = fetch_all(conn, SELECT + f" where {scope} and (%(status)s = 'all' or a.status::text = %(status)s) "
                                    "order by a.created_at desc", {**params, "status": status})
    return [_decorate(user, r) for r in rows]


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/approvals/{approval_id}/decision")
def decide(approval_id: UUID, body: DecisionIn, user: Principal = Depends(require_roles("admin", "manager")),
           conn=Depends(get_conn)):
    """Approve or reject. Approving closes a P1/P2 incident or schedules a change/release; rejecting sends it back."""
    scope, params = _scope(user)
    row = fetch_one(conn, SELECT + f" where a.id = %(id)s and {scope}", {"id": approval_id, **params})
    if row is None:
        raise api_error(404, "not_found", "Approval not found.")
    if row["status"] != "pending":
        raise api_error(409, "already_decided", "This approval has already been decided.")
    if body.decision == "rejected" and not (body.comment and body.comment.strip()):
        raise api_error(422, "comment_required", "Please say why you are rejecting this request.")
    updated = fetch_one(
        conn,
        """update approvals set status = %(d)s, decided_by = %(uid)s, comment = %(c)s
            where id = %(id)s and status = 'pending' returning id""",
        {"d": body.decision, "uid": user.id, "c": body.comment, "id": approval_id},
    )
    if updated is None:
        raise api_error(409, "already_decided", "This approval has already been decided.")
    return _decorate(user, fetch_one(conn, SELECT + " where a.id = %(id)s", {"id": approval_id}))
