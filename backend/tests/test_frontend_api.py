"""Tests for the endpoints the web front end uses: sign-in, passwords, problems, changes, releases, reports, audit."""
from conftest import DEFAULT_PASSWORD, IDS, as_user

API = "/api/v1"


# ---- sign in, refresh, passwords -----------------------------------------------------------

def test_login_returns_a_session_that_works(client):
    r = client.post(f"{API}/auth/login", json={"email": "devmgr@test.local", "password": DEFAULT_PASSWORD})
    assert r.status_code == 200
    s = r.json()
    assert {"access_token", "refresh_token", "expires_in"} <= set(s)
    me = client.get(f"{API}/me", headers={"Authorization": f"Bearer {s['access_token']}"})
    assert me.status_code == 200 and me.json()["role"] == "manager"


def test_login_wrong_password_or_unknown_email(client):
    for body in ({"email": "devmgr@test.local", "password": "nope"}, {"email": "ghost@test.local", "password": "x"}):
        r = client.post(f"{API}/auth/login", json=body)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


def test_login_validates_input(client):
    r = client.post(f"{API}/auth/login", json={"email": "", "password": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert client.post(f"{API}/auth/login", json={}).status_code == 422


def test_refresh(client):
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": "r-admin"})
    assert r.status_code == 200 and r.json()["access_token"] == "t-admin"
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": "r-bogus"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_change_own_password(client):
    h = as_user("devemp")
    bad = client.post(f"{API}/auth/password", json={"current_password": "wrong", "new_password": "newpass123"}, headers=h)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "wrong_password"
    short = client.post(f"{API}/auth/password", json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
                        headers=h)
    assert short.status_code == 422 and short.json()["error"]["code"] == "validation_error"
    same = client.post(f"{API}/auth/password",
                       json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD}, headers=h)
    assert same.status_code == 422 and same.json()["error"]["code"] == "same_password"
    ok = client.post(f"{API}/auth/password",
                     json={"current_password": DEFAULT_PASSWORD, "new_password": "newpass123"}, headers=h)
    assert ok.status_code == 200
    # old password no longer signs in, new one does
    assert client.post(f"{API}/auth/login", json={"email": "devemp@test.local", "password": DEFAULT_PASSWORD}
                       ).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "devemp@test.local", "password": "newpass123"}
                       ).status_code == 200
    assert client.post(f"{API}/auth/password", json={"current_password": "a", "new_password": "newpass123"}
                       ).status_code == 401  # needs a login


def test_admin_resets_a_password_and_others_cannot(client):
    uid = IDS["supemp"]
    body = {"new_password": "reset-pass-1"}
    assert client.post(f"{API}/users/{uid}/password", json=body, headers=as_user("devmgr")).status_code == 403
    assert client.post(f"{API}/users/{uid}/password", json=body, headers=as_user("supemp")).status_code == 403
    assert client.post(f"{API}/users/{uid}/password", json={"new_password": "short"},
                       headers=as_user("admin")).status_code == 422
    missing = client.post(f"{API}/users/00000000-0000-0000-0000-0000000000ff/password", json=body,
                          headers=as_user("admin"))
    assert missing.status_code == 404
    assert client.post(f"{API}/users/{uid}/password", json=body, headers=as_user("admin")).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "supemp@test.local", "password": "reset-pass-1"}
                       ).status_code == 200


