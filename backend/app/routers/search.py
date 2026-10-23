"""Global search: every word you type must appear somewhere in the record (any field, plus the names of the people,
team and application it points to). Results are limited to what the caller may see."""
from fastapi import APIRouter, Depends, Query

from ..db import fetch_all, fetch_one, get_conn
from ..rbac import Principal, current_user, visibility
from .projects import projects_for

router = APIRouter(tags=["search"])

PEOPLE = "left join services s on s.id = x.service_id left join teams t on t.id = x.team_id"
# type -> (table, title column, level column, owner column, assignee column, joins, text of the linked names)
RECORDS = {
    "incidents": ("incidents", "x.short_description", "x.priority::text", "requester_id", "assignee_id",
                  f"join profiles p1 on p1.id = x.requester_id left join profiles p2 on p2.id = x.assignee_id {PEOPLE}",
                  "s.name, t.name, p1.full_name, p1.email, p2.full_name, p2.email"),
    "problems": ("problems", "x.title", "x.priority::text", "raised_by", "owner_id",
                 f"join profiles p1 on p1.id = x.raised_by left join profiles p2 on p2.id = x.owner_id {PEOPLE}",
                 "s.name, t.name, p1.full_name, p1.email, p2.full_name, p2.email"),
    "defects": ("defects", "x.title", "x.severity::text", "raised_by", "assignee_id",
                f"join profiles p1 on p1.id = x.raised_by left join profiles p2 on p2.id = x.assignee_id {PEOPLE}",
                "s.name, t.name, p1.full_name, p1.email, p2.full_name, p2.email"),
    "changes": ("changes", "x.title", "x.risk::text", None, None,
                f"join profiles p1 on p1.id = x.requester_id {PEOPLE}", "s.name, t.name, p1.full_name, p1.email"),
    "releases": ("releases", "x.name", "x.environment::text", None, None,
                 f"join profiles p1 on p1.id = x.owner_id {PEOPLE}", "s.name, t.name, p1.full_name, p1.email"),
}


def _terms(q: str) -> tuple[str, dict]:
    words = [w for w in q.split() if w][:8]
    params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
    return params, words


def _match(text_expr: str, words: list[str]) -> str:
    return " and ".join(f"{text_expr} ilike %(w{i})s" for i in range(len(words))) or "false"


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=100), limit: int = Query(default=25, ge=1, le=100),
           user: Principal = Depends(current_user), conn=Depends(get_conn)):
    params, words = _terms(q.strip())
    out: dict = {"query": q.strip(), "groups": []}
    for kind, (table, title, level, owner, assignee, joins, names) in RECORDS.items():
        vis, vp = visibility(user, alias="x", owner_col=owner, assignee_col=assignee) if owner else ("true", {})
        where = f"{vis} and ({_match(f'concat_ws(chr(32), x::text, {names})', words)})"
        p = {**vp, **params, "limit": limit}
        total = fetch_one(conn, f"select count(*) as n from {table} x {joins} where {where}", p)["n"]
        rows = fetch_all(
            conn,
            f"""select x.id, x.project_id, x.number, {title} as title, x.status, {level} as level, t.name as team_name
                  from {table} x {joins} where {where} order by x.created_at desc limit %(limit)s""", p)
        out["groups"].append({"kind": kind, "total": total, "items": rows})
    if user.role in ("admin", "manager"):
        mine = [p["id"] for p in projects_for(conn, user)]
        rows = fetch_all(conn, f"""select id, name as title, project_name as detail from projects x
                                   where id = any(%(mine)s) and ({_match("concat_ws(chr(32), x::text)", words)}) order by name limit %(limit)s""",
                         {**params, "mine": mine, "limit": limit})
        out["groups"].append({"kind": "customers", "total": len(rows), "items": rows})
        rows = fetch_all(conn, f"""select id, name as title, description as detail from services x
                                   where ({_match("concat_ws(chr(32), x::text)", words)}) order by name limit %(limit)s""",
                         {**params, "limit": limit})
        out["groups"].append({"kind": "applications", "total": len(rows), "items": rows})
    if user.role == "admin":
        rows = fetch_all(
            conn, f"""select x.id, x.full_name as title, x.email || ' · ' || x.role::text as detail from profiles x
                       left join teams t on t.id = x.team_id
                       where ({_match("concat_ws(chr(32), x::text, t.name)", words)}) order by x.full_name limit %(limit)s""",
            {**params, "limit": limit})
        out["groups"].append({"kind": "users", "total": len(rows), "items": rows})
    return out
