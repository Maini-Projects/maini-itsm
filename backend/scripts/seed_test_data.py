"""Creates test users and test records so every screen and role can be tried out.

Run from the backend folder:   .venv\\Scripts\\python.exe scripts\\seed_test_data.py
It talks to the database in backend\\.env and creates real Supabase logins (one shared test password, written to
.test-users.txt). It goes through the API code, so numbers, SLA times and workflow rules come out exactly as in real use.
Re-running adds users/records again only if the emails are new, so run it once.
"""
import os
import random
import re
import secrets
import sys
from collections import Counter
from uuid import UUID

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import psycopg  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthAdmin, verified_user_id  # noqa: E402
from app.main import app  # noqa: E402

random.seed(7)
URL = re.search(r"^DATABASE_URL=(.*)$", open(".env").read(), re.M).group(1).strip().strip("\"'")
PASSWORD = "Test@" + secrets.token_urlsafe(6) + "9z"
API = "/api/v1"
CVS, APPLE = "CVS Health Care Systems", "Apple INC"

# ---- the 25 users --------------------------------------------------------------------------
USERS = []  # (key, full name, email, role, team, projects, status)
USERS += [("admin01", "Test Admin 01", "test.admin01@itsm.com", "admin", None, [], "active"),
          ("admin02", "Test Admin 02", "test.admin02@itsm.com", "admin", None, [], "active")]
USERS += [("eng01", "Test Engineer 01", "test.engineer01@itsm.com", "manager", "Development", [CVS, APPLE], "active"),
          ("eng02", "Test Engineer 02", "test.engineer02@itsm.com", "manager", "Support", [CVS], "active")]
for n in range(1, 22):
    projects = [CVS] if n <= 8 else [APPLE] if n <= 16 else [CVS, APPLE] if n <= 20 else []
    USERS.append((f"cust{n:02d}", f"Test Customer {n:02d}", f"test.customer{n:02d}@itsm.com", "employee",
                  "Development" if n % 2 else "Support", projects, "disabled" if n == 19 else "active"))

# ---- connect -------------------------------------------------------------------------------
conn = psycopg.connect(URL, prepare_threshold=None, autocommit=True)
team_id = {n: i for i, n in conn.execute("select id, name from teams").fetchall()}
project_id = {n: i for i, n in conn.execute("select id, name from projects").fetchall()}
ids: dict[str, UUID] = {}
auth = AuthAdmin()
made = 0
for key, name, email, role, team, projects, status in USERS:
    row = conn.execute("select id from profiles where email = %s", (email,)).fetchone()
    if row:
        ids[key] = row[0]
        continue
    uid = auth.create_user(email, PASSWORD)
    conn.execute("insert into profiles(id, email, full_name, role, team_id, status) values (%s,%s,%s,%s,%s,%s)",
                 (uid, email, name, role, team_id.get(team), status))
    for p in projects:
        conn.execute("insert into user_projects values (%s, %s)", (uid, project_id[p]))
    ids[key] = uid
    made += 1
print(f"users created: {made}")

# ---- call the API as any of them -----------------------------------------------------------
def act_as(request: Request) -> UUID:
    return UUID(request.headers["x-seed-user"])


app.dependency_overrides[verified_user_id] = act_as
client = TestClient(app)
client.__enter__()
errors: Counter = Counter()
counts: Counter = Counter()


def call(method, path, who, project=None, **kw):
    headers = {"X-Seed-User": str(ids[who])}
    if project:
        headers["X-Project-Id"] = str(project_id[project])
    r = client.request(method, API + path, headers=headers, **kw)
    if r.status_code >= 300:
        errors[f"{method} {path.split('/')[1] if '/' in path else path} -> {r.status_code} {r.json().get('error', {}).get('code')}"] += 1
        return None
    return r.json()


def mk(kind, path, who, project, body):
    rec = call("POST", path, who, project, json=body)
    if rec:
        counts[kind] += 1
    return rec


services = [r[0] for r in conn.execute("select id from services where active order by name").fetchall()]
svc = lambda: str(random.choice(services)) if services else None  # noqa: E731
customers = [u for u in USERS if u[3] == "employee" and u[6] == "active" and u[5]]

ISSUES = ["Cannot log in to the portal", "Report export is blank", "Payment posting is slow", "Invoice PDF missing totals",
          "VPN drops every hour", "Email notifications delayed", "Dashboard shows wrong totals", "Upload fails on large files",
          "Password reset email not arriving", "Page times out when saving", "Wrong tax shown at checkout",
          "Search returns no results", "User cannot access shared folder", "Batch job did not run overnight",
          "Mobile app crashes on start", "Duplicate records after import", "Approval button does nothing",
          "Scheduled report sent twice", "Slow response in the evening", "Incorrect currency symbol on invoices"]
