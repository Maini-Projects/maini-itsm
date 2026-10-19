"""API tests: every role, team scoping, the incident workflow, approvals (changes/releases), users, reference data, dashboard."""
from conftest import IDS, as_user

API = "/api/v1"


# ---- helpers -------------------------------------------------------------------------------

def raise_incident(client, who="devemp", **over):
    body = {"short_description": "Posting is slow", "impact": "High", "urgency": "High", **over}
    r = client.post(f"{API}/incidents", json=body, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def move(client, who, inc_id, to, **extra):
    return client.post(f"{API}/incidents/{inc_id}/transition", json={"to_status": to, **extra}, headers=as_user(who))


def assign(client, who, inc_id, assignee):
    return client.post(f"{API}/incidents/{inc_id}/assign", json={"assignee_id": str(IDS[assignee])},
                       headers=as_user(who))


def work_to_resolved(client, worker, inc_id):
    """Assign to the worker, start, resolve."""
    assert assign(client, "admin", inc_id, worker).status_code == 200
    assert move(client, worker, inc_id, "In Progress").status_code == 200
    r = move(client, worker, inc_id, "Resolved", resolution_notes="Fixed it.")
    assert r.status_code == 200, r.text
    return r.json()


# ---- login and "who am I" ------------------------------------------------------------------

def test_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "up"}


