"""Knowledge base: articles written by Administrators and Support Engineers, read and searched by everyone.
Articles live in the customer's own schema, so one customer's articles never mix with another's.
Customers only see published articles meant for everyone; staff also see drafts and staff-only notes."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, current_user, require_roles

router = APIRouter(tags=["knowledge base"])
staff_only = require_roles("admin", "manager")

SELECT = """
select x.id, x.project_id, x.title, {body} as body, x.category, x.audience, x.status,
       x.created_by, cb.full_name as created_by_name, x.created_at, x.updated_at
  from kb_articles x join profiles cb on cb.id = x.created_by
"""


def _visible(user: Principal) -> str:
    return "true" if user.role in ("admin", "manager") else "(x.status = 'published' and x.audience = 'everyone')"


@router.get("/kb")
def list_articles(q: str | None = None, category: str | None = None, project_id: UUID | None = None,
                  limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                  user: Principal = Depends(current_user), conn=Depends(get_conn)):
    words = [w for w in (q or "").split() if w][:8]
    params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
    match = " and ".join(f"concat_ws(chr(32), x.title, x.body, x.category) ilike %(w{i})s" for i in range(len(words))) or "true"
    where = f"""{_visible(user)} and ({match})
        and (%(cat)s::text is null or x.category = %(cat)s)
        and (%(proj)s::uuid is null or x.project_id = %(proj)s)"""
    p = {**params, "cat": category, "proj": project_id, "limit": limit, "offset": offset}
    total = fetch_one(conn, f"select count(*) as n from kb_articles x where {where}", p)["n"]
    items = fetch_all(conn, SELECT.format(body="left(x.body, 220)") + f" where {where} order by x.updated_at desc limit %(limit)s offset %(offset)s", p)
    cats = [r["category"] for r in fetch_all(
        conn, f"select distinct x.category from kb_articles x where {_visible(user)} and x.category is not null order by 1")]
    return {"items": items, "total": total, "categories": cats}


@router.get("/kb/{article_id}")
def get_article(article_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    row = fetch_one(conn, SELECT.format(body="x.body") + f" where x.id = %(i)s and {_visible(user)}", {"i": article_id})
    if row is None:
        raise api_error(404, "not_found", "Article not found.")
    return row


class ArticleIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(default="", max_length=50000)
    category: str | None = Field(default=None, max_length=80)
    audience: Literal["everyone", "staff"] = "everyone"
    status: Literal["draft", "published"] = "draft"


class ArticlePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    body: str | None = Field(default=None, max_length=50000)
    category: str | None = Field(default=None, max_length=80)
    audience: Literal["everyone", "staff"] | None = None
    status: Literal["draft", "published"] | None = None


@router.post("/kb", status_code=201)
def create_article(body: ArticleIn, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    if user.schema_name is None:
        raise api_error(403, "no_project", "You are not assigned to a customer yet. Ask an Administrator.")
    row = fetch_one(
        conn,
        """insert into kb_articles(title, body, category, audience, status, created_by, updated_by)
           values (%(t)s, %(b)s, %(c)s, %(a)s, %(s)s, %(u)s, %(u)s) returning id""",
        {"t": body.title.strip(), "b": body.body, "c": (body.category or "").strip() or None, "a": body.audience,
         "s": body.status, "u": user.id})
    return get_article(row["id"], user, conn)


@router.patch("/kb/{article_id}")
def update_article(article_id: UUID, body: ArticlePatch, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    if "category" in fields:
        fields["category"] = (fields["category"] or "").strip() or None
    sets = ", ".join(f"{c} = %({c})s" for c in fields)  # column names come from the model, not the caller
    row = fetch_one(conn, f"update kb_articles set {sets}, updated_by = %(u)s where id = %(i)s returning id",
                    {**fields, "u": user.id, "i": article_id})
    if row is None:
        raise api_error(404, "not_found", "Article not found.")
    return get_article(article_id, user, conn)


@router.delete("/kb/{article_id}", status_code=204)
def delete_article(article_id: UUID, user: Principal = Depends(staff_only), conn=Depends(get_conn)):
    if fetch_one(conn, "delete from kb_articles where id = %(i)s returning id", {"i": article_id}) is None:
        raise api_error(404, "not_found", "Article not found.")
