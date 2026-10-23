"""A small rule-based assistant (no AI model): it recognises what you ask from keywords and record numbers, runs the
same queries the screens use, and answers in plain words. It only ever sees what the signed-in user may see."""
import re

from fastapi import APIRouter, Depends, Query

from ..db import fetch_all, fetch_one, get_conn
from ..rbac import Principal, current_user, visibility

router = APIRouter(tags=["assistant"])

# kind -> (table, singular, level column, open condition, title column, owner column, assignee column, number prefix, route)
KINDS = {
    "incidents": ("incidents", "incident", "x.priority::text", "x.status not in ('Resolved','Closed')", "x.short_description", "requester_id", "assignee_id", "INC", "incidents"),
    "problems": ("problems", "problem", "x.priority::text", "x.status not in ('Resolved','Closed')", "x.title", "raised_by", "owner_id", "PRB", "problems"),
    "defects": ("defects", "defect", "x.severity::text", "x.status not in ('Resolved','Closed')", "x.title", "raised_by", "assignee_id", "DEF", "defects"),
    "changes": ("changes", "change", "x.risk::text", "x.status <> 'Closed'", "x.title", None, None, "CHG", "changes"),
    "releases": ("releases", "release", "x.environment::text", "x.status <> 'Closed'", "x.name", None, None, "REL", "releases"),
}
WORDS = {
    "incidents": r"incident|ticket|issue|outage", "problems": r"problem", "defects": r"defect|bug",
    "changes": r"change", "releases": r"release|deploy",
}
PRIORITY_NAME = {"P1": "Critical", "P2": "High", "P3": "Medium", "P4": "Low"}
SUGGESTIONS = ["How many open incidents are there?", "Show the latest high priority incidents", "When is the next release?",
               "Which incidents are past their SLA?", "Show my open incidents", "Pending approvals"]


def _scope(kind: str, user: Principal):
    table, singular, level, open_cond, title, owner, assignee, prefix, route = KINDS[kind]
    vis, vp = visibility(user, alias="x", owner_col=owner, assignee_col=assignee) if owner else ("true", {})
    return table, singular, level, open_cond, title, owner, assignee, prefix, route, vis, vp


def _kind_in(text: str) -> str | None:
    hits = [(m.start(), k) for k, pat in WORDS.items() for m in [re.search(pat, text)] if m]
    return min(hits)[1] if hits else None


def _levels(text: str, kind: str) -> list[str] | None:
    """'critical' -> only the top level; 'high' or 'urgent' -> the top two (the dashboard's Critical / High)."""
    if kind not in ("incidents", "problems", "defects"):
        return None
    codes = ["P1", "P2"] if kind != "defects" else ["Critical", "High"]
    if re.search(r"critical|p1|sev ?1", text):
        return codes[:1]
    if re.search(r"high|urgent|important|p2|major", text):
        return codes
    if re.search(r"medium|p3", text):
        return ["P3"] if kind != "defects" else ["Medium"]
    if re.search(r"\blow\b|p4", text):
        return ["P4"] if kind != "defects" else ["Low"]
    return None


def _level_text(levels: list[str] | None, kind: str) -> str:
    if not levels:
        return ""
    names = [PRIORITY_NAME.get(x, x) for x in levels]
    return (names[0] if len(names) == 1 else " / ".join(names)).lower() + (" severity " if kind == "defects" else " priority ")


def _items(rows, route, title_key="title"):
    return [{"label": f"{r['number']} · {r[title_key]}", "to": f"/{route}/{r['id']}", "meta": r.get("status")} for r in rows]


def _answer(text: str, answer: str, items=None, suggestions=None):
    return {"answer": answer, "items": items or [], "suggestions": suggestions or []}


