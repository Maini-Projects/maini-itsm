"""Audit history (admin only): who changed what, and when. The log is written by database triggers."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..db import fetch_all, fetch_one, get_conn
from ..rbac import Principal, require_roles

router = APIRouter(tags=["audit"])

Table = Literal["incidents", "problems", "defects", "changes", "releases", "approvals", "profiles", "sla_policies"]
LABEL = {"incidents": "incident", "problems": "problem", "defects": "defect", "changes": "change", "releases": "release",
         "approvals": "approval", "profiles": "user", "sla_policies": "SLA target"}
VERB = {"INSERT": "Created", "UPDATE": "Updated", "DELETE": "Deleted"}

# The human-readable name of the record: its number, an approval's record number, a user's email, an SLA priority
RECORD = """coalesce(a.new_values ->> 'number', a.old_values ->> 'number', a.new_values ->> 'record_number',
                     a.new_values ->> 'email', a.old_values ->> 'email', a.new_values ->> 'priority')"""

DEFAULT_DAYS = 10
CHOICES = (1, 3, 7, 10, 30, 60, 90, 180, 365)


def retention_days(conn, user_id) -> int:
    row = fetch_one(conn, "select retention_days from audit_settings where user_id = %(u)s", {"u": user_id})
    return row["retention_days"] if row else DEFAULT_DAYS


class RetentionIn(BaseModel):
    days: Literal[1, 3, 7, 10, 30, 60, 90, 180, 365]


@router.get("/audit/settings")
def get_audit_settings(user: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    return {"retention_days": retention_days(conn, user.id), "choices": list(CHOICES), "default": DEFAULT_DAYS}


@router.put("/audit/settings")
def set_audit_settings(body: RetentionIn, user: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    conn.execute(
        """insert into audit_settings(user_id, retention_days) values (%(u)s, %(d)s)
           on conflict (user_id) do update set retention_days = excluded.retention_days, updated_at = now()""",
        {"u": user.id, "d": body.days},
    )
    return {"retention_days": body.days, "choices": list(CHOICES), "default": DEFAULT_DAYS}


# Fields that change on every edit and say nothing useful in the history
NOISE = ("updated_at", "updated_by")


@router.get("/audit")
def audit_log(
    table: Table | None = None,
    record: str | None = Query(default=None, description="record number or email, e.g. INC-10001"),
    action: Literal["INSERT", "UPDATE", "DELETE"] | None = None,
    actor_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Principal = Depends(require_roles("admin")),
    conn=Depends(get_conn),
):
    days = retention_days(conn, user.id)
    where = f"""(%(table)s::text is null or a.table_name = %(table)s)
        and (%(record)s::text is null or {RECORD} ilike %(record)s)
        and (%(action)s::text is null or a.action = %(action)s)
        and (%(actor)s::uuid is null or a.actor_id = %(actor)s)
        and (%(since)s::timestamptz is null or a.at >= %(since)s)
        and (%(until)s::timestamptz is null or a.at <= %(until)s)
        and a.at >= now() - make_interval(days => %(days)s)"""
    params = {"table": table, "record": f"%{record}%" if record else None, "action": action, "actor": actor_id,
              "since": since, "until": until, "limit": limit, "offset": offset, "days": days, "noise": list(NOISE)}
    total = fetch_one(conn, f"select count(*) as n from audit_log a where {where}", params)["n"]
    rows = fetch_all(
        conn,
        f"""select a.id, a.at, a.action, a.table_name, a.record_id, p.full_name as actor_name,
                   {RECORD} as record,
                   a.old_values ->> 'status' as old_status, a.new_values ->> 'status' as new_status,
                   case when a.action = 'UPDATE' then array(
                        select k from jsonb_object_keys(a.new_values) k
                         where k <> all(%(noise)s) and a.new_values -> k is distinct from a.old_values -> k
                         order by k) end as changed_fields
              from audit_log a left join profiles p on p.id = a.actor_id
             where {where} order by a.id desc limit %(limit)s offset %(offset)s""",
        params,
    )
    for r in rows:
        r["summary"] = f"{VERB[r['action']]} {LABEL.get(r['table_name'], r['table_name'])}"
    return {"retention_days": days, "items": rows, "total": total, "limit": limit, "offset": offset}
