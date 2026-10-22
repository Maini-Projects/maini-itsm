"""Postgres access. One connection pool; each request uses one transaction."""
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init_pool(url: str, max_size: int = 5) -> None:
    global _pool
    _pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        # prepare_threshold=None: required for Supabase's transaction pooler (no prepared statements)
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
        open=True,
    )
    _pool.wait()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction() -> Iterator[Connection]:
    """Commits when the block ends normally, rolls back if it raises."""
    assert _pool is not None, "database pool is not initialised"
    with _pool.connection() as conn:
        yield conn


def get_conn() -> Iterator[Connection]:
    """FastAPI dependency: one transaction per request."""
    with transaction() as conn:
        yield conn
        if getattr(conn, "multi_views", False):
            from .tenant import drop_multi_views  # temporary views must not outlive the request
            drop_multi_views(conn)


def fetch_all(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    return conn.execute(sql, params or {}).fetchall()


def fetch_one(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> dict | None:
    return conn.execute(sql, params or {}).fetchone()