def test_login_required_and_error_format(client):
    r = client.get(f"{API}/me")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "missing_token", "message": "Sign in to use this service."}}
    r = client.get(f"{API}/me", headers={"Authorization": "Bearer t-nobody"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_me_describes_each_role(client):
    admin = client.get(f"{API}/me", headers=as_user("admin")).json()
    assert admin["role"] == "admin" and admin["team_id"] is None and "admin" in admin["menu"]
    mgr = client.get(f"{API}/me", headers=as_user("devmgr")).json()
    assert mgr["role"] == "manager" and mgr["team_name"] == "Development"
    assert "approvals" in mgr["menu"] and "admin" not in mgr["menu"]
    emp = client.get(f"{API}/me", headers=as_user("supemp")).json()
    assert emp["team_name"] == "Support" and emp["menu"] == ["dashboard", "incidents", "problems", "defects", "changes", "releases"]
    assert emp["organization_name"] == "CVS Health Care Systems"


def test_disabled_account_is_blocked(client, raw):
    raw.execute("update profiles set status = 'disabled' where id = %s", (IDS["devemp"],))
    r = client.get(f"{API}/me", headers=as_user("devemp"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_not_active"


# ---- raising incidents ---------------------------------------------------------------------

def test_new_incident_gets_priority_team_number_and_sla(client):
    inc = raise_incident(client)
    assert inc["number"].startswith("INC-") and inc["status"] == "New" and inc["priority"] == "P1"
    assert inc["team_name"] == "Development" and inc["requester_name"] == "Devemp"
    assert inc["response_due"] and inc["resolution_due"] and inc["minutes_to_resolution_due"] in (239, 240)
    assert inc["sla_breached"] is False
    low = raise_incident(client, impact="Low", urgency="Low")
    assert low["priority"] == "P4"


def test_validation_errors_use_the_standard_format(client):
    r = client.post(f"{API}/incidents", json={"short_description": "x"}, headers=as_user("devemp"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["fields"][0]["field"] == "short_description"


def test_only_admin_can_raise_for_someone_else(client):
    r = client.post(f"{API}/incidents", headers=as_user("devemp"),
                    json={"short_description": "For a colleague", "requester_id": str(IDS["devemp2"])})
    assert r.status_code == 403
    r = client.post(f"{API}/incidents", headers=as_user("admin"),
                    json={"short_description": "For a colleague", "requester_id": str(IDS["supemp"])})
    assert r.status_code == 201 and r.json()["requester_name"] == "Supemp" and r.json()["team_name"] == "Support"


# ---- who can see what ----------------------------------------------------------------------

def test_visibility_by_role_and_team(client):
    inc = raise_incident(client, "devemp")
    path = f"{API}/incidents/{inc['id']}"
    for who, sees in [("devemp", True), ("devmgr", True), ("admin", True),
                      ("devemp2", False), ("supmgr", False), ("supemp", False)]:
        r = client.get(path, headers=as_user(who))
        assert (r.status_code == 200) == sees, who
        listed = client.get(f"{API}/incidents", headers=as_user(who)).json()
        assert (listed["total"] == 1) == sees, who
        if not sees:
            assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_list_filters_and_paging(client):
    raise_incident(client, short_description="VPN down", impact="Low", urgency="Low")
    raise_incident(client, short_description="Finance posting delay")
    raise_incident(client, "supemp", short_description="Printer jam", impact="Medium", urgency="Medium")
    h = as_user("admin")
    assert client.get(f"{API}/incidents", headers=h).json()["total"] == 3
    assert client.get(f"{API}/incidents?priority=P1", headers=h).json()["total"] == 1
    assert client.get(f"{API}/incidents?q=vpn", headers=h).json()["items"][0]["short_description"] == "VPN down"
    assert client.get(f"{API}/incidents?mine=true", headers=h).json()["total"] == 0
    assert client.get(f"{API}/incidents?limit=1", headers=h).json()["items"].__len__() == 1
    assert client.get(f"{API}/incidents", headers=as_user("supmgr")).json()["total"] == 1


# ---- editing -------------------------------------------------------------------------------

def test_requester_edits_own_incident_only_while_new_and_only_basic_fields(client):
    inc = raise_incident(client)
    p = f"{API}/incidents/{inc['id']}"
    assert client.patch(p, json={"description": "More detail"}, headers=as_user("devemp")).status_code == 200
    assert client.patch(p, json={"impact": "Low"}, headers=as_user("devemp")).status_code == 403
    assert client.patch(p, json={"description": "x"}, headers=as_user("devemp2")).status_code == 404
    assign(client, "admin", inc["id"], "devmgr")
    assert client.patch(p, json={"description": "Too late"}, headers=as_user("devemp")).status_code == 403


def test_manager_edit_recalculates_priority_and_sla(client):
    inc = raise_incident(client)
    r = client.patch(f"{API}/incidents/{inc['id']}", json={"impact": "Low", "urgency": "Low"}, headers=as_user("devmgr"))
    assert r.status_code == 200 and r.json()["priority"] == "P4" and r.json()["minutes_to_resolution_due"] > 7000
    assert client.patch(f"{API}/incidents/{inc['id']}", json={}, headers=as_user("devmgr")).status_code == 422


# ---- assigning -----------------------------------------------------------------------------

def test_assignment_rules(client):
    inc = raise_incident(client)
    assert assign(client, "devemp", inc["id"], "devmgr").status_code == 403          # employees cannot assign
    assert assign(client, "supmgr", inc["id"], "supmgr").status_code == 404          # other team cannot even see it
    r = assign(client, "devmgr", inc["id"], "devemp2")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_assignee"  # employees cannot be assigned
    r = assign(client, "devmgr", inc["id"], "supmgr")
    assert r.status_code == 422                                                      # not another team's manager
    r = assign(client, "devmgr", inc["id"], "devmgr")
    assert r.status_code == 200 and r.json()["status"] == "Assigned" and r.json()["assignee_name"] == "Devmgr"
    assert assign(client, "devmgr", inc["id"], "admin").status_code == 200           # managers may hand to an admin


# ---- choosing a priority directly (Critical / High / Medium / Low) -------------------------

def test_incident_priority_is_chosen_directly(client):
    expected = {"P1": ("High", "High"), "P2": ("High", "Medium"), "P3": ("Medium", "Medium"), "P4": ("Low", "Low")}
    for code, (impact, urgency) in expected.items():
        r = client.post(f"{API}/incidents", json={"short_description": f"Priority {code}", "priority": code},
                        headers=as_user("devemp"))
        assert r.status_code == 201, r.text
        assert r.json()["priority"] == code and (r.json()["impact"], r.json()["urgency"]) == (impact, urgency)
    default = client.post(f"{API}/incidents", json={"short_description": "No priority given"}, headers=as_user("devemp"))
    assert default.json()["priority"] == "P3"                                           # Medium by default
    legacy = client.post(f"{API}/incidents", json={"short_description": "Old style", "impact": "High", "urgency": "High"},
                         headers=as_user("devemp"))
    assert legacy.json()["priority"] == "P1"                                            # impact/urgency still accepted
    bad = client.post(f"{API}/incidents", json={"short_description": "Bad priority", "priority": "Urgent"},
                      headers=as_user("devemp"))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"


def test_changing_the_priority_updates_the_sla_clocks_and_is_staff_only(client):
    inc = raise_incident(client, priority="P4")
    assert inc["priority"] == "P4"
    h = as_user("devmgr")
    r = client.patch(f"{API}/incidents/{inc['id']}", json={"priority": "P1"}, headers=h)
    assert r.status_code == 200 and r.json()["priority"] == "P1"
    assert r.json()["resolution_due"] != inc["resolution_due"]                          # clocks recomputed
    assert client.patch(f"{API}/incidents/{inc['id']}", json={"priority": "P2"}, headers=as_user("devemp")).status_code == 403
    assert client.patch(f"{API}/incidents/{inc['id']}", json={"priority": None}, headers=h).status_code == 200
    assert client.get(f"{API}/incidents/{inc['id']}", headers=h).json()["priority"] == "P1"   # null changes nothing
    assert client.patch(f"{API}/incidents/{inc['id']}", json={"priority": "P9"}, headers=h).status_code == 422
    low = client.get(f"{API}/incidents", params={"priority": "P1"}, headers=h).json()
    assert low["total"] == 1


# ---- closing incidents: no approval at any priority -----------------------------------------

def test_p3_flow_requester_confirms_and_no_approval_is_created(client):
    inc = raise_incident(client, impact="Medium", urgency="Medium")
    assert inc["priority"] == "P3"
    work_to_resolved(client, "devmgr", inc["id"])
    assert move(client, "devemp2", inc["id"], "Closed").status_code == 404            # not their incident
    r = move(client, "devemp", inc["id"], "Closed")
    assert r.status_code == 200 and r.json()["status"] == "Closed" and r.json()["closed_at"]
    assert client.get(f"{API}/approvals?status=all", headers=as_user("admin")).json() == []


def test_requester_can_reopen_a_resolved_incident_but_not_move_it_otherwise(client):
    inc = raise_incident(client, impact="Medium", urgency="Medium")
    assert move(client, "devemp", inc["id"], "In Progress").status_code == 403
    work_to_resolved(client, "devmgr", inc["id"])
    r = move(client, "devemp", inc["id"], "In Progress")
    assert r.status_code == 200 and r.json()["status"] == "In Progress" and r.json()["resolved_at"] is None
    assert move(client, "devemp", inc["id"], "Resolved", resolution_notes="me").status_code == 403


def test_workflow_rules_are_enforced_with_clear_errors(client):
    inc = raise_incident(client, impact="Medium", urgency="Medium")
    r = move(client, "devmgr", inc["id"], "Closed")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    r = move(client, "devmgr", inc["id"], "Assigned")
    assert r.status_code == 422 and r.json()["error"]["code"] == "assignee_required"
    assign(client, "devmgr", inc["id"], "devmgr")
    move(client, "devmgr", inc["id"], "In Progress")
    r = move(client, "devmgr", inc["id"], "Resolved")
    assert r.status_code == 422 and r.json()["error"]["code"] == "resolution_notes_required"
    move(client, "devmgr", inc["id"], "Resolved", resolution_notes="Done")
    r = move(client, "devmgr", inc["id"], "Pending Approval")                       # no such status any more
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert move(client, "supmgr", inc["id"], "Closed").status_code == 404


def test_closed_incident_cannot_be_edited_or_reassigned(client):
    inc = raise_incident(client, impact="Low", urgency="Low")
    work_to_resolved(client, "devmgr", inc["id"])
    move(client, "devemp", inc["id"], "Closed")
    r = client.patch(f"{API}/incidents/{inc['id']}", json={"description": "x"}, headers=as_user("admin"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "incident_closed"
    assert assign(client, "admin", inc["id"], "admin").status_code == 409


# ---- P1/P2 incidents close directly too ----------------------------------------------------

def test_p1_closes_directly_by_the_manager_with_no_approval(client):
    inc = raise_incident(client)
    assert inc["priority"] == "P1"
    work_to_resolved(client, "devmgr", inc["id"])
    r = move(client, "devmgr", inc["id"], "Closed")
    assert r.status_code == 200 and r.json()["status"] == "Closed" and r.json()["closed_at"]
    assert client.get(f"{API}/approvals?status=all", headers=as_user("admin")).json() == []
    assert client.get(f"{API}/approvals?status=all", headers=as_user("devmgr")).json() == []


def test_p2_requester_confirms_and_admin_can_close(client):
    inc = raise_incident(client, impact="High", urgency="Medium")                      # P2
    assert inc["priority"] == "P2"
    work_to_resolved(client, "devmgr", inc["id"])
    assert move(client, "devemp2", inc["id"], "Closed").status_code == 404            # not their incident
    r = move(client, "devemp", inc["id"], "Closed")
    assert r.status_code == 200 and r.json()["status"] == "Closed"
    other = raise_incident(client, impact="High", urgency="Medium")
    work_to_resolved(client, "admin", other["id"])
    assert move(client, "admin", other["id"], "Closed").status_code == 200


def test_resolved_p1_can_be_reopened(client):
    inc = raise_incident(client)
    work_to_resolved(client, "devmgr", inc["id"])
    r = move(client, "devemp", inc["id"], "In Progress")
    assert r.status_code == 200 and r.json()["status"] == "In Progress" and r.json()["resolved_at"] is None


def test_pending_approval_is_not_an_incident_status_any_more(client):
    inc = raise_incident(client)
    work_to_resolved(client, "devmgr", inc["id"])
    r = move(client, "admin", inc["id"], "Pending Approval")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


# ---- comments and activity -----------------------------------------------------------------

def test_comments_internal_notes_and_activity(client):
    inc = raise_incident(client)
    cid = inc["id"]
    base = f"{API}/incidents/{cid}/comments"
    assert client.post(base, json={"body": "Any update?"}, headers=as_user("devemp")).status_code == 201
    r = client.post(base, json={"body": "secret", "internal": True}, headers=as_user("devemp"))
    assert r.status_code == 403
    assert client.post(base, json={"body": "Checking logs", "internal": True}, headers=as_user("devmgr")).status_code == 201
    assert client.post(base, json={"body": "nope"}, headers=as_user("supemp")).status_code == 404
    assert len(client.get(base, headers=as_user("devmgr")).json()) == 2
    assert [c["body"] for c in client.get(base, headers=as_user("devemp")).json()] == ["Any update?"]

    assign(client, "devmgr", cid, "devmgr")
    events = client.get(f"{API}/incidents/{cid}/activity", headers=as_user("devmgr")).json()
    texts = [e["text"] for e in events]
    assert "Incident created" in texts and "Status changed from New to Assigned" in texts
    assert "Assigned to Devmgr" in texts and "Checking logs" in texts
    emp_texts = [e["text"] for e in client.get(f"{API}/incidents/{cid}/activity", headers=as_user("devemp")).json()]
    assert "Checking logs" not in emp_texts and "Any update?" in emp_texts


# ---- users (admin) -------------------------------------------------------------------------

def test_only_admin_manages_users(client):
    assert client.get(f"{API}/users", headers=as_user("devmgr")).status_code == 403
    assert client.get(f"{API}/users", headers=as_user("devemp")).status_code == 403
    users = client.get(f"{API}/users", headers=as_user("admin")).json()
    assert len(users) == 6 and {u["role"] for u in users} == {"admin", "manager", "employee"}
    assert len(client.get(f"{API}/users?role=manager", headers=as_user("admin")).json()) == 2


def test_admin_creates_users_and_bad_requests_leave_no_orphan_login(client, app):
    teams = {t["name"]: t["id"] for t in client.get(f"{API}/teams", headers=as_user("admin")).json()}
    assert set(teams) == {"Development", "Support"}
    h = as_user("admin")
    ok = client.post(f"{API}/users", headers=h, json={"email": "new.hire@company.com", "full_name": "New Hire",
                                                      "password": "a-long-password", "role": "employee",
                                                      "team_id": teams["Support"]})
    assert ok.status_code == 201 and ok.json()["team_name"] == "Support" and "password" not in ok.json()
    fake = app.state.fake_auth_admin
    assert len(fake.created) == 1 and fake.deleted == []

    r = client.post(f"{API}/users", headers=h, json={"email": "no.team@company.com", "full_name": "No Team",
                                                     "password": "a-long-password", "role": "employee"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "team_required"
    assert len(fake.created) == 1                                                      # rejected before any login was made

    r = client.post(f"{API}/users", headers=h, json={"email": "second.manager@company.com", "full_name": "Second Manager",
                                                     "password": "a-long-password", "role": "manager",
                                                     "team_id": teams["Development"]})
    assert r.status_code == 409                                                        # one manager per team
    assert len(fake.created) == 2 and len(fake.deleted) == 1                           # the login was cleaned up
    r = client.post(f"{API}/users", headers=h, json={"email": "not-an-email", "full_name": "X",
                                                     "password": "a-long-password", "role": "admin"})
    assert r.status_code == 422


def test_admin_updates_users_but_cannot_lock_themselves_out(client):
    h = as_user("admin")
    r = client.patch(f"{API}/users/{IDS['devemp']}", json={"status": "disabled"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    assert client.get(f"{API}/me", headers=as_user("devemp")).status_code == 403
    assert client.patch(f"{API}/users/{IDS['admin']}", json={"role": "employee"}, headers=h).json()["error"]["code"] \
        == "cannot_modify_self"
    assert client.patch(f"{API}/users/{IDS['admin']}", json={"status": "disabled"}, headers=h).status_code == 409
    assert client.patch(f"{API}/users/{IDS['devmgr']}", json={}, headers=h).status_code == 422
    assert client.patch(f"{API}/users/{'0' * 8}-0000-0000-0000-{'9' * 12}", json={"full_name": "Ghost"},
                        headers=h).status_code == 404


def test_assignable_list_is_limited_for_managers(client):
    names = lambda who: {u["full_name"] for u in client.get(f"{API}/users/assignable", headers=as_user(who)).json()}
    assert names("devmgr") == {"Devmgr", "Admin"}
    assert names("admin") == {"Admin", "Devmgr", "Supmgr"}
    assert client.get(f"{API}/users/assignable", headers=as_user("devemp")).status_code == 403


# ---- services and SLA ----------------------------------------------------------------------

def test_services_visible_to_all_editable_by_admin(client):
    assert len(client.get(f"{API}/services", headers=as_user("devemp")).json()) == 5
    body = {"name": "Data & Reporting", "criticality": "Medium"}
    assert client.post(f"{API}/services", json=body, headers=as_user("devmgr")).status_code == 403
    created = client.post(f"{API}/services", json=body, headers=as_user("admin"))
    assert created.status_code == 201
    sid = created.json()["id"]
    assert client.post(f"{API}/services", json=body, headers=as_user("admin")).status_code == 409   # duplicate name
    r = client.patch(f"{API}/services/{sid}", json={"active": False}, headers=as_user("admin"))
    assert r.status_code == 200 and r.json()["active"] is False
    assert client.patch(f"{API}/services/{sid}", json={"active": False}, headers=as_user("devmgr")).status_code == 403
    inc = raise_incident(client, service_id=sid)
    assert inc["service_name"] == "Data & Reporting"


def test_sla_targets_are_editable_and_apply_to_new_incidents(client):
    assert [s["priority"] for s in client.get(f"{API}/sla", headers=as_user("devemp")).json()] == ["P1", "P2", "P3", "P4"]
    body = {"response_minutes": 30, "resolution_minutes": 120}
    assert client.put(f"{API}/sla/P1", json=body, headers=as_user("devmgr")).status_code == 403
    assert client.put(f"{API}/sla/P1", json={"response_minutes": 60, "resolution_minutes": 30},
                      headers=as_user("admin")).status_code == 422
    assert client.put(f"{API}/sla/P1", json=body, headers=as_user("admin")).json()["resolution_minutes"] == 120
    inc = raise_incident(client)
    assert inc["minutes_to_resolution_due"] in (119, 120)


# ---- dashboard -----------------------------------------------------------------------------

def test_dashboard_counts_and_scoping(client):
    p1 = raise_incident(client)                                                         # P1
    raise_incident(client, impact="High", urgency="Medium")                             # P2
    raise_incident(client, impact="Medium", urgency="Medium")                           # P3
    raise_incident(client, "supemp", impact="Low", urgency="Low")                       # P4, other team
    admin = client.get(f"{API}/dashboard/summary", headers=as_user("admin")).json()
    assert admin["incidents"]["open"] == 4 and admin["incidents"]["p1_p2_open"] == 2
    assert admin["incidents"]["p1_open"] == 1 and admin["incidents"]["p2_open"] == 1
    workload = {t["name"]: t["open"] for t in admin["team_workload"]}
    assert workload == {"Development": 3, "Support": 1}
    assert admin["pending_approvals"]["total"] == 0 and admin["changes"]["active"] == 0

    mgr = client.get(f"{API}/dashboard/summary", headers=as_user("devmgr")).json()
    assert mgr["incidents"]["open"] == 3 and {t["name"]: t["open"] for t in mgr["team_workload"]}["Support"] == 0

    emp = client.get(f"{API}/dashboard/summary", headers=as_user("devemp2")).json()
    assert emp["incidents"]["open"] == 0 and emp["team_workload"] == [] and emp["problems"] is None
    emp1 = client.get(f"{API}/dashboard/summary", headers=as_user("devemp")).json()
    assert emp1["incidents"]["open"] == 3 and emp1["pending_approvals"] is None

    work_to_resolved(client, "devmgr", p1["id"])
    assert move(client, "devmgr", p1["id"], "Closed").status_code == 200
    after = client.get(f"{API}/dashboard/summary", headers=as_user("admin")).json()
    assert after["incidents"]["open"] == 3 and "awaiting_approval" not in after["incidents"]
    assert after["pending_approvals"] == {"total": 0, "change": 0, "release": 0}
    perf = {p["priority"]: p for p in after["sla_performance"]}
    assert perf["P1"]["resolved_this_month"] == 1 and perf["P1"]["percent"] == 100 and perf["P2"]["percent"] is None
    assert client.get(f"{API}/dashboard/summary", headers=as_user("devmgr")).json()["pending_approvals"]["total"] == 0


def test_sla_at_risk_and_breached_counts(client, raw):
    inc = raise_incident(client)
    raw.execute("update incidents set resolution_due = now() - interval '5 minutes' where id = %s", (inc["id"],))
    one = client.get(f"{API}/incidents/{inc['id']}", headers=as_user("admin")).json()
    assert one["sla_breached"] is True and one["minutes_to_resolution_due"] < 0
    s = client.get(f"{API}/dashboard/summary", headers=as_user("admin")).json()["incidents"]
    assert s["sla_breached"] == 1 and s["sla_at_risk"] == 1


# ---- the browser must be able to call us ---------------------------------------------------

def test_cors_allows_only_the_configured_front_end(client):
    ok = client.options(f"{API}/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options(f"{API}/me", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
