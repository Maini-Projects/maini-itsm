"""Who am I, teams, services, SLA targets."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, current_user, require_roles

router = APIRouter(tags=["reference"])


@router.get("/me")
def me(user: Principal = Depends(current_user), conn=Depends(get_conn)):
    """The signed-in user, their team and what their role may see. The front end builds its menu from this."""
    team = fetch_one(conn, "select name from teams where id = %(t)s", {"t": user.team_id}) if user.team_id else None
    org = fetch_one(conn, "select value from settings where key = 'organization_name'")
    menus = {
        "employee": ["dashboard", "incidents", "problems"],
        "manager": ["dashboard", "incidents", "problems", "changes", "releases", "approvals", "services", "reports"],
        "admin": ["dashboard", "incidents", "problems", "changes", "releases", "approvals", "services", "sla",
                  "reports", "audit", "admin"],
    }
    return {
        **user.model_dump(),
        "team_name": team["name"] if team else None,
        "organization_name": org["value"] if org else None,
        "menu": menus[user.role],
    }


@router.get("/teams")
def list_teams(_: Principal = Depends(current_user), conn=Depends(get_conn)):
    return fetch_all(conn, "select id, name from teams order by name")


# ---- services ("Projects & Services") ------------------------------------------------------

class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    owner_team_id: str | None = None
    criticality: Literal["High", "Medium", "Low"] = "Medium"
    active: bool = True


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    owner_team_id: str | None = None
    criticality: Literal["High", "Medium", "Low"] | None = None
    active: bool | None = None


@router.get("/services")
def list_services(_: Principal = Depends(current_user), conn=Depends(get_conn)):
    return fetch_all(
        conn,
        """select s.id, s.name, s.description, s.criticality, s.active, s.owner_team_id, t.name as owner_team_name,
                  (select count(*) from incidents i where i.service_id = s.id
                     and i.status not in ('Resolved','Pending Approval','Closed')) as open_incidents
           from services s left join teams t on t.id = s.owner_team_id
           order by s.name""",
    )


@router.post("/services", status_code=201)
def create_service(body: ServiceIn, _: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    return fetch_one(
        conn,
        """insert into services(name, description, owner_team_id, criticality, active)
           values (%(name)s, %(description)s, %(owner_team_id)s, %(criticality)s, %(active)s)
           returning id, name, description, criticality, active, owner_team_id""",
        body.model_dump(),
    )


@router.patch("/services/{service_id}")
def update_service(service_id: str, body: ServicePatch, _: Principal = Depends(require_roles("admin")),
                   conn=Depends(get_conn)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise api_error(422, "nothing_to_update", "Send at least one field to change.")
    sets = ", ".join(f"{col} = %({col})s" for col in changes)  # column names come from the model, not the caller
    row = fetch_one(conn, f"update services set {sets} where id = %(id)s "
                          "returning id, name, description, criticality, active, owner_team_id",
                    {**changes, "id": service_id})
    if row is None:
        raise api_error(404, "not_found", "Service not found.")
    return row


# ---- SLA targets ---------------------------------------------------------------------------

class SlaIn(BaseModel):
    response_minutes: int = Field(gt=0)
    resolution_minutes: int = Field(gt=0)


@router.get("/sla")
def list_sla(_: Principal = Depends(current_user), conn=Depends(get_conn)):
    return fetch_all(conn, "select priority, response_minutes, resolution_minutes from sla_policies order by priority")


@router.put("/sla/{priority}")
def update_sla(priority: Literal["P1", "P2", "P3", "P4"], body: SlaIn,
               _: Principal = Depends(require_roles("admin")), conn=Depends(get_conn)):
    """New targets apply to incidents raised or re-prioritised from now on."""
    if body.resolution_minutes < body.response_minutes:
        raise api_error(422, "invalid_value", "Resolution time cannot be shorter than response time.")
    return fetch_one(
        conn,
        """update sla_policies set response_minutes = %(r)s, resolution_minutes = %(s)s, updated_at = now()
           where priority = %(p)s returning priority, response_minutes, resolution_minutes""",
        {"r": body.response_minutes, "s": body.resolution_minutes, "p": priority},
    )
