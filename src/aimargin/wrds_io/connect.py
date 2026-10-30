"""WRDS connection, statement timeout and the parquet query cache (BUILD_BRIEF §2.1).

Credentials: ``WRDS_USERNAME`` (+ optional ``WRDS_PASSWORD``, written once to
~/.pgpass with mode 600) or an existing ~/.pgpass. Expect a Duo push the first
time a new machine connects.
"""

from __future__ import annotations

import os
import socket
import stat
from pathlib import Path
from typing import Any

import pandas as pd

from ..settings import Workspace
from ..utils import get_logger, read_json, utc_now_iso, write_json

log = get_logger(__name__)

WRDS_HOST = "wrds-pgdata.wharton.upenn.edu"
WRDS_PORT = 9737
WRDS_DB = "wrds"


def tcp_reachable(host: str = WRDS_HOST, port: int = WRDS_PORT, timeout: float = 6.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except OSError as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def ensure_pgpass(username: str, password: str) -> Path:
    """Add a WRDS line to ~/.pgpass if it is not already there (never prints the secret)."""
    path = Path.home() / ".pgpass"
    line = f"{WRDS_HOST}:{WRDS_PORT}:{WRDS_DB}:{username}:{password}"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    if f"{WRDS_HOST}:{WRDS_PORT}:{WRDS_DB}:{username}:" not in existing:
        with open(path, "a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(line + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


class WrdsClient:
    """Thin wrapper over ``wrds.Connection`` with timeouts and failure capture."""

    def __init__(self, statement_timeout_s: int = 900):
        self.statement_timeout_s = statement_timeout_s
        self.db: Any = None
        self.error: str | None = None
        self._describe_cache: dict[tuple[str, str], list[str] | None] = {}

    @property
    def connected(self) -> bool:
        return self.db is not None

    def connect(self) -> bool:
        if self.db is not None:
            return True
        username = os.environ.get("WRDS_USERNAME", "").strip()
        password = os.environ.get("WRDS_PASSWORD", "")
        has_pgpass = (Path.home() / ".pgpass").exists()
        if not username and not has_pgpass:
            self.error = "no credentials: set WRDS_USERNAME (and WRDS_PASSWORD) or create ~/.pgpass"
            return False
        reachable, detail = tcp_reachable()
        if not reachable:
            self.error = (f"cannot reach {WRDS_HOST}:{WRDS_PORT} ({detail}); the network may block "
                          "PostgreSQL traffic")
            return False
        try:
            import wrds  # noqa: PLC0415  (optional dependency)
        except ImportError:
            self.error = "the 'wrds' package is not installed: pip install -e '.[wrds]'"
            return False
        if username and password:
            ensure_pgpass(username, password)
        try:
            log.info("connecting to WRDS as %s (approve the Duo push if prompted) ...", username or "<pgpass>")
            if username:
                self.db = wrds.Connection(wrds_username=username)
            else:
                self.db = wrds.Connection()
        except Exception as exc:
            self.error = f"connection failed: {exc}"
            self.db = None
            return False
        self._set_timeout()
        return True

    def _set_timeout(self) -> None:
        try:
            from sqlalchemy import text

            self.db.connection.execute(text(f"SET statement_timeout = {int(self.statement_timeout_s * 1000)}"))
        except Exception as exc:
            log.warning("could not set statement_timeout: %s", exc)

    def sql(self, query: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        if not self.connect():
            raise RuntimeError(self.error or "WRDS not connected")
        if params:
            return self.db.raw_sql(query, params=params)
        return self.db.raw_sql(query)

    def try_sql(self, query: str) -> tuple[pd.DataFrame | None, str | None]:
        try:
            return self.sql(query), None
        except Exception as exc:
            return None, str(exc).strip().split("\n")[0][:300]

    def describe(self, library: str, table: str) -> list[str] | None:
        key = (library, table)
        if key in self._describe_cache:
            return self._describe_cache[key]
        columns: list[str] | None = None
        try:
            description = self.db.describe_table(library=library, table=table)
            if description is not None and "name" in description.columns:
                names = description["name"].tolist()
                columns = []
                for i in range(len(names)):
                    columns.append(str(names[i]).lower())
        except Exception:
            columns = None
        if columns is None or len(columns) == 0:
            probe, error = self.try_sql(f"SELECT * FROM {library}.{table} LIMIT 1")
            if probe is not None:
                columns = []
                names = probe.columns.tolist()
                for i in range(len(names)):
                    columns.append(str(names[i]).lower())
        self._describe_cache[key] = columns
        return columns

    def list_tables(self, library: str) -> list[str]:
        try:
            tables = self.db.list_tables(library=library)
        except Exception:
            return []
        out = []
        for i in range(len(tables or [])):
            out.append(str(tables[i]))
        return out

    def list_libraries(self) -> list[str]:
        try:
            values = self.db.list_libraries()
        except Exception:
            return []
        out = []
        for i in range(len(values or [])):
            out.append(str(values[i]))
        return sorted(out)

    def close(self) -> None:
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None


class QueryCache:
    """data/raw/wrds/<library>.<table>/<asof>[__tag].parquet + a JSON sidecar."""

    def __init__(self, ws: Workspace):
        self.root = ws.raw_wrds

    def path(self, library_table: str, asof: str, tag: str = "") -> Path:
        name = asof + (f"__{tag}" if tag else "")
        return self.root / library_table / f"{name}.parquet"

    def get(self, library_table: str, asof: str, tag: str = "") -> pd.DataFrame | None:
        path = self.path(library_table, asof, tag)
        if path.exists():
            try:
                return pd.read_parquet(path)
            except Exception as exc:
                log.warning("cache file %s unreadable (%s); re-pulling", path, exc)
        return None

    def put(self, library_table: str, asof: str, frame: pd.DataFrame, sql: str, tag: str = "",
            effective_latest_date: str | None = None) -> Path:
        path = self.path(library_table, asof, tag)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        write_json(path.with_suffix(".json"), {
            "sql": sql, "pulled_ts_utc": utc_now_iso(), "rows": int(len(frame)),
            "effective_latest_date": effective_latest_date,
        })
        return path

    def meta(self, library_table: str, asof: str, tag: str = "") -> dict[str, Any]:
        return read_json(self.path(library_table, asof, tag).with_suffix(".json"), default={}) or {}


def cached_sql(client: WrdsClient, cache: QueryCache, library_table: str, asof: str, sql: str,
               tag: str = "", effective_latest_date: str | None = None, refresh: bool = False) -> pd.DataFrame:
    if not refresh:
        hit = cache.get(library_table, asof, tag)
        if hit is not None:
            return hit
    frame = client.sql(sql)
    cache.put(library_table, asof, frame, sql, tag, effective_latest_date)
    return frame
