"""Gives every project its own schema and moves that project's existing records into it.

Run from the backend folder:  .venv\\Scripts\\python.exe scripts\\migrate_to_schemas.py
Everything happens in one transaction: row counts are checked before it commits, and the old shared tables are only
moved (not deleted) into a schema called `legacy`. Safe to run again: projects that already have a schema are skipped.
"""
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import psycopg  # noqa: E402

from app.tenant import TENANT_TABLES, provision, schema_name_for  # noqa: E402

URL = re.search(r"^DATABASE_URL=(.*)$", open(".env").read(), re.M).group(1).strip().strip("\"'")
MOVE_TO_LEGACY = [t for t in TENANT_TABLES if t != "audit_log"]  # public.audit_log keeps user / SLA history
DIRECT = ["incidents", "problems", "defects", "changes", "releases"]  # carry project_id
# child tables: (table, parent column, parent table)
CHILD = [("incident_comments", "incident_id", "incidents"), ("problem_incidents", "problem_id", "problems"),
         ("defect_comments", "defect_id", "defects"), ("release_changes", "release_id", "releases")]
RECORD_KIND = {"incident": "incidents", "problem": "problems", "change": "changes", "release": "releases", "defect": "defects"}


def columns(conn, table: str) -> str:
    """The new table's columns, in order, except the identity column."""
    rows = conn.execute("""select column_name from information_schema.columns
                            where table_schema = current_schema() and table_name = %s and is_identity = 'NO'
                            order by ordinal_position""", (table,)).fetchall()
    return ", ".join(r[0] for r in rows)


def fill_from_public(conn, project_id):
    for t in DIRECT:
        cols = columns(conn, t)
        conn.execute(f"insert into {t} ({cols}) select {cols} from public.{t} where project_id = %s", (project_id,))
    for t, col, parent in CHILD:
        cols = columns(conn, t)
        conn.execute(f"insert into {t} ({cols}) select {cols} from public.{t} where {col} in (select id from {parent})")
    cols = columns(conn, "approvals")
    conn.execute(f"""insert into approvals ({cols}) select {cols} from public.approvals a
                      where (a.record_type = 'incident' and a.record_id in (select id from incidents))
                         or (a.record_type = 'change'   and a.record_id in (select id from changes))
                         or (a.record_type = 'release'  and a.record_id in (select id from releases))
                         or (a.record_type = 'problem'  and a.record_id in (select id from problems))""")
    cols = columns(conn, "attachments")
    conn.execute(f"""insert into attachments ({cols}) select {cols} from public.attachments a
                      where a.record_id in (select id from incidents union select id from problems union select id from defects
                                            union select id from changes union select id from releases)""")
    cols = columns(conn, "audit_log")
    conn.execute(f"""insert into audit_log ({cols}) select {cols} from public.audit_log a
                      where a.table_name in ('incidents','problems','defects','changes','releases','approvals')
                        and a.record_id in (select id from incidents union select id from problems union select id from defects
                                            union select id from changes union select id from releases union select id from approvals)
                      order by a.id""")
    # numbering continues after the highest number already used
    for seq, table, prefix in [("incident_seq", "incidents", "INC-"), ("problem_seq", "problems", "PRB-"),
                               ("change_seq", "changes", "CHG-"), ("release_seq", "releases", "REL-"),
                               ("defect_seq", "defects", "DEF-")]:
        top = conn.execute(f"select max(substring(number from '[0-9]+$')::int) from {table}").fetchone()[0]
        if top:
            conn.execute("select setval(%s, %s)", (seq, top))


with psycopg.connect(URL, prepare_threshold=None) as c:
    projects = c.execute("select id, name, schema_name from projects order by created_at").fetchall()
    taken = {p[2] for p in projects if p[2]}
    for pid, name, schema in projects:
        if schema:
            continue
        schema = schema_name_for(name, taken)
        taken.add(schema)
        c.execute("update projects set schema_name = %s where id = %s", (schema, pid))
        provision(c, schema, pid, lambda conn, pid=pid: fill_from_public(conn, pid))
        print(f"{name}: schema {schema}")

    # check: every old row with a project is now in exactly one customer schema
    c.execute("set local search_path to public")
    for t in DIRECT:
        old = c.execute(f"select count(*) from public.{t} where project_id is not null").fetchone()[0]
        new = sum(c.execute(f'select count(*) from "{s}".{t}').fetchone()[0]
                  for (s,) in c.execute("select schema_name from projects where schema_name is not null").fetchall())
        print(f"  {t}: before {old}, in customer schemas {new}")
        assert old == new, f"{t}: row counts differ"
    orphan = sum(c.execute(f"select count(*) from public.{t} where project_id is null").fetchone()[0] for t in DIRECT)
    assert orphan == 0, f"{orphan} records have no project"

    if c.execute("select to_regclass('public.incidents')").fetchone()[0]:
        c.execute("create schema if not exists legacy")
        for t in MOVE_TO_LEGACY:
            c.execute(f"alter table public.{t} set schema legacy")
        print("old shared tables moved to schema 'legacy'")
    if os.environ.get("DRY_RUN"):
        c.rollback()
        print("DRY RUN: rolled back, nothing changed")
    else:
        c.commit()
print("done")
