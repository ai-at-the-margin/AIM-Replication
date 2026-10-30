"""Datastream (tr_ds_equities): total-return index cross-check and MSCI ACWI lists.

Both uses are optional. Every function returns an empty frame on failure so the
pipeline continues on Compustat alone (the outcome is recorded in source_log).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from ..utils import get_logger
from .connect import WrdsClient
from .prices import _in_list

log = get_logger(__name__)


def isin_to_infocode(client: WrdsClient, isins: list[str]) -> pd.DataFrame:
    """Map ISINs to Datastream infocodes via ds2ctryqtinfo / ds2scdqtinfo (whichever exists)."""
    if len(isins) == 0:
        return pd.DataFrame(columns=["isin", "infocode"])
    candidates = [("ds2ctryqtinfo", "isin"), ("ds2scdqtinfo", "isin"), ("ds2isin", "isin")]
    for i in range(len(candidates)):
        table, column = candidates[i]
        columns = client.describe("tr_ds_equities", table)
        if columns is None or column not in columns or "infocode" not in columns:
            continue
        frame, error = client.try_sql(
            f"SELECT {column} AS isin, infocode FROM tr_ds_equities.{table} WHERE {column} IN ({_in_list(isins)})")
        if frame is not None:
            return frame.drop_duplicates(subset=["isin"])
    return pd.DataFrame(columns=["isin", "infocode"])


def total_return_index(client: WrdsClient, infocodes: list[str], start: dt.date, end: dt.date,
                       table: str = "ds2primqtri", date_col: str = "marketdate") -> pd.DataFrame:
    if len(infocodes) == 0:
        return pd.DataFrame(columns=["infocode", "date", "ri"])
    frame, error = client.try_sql(
        f"SELECT infocode, {date_col} AS date, ri FROM tr_ds_equities.{table} "
        f"WHERE infocode IN ({_in_list(infocodes)}) AND {date_col} BETWEEN '{start}' AND '{end}'")
    if frame is None:
        log.warning("Datastream RI unavailable: %s", error)
        return pd.DataFrame(columns=["infocode", "date", "ri"])
    return frame


def momentum_12_1_from_ri(ri: pd.DataFrame, asof: dt.date) -> pd.DataFrame:
    """Simple 12-1 momentum from a total-return index (for the global spot check, §7.3)."""
    if ri is None or len(ri) == 0:
        return pd.DataFrame(columns=["infocode", "mom_12_1_ds"])
    work = ri.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["ri"] = pd.to_numeric(work["ri"], errors="coerce")
    stamp = pd.Timestamp(asof)
    end = stamp - pd.Timedelta(days=30)
    start = stamp - pd.Timedelta(days=365)
    rows = []
    groups = work.dropna().groupby("infocode")
    keys = list(groups.groups.keys())
    for i in range(len(keys)):
        g = groups.get_group(keys[i]).sort_values("date")
        a = g[g["date"] <= start]
        b = g[g["date"] <= end]
        if len(a) == 0 or len(b) == 0 or a["ri"].iat[-1] <= 0:
            continue
        rows.append({"infocode": keys[i], "mom_12_1_ds": b["ri"].iat[-1] / a["ri"].iat[-1] - 1.0})
    return pd.DataFrame(rows, columns=["infocode", "mom_12_1_ds"])
