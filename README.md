# Maini ITSM

IT service management portal: incidents, problems, changes, releases, approvals, SLAs, audit.
React front end (next step) -> FastAPI back end -> Supabase (Postgres + Auth), hosted on Render.

The front end only ever talks to the back end's REST API, so it can be replaced by any other
technology without touching the back end or the database.

```
supabase/migrations/   the database: run in order (001, 002, ...) in the Supabase SQL editor
supabase/schema_checks.sql   59 rule checks for the database (see "Tests")
backend/               FastAPI service (deployed on Render)
  app/main.py            app entry point, /healthz
  app/routers/           reference (me, teams, services, SLA), users, incidents, approvals, dashboard
  app/rbac.py            who may see what; app/auth.py login; app/errors.py error format
  tests/                 38 automated tests
render.yaml            Render Blueprint for the back end
```

## Roles and teams

| | Employee | Manager | Admin |
|---|---|---|---|
| Sees incidents | only their own | their team's, plus any they raised or are assigned | all |
| Raises incidents / problems | yes | yes | yes (also on someone's behalf) |
| Works incidents (assign, edit, move on) | confirms or reopens own resolved incident | their team's | all |
| Approves P1/P2 incident closure | no | own team, never their own work | yes |
| Raises changes and releases | no | yes | yes |
| Approves changes and releases | no | no | yes |
| Users, services, SLA targets | no | no | yes |

Two teams: Development and Support. Each team has at most one manager.

Incident workflow: New, Assigned, In Progress, (Pending), Resolved, Closed. P1/P2 go
Resolved -> Pending Approval -> Closed (approval) or back to In Progress (rejection). P3/P4 close
directly. The database enforces this, so no client can bypass it.

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

## Set up the database (Supabase)

1. SQL editor: run `supabase/migrations/001_foundation_schema.sql`, then `002_clear_resolved_at_on_reopen.sql`.
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

Verified: the database rules and all API role/team rules against a real Postgres 16, and the app
starting under uvicorn. **Not yet verified:** the live Supabase sign-in and user-creation calls (tested
against a pretend Supabase only), and the Render deployment.

## API overview (all under `/api/v1`, all need `Authorization: Bearer <token>`)

| Area | Endpoints |
|---|---|
| Session | `GET /me` (role, team, menu to show) |
| Reference | `GET /teams`, `GET/POST/PATCH /services`, `GET/PUT /sla` |
| Users (admin) | `GET/POST /users`, `PATCH /users/{id}`, `GET /users/assignable` |
| Incidents | `GET/POST /incidents`, `GET/PATCH /incidents/{id}`, `POST .../assign`, `POST .../transition`, `GET/POST .../comments`, `GET .../activity` |
| Approvals | `GET /approvals`, `POST /approvals/{id}/decision` |
| Dashboard | `GET /dashboard/summary` |
| System | `GET /healthz` (no login) |

Every error looks like `{"error": {"code": "...", "message": "..."}}`.

## Not built yet

Problems, changes, releases, reports and audit-history endpoints (the database already supports
them), the React front end, email notifications, and the self-registration screen.
