"""File storage in Supabase Storage (a private bucket). The API uses the service-role key, so the files are
never reachable except through the API, which checks who may see the record first.

FileStore is a dependency, so tests (or another storage provider later) can replace it.
"""
import httpx

from .config import get_settings
from .errors import api_error

_http: httpx.Client | None = None


def _client() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=30)
    return _http


class FileStore:
    def _url_and_headers(self, path: str) -> tuple[str, dict]:
        settings = get_settings()
        key = settings.supabase_service_role_key
        if not settings.supabase_url or not key:
            raise api_error(500, "storage_not_configured", "Supabase keys are not set on the server.")
        url = f"{settings.supabase_url}/storage/v1/object/{settings.attachments_bucket}/{path}"
        return url, {"Authorization": f"Bearer {key}", "apikey": key}

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        url, headers = self._url_and_headers(path)
        headers.update(kwargs.pop("headers", {}))
        try:
            return _client().request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise api_error(503, "storage_unavailable", "File storage could not be reached. Try again in a moment.")

    @staticmethod
    def _fail(resp: httpx.Response):
        if resp.status_code == 404 or "bucket not found" in resp.text.lower():
            raise api_error(502, "storage_bucket_missing",
                            "The file storage bucket was not found. Run migration 005_attachments.sql in Supabase.")
        raise api_error(502, "storage_error", "File storage rejected the request.")

    def put(self, path: str, data: bytes, content_type: str) -> None:
        resp = self._send("POST", path, content=data, headers={"Content-Type": content_type, "x-upsert": "false"})
        if resp.status_code >= 300:
            self._fail(resp)

    def get(self, path: str) -> bytes:
        resp = self._send("GET", path)
        if resp.status_code in (400, 404):
            raise api_error(404, "file_missing", "The file is no longer in storage.")
        if resp.status_code >= 300:
            self._fail(resp)
        return resp.content

    def delete(self, path: str) -> None:
        resp = self._send("DELETE", path)
        if resp.status_code >= 300 and resp.status_code not in (400, 404):  # already gone is fine
            self._fail(resp)


def get_file_store() -> FileStore:
    return FileStore()
