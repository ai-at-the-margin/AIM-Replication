"""RavenPack news counts over the 30 days before the as-of date (BUILD_BRIEF §8.12)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from ..utils import get_logger
from .connect import WrdsClient
from .prices import _in_list

log = get_logger(__name__)


def news_counts(client: WrdsClient, isins: list[str], asof: dt.date, min_relevance: int = 75) -> pd.DataFrame:
    """isin -> number of relevant news items in [T-30, T]. Empty frame if unavailable."""
    columns = ["isin", "news_count_30d"]
    if len(isins) == 0:
        return pd.DataFrame(columns=columns)
    start = asof - dt.timedelta(days=30)
    years = sorted({start.year, asof.year})
    mapping, error = client.try_sql(
        "SELECT rp_entity_id, data_value AS isin FROM ravenpack_common.rp_entity_mapping "
        f"WHERE data_type = 'ISIN' AND data_value IN ({_in_list(isins)})")
    if mapping is None or len(mapping) == 0:
        log.warning("RavenPack entity mapping unavailable: %s", error)
        return pd.DataFrame(columns=columns)
    entity_ids = mapping["rp_entity_id"].astype(str).unique().tolist()
    pieces = []
    for i in range(len(years)):
        table = f"rpa_djpr_equities_{years[i]}"
        counts, error = client.try_sql(
            f"SELECT rp_entity_id, COUNT(*) AS n FROM ravenpack_dj.{table} "
            f"WHERE timestamp_utc BETWEEN '{start}' AND '{asof} 23:59:59' AND relevance >= {min_relevance} "
            f"AND rp_entity_id IN ({_in_list(entity_ids)}) GROUP BY rp_entity_id")
        if counts is not None:
            pieces.append(counts)
        else:
            log.warning("RavenPack %s unavailable: %s", table, error)
    if len(pieces) == 0:
        return pd.DataFrame(columns=columns)
    total = pd.concat(pieces).groupby("rp_entity_id", as_index=False)["n"].sum()
    merged = mapping.merge(total, on="rp_entity_id", how="left").fillna({"n": 0})
    out = merged.groupby("isin", as_index=False)["n"].sum().rename(columns={"n": "news_count_30d"})
    return out[columns]
