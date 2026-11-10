"""DuckDB wrapper: schema creation, idempotent upserts, parquet export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ..utils import get_logger, stable_hash, utc_now_iso
from .schemas import TABLES

log = get_logger(__name__)


class Store:
    """One DuckDB database per workspace (``processed/aim.duckdb``)."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.con = duckdb.connect(str(path))
        self._init_schema()

    # ------------------------------------------------------------------ schema
    def _init_schema(self) -> None:
        names = list(TABLES.keys())
        for i in range(len(names)):
            name = names[i]
            spec = TABLES[name]
            columns = spec["columns"]
            parts = []
            for j in range(len(columns)):
                parts.append(f'"{columns[j][0]}" {columns[j][1]}')
            pk = ", ".join(spec["pk"])
            ddl = f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(parts)}, PRIMARY KEY ({pk}))"
            self.con.execute(ddl)
            self._add_missing_columns(name, columns)

    def _add_missing_columns(self, name: str, columns: list) -> None:
        existing = self.con.execute(f"PRAGMA table_info('{name}')").fetchdf()
        have = set()
        names = existing["name"].tolist()
        for i in range(len(names)):
            have.add(names[i])
        for i in range(len(columns)):
            if columns[i][0] not in have:
                self.con.execute(f'ALTER TABLE {name} ADD COLUMN "{columns[i][0]}" {columns[i][1]}')

    # ------------------------------------------------------------------ writes
    def upsert(self, table: str, rows: list[dict[str, Any]] | pd.DataFrame) -> int:
        """Insert or replace rows keyed on the table's primary key. Returns row count."""
        spec = TABLES[table]
        frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        if frame is None or len(frame) == 0:
            return 0
        frame = frame.copy()
        columns = spec["columns"]
        for i in range(len(columns)):
            if columns[i][0] not in frame.columns:
                frame[columns[i][0]] = None
        frame = frame.drop_duplicates(subset=spec["pk"], keep="last")
        select_parts = []
        for i in range(len(columns)):
            select_parts.append(f'CAST("{columns[i][0]}" AS {columns[i][1]}) AS "{columns[i][0]}"')
        ordered = []
        for i in range(len(columns)):
            ordered.append(columns[i][0])
        frame = frame[ordered]
        frame = frame.astype(object).where(pd.notna(frame), None)
        self.con.register("_incoming", frame)
        try:
            # Migrations append columns, so physical order can differ from TABLES.
            self.con.execute(f"INSERT OR REPLACE INTO {table} BY NAME SELECT {', '.join(select_parts)} FROM _incoming")
        finally:
            self.con.unregister("_incoming")
        return len(frame)

    def replace_where(self, table: str, where: str, params: list[Any], rows: list[dict] | pd.DataFrame) -> int:
        """Delete rows matching ``where`` then insert ``rows`` (used for per-call child tables)."""
        self.con.execute(f"DELETE FROM {table} WHERE {where}", params)
        return self.upsert(table, rows)

    def delete_where(self, table: str, where: str, params: list[Any] | None = None) -> None:
        self.con.execute(f"DELETE FROM {table} WHERE {where}", params or [])

    def log_drop(self, stage: str, entity: str, reason: str, detail: str = "") -> None:
        """Record every dropped observation (BUILD_BRIEF §0.5: log every drop)."""
        row = {
            "log_id": stable_hash([stage, entity, reason, detail], 20),
            "stage": stage, "entity": entity, "reason": reason, "detail": detail[:2000],
            "logged_ts_utc": utc_now_iso(),
        }
        self.upsert("drop_log", [row])

    # ------------------------------------------------------------------- reads
    def query(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        return self.con.execute(sql, params or []).fetchdf()

    def table(self, name: str) -> pd.DataFrame:
        return self.query(f"SELECT * FROM {name}")

    def count(self, name: str) -> int:
        return int(self.con.execute(f"SELECT COUNT(*) FROM {name}").fetchall()[0][0])

    def export_parquet(self, folder: Path) -> list[Path]:
        folder.mkdir(parents=True, exist_ok=True)
        written = []
        names = list(TABLES.keys())
        for i in range(len(names)):
            target = folder / f"{names[i]}.parquet"
            self.con.execute(f"COPY {names[i]} TO '{target.as_posix()}' (FORMAT PARQUET)")
            written.append(target)
        return written

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:
            pass

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
