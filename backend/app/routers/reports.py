"""Standard reports for managers and admins, limited to what the caller may see. JSON for the screen,
CSV (opens in Excel) with ?format=csv.

Column keys ending in _at / _start / _end are shown as dates by the front end.
"""
import csv
import io
from datetime import date, datetime, timezone
from typing import Callable, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..db import fetch_all, get_conn
from ..errors import api_error
from ..rbac import Principal, require_roles, visibility

router = APIRouter(tags=["reports"])

NOT_OPEN = "('Resolved','Closed')"
ROW_LIMIT = 5000
PRIORITY_NAMES = {"P1": "Critical", "P2": "High", "P3": "Medium", "P4": "Low"}


def col(key: str, label: str) -> dict:
    return {"key": key, "label": label}


def _incidents(conn, user, where: str, select: str, order: str, extra_params: dict | None = None) -> list[dict]:
    vis, vp = visibility(user)
    return fetch_all(
        conn,
        f"""select {select}
              from incidents i
              left join services s on s.id = i.service_id
              left join teams t on t.id = i.team_id
              left join profiles asg on asg.id = i.assignee_id
             where {vis} and {where} order by {order} limit {ROW_LIMIT}""",
        {**vp, **(extra_params or {})},
    )


# Each report returns (columns, rows, chart). chart is None or {"label", "labels", "values"}.

def open_incidents(conn, user):
    rows = _incidents(
        conn, user, f"i.status not in {NOT_OPEN}",
        """i.number, i.short_description, i.priority::text as priority, i.status, s.name as service_name,
           t.name as team_name, asg.full_name as assignee_name, i.resolution_due as resolution_due_at,
           i.created_at""",
        "i.priority, i.resolution_due")
    cols = [col("number", "Incident"), col("short_description", "Description"), col("priority", "Priority"),
            col("status", "Status"), col("service_name", "Service"), col("team_name", "Team"),
            col("assignee_name", "Assignee"), col("resolution_due_at", "Resolution due"), col("created_at", "Created")]
    return cols, rows, None


def _grouped(conn, user, group_expr: str, label_alias: str) -> list[dict]:
    vis, vp = visibility(user)
    return fetch_all(
        conn,
        f"""select {group_expr} as {label_alias}, count(*) as total,
                   count(*) filter (where i.status not in {NOT_OPEN}) as open_count,
                   count(*) filter (where i.status not in {NOT_OPEN} and i.resolution_due < now()) as breached
              from incidents i left join services s on s.id = i.service_id
             where {vis} group by 1 order by 1""",
        vp,
    )


def by_priority(conn, user):
    rows = _grouped(conn, user, "i.priority::text", "priority")
    cols = [col("priority", "Priority"), col("total", "Incidents"), col("open_count", "Open"),
            col("breached", "Open and past SLA")]
    return cols, rows, {"label": "Incidents by priority", "labels": [r["priority"] for r in rows],
                        "values": [r["total"] for r in rows]}


def by_service(conn, user):
    rows = _grouped(conn, user, "coalesce(s.name, 'No service')", "service_name")
    rows.sort(key=lambda r: (-r["total"], r["service_name"]))
    cols = [col("service_name", "Service"), col("total", "Incidents"), col("open_count", "Open"),
            col("breached", "Open and past SLA")]
    return cols, rows, {"label": "Incidents by service", "labels": [r["service_name"] for r in rows],
                        "values": [r["total"] for r in rows]}


def sla_breaches(conn, user):
    rows = _incidents(
        conn, user, f"i.status not in {NOT_OPEN} and i.resolution_due < now()",
        """i.number, i.short_description, i.priority::text as priority, i.status, t.name as team_name,
           asg.full_name as assignee_name, i.resolution_due as resolution_due_at,
           round((extract(epoch from (now() - i.resolution_due)) / 3600)::numeric, 1) as hours_overdue""",
        "i.resolution_due")
    cols = [col("number", "Incident"), col("short_description", "Description"), col("priority", "Priority"),
            col("status", "Status"), col("team_name", "Team"), col("assignee_name", "Assignee"),
            col("resolution_due_at", "Resolution due"), col("hours_overdue", "Hours overdue")]
    return cols, rows, None


def open_problems(conn, user):
    vis, vp = visibility(user, alias="p", owner_col="raised_by", assignee_col="owner_id")
    rows = fetch_all(
        conn,
        f"""select p.number, p.title, p.priority::text as priority, p.status, s.name as service_name,
                   ow.full_name as owner_name, p.created_at
              from problems p left join services s on s.id = p.service_id
              left join profiles ow on ow.id = p.owner_id
             where {vis} and p.status not in ('Resolved','Closed') order by p.priority, p.created_at
             limit {ROW_LIMIT}""",
        vp)
    cols = [col("number", "Problem"), col("title", "Title"), col("priority", "Priority"), col("status", "Status"),
            col("service_name", "Service"), col("owner_name", "Owner"), col("created_at", "Created")]
    return cols, rows, None


def open_defects(conn, user):
    vis, vp = visibility(user, alias="d", owner_col="raised_by", assignee_col="assignee_id")
    rows = fetch_all(
        conn,
        f"""select d.number, d.title, d.severity::text as severity, d.environment::text as environment, d.status,
                   s.name as service_name, t.name as team_name, asg.full_name as assignee_name, d.created_at
              from defects d left join services s on s.id = d.service_id left join teams t on t.id = d.team_id
              left join profiles asg on asg.id = d.assignee_id
             where {vis} and d.status not in ('Resolved','Closed')
             order by array_position(array['Critical','High','Medium','Low'], d.severity::text), d.created_at
             limit {ROW_LIMIT}""",
        vp)
    cols = [col("number", "Defect"), col("title", "Title"), col("severity", "Severity"),
            col("environment", "Environment"), col("status", "Status"), col("service_name", "Service"),
            col("team_name", "Team"), col("assignee_name", "Assignee"), col("created_at", "Created")]
    return cols, rows, None


