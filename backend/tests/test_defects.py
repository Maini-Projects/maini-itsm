"""Defects: raise, scoping by role and team, edit rules, assignment, the workflow, notes, activity, reports, audit."""
from conftest import IDS, as_user

API = "/api/v1"


def raise_defect(client, who="devemp", **over):
    body = {"title": "Totals wrong on invoice screen", "severity": "High", "environment": "UAT", **over}
    r = client.post(f"{API}/defects", json=body, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def dmove(client, who, did, to, **extra):
    return client.post(f"{API}/defects/{did}/transition", json={"to_status": to, **extra}, headers=as_user(who))


def dassign(client, who, did, assignee):
    return client.post(f"{API}/defects/{did}/assign", json={"assignee_id": str(IDS[assignee])}, headers=as_user(who))


def to_resolved(client, worker, did):
    assert dassign(client, "admin", did, worker).status_code == 200
    assert dmove(client, worker, did, "In Progress").status_code == 200
    r = dmove(client, worker, did, "Resolved", resolution_notes="Fixed the rounding.")
    assert r.status_code == 200, r.text
    return r.json()


# ---- raising and seeing --------------------------------------------------------------------

def test_new_defect_gets_number_team_and_starts_new(client):
    d = raise_defect(client, description="Total shows 99.9", steps_to_reproduce="Open invoice 12",
                     expected_result="100.00", actual_result="99.90")
    assert d["number"].startswith("DEF-") and d["status"] == "New" and d["severity"] == "High"
    assert d["environment"] == "UAT" and d["team_name"] == "Development" and d["raised_by_name"] == "Devemp"
    assert d["assignee_id"] is None and d["can_manage"] is False
    assert d["steps_to_reproduce"] == "Open invoice 12" and d["actual_result"] == "99.90"


def test_defaults_and_validation(client):
    d = client.post(f"{API}/defects", json={"title": "Minimal defect"}, headers=as_user("devemp")).json()
    assert d["severity"] == "Medium" and d["environment"] == "Production"
    for bad in ({"title": "x"}, {"title": "Fine title", "severity": "Urgent"},
                {"title": "Fine title", "environment": "Dev"}, {}):
        r = client.post(f"{API}/defects", json=bad, headers=as_user("devemp"))
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert client.post(f"{API}/defects", json={"title": "Needs login"}).status_code == 401


def test_visibility_by_role_and_team(client):
    d = raise_defect(client, "devemp")
    assert client.get(f"{API}/defects", headers=as_user("devemp")).json()["total"] == 1
    assert client.get(f"{API}/defects", headers=as_user("devemp2")).json()["total"] == 0      # same team, not theirs
    assert client.get(f"{API}/defects", headers=as_user("supemp")).json()["total"] == 0
    assert client.get(f"{API}/defects", headers=as_user("devmgr")).json()["total"] == 1       # their team
    assert client.get(f"{API}/defects", headers=as_user("supmgr")).json()["total"] == 0       # other team
    assert client.get(f"{API}/defects", headers=as_user("admin")).json()["total"] == 1
    for who, code in (("devemp2", 404), ("supemp", 404), ("supmgr", 404), ("devmgr", 200), ("admin", 200)):
        assert client.get(f"{API}/defects/{d['id']}", headers=as_user(who)).status_code == code, who
    assert client.get(f"{API}/defects/{d['id']}", headers=as_user("devmgr")).json()["can_manage"] is True


def test_list_filters_and_paging(client):
    a = raise_defect(client, "devemp", title="Alpha crash", severity="Critical", environment="Production")
    raise_defect(client, "devemp", title="Beta typo", severity="Low", environment="UAT")
    h = as_user("admin")
    get = lambda **p: client.get(f"{API}/defects", params=p, headers=h).json()
    assert get(q="alpha")["total"] == 1 and get(q=a["number"])["total"] == 1
    assert get(severity="Low")["items"][0]["title"] == "Beta typo"
    assert get(environment="Production")["total"] == 1
    assert get(status="New")["total"] == 2 and get(status="Closed")["total"] == 0
    assert get(team_id=str(a["team_id"]))["total"] == 2
    assert get(mine=True)["total"] == 0 and get(open_only=True)["total"] == 2
    page = get(limit=1, offset=1)
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get(f"{API}/defects", params={"severity": "Huge"}, headers=h).status_code == 422


# ---- editing -------------------------------------------------------------------------------

def test_edit_rules(client):
    d = raise_defect(client, "devemp")
    did = d["id"]
    ok = client.patch(f"{API}/defects/{did}", json={"title": "Better title", "actual_result": "x"},
                      headers=as_user("devemp"))
    assert ok.status_code == 200 and ok.json()["title"] == "Better title"
    sev = client.patch(f"{API}/defects/{did}", json={"severity": "Critical"}, headers=as_user("devemp"))
    assert sev.status_code == 403
    assert client.patch(f"{API}/defects/{did}", json={"title": "Hijacked"}, headers=as_user("devemp2")).status_code == 404
    assert client.patch(f"{API}/defects/{did}", json={}, headers=as_user("devmgr")).status_code == 422
    staff = client.patch(f"{API}/defects/{did}", json={"severity": "Critical", "environment": "Production"},
                         headers=as_user("devmgr"))
    assert staff.status_code == 200 and staff.json()["severity"] == "Critical" and staff.json()["can_manage"] is True
    dassign(client, "devmgr", did, "devmgr")
    late = client.patch(f"{API}/defects/{did}", json={"title": "Too late now"}, headers=as_user("devemp"))
    assert late.status_code == 403                                              # no longer New
    assert client.patch(f"{API}/defects/{did}", json={"title": "Spy spy"}, headers=as_user("supmgr")).status_code == 404


def test_closed_defect_cannot_be_edited_or_reassigned(client):
    d = raise_defect(client)
    to_resolved(client, "devmgr", d["id"])
    assert dmove(client, "devemp", d["id"], "Closed").status_code == 200
    r = client.patch(f"{API}/defects/{d['id']}", json={"description": "x"}, headers=as_user("admin"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "defect_closed"
    assert dassign(client, "admin", d["id"], "admin").status_code == 409


# ---- assigning -----------------------------------------------------------------------------

def test_assignment_rules(client):
    d = raise_defect(client)
    did = d["id"]
    assert dassign(client, "devemp", did, "devmgr").status_code == 403                  # employees cannot assign
    assert dassign(client, "supmgr", did, "supmgr").status_code == 404                  # other team cannot see it
    bad = dassign(client, "devmgr", did, "devemp2")                                      # only managers or admins
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_assignee"
    other = dassign(client, "devmgr", did, "supmgr")                                     # not another team's manager
    assert other.status_code == 422
    ok = dassign(client, "devmgr", did, "devmgr")
    assert ok.status_code == 200 and ok.json()["status"] == "Assigned" and ok.json()["assignee_name"] == "Devmgr"
    again = dassign(client, "devmgr", did, "admin")                                      # reassign keeps the status
    assert again.status_code == 200 and again.json()["status"] == "Assigned" and again.json()["assignee_name"] == "Admin"


# ---- the workflow --------------------------------------------------------------------------

def test_full_workflow_and_stamps(client):
    d = raise_defect(client)
    did = d["id"]
    assert dassign(client, "admin", did, "devmgr").json()["status"] == "Assigned"
    r = dmove(client, "devmgr", did, "In Progress")
    assert r.status_code == 200 and r.json()["status"] == "In Progress"
    assert dmove(client, "devmgr", did, "Pending").json()["status"] == "Pending"
    assert dmove(client, "devmgr", did, "In Progress").json()["status"] == "In Progress"
    r = dmove(client, "devmgr", did, "Resolved", resolution_notes="Rounded correctly")
    assert r.status_code == 200 and r.json()["resolved_at"] and r.json()["resolution_notes"] == "Rounded correctly"
    r = dmove(client, "devmgr", did, "Closed")
    assert r.status_code == 200 and r.json()["status"] == "Closed" and r.json()["closed_at"]
    assert client.get(f"{API}/approvals?status=all", headers=as_user("admin")).json() == []   # no approvals, ever


def test_workflow_rules_are_enforced_with_clear_errors(client):
    did = raise_defect(client)["id"]
    r = dmove(client, "devmgr", did, "Closed")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    r = dmove(client, "devmgr", did, "Assigned")
    assert r.status_code == 422 and r.json()["error"]["code"] == "assignee_required"
    dassign(client, "devmgr", did, "devmgr")
    dmove(client, "devmgr", did, "In Progress")
    r = dmove(client, "devmgr", did, "Resolved")
    assert r.status_code == 422 and r.json()["error"]["code"] == "resolution_notes_required"
    assert dmove(client, "devmgr", did, "Pending Approval").status_code == 422          # no such status
    assert dmove(client, "supmgr", did, "Resolved", resolution_notes="x").status_code == 404


def test_reporter_can_confirm_or_reopen_only_when_resolved(client):
    did = raise_defect(client)["id"]
    assert dmove(client, "devemp", did, "In Progress").status_code == 403
    to_resolved(client, "devmgr", did)
    assert dmove(client, "devemp2", did, "Closed").status_code == 404
    assert dmove(client, "devemp", did, "Resolved", resolution_notes="me").status_code == 403
    r = dmove(client, "devemp", did, "In Progress")                                      # reopen
    assert r.status_code == 200 and r.json()["status"] == "In Progress" and r.json()["resolved_at"] is None
    to = client.get(f"{API}/defects/{did}", headers=as_user("devemp")).json()
    assert to["status"] == "In Progress"
    dmove(client, "devmgr", did, "Resolved", resolution_notes="Really fixed")
    assert dmove(client, "devemp", did, "Closed").json()["status"] == "Closed"


# ---- notes and activity --------------------------------------------------------------------

def test_notes_internal_notes_and_activity(client):
    d = raise_defect(client)
    did = d["id"]
    base = f"{API}/defects/{did}/comments"
    assert client.post(base, json={"body": "Any update?"}, headers=as_user("devemp")).status_code == 201
    assert client.post(base, json={"body": "secret", "internal": True}, headers=as_user("devemp")).status_code == 403
    assert client.post(base, json={"body": "Looking into it", "internal": True}, headers=as_user("devmgr")).status_code == 201
    assert client.post(base, json={"body": ""}, headers=as_user("devemp")).status_code == 422
    assert client.post(base, json={"body": "hi"}, headers=as_user("supmgr")).status_code == 404
    assert [c["body"] for c in client.get(base, headers=as_user("devemp")).json()] == ["Any update?"]
    assert len(client.get(base, headers=as_user("devmgr")).json()) == 2

    dassign(client, "devmgr", did, "devmgr")
    client.patch(f"{API}/defects/{did}", json={"severity": "Critical"}, headers=as_user("devmgr"))
    dmove(client, "devmgr", did, "In Progress")
    events = client.get(f"{API}/defects/{did}/activity", headers=as_user("devmgr")).json()
    texts = [e["text"] for e in events]
    assert "Defect created" in texts and "Assigned to Devmgr" in texts
    assert "Status changed from Assigned to In Progress" in texts
    assert "Severity changed from High to Critical" in texts
    assert any(e["type"] == "note" and e["internal"] for e in events)
    assert [e["at"] for e in events] == sorted((e["at"] for e in events), reverse=True)
    reporter_view = client.get(f"{API}/defects/{did}/activity", headers=as_user("devemp")).json()
    assert not any(e.get("internal") for e in reporter_view) and any(e["type"] == "note" for e in reporter_view)
    assert client.get(f"{API}/defects/{did}/activity", headers=as_user("supmgr")).status_code == 404


# ---- menu, dashboard, reports, audit -------------------------------------------------------

def test_menu_and_dashboard_include_defects(client):
    for who in ("devemp", "devmgr", "admin"):
        assert "defects" in client.get(f"{API}/me", headers=as_user(who)).json()["menu"]
    raise_defect(client, "devemp", severity="Critical")
    raise_defect(client, "supemp", severity="Low")
    done = raise_defect(client, "devemp", severity="High")
    to_resolved(client, "devmgr", done["id"])
    s = lambda who: client.get(f"{API}/dashboard/summary", headers=as_user(who)).json()["defects"]
    assert s("admin") == {"open": 2, "critical_open": 1}
    assert s("devmgr") == {"open": 1, "critical_open": 1}
    assert s("supmgr") == {"open": 1, "critical_open": 0}
    assert s("devemp") == {"open": 1, "critical_open": 1}
    assert s("devemp2") == {"open": 0, "critical_open": 0}


def test_defect_reports(client):
    raise_defect(client, "devemp", severity="Critical")
    raise_defect(client, "supemp", severity="Low", title="Typo in footer")
    keys = {r["key"] for r in client.get(f"{API}/reports", headers=as_user("admin")).json()}
    assert {"open_defects", "defects_by_severity"} <= keys
    openr = client.get(f"{API}/reports/open_defects", headers=as_user("admin")).json()
    assert [r["severity"] for r in openr["rows"]] == ["Critical", "Low"]                 # worst first
    assert openr["rows"][0]["number"].startswith("DEF-")
    mine = client.get(f"{API}/reports/open_defects", headers=as_user("supmgr")).json()
    assert [r["title"] for r in mine["rows"]] == ["Typo in footer"]
    sev = client.get(f"{API}/reports/defects_by_severity", headers=as_user("admin")).json()
    assert dict(zip(sev["chart"]["labels"], sev["chart"]["values"])) == {"Critical": 1, "Low": 1}
    csv_text = client.get(f"{API}/reports/open_defects", params={"format": "csv"}, headers=as_user("admin")).text
    assert csv_text.startswith("﻿Defect,Title,Severity")


def test_defects_are_in_the_audit_history(client):
    d = raise_defect(client)
    dassign(client, "admin", d["id"], "devmgr")
    h = as_user("admin")
    rows = client.get(f"{API}/audit", params={"table": "defects", "record": d["number"]}, headers=h).json()
    assert rows["total"] == 2 and {r["record"] for r in rows["items"]} == {d["number"]}
    update = next(r for r in rows["items"] if r["action"] == "UPDATE")
    assert update["summary"] == "Updated defect" and update["old_status"] == "New" and update["new_status"] == "Assigned"
    assert "assignee_id" in update["changed_fields"] and update["actor_name"] == "Admin"
    created = next(r for r in rows["items"] if r["action"] == "INSERT")
    assert created["summary"] == "Created defect" and created["actor_name"] == "Devemp"
