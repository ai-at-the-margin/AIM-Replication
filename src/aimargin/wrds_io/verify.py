"""WRDS probes for `aim verify` (BUILD_BRIEF §0.2, §11 Phase 0).

For every logical table: can we read it, which physical column serves each logical
field, and what is its effective latest date. Then pick a source per input
(primary -> fallback) and run the special checks (CRSP quarterly vintage, Snapshot
global coverage, Datastream MSCI lists, CIQ <-> gvkey link).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from ..utils import as_date, get_logger
from .connect import WrdsClient
from .freshness import Freshness, effective_latest_date

log = get_logger(__name__)


@dataclass
class TableProbe:
    key: str
    library: str
    table: str | None
    ok: bool = False
    columns: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    error: str | None = None
    freshness: Freshness | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok, "library": self.library, "table": self.table, "columns": self.columns,
            "missing": self.missing, "error": self.error,
        }
        if self.freshness is not None:
            out["effective_latest_date"] = str(self.freshness.effective_latest_date) if self.freshness.effective_latest_date else None
            out["raw_max_date"] = str(self.freshness.raw_max_date) if self.freshness.raw_max_date else None
            out["future_rows_discarded"] = self.freshness.future_rows
            out["freshness_detail"] = self.freshness.detail
        return out


def discover_table(client: WrdsClient, library: str, patterns: list[str]) -> str | None:
    tables = client.list_tables(library)
    for p in range(len(patterns)):
        regex = re.compile(patterns[p], re.I)
        for i in range(len(tables)):
            if regex.search(tables[i]):
                return tables[i]
    return None


def probe_table(client: WrdsClient, key: str, spec: dict[str, Any], today: dt.date,
                lookback_days: int = 75) -> TableProbe:
    library = str(spec.get("library"))
    table = spec.get("table")
    if table is None and spec.get("discover_patterns"):
        table = discover_table(client, library, list(spec["discover_patterns"]))
    if table is not None and "{year}" in str(table):
        table = str(table).replace("{year}", str(today.year))
    probe = TableProbe(key=key, library=library, table=table)
    if table is None:
        probe.error = "no matching table found"
        return probe
    columns = client.describe(library, str(table))
    if columns is None:
        probe.error = f"{library}.{table} not readable"
        return probe
    have = set(columns)
    fields = spec.get("fields") or {}
    optional = set(spec.get("optional") or [])
    names = list(fields.keys())
    for i in range(len(names)):
        candidates = fields[names[i]] or []
        chosen = None
        for j in range(len(candidates)):
            if str(candidates[j]).lower() in have:
                chosen = str(candidates[j]).lower()
                break
        if chosen is None:
            if names[i] not in optional:
                probe.missing.append(names[i])
        else:
            probe.columns[names[i]] = chosen
    probe.ok = len(probe.missing) == 0
    if not probe.ok:
        probe.error = f"missing required fields: {', '.join(probe.missing)}"
        return probe
    date_field = spec.get("date_field")
    if date_field and date_field in probe.columns:
        column = probe.columns[date_field]
        start = today - dt.timedelta(days=lookback_days)
        sql = (f"SELECT {column} AS date, COUNT(*) AS n FROM {library}.{table} "
               f"WHERE {column} >= '{start.isoformat()}' GROUP BY 1 ORDER BY 1")
        counts, error = client.try_sql(sql)
        if error is not None:
            probe.error = f"freshness query failed: {error}"
        elif counts is not None:
            probe.freshness = effective_latest_date(counts, today)
    return probe


def choose_sources(probes: dict[str, TableProbe], sources_cfg: dict[str, Any],
                   today: dt.date) -> list[dict[str, Any]]:
    """Primary -> fallback per input; returns one source_log row per input."""
    rows: list[dict[str, Any]] = []
    inputs = sources_cfg.get("inputs", {})
    names = list(inputs.keys())
    for i in range(len(names)):
        spec = inputs[names[i]]
        candidates = spec.get("candidates") or []
        chosen = None
        fallback_used = False
        notes: list[str] = []
        best_date = None
        for j in range(len(candidates)):
            probe = probes.get(candidates[j])
            if probe is None or not probe.ok:
                reason = "not probed" if probe is None else (probe.error or "failed")
                notes.append(f"{candidates[j]}: {reason}")
                continue
            latest = probe.freshness.effective_latest_date if probe.freshness else None
            if spec.get("prefer_most_current") and chosen is not None:
                if latest is not None and (best_date is None or latest > best_date):
                    chosen, best_date, fallback_used = candidates[j], latest, True
                    notes.append(f"{candidates[j]} is more current ({latest})")
                continue
            if chosen is None:
                chosen = candidates[j]
                best_date = latest
                fallback_used = j > 0
                if not spec.get("prefer_most_current"):
                    break
        status = "ok" if chosen is not None else ("HALT" if spec.get("required") else "unavailable")
        rows.append({
            "input": names[i], "source_used": chosen, "fallback_used": fallback_used,
            "effective_latest_date": str(best_date) if best_date else None, "required": bool(spec.get("required")),
            "status": status, "notes": "; ".join(notes),
        })
    return rows


def map_compustat_exchanges(client: WrdsClient, probe: TableProbe, exchanges_cfg: dict[str, Any]) -> dict[str, str]:
    """Compustat exchg code -> canonical exchange code, by description substrings."""
    out: dict[str, str] = {}
    entries = exchanges_cfg.get("exchanges", {})
    codes = list(entries.keys())
    for i in range(len(codes)):
        fixed = entries[codes[i]].get("comp_exchg") or []
        for j in range(len(fixed)):
            out[str(fixed[j])] = codes[i]
    if not probe.ok:
        return out
    frame, error = client.try_sql(
        f"SELECT {probe.columns['exchg']} AS exchg, {probe.columns['description']} AS description "
        f"FROM {probe.library}.{probe.table}")
    if frame is None:
        log.warning("r_ex_codes unreadable: %s", error)
        return out
    values = frame["exchg"].tolist()
    descriptions = frame["description"].tolist()
    for r in range(len(values)):
        text = str(descriptions[r] or "").lower()
        for i in range(len(codes)):
            patterns = entries[codes[i]].get("comp_desc") or []
            for j in range(len(patterns)):
                if str(patterns[j]).lower() in text and str(values[r]) not in out:
                    out[str(int(values[r]))] = codes[i]
    return out


def special_checks(client: WrdsClient, today: dt.date) -> dict[str, Any]:
    """CRSP quarterly vintage, Datastream MSCI lists, CIQ <-> gvkey link, RavenPack year table."""
    out: dict[str, Any] = {}
    for library in ("crsp", "crsp_q_stock"):
        frame, error = client.try_sql(f"SELECT MAX(dlycaldt) AS latest FROM {library}.dsf_v2 "
                                      f"WHERE dlycaldt >= '{(today - dt.timedelta(days=900)).isoformat()}'")
        out[f"{library}.dsf_v2_latest"] = (str(as_date(frame["latest"].iat[0])) if frame is not None and len(frame) > 0
                                           else f"error: {error}")
    frame, error = client.try_sql("SELECT COUNT(*) AS n FROM ciq_common.wrds_gvkey")
    out["ciq_gvkey_links"] = int(frame["n"].iat[0]) if frame is not None else f"error: {error}"
    msci = []
    tables = client.list_tables("tr_ds_equities")
    index_tables = []
    for i in range(len(tables)):
        if "index" in tables[i] or "const" in tables[i]:
            index_tables.append(tables[i])
    out["datastream_index_tables"] = index_tables
    for i in range(len(index_tables)):
        columns = client.describe("tr_ds_equities", index_tables[i]) or []
        name_cols = []
        for j in range(len(columns)):
            if "name" in columns[j] or "desc" in columns[j]:
                name_cols.append(columns[j])
        for j in range(len(name_cols)):
            frame, error = client.try_sql(
                f"SELECT * FROM tr_ds_equities.{index_tables[i]} WHERE UPPER({name_cols[j]}) LIKE '%MSCI AC WORLD%' "
                f"OR UPPER({name_cols[j]}) LIKE '%MSCI ACWI%' LIMIT 5")
            if frame is not None and len(frame) > 0:
                msci.append({"table": index_tables[i], "column": name_cols[j], "rows": frame.head(5).to_dict("records")})
    out["datastream_msci_acwi_lists"] = msci
    snapshot_tables = client.list_tables("comp_snapshot")
    global_like = []
    for i in range(len(snapshot_tables)):
        if re.search(r"(^csg|global|^g_|_g_)", snapshot_tables[i], re.I):
            global_like.append(snapshot_tables[i])
    out["snapshot_tables"] = len(snapshot_tables)
    out["snapshot_global_candidates"] = global_like
    return out