def defects_by_severity(conn, user):
    vis, vp = visibility(user, alias="d", owner_col="raised_by", assignee_col="assignee_id")
    rows = fetch_all(
        conn,
        f"""select d.severity::text as severity, count(*) as total,
                   count(*) filter (where d.status not in ('Resolved','Closed')) as open_count
              from defects d where {vis} group by 1
             order by array_position(array['Critical','High','Medium','Low'], d.severity::text)""",
        vp)
    cols = [col("severity", "Severity"), col("total", "Defects"), col("open_count", "Open")]
    return cols, rows, {"label": "Defects by severity", "labels": [r["severity"] for r in rows],
                        "values": [r["total"] for r in rows]}


def changes_by_status(conn, user):
    vis, vp = visibility(user, alias="c", owner_col="requester_id", assignee_col=None)
    rows = fetch_all(
        conn,
        f"""select c.status, count(*) as total,
                   count(*) filter (where c.type = 'Emergency') as emergency,
                   count(*) filter (where c.risk = 'High') as high_risk
              from changes c where {vis} group by c.status order by total desc, c.status""",
        vp)
    cols = [col("status", "Status"), col("total", "Changes"), col("emergency", "Emergency"),
            col("high_risk", "High risk")]
    return cols, rows, {"label": "Changes by status", "labels": [r["status"] for r in rows],
                        "values": [r["total"] for r in rows]}


def upcoming_releases(conn, user):
    vis, vp = visibility(user, alias="r", owner_col="owner_id", assignee_col=None)
    rows = fetch_all(
        conn,
        f"""select r.number, r.name, r.environment::text as environment, r.status, s.name as service_name,
                   ow.full_name as owner_name, r.deployment_at
              from releases r left join services s on s.id = r.service_id
              join profiles ow on ow.id = r.owner_id
             where {vis} and r.status <> 'Closed' order by r.deployment_at nulls last, r.number
             limit {ROW_LIMIT}""",
        vp)
    cols = [col("number", "Release"), col("name", "Name"), col("environment", "Environment"),
            col("status", "Status"), col("service_name", "Service"), col("owner_name", "Owner"),
            col("deployment_at", "Deployment")]
    return cols, rows, None


def pending_approvals(conn, user):
    if user.role == "admin":
        where, params = "true", {}
    else:
        where, params = "a.approver_role = 'manager' and a.team_id = %(team)s", {"team": user.team_id}
    rows = fetch_all(
        conn,
        f"""select a.record_number, a.record_type::text as record_type, a.approver_role::text as approver_role,
                   rb.full_name as requested_by_name, a.created_at
              from approvals a join profiles rb on rb.id = a.requested_by
             where a.status = 'pending' and {where} order by a.created_at limit {ROW_LIMIT}""",
        params)
    cols = [col("record_number", "Request"), col("record_type", "Type"), col("approver_role", "Approver"),
            col("requested_by_name", "Requested by"), col("created_at", "Requested")]
    return cols, rows, None


REPORTS: dict[str, tuple[str, str, Callable]] = {
    "open_incidents": ("Open incidents", "Incidents", open_incidents),
    "incidents_by_priority": ("Incidents by priority", "Incidents", by_priority),
    "incidents_by_service": ("Incidents by service", "Incidents", by_service),
    "sla_breaches": ("Open incidents past their SLA", "SLA", sla_breaches),
    "open_problems": ("Open problems", "Problems", open_problems),
    "open_defects": ("Open defects", "Defects", open_defects),
    "defects_by_severity": ("Defects by severity", "Defects", defects_by_severity),
    "changes_by_status": ("Changes by status", "Changes", changes_by_status),
    "upcoming_releases": ("Releases not yet closed", "Releases", upcoming_releases),
    "pending_approvals": ("Pending approvals", "Governance", pending_approvals),
}

staff_only = require_roles("admin", "manager")


@router.get("/reports")
def list_reports(_: Principal = Depends(staff_only)):
    return [{"key": k, "title": title, "category": cat, "available": True, "reason": None}
            for k, (title, cat, _fn) in REPORTS.items()]


def _cell(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return "" if v is None else v


@router.get("/reports/{key}")
def run_report(key: str, format: Literal["json", "csv"] = "json", user: Principal = Depends(staff_only),
               conn=Depends(get_conn)):
    if key not in REPORTS:
        raise api_error(404, "not_found", "Report not found.")
    title, category, fn = REPORTS[key]
    columns, rows, chart = fn(conn, user)
    for r in rows:  # priorities are shown as Critical / High / Medium / Low
        if r.get("priority") in PRIORITY_NAMES:
            r["priority"] = PRIORITY_NAMES[r["priority"]]
    if chart:
        chart["labels"] = [PRIORITY_NAMES.get(label, label) for label in chart["labels"]]
    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([c["label"] for c in columns])
        for r in rows:
            writer.writerow([_cell(r[c["key"]]) for c in columns])
        return Response(content="﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{key}.csv"'})
    scope = "All teams" if user.role == "admin" else "Your team"
    return {"key": key, "title": title, "category": category, "scope": scope,
            "generated_at": datetime.now(timezone.utc), "columns": columns, "rows": rows, "chart": chart}
