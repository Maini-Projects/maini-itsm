"""Adds the knowledge base table to every existing customer schema (new customers get it automatically).

Run from the backend folder:  .venv\\Scripts\\python.exe scripts\\add_knowledge_base.py     Safe to run again.
"""
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import psycopg  # noqa: E402

from app.tenant import KB_TABLES, SQL_DIR, add_project_column, use_schema  # noqa: E402

URL = re.search(r"^DATABASE_URL=(.*)$", open(".env").read(), re.M).group(1).strip().strip("\"'")
with psycopg.connect(URL, prepare_threshold=None) as c:
    for pid, name, schema in c.execute("select id, name, schema_name from projects where schema_name is not null").fetchall():
        use_schema(c, schema)
        if c.execute("select to_regclass(%s)", (f"{schema}.kb_articles",)).fetchone()[0] is None:
            c.execute((SQL_DIR / "kb.sql").read_text(encoding="utf8"))
            add_project_column(c, pid)
            roles = {r[0] for r in c.execute("select rolname from pg_roles where rolname = 'service_role'").fetchall()}
            if roles:
                c.execute(f'grant all on all tables in schema "{schema}" to service_role')
            print(f"{name}: knowledge base added")
        else:
            print(f"{name}: already there")
    c.commit()
