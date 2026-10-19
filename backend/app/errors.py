"""One error format for every failure: {"error": {"code": "...", "message": "..."}}.

Business-rule violations raised by the database (see the schema) become clear HTTP errors.
"""
import logging

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import errors as pgerr
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("itsm")

# Rule name (the text before ':' in the database message) -> HTTP status
RULE_STATUS = {
    "forbidden": 403,
    "self_approval": 403,
    "invalid_transition": 409,
    "approval_required": 409,
    "approval_not_needed": 409,
    "assignee_required": 422,
    "resolution_notes_required": 422,
    "decider_required": 422,
}


def api_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _envelope(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return _envelope(exc.status_code, exc.detail["code"], exc.detail["message"])
        return _envelope(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "problem": e["msg"]}
            for e in exc.errors()
        ]
        return _envelope(422, "validation_error", "The request is not valid.", fields=fields)

    @app.exception_handler(psycopg.Error)
    async def database_error(_: Request, exc: psycopg.Error):
        message = (exc.diag.message_primary if exc.diag else None) or str(exc)
        if isinstance(exc, pgerr.RaiseException):
            code, _, rest = message.partition(":")
            code = code.strip()
            return _envelope(RULE_STATUS.get(code, 400), code, (rest or message).strip())
        if isinstance(exc, pgerr.UniqueViolation):
            return _envelope(409, "duplicate", "That record already exists or conflicts with an existing one.")
        if isinstance(exc, pgerr.ForeignKeyViolation):
            return _envelope(422, "invalid_reference", "A referenced record does not exist.")
        if isinstance(exc, (pgerr.CheckViolation, pgerr.NotNullViolation, pgerr.InvalidTextRepresentation)):
            return _envelope(422, "invalid_value", "A value is missing or not allowed.")
        log.exception("database error")
        return _envelope(500, "database_error", "The database could not complete the request.")
