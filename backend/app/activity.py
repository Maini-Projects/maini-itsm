"""Activity timeline (created, status, owner, priority changes) built from the audit log."""
from .db import fetch_all

SINGULAR = {"problems": "Problem", "changes": "Change", "releases": "Release"}


def timeline(conn, table: str, record_id, owner_key: str | None = None) -> list[dict]:
    """Newest-first events for one record. `owner_key` is the audit field holding the person responsible
    (problems: owner_id), or None when the record has no assignable owner."""
    rows = fetch_all(
        conn,
        """select a.at, a.action, p.full_name as actor_name,
                  a.old_values ->> 'status' as old_status, a.new_values ->> 'status' as new_status,
                  a.old_values ->> %(ok)s as old_owner,    a.new_values ->> %(ok)s as new_owner,
                  a.old_values ->> 'priority' as old_priority, a.new_values ->> 'priority' as new_priority
             from audit_log a left join profiles p on p.id = a.actor_id
            where a.table_name = %(t)s and a.record_id = %(id)s
            order by a.id desc""",
        {"t": table, "id": record_id, "ok": owner_key or "-"},
    )
    ids = {r[k] for r in rows for k in ("old_owner", "new_owner") if r[k]}
    names = {}
    if ids:
        names = {str(r["id"]): r["full_name"] for r in
                 fetch_all(conn, "select id, full_name from profiles where id = any(%(ids)s::uuid[])",
                           {"ids": list(ids)})}
    events = []
    for r in rows:
        who = r["actor_name"] or "System"
        if r["action"] == "INSERT":
            events.append({"at": r["at"], "type": "created", "actor": who, "text": f"{SINGULAR[table]} created"})
            continue
        if r["old_status"] != r["new_status"]:
            events.append({"at": r["at"], "type": "status", "actor": who,
                           "text": f"Status changed from {r['old_status']} to {r['new_status']}"})
        if owner_key and r["old_owner"] != r["new_owner"]:
            events.append({"at": r["at"], "type": "assignment", "actor": who,
                           "text": f"Owner set to {names.get(r['new_owner'], 'nobody')}"})
        if r["old_priority"] != r["new_priority"]:
            events.append({"at": r["at"], "type": "priority", "actor": who,
                           "text": f"Priority changed from {r['old_priority']} to {r['new_priority']}"})
    return events
