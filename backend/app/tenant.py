"""One schema per customer.

Shared data (users, teams, projects, applications, SLA targets, workflow rules) lives in `public`. Everything a
customer owns (incidents, problems, defects, changes, releases, approvals, attachments, audit history) lives in that
customer's own schema, so one customer's rows can never sit in the same table as another's.

provision() builds a customer's schema from app/tenant_sql/*.sql (regenerate those with
scripts/generate_tenant_template.py after a migration changes a customer table).
"""
import re
from pathlib import Path
from typing import Callable

SQL_DIR = Path(__file__).parent / "tenant_sql"
SCHEMA_RE = re.compile(r"^cust_[a-z0-9_]{1,50}$")

# The customer-owned tables, parents first
TENANT_TABLES = ["incidents", "incident_comments", "problems", "problem_incidents", "defects", "defect_comments",
                 "changes", "releases", "release_changes", "approvals", "attachments", "audit_log"]


# (table, its number sequence, number prefix): numbers are INC-1, PRB-1, DEF-1, CHG-1, REL-1, counted per customer
NUMBERING = [("incidents", "incident_seq", "INC"), ("problems", "problem_seq", "PRB"), ("defects", "defect_seq", "DEF"),
             ("changes", "change_seq", "CHG"), ("releases", "release_seq", "REL")]
MAIN_TABLES = [t for t, _s, _p in NUMBERING]
KB_TABLES = ["kb_articles"]  # knowledge base: created from tenant_sql/kb.sql, not part of the numbered records


def apply_numbering(conn) -> None:
    """Numbers in the current schema count from 1. The search_path must already be set."""
    for table, seq, prefix in NUMBERING:
        conn.execute(f"alter sequence {seq} restart with 1")
        conn.execute(f"alter table {table} alter column number set default '{prefix}-' || nextval('{seq}')")


def add_project_column(conn, project_id) -> None:
    """Every row says which customer it belongs to (the same value for the whole schema), so lists that combine
    several customers can show it."""
    for t in MAIN_TABLES + KB_TABLES:
        conn.execute(f"alter table {t} add column if not exists project_id uuid not null default '{project_id}'")


def schema_name_for(project_name: str, taken: set[str]) -> str:
    """cust_<name>, made of lowercase letters, digits and underscores, and different from every name in `taken`."""
    base = "cust_" + (re.sub(r"[^a-z0-9]+", "_", project_name.lower()).strip("_") or "project")[:40]
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    return name


def use_schema(conn, schema: str) -> None:
    """Make the rest of this transaction read and write this customer's tables."""
    if not SCHEMA_RE.match(schema):
        raise ValueError(f"not a customer schema: {schema!r}")
    # pg_temp is listed explicitly (after the customer) so a leftover temporary view can never shadow a real table
    conn.execute("select set_config('search_path', %(p)s, true)", {"p": f'"{schema}", pg_temp, public'})


def use_schemas(conn, schemas: list[str]) -> None:
    """Read several customers at once: temporary views stitch their tables together (read only).

    Each view is a UNION ALL of the same table in every chosen schema, so the customers' rows stay in their own
    tables and are only combined for this one request. Writes use use_schema() on the single schema that owns the row.
    """
    if len(schemas) == 1:
        return use_schema(conn, schemas[0])
    if not all(SCHEMA_RE.match(s) for s in schemas):
        raise ValueError("not a customer schema")
    for t in TENANT_TABLES + KB_TABLES:
        union = " union all ".join(f'select * from "{s}".{t}' for s in schemas)
        conn.execute(f"create or replace temp view {t} as {union}")
    quoted = ", ".join(f'"{s}"' for s in schemas)
    conn.execute("select set_config('search_path', %(p)s, true)", {"p": f"pg_temp, {quoted}, public"})
    conn.multi_views = True  # get_conn drops the views again before the transaction ends


def drop_multi_views(conn) -> None:
    conn.execute("drop view if exists " + ", ".join(f"pg_temp.{t}" for t in TENANT_TABLES + KB_TABLES))
    conn.multi_views = False


WRITE_TABLE = {"incidents": "incidents", "problems": "problems", "defects": "defects", "changes": "changes",
               "releases": "releases", "approvals": "approvals", "attachments": "attachments", "kb": "kb_articles"}


def schema_owning(conn, schemas: list[str], path: str, ids: list) -> str:
    """Which of the chosen customers owns the record a write request is about (the first one when it creates a new record)."""
    parts = path.split("/")
    table = WRITE_TABLE.get(parts[3]) if len(parts) > 3 else None
    if table:
        for schema in schemas:
            for rid in ids:
                if conn.execute(f'select 1 from "{schema}".{table} where id = %(i)s', {"i": rid}).fetchone():
                    return schema
    return schemas[0]


def provision(conn, schema: str, project_id, fill: Callable | None = None) -> None:
    """Create the schema and its tables (once). `fill(conn)` may load existing rows before the triggers are attached."""
    if not SCHEMA_RE.match(schema):
        raise ValueError(f"not a customer schema: {schema!r}")
    exists = conn.execute("select 1 from pg_namespace where nspname = %(s)s", {"s": schema}).fetchone()
    if exists:
        return
    conn.execute(f'create schema "{schema}"')
    use_schema(conn, schema)
    conn.execute((SQL_DIR / "tables.sql").read_text(encoding="utf8"))
    conn.execute((SQL_DIR / "kb.sql").read_text(encoding="utf8"))
    apply_numbering(conn)
    if fill:
        fill(conn)
    add_project_column(conn, project_id)
    conn.execute((SQL_DIR / "triggers.sql").read_text(encoding="utf8"))
    roles = {r["rolname"] if isinstance(r, dict) else r[0]
             for r in conn.execute("select rolname from pg_roles where rolname in ('service_role','anon','authenticated')").fetchall()}
    if "service_role" in roles:
        conn.execute(f'grant usage on schema "{schema}" to service_role')
        conn.execute(f'grant all on all tables in schema "{schema}" to service_role')
        conn.execute(f'grant all on all sequences in schema "{schema}" to service_role')
    for role in roles & {"anon", "authenticated"}:
        conn.execute(f'revoke all on schema "{schema}" from {role}')
