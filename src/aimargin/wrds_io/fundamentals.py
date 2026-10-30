"""Restated Compustat fundamentals (fallback for Snapshot), entered on rdq or datadate + lag."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .prices import _in_list
from .schema import TableMap

ANNUAL_ITEMS = ["ceq", "seq", "ib", "at", "revt", "cogs", "dltt", "dlc", "oancf"]
STANDARD_FILTERS = {
    "na": {"indfmt": "INDL", "datafmt": "STD", "popsrc": "D", "consol": "C"},
    "global": {"indfmt": "INDL", "datafmt": "HIST_STD", "popsrc": "I", "consol": "C"},
}


def _filters(m: TableMap, region: str) -> str:
    parts = []
    wanted = STANDARD_FILTERS[region]
    keys = list(wanted.keys())
    for i in range(len(keys)):
        if m.has(keys[i]):
            parts.append(f"{m.c(keys[i])} = '{wanted[keys[i]]}'")
    return (" AND " + " AND ".join(parts)) if parts else ""


def annual_sql(m: TableMap, gvkeys: list[str], start: dt.date, end: dt.date, region: str) -> str:
    fields = ["gvkey", "datadate", "fyear", "currency"] + ANNUAL_ITEMS
    return (f"SELECT {m.select(fields)} FROM {m.fq} WHERE {m.c('gvkey')} IN ({_in_list(gvkeys)}) "
            f"AND {m.c('datadate')} BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'{_filters(m, region)}")


def quarterly_book_sql(m: TableMap, gvkeys: list[str], start: dt.date, end: dt.date, region: str) -> str:
    fields = ["gvkey", "datadate", "rdq", "currency", "ceq"]
    return (f"SELECT {m.select(fields)} FROM {m.fq} WHERE {m.c('gvkey')} IN ({_in_list(gvkeys)}) "
            f"AND {m.c('datadate')} BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'{_filters(m, region)}")


def standardise_annual(frame: pd.DataFrame, lag_days: int, source: str) -> pd.DataFrame:
    out = frame.copy()
    columns = ["gvkey", "datadate", "currency"] + ANNUAL_ITEMS
    for i in range(len(columns)):
        if columns[i] not in out.columns:
            out[columns[i]] = None
    out["gvkey"] = out["gvkey"].astype(str).str.zfill(6)
    out["datadate"] = pd.to_datetime(out["datadate"], errors="coerce")
    for i in range(len(ANNUAL_ITEMS)):
        out[ANNUAL_ITEMS[i]] = pd.to_numeric(out[ANNUAL_ITEMS[i]], errors="coerce")
    out["ceq"] = out["ceq"].fillna(out["seq"])
    if "available_date" not in out.columns or out["available_date"].isna().all():
        out["available_date"] = out["datadate"] + pd.Timedelta(days=lag_days)
    out["available_date"] = pd.to_datetime(out["available_date"], errors="coerce")
    out["source"] = source
    return out[["gvkey", "datadate", "available_date", "currency"] + ANNUAL_ITEMS + ["source"]]


def standardise_book(frame: pd.DataFrame, lag_days: int, source: str) -> pd.DataFrame:
    out = frame.copy()
    for column in ("gvkey", "datadate", "currency", "ceq", "rdq"):
        if column not in out.columns:
            out[column] = None
    out["gvkey"] = out["gvkey"].astype(str).str.zfill(6)
    out["datadate"] = pd.to_datetime(out["datadate"], errors="coerce")
    out["ceq"] = pd.to_numeric(out["ceq"], errors="coerce")
    rdq = pd.to_datetime(out["rdq"], errors="coerce")
    if "available_date" in out.columns and out["available_date"].notna().any():
        out["available_date"] = pd.to_datetime(out["available_date"], errors="coerce")
    else:
        out["available_date"] = rdq.fillna(out["datadate"] + pd.Timedelta(days=lag_days))
    out["source"] = source
    return out[["gvkey", "datadate", "available_date", "currency", "ceq", "source"]]


def as_known_at(frame: pd.DataFrame, asof: dt.date) -> pd.DataFrame:
    """Rows available on or before the as-of date."""
    if frame is None or len(frame) == 0:
        return frame
    return frame[frame["available_date"] <= pd.Timestamp(asof)].copy()