PRIORITIES = ["P1", "P2", "P3", "P3", "P3", "P4", "P2", "P4"]

# ---- incidents: every status, priority and project ----------------------------------------
incidents = []
steps = ["New", "Assigned", "In Progress", "Pending", "Resolved", "Closed", "Reopened", "New"]
for i in range(36):
    who = customers[i % len(customers)]
    key, proj = who[0], random.choice(who[5])
    inc = mk("incidents", "/incidents", key, proj,
             {"short_description": f"{ISSUES[i % len(ISSUES)]} ({proj.split()[0]})", "description": "Test incident created by the seed script.",
              "priority": PRIORITIES[i % len(PRIORITIES)], "service_id": svc()})
    if not inc:
        continue
    incidents.append((inc, key, proj))
    step = steps[i % len(steps)]
    staff = "admin01" if i % 3 else "eng01" if who[4] == "Development" else "eng02"
    if step == "New":
        continue
    call("POST", f"/incidents/{inc['id']}/assign", "admin01", proj, json={"assignee_id": str(ids["admin01" if staff == "admin01" else staff])})
    if step in ("In Progress", "Pending", "Resolved", "Closed", "Reopened"):
        call("POST", f"/incidents/{inc['id']}/transition", "admin01", proj, json={"to_status": "In Progress"})
    if step == "Pending":
        call("POST", f"/incidents/{inc['id']}/transition", "admin01", proj, json={"to_status": "Pending"})
    if step in ("Resolved", "Closed", "Reopened"):
        call("POST", f"/incidents/{inc['id']}/transition", "admin01", proj, json={"to_status": "Resolved", "resolution_notes": "Fixed by restarting the service and clearing the cache."})
    if step == "Closed":
        call("POST", f"/incidents/{inc['id']}/transition", key, proj, json={"to_status": "Closed"})
    if step == "Reopened":
        call("POST", f"/incidents/{inc['id']}/transition", key, proj, json={"to_status": "In Progress"})
    if i % 4 == 0:
        call("POST", f"/incidents/{inc['id']}/comments", key, proj, json={"body": "Any update on this? It is blocking our team."})
        call("POST", f"/incidents/{inc['id']}/comments", "admin01", proj, json={"body": "Looking into it now.", "internal": False})
        call("POST", f"/incidents/{inc['id']}/comments", "admin01", proj, json={"body": "Internal: check the last deployment first.", "internal": True})

# a few incidents already past their SLA, so the SLA reports and dashboard have something to show
try:
    conn.execute("""update incidents set resolution_due = now() - interval '5 hours'
                     where id in (select id from incidents where status in ('New','Assigned','In Progress')
                                  and number like 'INC-%' order by created_at desc limit 4)""")
    print("SLA breaches set on 4 open incidents")
except Exception as e:  # noqa: BLE001
    print("could not backdate SLA:", str(e)[:80])

# ---- defects -------------------------------------------------------------------------------
SEV = ["Critical", "High", "Medium", "Low"]
for i in range(14):
    who = customers[(i * 3) % len(customers)]
    key, proj = who[0], random.choice(who[5])
    d = mk("defects", "/defects", key, proj,
           {"title": f"Defect: {ISSUES[(i + 5) % len(ISSUES)]}", "description": "Seeded test defect.",
            "steps_to_reproduce": "1. Sign in  2. Open the screen  3. Click Save",
            "expected_result": "Record is saved", "actual_result": "An error appears",
            "severity": SEV[i % 4], "environment": "Production" if i % 3 else "UAT", "service_id": svc()})
    if not d or i % 3 == 0:
        continue
    call("POST", f"/defects/{d['id']}/assign", "admin01", proj, json={"assignee_id": str(ids["admin01"])})
    if i % 3 >= 1:
        call("POST", f"/defects/{d['id']}/transition", "admin01", proj, json={"to_status": "In Progress"})
    if i % 6 in (2, 5):
        call("POST", f"/defects/{d['id']}/transition", "admin01", proj, json={"to_status": "Resolved", "resolution_notes": "Patched in the next build."})
    if i % 6 == 5:
        call("POST", f"/defects/{d['id']}/transition", "admin01", proj, json={"to_status": "Closed"})

