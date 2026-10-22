"""Standard reports for managers and admins, limited to what the caller may see. JSON for the screen,
CSV (opens in Excel) with ?format=csv.

Column keys ending in _at / _start / _end are shown as dates by the front end.
"""
import csv
import io
from datetime import date, datetime, timezone
from typing import Callable, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..db import fetch_all, get_conn
from ..errors import api_error
from ..rbac import Principal, require_roles, visibility

router = APIRouter(tags=["reports"])

NOT_OPEN = "('Resolved','Closed')"
ROW_LIMIT = 5000
ROLE_NAMES = {"admin": "Administrator", "manager": "Support Engineer", "employee": "Customer"}
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
            col("status", "Status"), col("service_name", "Application"), col("team_name", "Team"),
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
    return cols, rows, {"key": "priority", "label": "Incidents by priority", "labels": [r["priority"] for r in rows],
                        "values": [r["total"] for r in rows]}


def by_service(conn, user):
    rows = _grouped(conn, user, "coalesce(s.name, 'No service')", "service_name")
    rows.sort(key=lambda r: (-r["total"], r["service_name"]))
    cols = [col("service_name", "Application"), col("total", "Incidents"), col("open_count", "Open"),
            col("breached", "Open and past SLA")]
    return cols, rows, {"key": "service_name", "label": "Incidents by application", "labels": [r["service_name"] for r in rows],
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
            col("service_name", "Application"), col("owner_name", "Owner"), col("created_at", "Created")]
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
            col("environment", "Environment"), col("status", "Status"), col("service_name", "Application"),
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
    return cols, rows, {"key": "severity", "label": "Defects by severity", "labels": [r["severity"] for r in rows],
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
    return cols, rows, {"key": "status", "label": "Changes by status", "labels": [r["status"] for r in rows],
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
            col("status", "Status"), col("service_name", "Application"), col("owner_name", "Owner"),
            col("deployment_at", "Deployment")]
    return cols, rows, None


def pending_approvals(conn, user):
    if user.role == "admin":
        where, params = "true", {}
    else:
        where, params = "a.approver_role = 'manager' and a.team_id = %(team)s", {"team": user.team_id}
    where += """ and exists (select 1 from (
            select id, project_id from incidents union all select id, project_id from changes
            union all select id, project_id from releases) rec
          where rec.id = a.record_id and rec.project_id = any(%(proj)s))"""
    params["proj"] = user.project_ids
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
    "incidents_by_service": ("Incidents by application", "Incidents", by_service),
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


# Bar colours: meaningful ones for well-known labels, otherwise a rotating palette (same as the on-screen graph)
SEMANTIC = {"Critical": "#c0392b", "High": "#e67e22", "Medium": "#f1c40f", "Low": "#2e9e6b", "P1": "#c0392b",
            "P2": "#e67e22", "P3": "#f1c40f", "P4": "#2e9e6b", "New": "#4a7fb5", "Assigned": "#7a5aa6",
            "In Progress": "#e67e22", "Pending": "#f1c40f", "Resolved": "#2e9e6b", "Closed": "#7f8c8d",
            "Production": "#c74634", "UAT": "#2f8aa0"}
PALETTE = ["#c74634", "#2f8aa0", "#e0a03a", "#4a7fb5", "#2e9e6b", "#7a5aa6", "#d96a8a", "#6b8e23", "#b5651d", "#3d5a80"]

# The column a list report is counted by for its bar graph, in order of preference
CHART_BY = ("priority", "severity", "status", "environment", "team_name", "service_name", "record_type", "approver_role")


def _auto_chart(columns: list[dict], rows: list[dict]) -> dict | None:
    """Reports that are plain lists get a bar graph counting their rows by the first suitable column."""
    labels = {c["key"]: c["label"] for c in columns}
    for key in CHART_BY:
        if key in labels and rows:
            counts: dict[str, int] = {}
            for r in rows:
                name = str(r.get(key) or "None")
                counts[name] = counts.get(name, 0) + 1
            ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            return {"key": key, "label": f"Number of records by {labels[key].lower()}", "labels": [k for k, _ in ordered],
                    "values": [v for _, v in ordered]}
    return None


def _pdf(title: str, category: str, scope: str, columns: list[dict], rows: list[dict], chart: dict | None) -> bytes:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    brand = colors.HexColor("#963322")
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("cell", fontSize=7.5, leading=9)
    head = styles["BodyText"].clone("head", fontSize=7.5, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=title)
    story = [Paragraph(f"<font color='#963322'><b>{category.upper()}</b></font>", styles["BodyText"]),
             Paragraph(f"<b>{title}</b>", styles["Title"]),
             Paragraph(f"Scope: {scope} &middot; generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC &middot; "
                       f"{len(rows)} row(s)", styles["BodyText"]), Spacer(1, 6 * mm)]
    if chart and chart["labels"]:
        labels = [str(x)[:22] for x in chart["labels"]][:20]
        values = [float(v or 0) for v in chart["values"]][:20]
        d = Drawing(260 * mm, 62 * mm)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 12 * mm, 14 * mm, 236 * mm, 40 * mm
        bc.data = [values]
        bc.categoryAxis.categoryNames = labels
        bc.categoryAxis.labels.fontSize = 7
        bc.categoryAxis.labels.angle = 20 if len(labels) > 6 else 0
        bc.categoryAxis.labels.boxAnchor = "ne" if len(labels) > 6 else "n"
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(values + [1]) * 1.15
        bc.valueAxis.labels.fontSize = 7
        for i, label in enumerate(chart["labels"][:20]):
            bc.bars[(0, i)].fillColor = colors.HexColor(SEMANTIC.get(str(label), PALETTE[i % len(PALETTE)]))
        bc.barLabelFormat = "%d"
        bc.barLabels.nudge = 6
        bc.barLabels.fontSize = 7
        d.add(bc)
        story += [Paragraph(f"<b>{chart['label']}</b>", styles["BodyText"]), d, Spacer(1, 4 * mm)]
    if rows:
        def cell(c, r):
            v = r.get(c["key"])
            if isinstance(v, (datetime, date)):
                v = v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else v.isoformat()
            return Paragraph("" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;"), small)
        data = [[Paragraph(c["label"], head) for c in columns]] + [[cell(c, r) for c in columns] for r in rows[:1000]]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), brand), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f1ee")]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ddd7d1"))]))
        story.append(t)
        if len(rows) > 1000:
            story.append(Paragraph("Showing the first 1000 rows. Download the CSV for everything.", small))
    else:
        story.append(Paragraph("No data for this report yet.", styles["BodyText"]))
    doc.build(story)
    return buf.getvalue()


