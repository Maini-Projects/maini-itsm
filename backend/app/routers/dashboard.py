"""Numbers for the dashboard home screen, always calculated live and limited to what the caller may see."""
from fastapi import APIRouter, Depends

from ..db import fetch_all, fetch_one, get_conn
from ..rbac import Principal, current_user, visibility

router = APIRouter(tags=["dashboard"])

OPEN = "i.status not in ('Resolved','Closed')"
# "At risk": still open and either already late, or inside the last 25% of its resolution window (min 30 min)
AT_RISK = "i.resolution_due < now() + greatest((i.resolution_due - i.created_at) * 0.25, interval '30 minutes')"


@router.get("/dashboard/summary")
def summary(user: Principal = Depends(current_user), conn=Depends(get_conn)):
    vis, vp = visibility(user)
    staff = user.role in ("admin", "manager")

    incidents = fetch_one(
        conn,
        f"""select count(*) filter (where {OPEN}) as open,
                   count(*) filter (where {OPEN} and i.priority in ('P1','P2')) as p1_p2_open,
                   count(*) filter (where {OPEN} and i.priority = 'P1') as p1_open,
                   count(*) filter (where {OPEN} and i.priority = 'P2') as p2_open,
                   count(*) filter (where {OPEN} and {AT_RISK}) as sla_at_risk,
                   count(*) filter (where {OPEN} and i.resolution_due < now()) as sla_breached,
                   count(*) filter (where {OPEN} and i.resolution_due between now() and now() + interval '30 minutes')
                       as due_within_30_min
              from incidents i where {vis}""",
        vp,
    )

    perf_rows = {r["priority"]: r for r in fetch_all(
        conn,
        f"""select i.priority::text as priority, count(*) as resolved,
                   count(*) filter (where i.resolved_at <= i.resolution_due) as within_sla
              from incidents i where i.resolved_at >= date_trunc('month', now()) and {vis}
             group by i.priority""",
        vp,
    )}
    sla_performance = []
    for p in ("P1", "P2", "P3", "P4"):
        r = perf_rows.get(p)
        resolved = r["resolved"] if r else 0
        sla_performance.append({
            "priority": p, "resolved_this_month": resolved,
            "within_sla": r["within_sla"] if r else 0,
            "percent": round(100 * r["within_sla"] / resolved) if resolved else None,
        })

    dvis, dp = visibility(user, alias="d", owner_col="raised_by", assignee_col="assignee_id")
    defects = fetch_one(
        conn,
        f"""select count(*) filter (where d.status not in ('Resolved','Closed')) as open,
                   count(*) filter (where d.status not in ('Resolved','Closed') and d.severity = 'Critical')
                       as critical_open
              from defects d where {dvis}""",
        dp,
    )

    result = {"incidents": incidents, "defects": defects, "sla_performance": sla_performance, "team_workload": [],
              "pending_approvals": None, "problems": None, "changes": None, "releases": None}
    if not staff:
        return result

    result["team_workload"] = fetch_all(
        conn,
        f"""select t.id, t.name,
                   count(i.id) filter (where {OPEN}) as open,
                   count(i.id) filter (where {OPEN} and {AT_RISK}) as at_risk
              from teams t left join incidents i on i.team_id = t.id and {vis}
             group by t.id, t.name order by t.name""",
        vp,
    )

    if user.role == "admin":
        appr_where, appr_params = "true", {}
        scope, sp = "true", {}
    else:
        appr_where = "a.approver_role = 'manager' and a.team_id = %(team)s and a.requested_by <> %(me)s"
        appr_params = {"team": user.team_id, "me": user.id}
        scope, sp = "x.team_id = %(team)s", {"team": user.team_id}
    by_type = {r["record_type"]: r["n"] for r in fetch_all(
        conn, f"select a.record_type::text, count(*) as n from approvals a "
              f"where a.status = 'pending' and {appr_where} group by a.record_type", appr_params)}
    result["pending_approvals"] = {"total": sum(by_type.values()), "change": by_type.get("change", 0),
                                   "release": by_type.get("release", 0)}

    result["problems"] = {r["status"]: r["n"] for r in fetch_all(
        conn, f"select x.status, count(*) as n from problems x "
              f"where x.status not in ('Resolved','Closed') and {scope} group by x.status", sp)}
    result["changes"] = fetch_one(
        conn,
        f"""select count(*) filter (where x.status <> 'Closed') as active,
                   count(*) filter (where x.status = 'Approval Pending') as approval_pending,
                   count(*) filter (where x.status = 'Scheduled') as scheduled,
                   count(*) filter (where x.status <> 'Closed' and x.type = 'Emergency') as emergency
              from changes x where {scope}""", sp)
    upcoming = fetch_all(
        conn,
        f"""select x.id, x.number, x.name, x.environment::text as environment, x.status, x.deployment_at
              from releases x
             where x.status <> 'Closed' and x.deployment_at between now() and now() + interval '14 days' and {scope}
             order by x.deployment_at limit 5""", sp)
    upcoming_count = fetch_one(
        conn,
        f"""select count(*) as n from releases x
             where x.status <> 'Closed' and x.deployment_at between now() and now() + interval '14 days' and {scope}""",
        sp)["n"]
    result["releases"] = {"upcoming_14_days": upcoming_count, "next": upcoming}
    return result