# ---- problems (linked to incidents) --------------------------------------------------------
for i in range(8):
    proj = CVS if i % 2 == 0 else APPLE
    who = "eng01"
    p = mk("problems", "/problems", who, proj, {"title": f"Recurring issue: {ISSUES[(i + 9) % len(ISSUES)]}",
                                               "description": "Several incidents point to the same cause.",
                                               "priority": PRIORITIES[i % 4], "service_id": svc()})
    if not p:
        continue
    for inc, _k, iproj in incidents:
        if iproj == proj and counts[f"link{p['id']}"] < 2:
            if call("POST", f"/problems/{p['id']}/incidents", "admin01", proj, json={"incident_id": inc["id"]}):
                counts[f"link{p['id']}"] += 1
    if i % 4 >= 1:
        call("POST", f"/problems/{p['id']}/assign", "admin01", proj, json={"owner_id": str(ids["eng01"])})
        call("POST", f"/problems/{p['id']}/transition", "admin01", proj, json={"to_status": "Investigating"})
    if i % 4 >= 2:
        call("PATCH", f"/problems/{p['id']}", "admin01", proj, json={"root_cause": "Memory leak in the nightly job.", "workaround": "Restart the job."})
        call("POST", f"/problems/{p['id']}/transition", "admin01", proj, json={"to_status": "Root Cause Identified"})
    if i % 4 == 3:
        call("POST", f"/problems/{p['id']}/transition", "admin01", proj, json={"to_status": "Fix Planned"})

# ---- changes (with approvals) and releases -------------------------------------------------
import datetime as dt  # noqa: E402

now = dt.datetime.now(dt.timezone.utc)
change_ids = []
for i in range(9):
    proj = CVS if i % 2 == 0 else APPLE
    who = "eng01" if i % 3 else "admin01"
    c = mk("changes", "/changes", who, proj,
           {"title": f"Change: upgrade {['database', 'app server', 'VPN gateway', 'mail relay', 'reporting tool'][i % 5]}",
            "type": ["Standard", "Normal", "Emergency"][i % 3], "risk": ["Low", "Medium", "High"][i % 3],
            "implementation_plan": "Apply the update during the maintenance window.", "test_plan": "Run the smoke tests.",
            "backout_plan": "Restore the previous version.", "service_id": svc(),
            "planned_start": (now + dt.timedelta(days=2 + i)).isoformat(), "planned_end": (now + dt.timedelta(days=2 + i, hours=3)).isoformat()})
    if not c:
        continue
    change_ids.append((c["id"], proj))
    if i % 3 >= 1:  # Draft -> Submitted -> Under Review -> Approval Pending
        call("POST", f"/changes/{c['id']}/transition", "admin01", proj, json={"to_status": "Submitted"})
        call("POST", f"/changes/{c['id']}/transition", "admin01", proj, json={"to_status": "Under Review"})
    if i % 3 == 2:
        call("POST", f"/changes/{c['id']}/transition", "admin01", proj, json={"to_status": "Approval Pending"})

for i in range(6):
    proj = CVS if i % 2 == 0 else APPLE
    r = mk("releases", "/releases", "eng01" if i % 2 else "admin01", proj,
           {"name": f"Release 2026.{i + 1}", "environment": "Production" if i % 2 else "UAT",
            "scope": "Bug fixes and small improvements.", "rollback_plan": "Redeploy the previous package.", "service_id": svc(),
            "deployment_at": (now + dt.timedelta(days=3 + i * 2)).isoformat()})
    if not r:
        continue
    for cid, cproj in change_ids:
        if cproj == proj and counts[f"rl{r['id']}"] < 1:
            if call("POST", f"/releases/{r['id']}/changes", "admin01", proj, json={"change_id": cid}):
                counts[f"rl{r['id']}"] += 1
    if i % 3 >= 1:  # Planned -> Under Review (waits for an approval)
        call("POST", f"/releases/{r['id']}/transition", "admin01", proj, json={"to_status": "Under Review"})

# ---- decide some approvals: approve a few, reject one, leave the rest pending ---------------
pend = call("GET", "/approvals?status=pending", "admin01") or []
for k, a in enumerate(pend):
    if k % 3 == 0:
        call("POST", f"/approvals/{a['id']}/decision", "admin01", json={"decision": "approved", "comment": "Looks good."})
    elif k % 3 == 1:
        call("POST", f"/approvals/{a['id']}/decision", "admin01", json={"decision": "rejected", "comment": "Please add a back-out plan."})

client.__exit__(None, None, None)

with open(".test-users.txt", "w") as f:
    f.write(f"Shared password for all test users: {PASSWORD}\n\n")
    for key, name, email, role, team, projects, status in USERS:
        f.write(f"{name:18} {email:34} {role:9} team={team or '-':12} projects={', '.join(projects) or 'none'} {status if status != 'active' else ''}\n")

print("records:", {k: v for k, v in counts.items() if not k.startswith(("link", "rl"))})
print("steps the rules refused:", dict(errors) or "none")