# The list page a report's bars open, and any filter that goes with every bar
REPORT_PAGE = {"open_incidents": ("/incidents", {"open_only": "1"}), "incidents_by_priority": ("/incidents", {}),
               "incidents_by_service": ("/incidents", {}), "sla_breaches": ("/incidents", {"open_only": "1"}),
               "open_problems": ("/problems", {"open_only": "1"}), "open_defects": ("/defects", {"open_only": "1"}),
               "defects_by_severity": ("/defects", {}), "changes_by_status": ("/changes", {}),
               "upcoming_releases": ("/releases", {})}
BAR_FILTER = {"priority": "priority", "severity": "severity", "status": "status", "environment": "environment"}
PRIORITY_CODES = {v: k for k, v in PRIORITY_NAMES.items()}


def _bar_links(conn, key: str, chart: dict) -> list[str | None]:
    """For each bar, the page (with filters) that shows the records it counts. None when there is no such page."""
    page, fixed = REPORT_PAGE.get(key, (None, {}))
    if page is None:
        return [None] * len(chart["labels"])
    out = []
    services = {}
    if chart.get("key") == "service_name":
        services = {r["name"]: str(r["id"]) for r in fetch_all(conn, "select id, name from services")}
    for label in chart["labels"]:
        params = dict(fixed)
        col = chart.get("key")
        if col in BAR_FILTER:
            params[BAR_FILTER[col]] = PRIORITY_CODES.get(label, label) if col == "priority" else label
        elif col == "service_name":
            if label not in services:
                out.append(None)
                continue
            params["service_id"] = services[label]
        out.append(page + ("?" + urlencode(params) if params else ""))
    return out


def _cell(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return "" if v is None else v


@router.get("/reports/{key}")
def run_report(key: str, format: Literal["json", "csv", "pdf"] = "json", user: Principal = Depends(staff_only),
               conn=Depends(get_conn)):
    if key not in REPORTS:
        raise api_error(404, "not_found", "Report not found.")
    title, category, fn = REPORTS[key]
    columns, rows, chart = fn(conn, user)
    for r in rows:  # priorities are shown as Critical / High / Medium / Low
        if r.get("priority") in PRIORITY_NAMES:
            r["priority"] = PRIORITY_NAMES[r["priority"]]
        if r.get("approver_role") in ROLE_NAMES:
            r["approver_role"] = ROLE_NAMES[r["approver_role"]]
    if chart is None:
        chart = _auto_chart(columns, rows)
    if chart:
        chart["labels"] = [PRIORITY_NAMES.get(label, label) for label in chart["labels"]]
        chart["links"] = _bar_links(conn, key, chart)
    scope = "All teams" if user.role == "admin" else "Your team"
    if format == "pdf":
        return Response(content=_pdf(title, category, scope, columns, rows, chart), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{key}.pdf"'})
    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([c["label"] for c in columns])
        for r in rows:
            writer.writerow([_cell(r[c["key"]]) for c in columns])
        return Response(content="﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{key}.csv"'})
    return {"key": key, "title": title, "category": category, "scope": scope,
            "generated_at": datetime.now(timezone.utc), "columns": columns, "rows": rows, "chart": chart}
