# Maini ITSM

IT service management portal: incidents, problems, defects, changes, releases, approvals, SLAs, audit.
React front end -> FastAPI back end -> Supabase (Postgres + Auth), hosted on Render.

The front end only ever talks to the back end's REST API, so it can be replaced by any other
technology without touching the back end or the database.

```
supabase/migrations/   the database: run in order (001, 002, ...) in the Supabase SQL editor
supabase/schema_checks.sql   64 rule checks for the database (see "Tests")
backend/               FastAPI service (deployed on Render)
  app/main.py            app entry point, /healthz
  app/routers/           auth, reference (me, teams, services, SLA), users, incidents, problems, defects,
                         changes, releases, approvals, dashboard, reports, audit
  app/rbac.py            who may see what; app/auth.py login; app/errors.py error format
  tests/                 107 automated tests
frontend/              React + Vite web app (talks only to the back end's REST API)
render.yaml            Render Blueprint for the back end
```

## Roles and teams

| | Customer | Support Engineer | Administrator |
|---|---|---|---|
| Sees incidents | only their own | their team's, plus any they raised or are assigned | all |
| Raises incidents / problems / defects | yes | yes | yes (incidents also on someone's behalf) |
| Works incidents (assign, edit, move on) | confirms or reopens own resolved incident | their team's | all |
| Sees changes and releases | all, read-only | all (edits only their team's) | all |
| Raises changes and releases | no | yes | yes |
| Approves changes and releases | no | no | yes |
| Users, services, SLA targets | no | no | yes |

The roles are shown as Customer, Support Engineer and Administrator. In the database and the API they are still stored as
`employee`, `manager` and `admin`, so renaming a role in the screens never needs a data change.

Two teams: Development and Support. Each team has at most one Support Engineer.

Incident workflow: New, Assigned, In Progress, (Pending), Resolved, Closed. Every priority closes directly
from Resolved; incidents, problems and defects need no approval. Defects (bugs found in a service) follow the
same steps as incidents, with a severity (Critical, High, Medium, Low) and an environment instead of SLA clocks. Only changes and releases are approved (by an Administrator).
The database enforces this, so no client can bypass it.

## Run it locally

You need Python 3.11+ (tested on 3.13).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                       # then fill in the values
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs: every endpoint can be tried there. To call the protected ones, get an
access token by signing in, then click **Authorize** and paste the token (tokens expire after about an hour).

```powershell
# Windows PowerShell
$r = Invoke-RestMethod -Method Post -Uri "https://<project-ref>.supabase.co/auth/v1/token?grant_type=password" `
  -Headers @{ apikey = "<anon key>" } -ContentType "application/json" `
  -Body '{"email":"<your email>","password":"<your password>"}'
$r.access_token
```
```bash
# macOS / Linux
curl -s -X POST "https://<project-ref>.supabase.co/auth/v1/token?grant_type=password" \
  -H "apikey: <anon key>" -H "Content-Type: application/json" \
  -d '{"email":"<your email>","password":"<your password>"}'
```

## Run the web app locally

You need Node 20+. The back end must be running first (previous section).

```powershell
cd frontend
copy .env.example .env      # VITE_API_URL=http://localhost:8000
npm install
npm run dev                 # http://localhost:5173, sign in with a Supabase user that has a profile
npm run build               # production build into frontend/dist
```

The back end's `CORS_ORIGINS` must include the address the app runs on (default allows
`http://localhost:5173` and `http://127.0.0.1:5173`).

## Self sign-up

The sign-in page has a **Create an account** link. The form asks for name, email and password only. The new login cannot use the
portal until an Administrator opens **Admin**, finds it under *Sign-up requests waiting for approval* (the sidebar shows a count),
and approves it by choosing a role and team, or rejects it (which removes the login). Until then, signing in says the request is
waiting for approval. Needs migration 006.

## File attachments

Files are attached in the **Activity** tab of every incident, problem, defect, change and release: incidents and defects
have an **Attach file** button inside the *Add a note* box (so a note and a file can go together), the others have an
*Attach a file* box. Attached files appear in the activity timeline with Download and Remove. You can attach images (png, jpg, gif, webp)
and documents (pdf, txt, csv, log, doc, docx, xls, xlsx, ppt, pptx), **up to 1 MB per file**. The files are stored in a private
Supabase Storage bucket named `attachments` (created by migration 005); nobody can reach it directly. The back end checks
who may see a record before it uploads or serves a file, and always serves files as downloads. The 1 MB limit is enforced by the
back end, the database and the bucket. Customers can attach to their own incidents, problems and defects; only Support Engineers
(their own team) and Administrators attach to changes and releases, and everyone can download what they can see.

The back end needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for this (the same keys it already uses). The bucket name can be
changed with `ATTACHMENTS_BUCKET` (default `attachments`).

## Set up the database (Supabase)

1. SQL editor: run `supabase/migrations/001_foundation_schema.sql`, then `002_clear_resolved_at_on_reopen.sql`,
   then `003_remove_incident_approval.sql`, `004_defects.sql`, `005_attachments.sql` and `006_signup_requests.sql`
   (005 also creates the private `attachments` Storage bucket, 1 MB per file).
2. Authentication > Users > Add user (auto-confirm), then give that login a profile:
   ```sql
   insert into profiles (id, email, full_name, role, team_id)
   values ('<user uuid>', '<email>', '<name>', 'admin', null);
   ```
3. Later users are created by an admin through `POST /api/v1/users`, which creates the login and profile together.

## Deploy the back end (Render)

1. Push this folder to a GitHub repository (the `.env` file is excluded by `.gitignore`).
2. Render > New > Blueprint > choose the repository. Enter the values it asks for (see `backend/.env.example`).
3. When it is live, open `https://<service>.onrender.com/healthz` (should say `{"status":"ok","database":"up"}`) and `/docs`.
4. Set `CORS_ORIGINS` to the front end's address once the front end exists.

## Tests

```bash
# API tests need any Postgres 15+ you may create databases in; they make and drop their own
TEST_PG_ADMIN_URL="postgresql://postgres:<password>@localhost:5432/postgres" pytest

# Database rule checks: apply the migrations to an empty database that has a minimal auth.users table, then
psql -d <empty database> -f supabase/schema_checks.sql      # rolls back, leaves no data
```

Verified: the database rules and all API role/team rules against a real Postgres 16, the app under
uvicorn, and every endpoint the web app calls over real HTTP with browser CORS headers (Supabase sign-in
replaced by a stand-in). **Not yet verified:** the live Supabase sign-in, token refresh, password and
user-creation calls (tested against a pretend Supabase only), and the Render deployment.

## API overview (all under `/api/v1`; everything except `/auth/login`, `/auth/refresh` and `/healthz` needs `Authorization: Bearer <token>`)

| Area | Endpoints |
|---|---|
| Sign in / up | `POST /auth/login`, `POST /auth/register` (self sign-up, waits for approval), `POST /auth/refresh`, `POST /auth/password` (change own) |
| Session | `GET /me` (role, team, menu to show) |
| Reference | `GET /teams`, `GET/POST/PATCH /services`, `GET/PUT /sla` |
| Users (admin) | `GET /signup-requests`, `POST /signup-requests/{id}/approve` and `/reject`, `GET/POST /users`, `PATCH /users/{id}`, `POST /users/{id}/password`, `GET /users/assignable` |
| Incidents | `GET/POST /incidents`, `GET/PATCH /incidents/{id}`, `POST .../assign`, `POST .../transition`, `GET/POST .../comments`, `GET .../activity` |
| Problems | `GET/POST /problems`, `GET/PATCH /problems/{id}`, `POST .../assign`, `POST .../transition`, `POST .../incidents`, `DELETE .../incidents/{incident_id}`, `GET .../activity` |
| Defects | `GET/POST /defects`, `GET/PATCH /defects/{id}`, `POST .../assign`, `POST .../transition`, `GET/POST .../comments`, `GET .../activity` |
| Changes (manager, admin) | `GET/POST /changes`, `GET/PATCH /changes/{id}`, `POST .../transition`, `GET .../activity` |
| Releases (manager, admin) | `GET/POST /releases`, `GET/PATCH /releases/{id}`, `POST .../transition`, `POST .../changes`, `DELETE .../changes/{change_id}`, `GET .../activity` |
| Attachments | `GET/POST /{incidents,problems,defects,changes,releases}/{id}/attachments`, `GET /attachments/{id}/download`, `DELETE /attachments/{id}` |
| Approvals | `GET /approvals`, `POST /approvals/{id}/decision` |
| Dashboard | `GET /dashboard/summary` |
| Reports (manager, admin) | `GET /reports`, `GET /reports/{key}` (add `?format=csv` to download) |
| Audit (admin) | `GET /audit` (filters: table, record, action, actor_id, since, until) |
| System | `GET /healthz` (no login) |

Every error looks like `{"error": {"code": "...", "message": "..."}}`.

## Not built yet

Email notifications and the self-registration screen. Deploying the front end (for example as a Render
static site with `npm run build`, publish directory `dist`, and `VITE_API_URL` set to the API address).