def test_cors_allows_the_front_end_origin(client):
    r = client.options(f"{API}/me", headers={"Origin": "http://localhost:5173",
                                             "Access-Control-Request-Method": "GET",
                                             "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = client.options(f"{API}/me", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


# ---- problems ------------------------------------------------------------------------------

def new_problem(client, who="devemp", **over):
    r = client.post(f"{API}/problems", json={"title": "Recurring posting failures", **over}, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def raise_incident(client, who="devemp", **over):
    r = client.post(f"{API}/incidents", json={"short_description": "Posting is slow", **over}, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def pmove(client, who, pid, to):
    return client.post(f"{API}/problems/{pid}/transition", json={"to_status": to}, headers=as_user(who))


def test_employee_raises_and_sees_only_own_problems(client):
    p = new_problem(client, "devemp", description="Impact")
    assert p["number"].startswith("PRB-") and p["status"] == "Identified" and p["priority"] == "P3"
    assert p["raised_by_name"] == "Devemp" and p["team_name"] == "Development" and p["can_manage"] is False
    mine = client.get(f"{API}/problems", headers=as_user("devemp")).json()
    assert mine["total"] == 1 and mine["items"][0]["related_incidents"] == 0
    assert client.get(f"{API}/problems", headers=as_user("devemp2")).json()["total"] == 0
    assert client.get(f"{API}/problems/{p['id']}", headers=as_user("devemp2")).status_code == 404
    assert client.get(f"{API}/problems/{p['id']}", headers=as_user("supmgr")).status_code == 404
    assert client.get(f"{API}/problems/{p['id']}", headers=as_user("devmgr")).json()["can_manage"] is True
    assert client.get(f"{API}/problems", headers=as_user("admin")).json()["total"] == 1
    assert client.get(f"{API}/problems", headers=as_user("supmgr")).json()["total"] == 0


def test_problem_create_rules(client):
    r = client.post(f"{API}/problems", json={"title": "x"}, headers=as_user("devemp"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post(f"{API}/problems", json={"title": "Priority grab", "priority": "P1"}, headers=as_user("devemp"))
    assert r.status_code == 403
    p = new_problem(client, "devmgr", priority="P1")
    assert p["priority"] == "P1"
    assert client.post(f"{API}/problems", json={"title": "Needs login"}).status_code == 401


def test_problem_list_filters(client):
    a = new_problem(client, "devmgr", title="Alpha failure", priority="P1")
    new_problem(client, "devmgr", title="Beta failure", priority="P4")
    assert client.get(f"{API}/problems", params={"q": "alpha"}, headers=as_user("admin")).json()["total"] == 1
    assert client.get(f"{API}/problems", params={"priority": "P4"}, headers=as_user("admin")).json()["total"] == 1
    assert client.get(f"{API}/problems", params={"status": "Closed"}, headers=as_user("admin")).json()["total"] == 0
    assert client.get(f"{API}/problems", params={"q": a["number"]}, headers=as_user("admin")).json()["total"] == 1
    page = client.get(f"{API}/problems", params={"limit": 1, "offset": 1}, headers=as_user("admin")).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get(f"{API}/problems", params={"priority": "P9"}, headers=as_user("admin")).status_code == 422


def test_problem_editing_rules(client):
    p = new_problem(client, "devemp")
    pid = p["id"]
    ok = client.patch(f"{API}/problems/{pid}", json={"title": "Better title"}, headers=as_user("devemp"))
    assert ok.status_code == 200 and ok.json()["title"] == "Better title"
    staff_field = client.patch(f"{API}/problems/{pid}", json={"root_cause": "x"}, headers=as_user("devemp"))
    assert staff_field.status_code == 403
    assert client.patch(f"{API}/problems/{pid}", json={"title": "Hijack"}, headers=as_user("devemp2")).status_code == 404
    assert client.patch(f"{API}/problems/{pid}", json={}, headers=as_user("devmgr")).status_code == 422
    done = client.patch(f"{API}/problems/{pid}", json={"root_cause": "Bad index", "workaround": "Restart",
                                                       "permanent_solution": "Rebuild", "priority": "P2"},
                        headers=as_user("devmgr"))
    assert done.status_code == 200 and done.json()["root_cause"] == "Bad index" and done.json()["priority"] == "P2"
    # once past Identified the raiser can no longer edit
    assert pmove(client, "devmgr", pid, "Investigating").status_code == 200
    assert client.patch(f"{API}/problems/{pid}", json={"title": "Late edit"}, headers=as_user("devemp")).status_code == 403
    # other team's manager cannot see it
    assert client.patch(f"{API}/problems/{pid}", json={"title": "x" * 5}, headers=as_user("supmgr")).status_code == 404


def test_problem_workflow_owner_and_activity(client):
    p = new_problem(client, "devmgr")
    pid = p["id"]
    assert pmove(client, "devemp", pid, "Investigating").status_code == 403
    assert pmove(client, "devmgr", pid, "Fix Planned").status_code == 409        # skipping steps
    assert pmove(client, "devmgr", pid, "Investigating").status_code == 200
    r = pmove(client, "devmgr", pid, "Root Cause Identified")                    # needs the root cause first
    assert r.status_code == 422 and r.json()["error"]["code"] == "root_cause_required"
    client.patch(f"{API}/problems/{pid}", json={"root_cause": "Bad index"}, headers=as_user("devmgr"))
    for step in ("Root Cause Identified", "Fix Planned", "Resolved", "Closed"):
        r = pmove(client, "devmgr", pid, step)
        assert r.status_code == 200 and r.json()["status"] == step, r.text
    closed = client.patch(f"{API}/problems/{pid}", json={"title": "Edit closed"}, headers=as_user("admin"))
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "problem_closed"
    assert pmove(client, "supmgr", pid, "Investigating").status_code == 404

    q = new_problem(client, "devemp")
    bad = client.post(f"{API}/problems/{q['id']}/assign", json={"owner_id": str(IDS["supemp"])}, headers=as_user("devmgr"))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_assignee"
    other_team = client.post(f"{API}/problems/{q['id']}/assign", json={"owner_id": str(IDS["supmgr"])},
                             headers=as_user("devmgr"))
    assert other_team.status_code == 422
    assert client.post(f"{API}/problems/{q['id']}/assign", json={"owner_id": str(IDS["devmgr"])},
                       headers=as_user("devemp")).status_code == 403
    ok = client.post(f"{API}/problems/{q['id']}/assign", json={"owner_id": str(IDS["devmgr"])}, headers=as_user("devmgr"))
    assert ok.status_code == 200 and ok.json()["owner_name"] == "Devmgr"
    events = client.get(f"{API}/problems/{q['id']}/activity", headers=as_user("devmgr")).json()
    texts = [e["text"] for e in events]
    assert "Problem created" in texts and "Owner set to Devmgr" in texts
    assert client.get(f"{API}/problems/{q['id']}/activity", headers=as_user("supmgr")).status_code == 404


def test_problem_incident_links(client):
    p = new_problem(client, "devmgr")
    inc = raise_incident(client, "devemp")
    pid, iid = p["id"], inc["id"]
    assert client.post(f"{API}/problems/{pid}/incidents", json={"incident_id": iid},
                       headers=as_user("devemp")).status_code == 403
    ok = client.post(f"{API}/problems/{pid}/incidents", json={"incident_id": iid}, headers=as_user("devmgr"))
    assert ok.status_code == 201 and ok.json()["related_incidents"] == 1
    assert ok.json()["incidents"][0]["number"] == inc["number"]
    again = client.post(f"{API}/problems/{pid}/incidents", json={"incident_id": iid}, headers=as_user("devmgr"))
    assert again.status_code == 201 and again.json()["related_incidents"] == 1   # no duplicate
    # a manager cannot link an incident they cannot see
    hidden = raise_incident(client, "supemp")
    r = client.post(f"{API}/problems/{pid}/incidents", json={"incident_id": hidden["id"]}, headers=as_user("devmgr"))
    assert r.status_code == 404
    assert client.get(f"{API}/problems", headers=as_user("devmgr")).json()["items"][0]["related_incidents"] == 1
    gone = client.delete(f"{API}/problems/{pid}/incidents/{iid}", headers=as_user("devmgr"))
    assert gone.status_code == 200 and gone.json()["related_incidents"] == 0
    assert client.delete(f"{API}/problems/{pid}/incidents/{iid}", headers=as_user("devmgr")).status_code == 404
    assert client.delete(f"{API}/problems/{pid}/incidents/{iid}", headers=as_user("devemp")).status_code == 403


# ---- changes -------------------------------------------------------------------------------

FULL_CHANGE = {"title": "Upgrade ERP patch", "type": "Normal", "risk": "High",
               "implementation_plan": "Apply patch", "backout_plan": "Restore snapshot", "test_plan": "Smoke test",
               "planned_start": "2026-11-01T09:00:00Z", "planned_end": "2026-11-01T11:00:00Z"}


def new_change(client, who="devmgr", **over):
    r = client.post(f"{API}/changes", json={**FULL_CHANGE, **over}, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def cmove(client, who, cid, to):
    return client.post(f"{API}/changes/{cid}/transition", json={"to_status": to}, headers=as_user(who))


def decide(client, who, approval_id, decision="approved", comment=None):
    return client.post(f"{API}/approvals/{approval_id}/decision", json={"decision": decision, "comment": comment},
                       headers=as_user(who))


def test_everyone_can_read_changes_but_only_staff_can_write(client):
    assert client.get(f"{API}/changes").status_code == 401
    c = new_change(client)
    cid = c["id"]
    for who in ("devemp", "devemp2", "supemp"):                                    # employees: read-only, any team
        assert client.get(f"{API}/changes", headers=as_user(who)).json()["total"] == 1, who
        d = client.get(f"{API}/changes/{cid}", headers=as_user(who))
        assert d.status_code == 200 and d.json()["can_manage"] is False, who
        assert client.get(f"{API}/changes/{cid}/activity", headers=as_user(who)).status_code == 200
        assert client.post(f"{API}/changes", json=FULL_CHANGE, headers=as_user(who)).status_code == 403
        assert client.patch(f"{API}/changes/{cid}", json={"title": "Not allowed"}, headers=as_user(who)).status_code == 403
        assert cmove(client, who, cid, "Submitted").status_code == 403
    assert client.get(f"{API}/changes/{cid}", headers=as_user("supmgr")).json()["can_manage"] is False


def test_manager_raises_and_scoping(client):
    c = new_change(client, "devmgr")
    assert c["number"].startswith("CHG-") and c["status"] == "Draft" and c["can_manage"] is True
    assert c["requester_name"] == "Devmgr" and c["team_name"] == "Development"
    assert c["releases"] == [] and c["approvals"] == []
    other = client.get(f"{API}/changes/{c['id']}", headers=as_user("supmgr"))        # another team: can read, not change
    assert other.status_code == 200 and other.json()["can_manage"] is False
    assert client.get(f"{API}/changes", headers=as_user("supmgr")).json()["total"] == 1
    assert client.get(f"{API}/changes", headers=as_user("admin")).json()["total"] == 1
    admin_made = new_change(client, "admin", title="Admin change")
    seen = client.get(f"{API}/changes/{admin_made['id']}", headers=as_user("devmgr")).json()
    assert seen["can_manage"] is False and seen["title"] == "Admin change"
    assert client.patch(f"{API}/changes/{admin_made['id']}", json={"title": "Edited by manager"},
                        headers=as_user("devmgr")).status_code == 403


def test_change_validation_and_filters(client):
    bad = client.post(f"{API}/changes", json={**FULL_CHANGE, "planned_end": "2026-10-01T00:00:00Z"},
                      headers=as_user("devmgr"))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_dates"
    assert client.post(f"{API}/changes", json={**FULL_CHANGE, "type": "Weird"}, headers=as_user("devmgr")).status_code == 422
    new_change(client, title="Emergency fix", type="Emergency", risk="Low")
    new_change(client, title="Routine job", type="Standard", risk="Medium")
    h = as_user("admin")
    assert client.get(f"{API}/changes", params={"type": "Emergency"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/changes", params={"risk": "Medium"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/changes", params={"q": "routine"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/changes", params={"status": "Draft"}, headers=h).json()["total"] == 2
    assert client.get(f"{API}/changes", params={"status": "Closed"}, headers=h).json()["total"] == 0


def test_change_edit_rules(client):
    c = new_change(client)
    cid = c["id"]
    ok = client.patch(f"{API}/changes/{cid}", json={"title": "Renamed change", "risk": "Low"}, headers=as_user("devmgr"))
    assert ok.status_code == 200 and ok.json()["title"] == "Renamed change" and ok.json()["risk"] == "Low"
    assert client.patch(f"{API}/changes/{cid}", json={"title": "Nope nope"}, headers=as_user("supmgr")).status_code == 403
    assert client.patch(f"{API}/changes/{cid}", json={}, headers=as_user("devmgr")).status_code == 422
    dates = client.patch(f"{API}/changes/{cid}", json={"planned_end": "2020-01-01T00:00:00Z"}, headers=as_user("devmgr"))
    assert dates.status_code == 422
    assert cmove(client, "devmgr", cid, "Submitted").status_code == 200
    locked = client.patch(f"{API}/changes/{cid}", json={"title": "Too late"}, headers=as_user("devmgr"))
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "change_locked"
    assert client.patch(f"{API}/changes/{cid}", json={"title": "Admin edit"}, headers=as_user("admin")).status_code == 200


def test_change_full_lifecycle_with_admin_approval(client):
    c = new_change(client)
    cid = c["id"]
    assert cmove(client, "devmgr", cid, "Submitted").json()["status"] == "Submitted"
    assert cmove(client, "devmgr", cid, "Implementation").status_code == 409           # skipping steps
    assert cmove(client, "devmgr", cid, "Under Review").json()["status"] == "Under Review"
    sent = cmove(client, "devmgr", cid, "Approval Pending")
    assert sent.status_code == 200 and sent.json()["approvals"][0]["status"] == "pending"
    again = cmove(client, "devmgr", cid, "Implementation")
    assert again.status_code == 409 and again.json()["error"]["code"] == "awaiting_approval"
    aid = sent.json()["approvals"][0]["id"]
    # the manager who raised it cannot approve; neither can another team's manager
    assert decide(client, "devmgr", aid).status_code == 404 or decide(client, "devmgr", aid).status_code == 403
    assert decide(client, "supmgr", aid).status_code == 404
    reject = decide(client, "admin", aid, "rejected")                                   # a reason is needed
    assert reject.status_code == 422
    assert decide(client, "admin", aid, "rejected", "Needs a test plan").status_code == 200
    back = client.get(f"{API}/changes/{cid}", headers=as_user("devmgr")).json()
    assert back["status"] == "Draft" and back["approvals"][0]["comment"] == "Needs a test plan"
    assert back["approvals"][0]["decided_by_name"] == "Admin"
    for step in ("Submitted", "Under Review", "Approval Pending"):
        assert cmove(client, "devmgr", cid, step).status_code == 200
    aid2 = client.get(f"{API}/changes/{cid}", headers=as_user("admin")).json()["approvals"][0]["id"]
    assert decide(client, "admin", aid2).status_code == 200
    sched = client.get(f"{API}/changes/{cid}", headers=as_user("devmgr")).json()
    assert sched["status"] == "Scheduled" and len(sched["approvals"]) == 2
    for step in ("Implementation", "Implemented", "Closed"):
        r = cmove(client, "devmgr", cid, step)
        assert r.status_code == 200 and r.json()["status"] == step, r.text
    texts = [e["text"] for e in client.get(f"{API}/changes/{cid}/activity", headers=as_user("devmgr")).json()]
    assert "Change created" in texts and "Status changed from Implemented to Closed" in texts
    assert client.get(f"{API}/changes/{cid}/activity", headers=as_user("supmgr")).status_code == 200   # readable by all


def test_change_needs_plans_before_approval(client):
    c = new_change(client, implementation_plan=None, backout_plan=None, planned_start=None, planned_end=None)
    cid = c["id"]
    for step in ("Submitted", "Under Review"):
        assert cmove(client, "devmgr", cid, step).status_code == 200
    r = cmove(client, "devmgr", cid, "Approval Pending")
    assert r.status_code == 422 and r.json()["error"]["code"] == "incomplete_change"
    assert "implementation plan" in r.json()["error"]["message"] and "planned start" in r.json()["error"]["message"]
    # admin can fill the gaps even though it is no longer a Draft
    fix = client.patch(f"{API}/changes/{cid}", json={"implementation_plan": "Do it", "backout_plan": "Undo it",
                                                     "planned_start": "2026-11-01T09:00:00Z"}, headers=as_user("admin"))
    assert fix.status_code == 200
    assert cmove(client, "devmgr", cid, "Approval Pending").status_code == 200


def test_change_transition_cannot_fake_approval(client):
    c = new_change(client)
    for status in ("Scheduled", "Draft", "Nonsense"):
        assert cmove(client, "devmgr", c["id"], status).status_code == 422
    assert cmove(client, "devemp", c["id"], "Submitted").status_code == 403


# ---- releases ------------------------------------------------------------------------------

FULL_RELEASE = {"name": "Q4 ERP release", "environment": "Production", "scope": "Patch + reports",
                "rollback_plan": "Restore backup", "deployment_at": "2026-11-05T22:00:00Z"}


def new_release(client, who="devmgr", **over):
    r = client.post(f"{API}/releases", json={**FULL_RELEASE, **over}, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def rmove(client, who, rid, to):
    return client.post(f"{API}/releases/{rid}/transition", json={"to_status": to}, headers=as_user(who))


def test_everyone_can_read_releases_but_only_staff_can_write(client):
    assert client.get(f"{API}/releases").status_code == 401
    assert client.post(f"{API}/releases", json=FULL_RELEASE, headers=as_user("devemp")).status_code == 403
    r = new_release(client)
    assert r["number"].startswith("REL-") and r["status"] == "Planned" and r["owner_name"] == "Devmgr"
    assert r["changes"] == [] and r["approvals"] == [] and r["can_manage"] is True
    for who in ("devemp", "supemp", "supmgr"):                                     # read-only for everyone else
        d = client.get(f"{API}/releases/{r['id']}", headers=as_user(who))
        assert d.status_code == 200 and d.json()["can_manage"] is False, who
        assert client.get(f"{API}/releases", headers=as_user(who)).json()["total"] == 1, who
        assert client.get(f"{API}/releases/{r['id']}/activity", headers=as_user(who)).status_code == 200
        assert client.patch(f"{API}/releases/{r['id']}", json={"name": "Not allowed"}, headers=as_user(who)).status_code == 403
        assert rmove(client, who, r["id"], "Under Review").status_code == 403
    assert client.get(f"{API}/releases", headers=as_user("admin")).json()["total"] == 1


def test_release_filters_and_validation(client):
    new_release(client, name="UAT drop", environment="UAT")
    new_release(client, name="Prod drop")
    h = as_user("admin")
    assert client.get(f"{API}/releases", params={"environment": "UAT"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/releases", params={"q": "prod"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/releases", params={"status": "Planned"}, headers=h).json()["total"] == 2
    assert client.post(f"{API}/releases", json={"name": "ab"}, headers=h).status_code == 422
    assert client.post(f"{API}/releases", json={**FULL_RELEASE, "environment": "Dev"}, headers=h).status_code == 422


def test_release_changes_and_lifecycle(client):
    rel = new_release(client)
    chg = new_change(client)
    rid, cid = rel["id"], chg["id"]
    added = client.post(f"{API}/releases/{rid}/changes", json={"change_id": cid}, headers=as_user("devmgr"))
    assert added.status_code == 201 and [c["number"] for c in added.json()["changes"]] == [chg["number"]]
    assert client.post(f"{API}/releases/{rid}/changes", json={"change_id": cid}, headers=as_user("devmgr")
                       ).json()["changes"].__len__() == 1
    in_change = client.get(f"{API}/changes/{cid}", headers=as_user("devmgr")).json()
    assert in_change["releases"][0]["number"] == rel["number"]
    foreign = new_change(client, "supmgr", title="Support change")
    foreign_add = client.post(f"{API}/releases/{rid}/changes", json={"change_id": foreign["id"]},
                              headers=as_user("devmgr"))                              # readable, but not theirs to add
    assert foreign_add.status_code == 403 and foreign_add.json()["error"]["code"] == "forbidden"
    assert client.post(f"{API}/releases/{rid}/changes", json={"change_id": cid}, headers=as_user("supmgr")).status_code == 403

    sent = rmove(client, "devmgr", rid, "Under Review")
    assert sent.status_code == 200 and sent.json()["approvals"][0]["status"] == "pending"
    locked = client.post(f"{API}/releases/{rid}/changes", json={"change_id": cid}, headers=as_user("devmgr"))
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "release_locked"
    assert rmove(client, "devmgr", rid, "Ready to Deploy").status_code == 409
    aid = sent.json()["approvals"][0]["id"]
    assert decide(client, "admin", aid, "rejected", "Not ready").status_code == 200
    assert client.get(f"{API}/releases/{rid}", headers=as_user("devmgr")).json()["status"] == "Planned"
    assert rmove(client, "devmgr", rid, "Under Review").status_code == 200
    aid2 = client.get(f"{API}/releases/{rid}", headers=as_user("admin")).json()["approvals"][0]["id"]
    assert decide(client, "admin", aid2).status_code == 200
    assert client.get(f"{API}/releases/{rid}", headers=as_user("devmgr")).json()["status"] == "Approved"
    for step in ("Ready to Deploy", "Deployment", "Validated", "Closed"):
        r = rmove(client, "devmgr", rid, step)
        assert r.status_code == 200 and r.json()["status"] == step, r.text
    gone = client.delete(f"{API}/releases/{rid}/changes/{cid}", headers=as_user("admin"))
    assert gone.status_code == 409 and gone.json()["error"]["code"] == "release_closed"
    texts = [e["text"] for e in client.get(f"{API}/releases/{rid}/activity", headers=as_user("devmgr")).json()]
    assert "Release created" in texts and "Status changed from Validated to Closed" in texts


def test_release_remove_change_and_edit_rules(client):
    rel, chg = new_release(client), new_change(client)
    rid, cid = rel["id"], chg["id"]
    client.post(f"{API}/releases/{rid}/changes", json={"change_id": cid}, headers=as_user("devmgr"))
    assert client.delete(f"{API}/releases/{rid}/changes/{cid}", headers=as_user("devemp")).status_code == 403
    assert client.delete(f"{API}/releases/{rid}/changes/{cid}", headers=as_user("devmgr")).json()["changes"] == []
    assert client.delete(f"{API}/releases/{rid}/changes/{cid}", headers=as_user("devmgr")).status_code == 404
    ok = client.patch(f"{API}/releases/{rid}", json={"name": "Renamed release", "environment": "UAT"},
                      headers=as_user("devmgr"))
    assert ok.status_code == 200 and ok.json()["environment"] == "UAT"
    assert client.patch(f"{API}/releases/{rid}", json={}, headers=as_user("devmgr")).status_code == 422
    assert client.patch(f"{API}/releases/{rid}", json={"name": "Spy spy"}, headers=as_user("supmgr")).status_code == 403


def test_release_needs_scope_before_review_and_cannot_fake_approval(client):
    rel = new_release(client, scope=None, rollback_plan=None, deployment_at=None)
    r = rmove(client, "devmgr", rel["id"], "Under Review")
    assert r.status_code == 422 and r.json()["error"]["code"] == "incomplete_release"
    assert "scope" in r.json()["error"]["message"] and "deployment date" in r.json()["error"]["message"]
    for status in ("Approved", "Planned"):
        assert rmove(client, "devmgr", rel["id"], status).status_code == 422


# ---- approvals queue sees the new record types ---------------------------------------------

def test_approval_queue_lists_changes_and_releases(client):
    chg, rel = new_change(client), new_release(client)
    for step in ("Submitted", "Under Review", "Approval Pending"):
        cmove(client, "devmgr", chg["id"], step)
    rmove(client, "devmgr", rel["id"], "Under Review")
    queue = client.get(f"{API}/approvals", headers=as_user("admin")).json()
    by_type = {a["record_type"]: a for a in queue}
    assert set(by_type) == {"change", "release"}
    assert by_type["change"]["title"] == chg["title"] and by_type["change"]["risk"] == "High"
    assert by_type["change"]["can_decide"] is True and by_type["release"]["environment"] == "Production"
    mine = client.get(f"{API}/approvals", headers=as_user("devmgr")).json()
    assert len(mine) == 2 and not any(a["can_decide"] for a in mine)
    summary = client.get(f"{API}/dashboard/summary", headers=as_user("admin")).json()
    assert summary["pending_approvals"]["change"] == 1 and summary["pending_approvals"]["release"] == 1
    assert summary["changes"]["approval_pending"] == 1


# ---- reports -------------------------------------------------------------------------------

def test_reports_are_staff_only(client):
    assert client.get(f"{API}/reports", headers=as_user("devemp")).status_code == 403
    assert client.get(f"{API}/reports/open_incidents", headers=as_user("devemp")).status_code == 403
    assert client.get(f"{API}/reports").status_code == 401


def test_every_report_runs_in_json_and_csv_for_every_staff_role(client):
    raise_incident(client, "devemp", impact="High", urgency="High")
    raise_incident(client, "supemp", short_description="Printer jam", impact="Low", urgency="Low")
    new_problem(client, "devmgr")
    new_change(client)
    new_release(client)
    for who in ("admin", "devmgr", "supmgr"):
        listing = client.get(f"{API}/reports", headers=as_user(who)).json()
        assert listing and all(r["available"] for r in listing)
        for rep in listing:
            r = client.get(f"{API}/reports/{rep['key']}", headers=as_user(who))
            assert r.status_code == 200, (who, rep["key"], r.text)
            body = r.json()
            assert body["key"] == rep["key"] and body["columns"] and "generated_at" in body
            keys = {c["key"] for c in body["columns"]}
            assert all(keys <= set(row) for row in body["rows"])
            if body["chart"]:
                assert len(body["chart"]["labels"]) == len(body["chart"]["values"])
            c = client.get(f"{API}/reports/{rep['key']}", params={"format": "csv"}, headers=as_user(who))
            assert c.status_code == 200 and c.headers["content-type"].startswith("text/csv")
            assert f'{rep["key"]}.csv' in c.headers["content-disposition"]
            assert len(c.text.strip().splitlines()) == 1 + len(body["rows"])


def test_report_contents_and_scoping(client):
    raise_incident(client, "devemp", impact="High", urgency="High")           # P1, Development
    raise_incident(client, "supemp", impact="Low", urgency="Low")             # P4, Support
    admin = client.get(f"{API}/reports/incidents_by_priority", headers=as_user("admin")).json()
    assert admin["scope"] == "All teams"
    assert dict(zip(admin["chart"]["labels"], admin["chart"]["values"])) == {"Critical": 1, "Low": 1}
    dev = client.get(f"{API}/reports/incidents_by_priority", headers=as_user("devmgr")).json()
    assert dev["scope"] == "Your team" and dev["chart"]["labels"] == ["Critical"]
    open_inc = client.get(f"{API}/reports/open_incidents", headers=as_user("supmgr")).json()
    assert len(open_inc["rows"]) == 1 and open_inc["rows"][0]["priority"] == "Low"
    assert open_inc["rows"][0]["number"].startswith("INC-")
    csv_text = client.get(f"{API}/reports/open_incidents", params={"format": "csv"}, headers=as_user("admin")).text
    assert csv_text.startswith("﻿Incident,Description,Priority")
    assert client.get(f"{API}/reports/nope", headers=as_user("admin")).status_code == 404
    assert client.get(f"{API}/reports/open_incidents", params={"format": "pdf"}, headers=as_user("admin")).status_code == 422


def test_sla_breach_report_lists_overdue_incident(client, raw):
    inc = raise_incident(client, "devemp", impact="High", urgency="High")
    raw.execute("update incidents set resolution_due = now() - interval '3 hours' where id = %s", (inc["id"],))
    body = client.get(f"{API}/reports/sla_breaches", headers=as_user("admin")).json()
    assert len(body["rows"]) == 1 and float(body["rows"][0]["hours_overdue"]) >= 3


# ---- audit history -------------------------------------------------------------------------

def test_audit_is_admin_only(client):
    for who in ("devmgr", "devemp"):
        assert client.get(f"{API}/audit", headers=as_user(who)).status_code == 403
    assert client.get(f"{API}/audit").status_code == 401


def test_audit_lists_and_filters(client):
    inc = raise_incident(client, "devemp")
    client.post(f"{API}/incidents/{inc['id']}/assign", json={"assignee_id": str(IDS["devmgr"])}, headers=as_user("admin"))
    new_problem(client, "devmgr")
    h = as_user("admin")
    everything = client.get(f"{API}/audit", headers=h).json()
    assert everything["total"] >= 3 and everything["items"][0]["id"] > everything["items"][-1]["id"]
    row = everything["items"][0]
    assert {"at", "actor_name", "summary", "record", "old_status", "new_status", "changed_fields"} <= set(row)

    by_table = client.get(f"{API}/audit", params={"table": "incidents"}, headers=h).json()
    assert {r["table_name"] for r in by_table["items"]} == {"incidents"}
    by_record = client.get(f"{API}/audit", params={"record": inc["number"]}, headers=h).json()
    assert by_record["total"] == 2 and {r["record"] for r in by_record["items"]} == {inc["number"]}
    update = next(r for r in by_record["items"] if r["action"] == "UPDATE")
    assert update["summary"] == "Updated incident" and update["old_status"] == "New" and update["new_status"] == "Assigned"
    assert "status" in update["changed_fields"] and "assignee_id" in update["changed_fields"]
    assert "updated_at" not in update["changed_fields"]
    created = next(r for r in by_record["items"] if r["action"] == "INSERT")
    assert created["summary"] == "Created incident" and created["changed_fields"] is None
    assert client.get(f"{API}/audit", params={"action": "INSERT", "table": "problems"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/audit", params={"actor_id": str(IDS["devmgr"])}, headers=h).json()["total"] >= 1
    assert client.get(f"{API}/audit", params={"since": "2999-01-01T00:00:00Z"}, headers=h).json()["total"] == 0
    assert client.get(f"{API}/audit", params={"until": "2000-01-01T00:00:00Z"}, headers=h).json()["total"] == 0
    page = client.get(f"{API}/audit", params={"limit": 2, "offset": 1}, headers=h).json()
    assert len(page["items"]) == 2 and page["total"] == everything["total"]
    assert client.get(f"{API}/audit", params={"table": "audit_log"}, headers=h).status_code == 422
    users = client.get(f"{API}/audit", params={"table": "profiles"}, headers=h).json()
    assert users["items"] and users["items"][0]["record"].endswith("@test.local")
