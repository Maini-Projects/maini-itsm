"""Maini ITSM API. Run: uvicorn app.main:app   Interactive test page: /docs"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import get_settings
from .errors import register_error_handlers
from .routers import (approvals, attachments, audit, chat, auth_routes, changes, dashboard, defects, incidents, problems,
                      kb, projects, reference, releases, reports, search, users)


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


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Refuse a file upload that announces a body over 1 MB (plus form overhead) before it is read."""
    if request.method == "POST" and request.url.path.endswith("/attachments"):
        announced = request.headers.get("content-length", "")
        if announced.isdigit() and int(announced) > attachments.MAX_BYTES + 64 * 1024:
            return JSONResponse(status_code=413, content={"error": {
                "code": "file_too_large", "message": "That file is larger than 1 MB. Please choose a smaller file."}})
    return await call_next(request)

for module in (auth_routes, reference, users, incidents, problems, defects, changes, releases, approvals, dashboard,
               reports, audit, attachments, projects, search, kb, chat):
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
