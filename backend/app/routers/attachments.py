"""File attachments (images and documents, up to 1 MB each) on incidents, problems, defects, changes and releases.

The files live in a private Supabase Storage bucket; this module decides who may add, see and remove them:
  see / download - anyone who can see the record
  add            - incidents, problems, defects: anyone who can see the record (a customer on their own).
                   changes, releases: only whoever may work on that record (read-only people cannot add)
  remove         - the person who added it, whoever works the record, or an Administrator
Files are served as downloads (never opened inside the page) so an uploaded file can never run as a web page.
"""
import re
from typing import Callable, Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Response, UploadFile

from ..db import fetch_all, fetch_one, get_conn
from ..errors import api_error
from ..rbac import Principal, can_manage, current_user
from ..storage import FileStore, get_file_store
from . import changes, defects, incidents, problems, releases

router = APIRouter(tags=["attachments"])

MAX_BYTES = 1024 * 1024  # 1 MB

# extension -> (content type, signature the file must start with, or None for plain text / Office files)
ALLOWED = {
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    "jpg": ("image/jpeg", b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    "gif": ("image/gif", b"GIF8"),
    "webp": ("image/webp", b"RIFF"),
    "pdf": ("application/pdf", b"%PDF"),
    "txt": ("text/plain", None),
    "log": ("text/plain", None),
    "csv": ("text/csv", None),
    "doc": ("application/msword", None),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK"),
    "xls": ("application/vnd.ms-excel", None),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
    "ppt": ("application/vnd.ms-powerpoint", None),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", b"PK"),
}

Kind = Literal["incidents", "problems", "defects", "changes", "releases"]
# url name -> (record_type stored, loader that returns the record if this user may see it, needs manage rights to add)
KINDS: dict[str, tuple[str, Callable, bool]] = {
    "incidents": ("incident", incidents.load, False),
    "problems": ("problem", problems.load, False),
    "defects": ("defect", defects.load, False),
    "changes": ("change", changes.load, True),
    "releases": ("release", releases.load, True),
}
LOADERS = {rtype: loader for rtype, loader, _ in KINDS.values()}


def clean_name(raw: str | None) -> str:
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:150]


def _public(row: dict, user: Principal, record: dict) -> dict:
    return {
        "id": row["id"], "file_name": row["file_name"], "content_type": row["content_type"],
        "size_bytes": row["size_bytes"], "uploaded_by": row["uploaded_by"],
        "uploaded_by_name": row["uploaded_by_name"], "created_at": row["created_at"],
        "can_delete": row["uploaded_by"] == user.id or user.role == "admin" or can_manage(user, record),
    }


SELECT = """select a.id, a.record_type, a.record_id, a.file_name, a.content_type, a.size_bytes, a.storage_path,
                   a.uploaded_by, p.full_name as uploaded_by_name, a.created_at
              from attachments a join profiles p on p.id = a.uploaded_by"""


def _may_add(kind: str, user: Principal, record: dict) -> bool:
    needs_manage = KINDS[kind][2]
    return record["status"] != "Closed" and (not needs_manage or can_manage(user, record))


@router.get("/{kind}/{record_id}/attachments")
def list_attachments(kind: Kind, record_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn)):
    rtype, loader, _ = KINDS[kind]
    record = loader(conn, user, record_id)  # 404 unless this user may see the record
    rows = fetch_all(conn, SELECT + " where a.record_type = %(t)s and a.record_id = %(id)s "
                                    "order by a.created_at desc, a.id", {"t": rtype, "id": record_id})
    return {"items": [_public(r, user, record) for r in rows], "can_upload": _may_add(kind, user, record),
            "max_bytes": MAX_BYTES, "allowed_extensions": sorted(ALLOWED)}


@router.post("/{kind}/{record_id}/attachments", status_code=201)
def upload_attachment(kind: Kind, record_id: UUID, file: UploadFile = File(...),
                      user: Principal = Depends(current_user), conn=Depends(get_conn),
                      store: FileStore = Depends(get_file_store)):
    rtype, loader, needs_manage = KINDS[kind]
    record = loader(conn, user, record_id)
    if record["status"] == "Closed":
        raise api_error(409, "record_closed", "Files cannot be added to a closed record.")
    if needs_manage and not can_manage(user, record):
        raise api_error(403, "forbidden", "You can view the files on this record but not add new ones.")

    name = clean_name(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise api_error(415, "file_type_not_allowed",
                        "That file type is not allowed. You can attach images (png, jpg, gif, webp) and documents "
                        "(pdf, txt, csv, log, doc, docx, xls, xlsx, ppt, pptx).")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise api_error(413, "file_too_large", "That file is larger than 1 MB. Please choose a smaller file.")
    if not data:
        raise api_error(422, "empty_file", "That file is empty.")
    content_type, signature = ALLOWED[ext]
    if signature and not data.startswith(signature):
        raise api_error(415, "file_type_mismatch", f"That file does not look like a real .{ext} file.")

    attachment_id = uuid4()
    path = f"{rtype}/{record_id}/{attachment_id}.{ext}"  # never built from the uploaded name
    conn.execute(
        """insert into attachments(id, record_type, record_id, file_name, content_type, size_bytes, storage_path, uploaded_by)
           values (%(id)s, %(t)s, %(rid)s, %(name)s, %(ct)s, %(size)s, %(path)s, %(uid)s)""",
        {"id": attachment_id, "t": rtype, "rid": record_id, "name": name, "ct": content_type, "size": len(data),
         "path": path, "uid": user.id},
    )
    store.put(path, data, content_type)  # if storage fails the row above is rolled back
    row = fetch_one(conn, SELECT + " where a.id = %(id)s", {"id": attachment_id})
    return _public(row, user, record)


def _find(conn, user: Principal, attachment_id: UUID) -> tuple[dict, dict]:
    """The attachment and its record, if this user may see the record; otherwise 404."""
    row = fetch_one(conn, SELECT + " where a.id = %(id)s", {"id": attachment_id})
    if row is None:
        raise api_error(404, "not_found", "Attachment not found.")
    record = LOADERS[row["record_type"]](conn, user, row["record_id"])
    return row, record


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn),
                        store: FileStore = Depends(get_file_store)):
    row, _ = _find(conn, user, attachment_id)
    data = store.get(row["storage_path"])
    ascii_name = re.sub(r'[^A-Za-z0-9._-]', "_", row["file_name"])
    return Response(
        content=data, media_type=row["content_type"],
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(row['file_name'])}",
                 "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: UUID, user: Principal = Depends(current_user), conn=Depends(get_conn),
                      store: FileStore = Depends(get_file_store)):
    row, record = _find(conn, user, attachment_id)
    if not _public(row, user, record)["can_delete"]:
        raise api_error(403, "forbidden", "You can only remove files you added, or files on records you work on.")
    conn.execute("delete from attachments where id = %(id)s", {"id": attachment_id})
    store.delete(row["storage_path"])  # if storage fails the row delete is rolled back
    return Response(status_code=204)
