"""Attention and familiarity (BUILD_BRIEF §8.12, extension).

Each pick's analyst count and 30-day news count, as a percentile within its
market-cap decile of the estimation universe. 50 = typical for its size;
higher = more heavily covered than similar-sized stocks.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .data import AnalysisData


def cap_matched_percentiles(exposures: pd.DataFrame, column: str) -> pd.Series:
    universe = exposures[exposures["in_estimation_universe"] == True].dropna(subset=["mcap_usd"])  # noqa: E712
    if len(universe) < 20 or universe[column].notna().sum() < 20:
        return pd.Series(dtype=float)
    edges = np.quantile(universe["mcap_usd"], np.linspace(0, 1, 11))
    edges[0] = -np.inf
    edges[-1] = np.inf
    out = {}
    issuers = exposures["issuer_id"].tolist()
    caps = exposures["mcap_usd"].to_numpy(dtype=float)
    values = exposures[column].to_numpy(dtype=float)
    uni_caps = universe["mcap_usd"].to_numpy(dtype=float)
    uni_values = universe[column].to_numpy(dtype=float)
    for i in range(len(issuers)):
        if not np.isfinite(caps[i]) or not np.isfinite(values[i]):
            continue
        bucket = int(np.searchsorted(edges, caps[i], side="right") - 1)
        bucket = min(max(bucket, 0), 9)
        mask = (uni_caps > edges[bucket]) & (uni_caps <= edges[bucket + 1]) & np.isfinite(uni_values)
        peers = uni_values[mask]
        if len(peers) < 5:
            continue
        out[issuers[i]] = float((peers < values[i]).mean() * 100 + (peers == values[i]).mean() * 50)
    return pd.Series(out)


def attention_analysis(data: AnalysisData) -> dict[str, Any]:
    if len(data.exposures) == 0:
        return {"rows": []}
    analyst = cap_matched_percentiles(data.exposures, "analyst_count")
    news = cap_matched_percentiles(data.exposures, "news_count_30d")
    picks = data.holdings.dropna(subset=["issuer_id"]).copy()
    picks["analyst_pct"] = picks["issuer_id"].map(analyst)
    picks["news_pct"] = picks["issuer_id"].map(news)
    calls = data.valid[["call_id", "search_invoked"]]
    picks = picks.merge(calls, on="call_id", how="left")
    picks["search_state"] = np.where(picks["stage"] != "C", "offline",
                                     np.where(picks["search_invoked"].isna(), "connected_search_unknown",
                                              np.where(picks["search_invoked"].fillna(False), "connected_invoked",
                                                       "connected_not_invoked")))
    rows = []
    groups = picks.groupby(["prompt_id", "search_state"])
    keys = list(groups.groups.keys())
    for i in range(len(keys)):
        cell = groups.get_group(keys[i])
        rows.append({"prompt_id": keys[i][0], "search_state": keys[i][1], "n_picks": int(len(cell)),
                     "analyst_percentile": float(cell["analyst_pct"].mean()) if cell["analyst_pct"].notna().any() else None,
                     "news_percentile": float(cell["news_pct"].mean()) if cell["news_pct"].notna().any() else None})
    by_model = []
    groups = picks.groupby("model_requested")
    keys = list(groups.groups.keys())
    for i in range(len(keys)):
        cell = groups.get_group(keys[i])
        by_model.append({"model": keys[i], "analyst_percentile": float(cell["analyst_pct"].mean()),
                         "news_percentile": float(cell["news_pct"].mean())})
    return {"rows": rows, "by_model": by_model, "note": "50 = typical coverage for the stock's market-cap decile"}
