"""Maini ITSM API. Run: uvicorn app.main:app   Interactive test page: /docs"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import get_settings
from .errors import register_error_handlers
from .routers import (approvals, audit, auth_routes, changes, dashboard, incidents, problems, reference, releases,
                      reports, users)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    db.init_pool(settings.database_url, settings.db_pool_max)
    yield
    db.close_pool()


app = FastAPI(title="Maini ITSM API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,  # only the front-end addresses listed in CORS_ORIGINS
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
for module in (auth_routes, reference, users, incidents, problems, changes, releases, approvals, dashboard, reports,
               audit):
    app.include_router(module.router, prefix=API)


@app.get("/healthz", tags=["system"])
def healthz():
    """Used by Render to check the service is alive and the database answers."""
    try:
        with db.transaction() as conn:
            conn.execute("select 1")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "down", "database": "unreachable"})
    return {"status": "ok", "database": "up"}
