"""Test setup: a throwaway Postgres database with the real schema, fake logins, one user per role.

Run:  TEST_PG_ADMIN_URL="postgresql://postgres@localhost:5432/postgres" pytest
(any Postgres 15+ you may create databases in; the tests create and drop their own database)
"""
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
MIGRATIONS = sorted((Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob("*.sql"))

# Stand-ins for what Supabase provides in a real project
SHIM = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
create schema auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text);
"""


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0000-0000-{n:012d}")


IDS = {"admin": _id(1), "devmgr": _id(2), "devemp": _id(3), "devemp2": _id(4), "supmgr": _id(5), "supemp": _id(6)}


@pytest.fixture(scope="session")
def db_conninfo():
    if not ADMIN_URL:
        pytest.skip("set TEST_PG_ADMIN_URL to a Postgres you may create databases in")
    name = f"itsm_test_{os.getpid()}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(f"drop database if exists {name}")
        c.execute(f"create database {name}")
    conninfo = make_conninfo(ADMIN_URL, dbname=name)
    with psycopg.connect(conninfo, autocommit=True) as c:
        c.execute(SHIM)
        for migration in MIGRATIONS:  # applied in order, exactly as on Supabase
            c.execute(migration.read_text())
        team = {r[1]: r[0] for r in c.execute("select id, name from teams").fetchall()}
        people = [("admin", "admin", None), ("devmgr", "manager", "Development"), ("devemp", "employee", "Development"),
                  ("devemp2", "employee", "Development"), ("supmgr", "manager", "Support"),
                  ("supemp", "employee", "Support")]
        for key, role, team_name in people:
            c.execute("insert into auth.users(id, email) values (%s, %s)", (IDS[key], f"{key}@test.local"))
            c.execute("insert into profiles(id, email, full_name, role, team_id) values (%s,%s,%s,%s,%s)",
                      (IDS[key], f"{key}@test.local", key.title(), role, team.get(team_name)))
    yield conninfo
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(f"drop database if exists {name} with (force)")


@pytest.fixture(scope="session")
def raw(db_conninfo):
    """A direct, autocommitted connection for set-up, clean-up and checks."""
    with psycopg.connect(db_conninfo, autocommit=True) as c:
        yield c


class FakeAuthAdmin:
    """Replaces Supabase's login-creation service."""
    def __init__(self, conninfo: str):
        self.conninfo, self.created, self.deleted, self.passwords = conninfo, [], [], {}

    def create_user(self, email, password):
        new_id = uuid.uuid4()
        with psycopg.connect(self.conninfo, autocommit=True) as c:
            c.execute("insert into auth.users(id, email) values (%s, %s)", (new_id, email))
        self.created.append(new_id)
        return new_id

    def set_password(self, user_id, password):
        self.passwords[user_id] = password

    def delete_user(self, user_id):
        with psycopg.connect(self.conninfo, autocommit=True) as c:
            c.execute("delete from auth.users where id = %s", (user_id,))
        self.deleted.append(user_id)


DEFAULT_PASSWORD = "password123"


class FakeFileStore:
    """Replaces Supabase Storage: files are kept in a dict."""
    def __init__(self):
        self.files, self.fail_puts = {}, False

    def put(self, path, data, content_type):
        if self.fail_puts:
            from app.errors import api_error
            raise api_error(503, "storage_unavailable", "File storage could not be reached. Try again in a moment.")
        self.files[path] = (data, content_type)

    def get(self, path):
        from app.errors import api_error
        if path not in self.files:
            raise api_error(404, "file_missing", "The file is no longer in storage.")
        return self.files[path][0]

    def delete(self, path):
        self.files.pop(path, None)


class FakeAuthClient:
    """Replaces Supabase's password sign-in. Seeded users sign in as <key>@test.local with DEFAULT_PASSWORD
    (unless FakeAuthAdmin.set_password changed it); the token is "t-<key>", the refresh token "r-<key>"."""
    def __init__(self, admin: "FakeAuthAdmin"):
        self.admin = admin

    def login(self, email, password):
        for key, uid in IDS.items():
            if email == f"{key}@test.local":
                if password != self.admin.passwords.get(uid, DEFAULT_PASSWORD):
                    return None
                return {"access_token": f"t-{key}", "refresh_token": f"r-{key}", "expires_in": 3600,
                        "token_type": "bearer"}
        return None

    def refresh(self, refresh_token):
        key = refresh_token.removeprefix("r-")
        if key in IDS:
            return {"access_token": f"t-{key}", "refresh_token": refresh_token, "expires_in": 3600,
                    "token_type": "bearer"}
        return None


@pytest.fixture(scope="session")
def app(db_conninfo):
    os.environ["DATABASE_URL"] = db_conninfo
    os.environ["CORS_ORIGINS"] = "http://localhost:5173"
    from app.auth import get_auth_admin, get_auth_client, get_token_verifier
    from app.storage import get_file_store
    from app.errors import api_error
    from app.main import app as fastapi_app

    def fake_verify(token: str):
        key = token.removeprefix("t-")
        if key in IDS:
            return IDS[key]
        raise api_error(401, "invalid_token", "Your session has expired. Please sign in again.")

    fake_admin = FakeAuthAdmin(db_conninfo)
    fastapi_app.dependency_overrides[get_token_verifier] = lambda: fake_verify
    fastapi_app.dependency_overrides[get_auth_admin] = lambda: fake_admin
    fastapi_app.dependency_overrides[get_auth_client] = lambda: FakeAuthClient(fake_admin)
    fastapi_app.state.fake_auth_admin = fake_admin
    fake_store = FakeFileStore()
    fastapi_app.dependency_overrides[get_file_store] = lambda: fake_store
    fastapi_app.state.fake_file_store = fake_store
    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:  # runs the app start-up (opens the database pool)
        yield c


@pytest.fixture(autouse=True)
def clean(raw, app):
    """Every test starts from: the six seeded people, default services and SLA targets, no tickets."""
    yield
    keep = list(IDS.values())
    raw.execute("truncate signup_requests, incident_comments, defect_comments, attachments, approvals, problem_incidents, release_changes, incidents, "
                "problems, defects, changes, releases, audit_log restart identity")
    raw.execute("delete from profiles where id <> all(%s)", (keep,))
    raw.execute("delete from auth.users where id <> all(%s)", (keep,))
    raw.execute("update profiles set status = 'active' where id = any(%s)", (keep,))
    raw.execute("delete from services where name not in ('Oracle ERP Cloud','HCM Cloud','Procurement Integrations',"
                "'Corporate IT','Identity & Access')")
    raw.execute("update services set active = true")
    raw.execute("""update sla_policies s set response_minutes = v.r, resolution_minutes = v.s
                   from (values ('P1',15,240),('P2',60,1440),('P3',240,4320),('P4',1440,7200)) as v(p, r, s)
                   where s.priority::text = v.p""")
    app.state.fake_auth_admin.created.clear()
    app.state.fake_auth_admin.deleted.clear()
    app.state.fake_auth_admin.passwords.clear()
    app.state.fake_file_store.files.clear()
    app.state.fake_file_store.fail_puts = False


def as_user(who: str) -> dict:
    return {"Authorization": f"Bearer t-{who}"}
