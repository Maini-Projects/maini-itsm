"""Projects, and which of them a user works on (admin assigns them; customers get none)."""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, current_user, require_roles
from ..tenant import provision, schema_name_for, use_schema

router = APIRouter(tags=["projects"])


def projects_for(conn, user: Principal) -> list[dict]:
    """Administrators see every project; everyone else the ones assigned to them."""
    if user.role == "admin":
        return fetch_all(conn, "select id, name from projects order by name")
    return fetch_all(conn, """select p.id, p.name from projects p join user_projects up on up.project_id = p.id
                               where up.user_id = %(u)s order by p.name""", {"u": user.id})


@router.get("/projects")
def list_projects(user: Principal = Depends(current_user), conn=Depends(get_conn)):
    return projects_for(conn, user)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, actor: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    name = body.name.strip()
    if fetch_one(conn, "select 1 as x from projects where lower(name) = lower(%(n)s)", {"n": name}):
        raise api_error(409, "project_exists", "A project with that name already exists.")
    taken = {r["schema_name"] for r in fetch_all(conn, "select schema_name from projects where schema_name is not null")}
    schema = schema_name_for(name, taken)
    project = fetch_one(conn, "insert into projects(name, schema_name) values (%(n)s, %(s)s) returning id, name",
                        {"n": name, "s": schema})
    provision(conn, schema, project["id"])  # the customer's own set of tables, created right now
    if actor.schema_name:  # back to the customer this request started in
        use_schema(conn, actor.schema_name)
    else:
        conn.execute("select set_config('search_path', 'public', true)")
    return project


class AssignIn(BaseModel):
    project_ids: list[UUID]


def _manageable_target(conn, actor: Principal, user_id: UUID) -> dict:
    """Administrators may assign anyone; a Support Engineer only the Customers of their own team."""
    target = fetch_one(conn, "select id, role, team_id from profiles where id = %(u)s", {"u": user_id})
    if target is None:
        raise api_error(404, "not_found", "User not found.")
    if actor.role != "admin" and not (target["role"] == "employee" and target["team_id"] == actor.team_id):
        raise api_error(403, "forbidden", "You can only assign projects to the customers of your own team.")
    return target


@router.get("/users/{user_id}/projects")
def user_projects(user_id: UUID, actor: Principal = Depends(require_roles("admin", "manager")), conn=Depends(get_conn)):
    _manageable_target(conn, actor, user_id)
    return [r["project_id"] for r in fetch_all(conn, "select project_id from user_projects where user_id = %(u)s",
                                                {"u": user_id})]


@router.put("/users/{user_id}/projects")
def assign_projects(user_id: UUID, body: AssignIn, actor: Principal = Depends(require_roles("admin", "manager")),
                    conn=Depends(get_conn)):
    _manageable_target(conn, actor, user_id)
    ids = list(dict.fromkeys(body.project_ids))
    allowed = {p["id"] for p in projects_for(conn, actor)}  # a Support Engineer can hand out only their own projects
    if any(i not in allowed for i in ids):
        raise api_error(422, "unknown_project", "Choose from the projects you have access to.")
    if actor.role != "admin":  # keep the customer's projects that the engineer cannot see
        kept = [r["project_id"] for r in fetch_all(conn, "select project_id from user_projects where user_id = %(u)s",
                                                    {"u": user_id}) if r["project_id"] not in allowed]
        ids += kept
    conn.execute("delete from user_projects where user_id = %(u)s", {"u": user_id})
    for pid in ids:
        conn.execute("insert into user_projects(user_id, project_id) values (%(u)s, %(p)s)", {"u": user_id, "p": pid})
    return {"project_ids": ids}


def _people_query() -> str:
    return """select p.id, p.full_name, p.email, p.role, t.name as team_name
                from profiles p left join teams t on t.id = p.team_id
               where p.status = 'active' and p.role <> 'admin'
                 and (%(admin)s or (p.role = 'employee' and p.team_id = %(team)s))
               order by p.role, p.full_name"""


@router.get("/projects/overview")
def projects_overview(actor: Principal = Depends(require_roles("admin", "manager")), conn=Depends(get_conn)):
    """Projects with how many people work on each (a Support Engineer sees their own projects)."""
    mine = [p["id"] for p in projects_for(conn, actor)]
    return fetch_all(
        conn,
        """select p.id, p.name, p.created_at,
                  count(*) filter (where u.role = 'manager') as support_engineers,
                  count(*) filter (where u.role = 'employee') as customers
             from projects p
             left join user_projects up on up.project_id = p.id
             left join profiles u on u.id = up.user_id
            where p.id = any(%(mine)s) group by p.id order by p.name""",
        {"mine": mine},
    )


@router.get("/projects/{project_id}/members")
def project_members(project_id: UUID, actor: Principal = Depends(require_roles("admin", "manager")),
                    conn=Depends(get_conn)):
    """The people this user may assign to the project, and which of them already work on it."""
    if project_id not in {p["id"] for p in projects_for(conn, actor)}:
        raise api_error(404, "not_found", "Project not found.")
    people = fetch_all(conn, _people_query(), {"admin": actor.role == "admin", "team": actor.team_id})
    on = {r["user_id"] for r in fetch_all(conn, "select user_id from user_projects where project_id = %(p)s",
                                           {"p": project_id})}
    return [{**p, "member": p["id"] in on} for p in people]


class MembersIn(BaseModel):
    user_ids: list[UUID]


@router.put("/projects/{project_id}/members")
def set_project_members(project_id: UUID, body: MembersIn,
                        actor: Principal = Depends(require_roles("admin", "manager")), conn=Depends(get_conn)):
    if project_id not in {p["id"] for p in projects_for(conn, actor)}:
        raise api_error(404, "not_found", "Project not found.")
    allowed = {p["id"] for p in fetch_all(conn, _people_query(), {"admin": actor.role == "admin", "team": actor.team_id})}
    chosen = set(body.user_ids)
    if not chosen <= allowed:
        raise api_error(403, "forbidden", "You can only assign the people you manage.")
    # only touch the people this user may manage; everyone else keeps their current assignment
    conn.execute("delete from user_projects where project_id = %(p)s and user_id = any(%(a)s)",
                 {"p": project_id, "a": list(allowed)})
    for uid in chosen:
        conn.execute("insert into user_projects(user_id, project_id) values (%(u)s, %(p)s)", {"u": uid, "p": project_id})
    return {"user_ids": list(chosen)}
