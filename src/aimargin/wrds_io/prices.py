"""Daily prices from comp.secd / comp.g_secd (BUILD_BRIEF §2.2, §2.4 rules 1, 4)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .schema import TableMap

PRICE_FIELDS = ["gvkey", "iid", "date", "price", "adj", "trfd", "shares", "currency", "exchg", "tpci"]


def _in_list(values: list[str]) -> str:
    parts = []
    for i in range(len(values)):
        parts.append("'" + str(values[i]).replace("'", "") + "'")
    return ", ".join(parts)


def snapshot_sql(m: TableMap, date: dt.date) -> str:
    return (f"SELECT {m.select(PRICE_FIELDS)} FROM {m.fq} "
            f"WHERE {m.c('date')} = '{date.isoformat()}' AND {m.c('price')} IS NOT NULL")


def history_sql(m: TableMap, gvkeys: list[str], start: dt.date, end: dt.date) -> str:
    return (f"SELECT {m.select(PRICE_FIELDS)} FROM {m.fq} "
            f"WHERE {m.c('gvkey')} IN ({_in_list(gvkeys)}) "
            f"AND {m.c('date')} BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'")


def standardise(frame: pd.DataFrame, region: str) -> pd.DataFrame:
    """Typed columns; every PRICE_FIELD exists (missing ones are NaN)."""
    out = frame.copy()
    for i in range(len(PRICE_FIELDS)):
        if PRICE_FIELDS[i] not in out.columns:
            out[PRICE_FIELDS[i]] = None
    out["gvkey"] = out["gvkey"].astype(str).str.zfill(6)
    out["iid"] = out["iid"].astype(str)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in ("price", "adj", "trfd", "shares"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["exchg"] = pd.to_numeric(out["exchg"], errors="coerce").astype("Int64").astype(str)
    out["tpci"] = out["tpci"].astype(str)
    out["currency"] = out["currency"].astype(str)
    out["region"] = region
    return out[PRICE_FIELDS + ["region"]]


def drop_future(frame: pd.DataFrame, today: dt.date) -> tuple[pd.DataFrame, int]:
    """Discard rows dated after today (the bogus 2027/2028 rows) and report how many."""
    mask = frame["date"] > pd.Timestamp(today)
    return frame[~mask].copy(), int(mask.sum())


def dedupe(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """One row per (gvkey, iid, date), preferring rows with non-null price and trfd."""
    if len(frame) == 0:
        return frame, 0
    work = frame.copy()
    work["_quality"] = work["price"].notna().astype(int) * 2 + work["trfd"].notna().astype(int)
    work = work.sort_values(["gvkey", "iid", "date", "_quality"])
    before = len(work)
    work = work.drop_duplicates(subset=["gvkey", "iid", "date"], keep="last").drop(columns=["_quality"])
    return work.reset_index(drop=True), before - len(work)
