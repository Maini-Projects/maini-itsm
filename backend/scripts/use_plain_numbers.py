"""Existing customers: numbers become INC-1, PRB-1, ... (no customer code), every row gets its customer's project_id,
and the "(Apple)" style suffix the first test data carried is removed from incident descriptions.

Run from the backend folder:  .venv\\Scripts\\python.exe scripts\\use_plain_numbers.py
"""
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import psycopg  # noqa: E402

from app.tenant import MAIN_TABLES, NUMBERING, add_project_column, apply_numbering, use_schema  # noqa: E402

URL = re.search(r"^DATABASE_URL=(.*)$", open(".env").read(), re.M).group(1).strip().strip("\"'")
with psycopg.connect(URL, prepare_threshold=None) as c:
    for pid, name, schema in c.execute("select id, name, schema_name from projects where schema_name is not null order by created_at").fetchall():
        use_schema(c, schema)
        apply_numbering(c)
        for t in MAIN_TABLES + ["approvals"]:
            c.execute(f"alter table {t} disable trigger user")  # renumbering and tidying are not edits worth auditing
        for table, seq, prefix in NUMBERING:
            c.execute(f"""with n as (select id, row_number() over (order by created_at, id) as rn from {table})
                          update {table} x set number = '{prefix}-' || n.rn from n where n.id = x.id""")
            count = c.execute(f"select count(*) from {table}").fetchone()[0]
            c.execute("select setval(%s, %s, %s)", (seq, max(count, 1), count > 0))
        for rtype, table in (("incident", "incidents"), ("change", "changes"), ("release", "releases"), ("problem", "problems")):
            c.execute(f"update approvals a set record_number = x.number from {table} x where a.record_type = '{rtype}' and a.record_id = x.id")
        c.execute("update incidents set short_description = regexp_replace(short_description, ' \\([A-Za-z ]+\\)$', '')")
        add_project_column(c, pid)
        for t in MAIN_TABLES + ["approvals"]:
            c.execute(f"alter table {t} enable trigger user")
        print(name, [r[0] for r in c.execute("select number from incidents order by created_at limit 2").fetchall()],
              c.execute("select short_description from incidents order by created_at limit 1").fetchone()[0])
    c.commit()
print("done")