@router.get("/assistant")
def assistant(q: str = Query(min_length=1, max_length=300), user: Principal = Depends(current_user), conn=Depends(get_conn)):
    text = q.lower().strip()
    staff = user.role in ("admin", "manager")

    if re.fullmatch(r"(hi|hello|hey|good (morning|afternoon|evening))[ !.]*", text):
        return _answer(text, f"Hi {user.full_name.split()[0]}! Ask me about tickets, releases, approvals or SLAs. Try one of these.", suggestions=SUGGESTIONS)
    if re.fullmatch(r"(thanks|thank you|thx|ok|okay|great)[ !.]*", text):
        return _answer(text, "You're welcome! Anything else?", suggestions=SUGGESTIONS[:3])
    if re.search(r"\bhelp\b|what can you do|commands", text):
        return _answer(text, "I can count tickets, list the latest or high priority ones, look up a record by number (like INC-12), show the next release, SLA breaches, your own tickets and pending approvals. Ask in plain words.", suggestions=SUGGESTIONS)

    # a record number, e.g. INC-12
    m = re.search(r"\b(inc|prb|def|chg|rel)[- ]?(\d+)\b", text)
    if m:
        prefix = m.group(1).upper()
        kind = next(k for k, v in KINDS.items() if v[7] == prefix)
        table, singular, level, _o, title, _ow, _as, _p, route, vis, vp = _scope(kind, user)
        rows = fetch_all(conn, f"select x.id, x.number, {title} as title, x.status, {level} as level, x.project_id from {table} x where {vis} and x.number = %(n)s",
                         {**vp, "n": f"{prefix}-{m.group(2)}"})
        if not rows:
            return _answer(text, f"I couldn't find {prefix}-{m.group(2)} among the records you can see.", suggestions=SUGGESTIONS[:3])
        r = rows[0]
        lvl = PRIORITY_NAME.get(r["level"], r["level"])
        extra = f" ({len(rows)} customers have a record with that number)" if len(rows) > 1 else ""
        return _answer(text, f"{r['number']}: “{r['title']}” is {r['status']} ({lvl}).{extra}", _items(rows, route))

    kind = _kind_in(text)

    # approvals
    if re.search(r"approval", text):
        if not staff:
            return _answer(text, "Changes and releases are approved by an Administrator. You can follow their status on the Changes and Releases pages.")
        where = "a.status = 'pending'" + ("" if user.role == "admin" else " and a.approver_role = 'manager' and a.team_id = %(team)s")
        n = fetch_one(conn, f"select count(*) as n from approvals a where {where}", {"team": user.team_id})["n"]
        rows = fetch_all(conn, f"select a.record_number as number, a.record_type::text as type from approvals a where {where} order by a.created_at desc limit 5", {"team": user.team_id})
        return _answer(text, f"There {'is' if n == 1 else 'are'} {n} pending approval{'' if n == 1 else 's'}." + (" Latest: " + ", ".join(r["number"] for r in rows) + "." if rows else ""),
                       [{"label": "Open the approval queue", "to": "/approvals", "meta": None}])

    # SLA
    if re.search(r"\bsla\b|breach|overdue|past (their|the) (due|target)|\blate\b", text):
        table, _s, _l, open_cond, title, _ow, _as, _p, route, vis, vp = _scope("incidents", user)
        breached = fetch_all(conn, f"select x.id, x.number, x.short_description as title, x.status from incidents x where {vis} and {open_cond} and x.resolution_due < now() order by x.resolution_due limit 5", vp)
        n = fetch_one(conn, f"select count(*) as n from incidents x where {vis} and {open_cond} and x.resolution_due < now()", vp)["n"]
        risk = fetch_one(conn, f"select count(*) as n from incidents x where {vis} and {open_cond} and x.resolution_due between now() and now() + interval '2 hours'", vp)["n"]
        if not n:
            return _answer(text, f"No open incidents are past their SLA. {risk} due within the next 2 hours.")
        return _answer(text, f"{n} open incident{'' if n == 1 else 's'} {'is' if n == 1 else 'are'} past the SLA; {risk} more due within 2 hours. Most overdue:", _items(breached, route))

    # next / upcoming release
    if re.search(r"release", text) and re.search(r"next|upcoming|coming|soon|when|schedule", text):
        _t, _s, _l, _o, _ti, _ow, _as, _p, route, vis, vp = _scope("releases", user)
        rows = fetch_all(conn, f"select x.id, x.number, x.name as title, x.status, x.environment::text as env, x.deployment_at from releases x where {vis} and x.status <> 'Closed' and x.deployment_at >= now() order by x.deployment_at limit 3", vp)
        if not rows:
            return _answer(text, "There is no upcoming release scheduled.")
        r = rows[0]
        when = r["deployment_at"].strftime("%a %b %d at %H:%M UTC")
        return _answer(text, f"The next release is {r['number']} “{r['title']}” ({r['env']}), planned for {when} — status {r['status']}." + (" After that:" if len(rows) > 1 else ""), _items(rows, route))

    # unassigned
    if re.search(r"unassigned|not assigned|nobody|no one assigned|without (an )?assignee", text):
        table, _s, _l, open_cond, title, _ow, _as, _p, route, vis, vp = _scope("incidents", user)
        n = fetch_one(conn, f"select count(*) as n from incidents x where {vis} and {open_cond} and x.assignee_id is null", vp)["n"]
        rows = fetch_all(conn, f"select x.id, x.number, x.short_description as title, x.status from incidents x where {vis} and {open_cond} and x.assignee_id is null order by x.created_at desc limit 5", vp)
        return _answer(text, f"{n} open incident{'' if n == 1 else 's'} {'has' if n == 1 else 'have'} no assignee." + (" Latest:" if rows else ""), _items(rows, route))

    if kind or re.search(r"ticket|how many|\bcount\b|\btotal\b|latest|recent|\blast\b|\bmy\b|\bopen\b|\blist\b|\bshow\b", text):
        mine = bool(re.search(r"\bmy\b|\bmine\b|assigned to me|i raised|i created", text))
        wants_list = bool(re.search(r"\blast\b|latest|recent|newest|\blist\b|\bshow\b|which|what are|\btop\b|oldest", text)) or mine
        wants_count = bool(re.search(r"how many|\bcount\b|\btotal\b|number of", text))
        open_only = bool(re.search(r"\bopen\b|\bactive\b|unresolved|outstanding", text))
        include_closed = bool(re.search(r"\bclosed\b|\bresolved\b|\ball\b|\bever\b", text))

        if kind is None:  # "total tickets" without saying which kind: a summary of everything
            parts = []
            for k in KINDS:
                table, singular, level, open_cond, title, owner, assignee, prefix, route, vis, vp = _scope(k, user)
                r = fetch_one(conn, f"select count(*) as total, count(*) filter (where {open_cond}) as open from {table} x where {vis}", vp)
                parts.append(f"{r['total']} {k} ({r['open']} open)")
            return _answer(text, "You can see: " + ", ".join(parts) + ".", suggestions=SUGGESTIONS[:3])

        table, singular, level, open_cond, title, owner, assignee, prefix, route, vis, vp = _scope(kind, user)
        levels = _levels(text, kind)
        conds, params = [vis], dict(vp)
        if levels:
            conds.append(f"{level} = any(%(levels)s)")
            params["levels"] = levels
        if mine and owner:
            conds.append(f"(x.{owner} = %(me)s or x.{assignee} = %(me)s)")
            params["me"] = user.id
        where_all = " and ".join(conds)
        total = fetch_one(conn, f"select count(*) as n from {table} x where {where_all}", params)["n"]
        open_n = fetch_one(conn, f"select count(*) as n from {table} x where {where_all} and {open_cond}", params)["n"]
        noun_of = lambda n: _level_text(levels, kind) + (kind if n != 1 else singular)  # noqa: E731
        owner_text = " of yours" if mine else ""
        if wants_list and not wants_count:
            only_open = open_only or not include_closed
            where = where_all + (f" and {open_cond}" if only_open else "")
            rows = fetch_all(conn, f"select x.id, x.number, {title} as title, x.status from {table} x where {where} order by x.created_at desc limit 5", params)
            label = ("open " if only_open else "") + noun_of(len(rows))
            if not rows:
                return _answer(text, f"I found no {label}{owner_text}.")
            more = f" (of {open_n if only_open else total})" if (open_n if only_open else total) > len(rows) else ""
            return _answer(text, f"{'Your' if mine else 'The latest'} {len(rows)} {label}{more}:", _items(rows, route))
        if open_only and not include_closed:
            return _answer(text, f"There {'is' if open_n == 1 else 'are'} {open_n} open {noun_of(open_n)}{owner_text}.", [{"label": f"Open the {kind} list", "to": f"/{route}", "meta": None}])
        return _answer(text, f"There {'is' if total == 1 else 'are'} {total} {noun_of(total)}{owner_text} in total, {open_n} of them open.", [{"label": f"Open the {kind} list", "to": f"/{route}", "meta": None}])

    # nothing matched: look through knowledge base articles and incidents for the words
    words = [w for w in re.findall(r"[a-z0-9]{3,}", text) if w not in {"how", "the", "can", "what", "does", "this", "that", "with", "for", "and", "you", "are", "why"}][:5]
    if words:
        params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
        match = " or ".join(f"concat_ws(chr(32), x.title, x.body, x.category) ilike %(w{i})s" for i in range(len(words)))
        vis_kb = "true" if staff else "(x.status = 'published' and x.audience = 'everyone')"
        try:
            arts = fetch_all(conn, f"select x.id, x.title as number, '' as title, x.category as status from kb_articles x where {vis_kb} and ({match}) order by x.updated_at desc limit 3", params)
        except Exception:  # noqa: BLE001 - no customer selected yet
            arts = []
        if arts:
            return _answer(text, "I found these knowledge base articles that may help:",
                           [{"label": a["number"], "to": f"/kb/{a['id']}", "meta": a["status"]} for a in arts])
    return _answer(text, "I didn't quite get that. I can answer questions about your tickets, releases, approvals and SLAs. Try one of these:", suggestions=SUGGESTIONS)
