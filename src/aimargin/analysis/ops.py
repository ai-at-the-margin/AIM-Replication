"""Collection operations and resolution quality (extension): what the pipeline did and what it cost."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..store.db import Store
from .data import AnalysisData, present_models


def ops_analysis(data: AnalysisData, store: Store, planned: dict[str, int]) -> dict[str, Any]:
    calls = data.calls
    rows = []
    models = present_models(data, calls)
    for m in range(len(models)):
        sub = calls[calls["model_requested"] == models[m]]
        for stage in ("A", "B", "C"):
            cell = sub[sub["stage"] == stage]
            if len(cell) == 0:
                continue
            latency = cell["latency_s"].dropna()
            valid_n = int((cell["outcome"] == "valid").sum())
            cost = float(cell["est_cost_usd"].fillna(0).sum())
            searches = cell["search_count"].dropna()
            fetches = cell["fetch_count"].dropna()
            rows.append({"model": models[m], "provider": data.model_meta(models[m]).get("provider"), "stage": stage,
                         "calls": int(len(cell)), "completed": int((cell["status"] == "completed").sum()),
                         "errors": int((cell["status"] == "error").sum()), "valid": valid_n,
                         "cost_usd": cost, "cost_per_valid": cost / valid_n if valid_n else None,
                         "input_tokens": int(cell["input_tokens"].fillna(0).sum()),
                         "output_tokens": int(cell["output_tokens"].fillna(0).sum()),
                         "reasoning_tokens": int(cell["reasoning_tokens"].fillna(0).sum()),
                         "searches": int(searches.sum()) if len(searches) else None,
                         "search_counts_observed": int(len(searches)),
                         "fetches": int(fetches.sum()) if len(fetches) else None,
                         "fetch_counts_observed": int(len(fetches)),
                         "retried_calls": int((cell["attempts"].fillna(1) > 1).sum()),
                         "latency_p50": float(latency.quantile(0.5)) if len(latency) else None,
                         "latency_p95": float(latency.quantile(0.95)) if len(latency) else None})
    by_stage = []
    for stage in ("A", "B", "C"):
        cell = calls[calls["stage"] == stage]
        by_stage.append({"stage": stage, "planned": int(planned.get(stage, 0)), "collected": int(len(cell)),
                         "completed": int((cell["status"] == "completed").sum()),
                         "valid": int((cell["outcome"] == "valid").sum()),
                         "cost_usd": float(cell["est_cost_usd"].fillna(0).sum())})
    holdings = store.query(
        "SELECT h.call_id, h.resolution_status, h.resolution_method, h.is_adr, h.is_us_listed, c.model_requested, c.provider "
        "FROM holdings h JOIN calls c USING (call_id)")
    holdings = holdings[holdings["call_id"].isin(calls["call_id"])]
    resolution = []
    groups = holdings.groupby("model_requested")
    keys = list(groups.groups.keys())
    for k in range(len(keys)):
        cell = groups.get_group(keys[k])
        methods = cell["resolution_method"].fillna("none").value_counts(normalize=True).to_dict()
        resolution.append({"model": keys[k], "holdings": int(len(cell)),
                           "resolved": float(cell["resolution_status"].isin(["resolved", "resolved_low_confidence"]).mean()),
                           "low_confidence": float((cell["resolution_status"] == "resolved_low_confidence").mean()),
                           "unresolved": float((cell["resolution_status"] == "unresolved").mean()),
                           "methods": methods})
    overall_methods = holdings["resolution_method"].fillna("none").value_counts().to_dict()
    total_holdings = len(holdings)
    resolved_share = float(holdings["resolution_status"].isin(["resolved", "resolved_low_confidence"]).mean()) if total_holdings else None
    return {"by_model_stage": rows, "by_stage": by_stage, "resolution_by_model": resolution,
            "resolution_methods": overall_methods, "resolution_rate": resolved_share,
            "total_cost_usd": float(np.nansum(calls["est_cost_usd"].to_numpy(dtype=float))) if len(calls) else 0.0,
            "outcomes": calls["outcome"].value_counts().to_dict()}


def drops(store: Store, limit: int = 200) -> list[dict[str, Any]]:
    frame = store.query("SELECT stage, reason, COUNT(*) AS n FROM drop_log GROUP BY 1, 2 ORDER BY 3 DESC")
    return frame.head(limit).to_dict("records") if isinstance(frame, pd.DataFrame) else []
