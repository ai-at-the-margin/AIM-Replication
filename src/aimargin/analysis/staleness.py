"""Implied information date (extension, not in the paper).

The paper attributes the offline momentum failure to dated information. We test
that directly: measure each model's offline Momentum-mandate books on 12-1 month
momentum computed at successively earlier dates (T, T-1m, ..., T-18m). The lag at
which the books look most 'momentum-like' is the model's *implied information
date*, which we set next to its stated knowledge cutoff. Searching models should
peak at lag 0.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

from .data import AnalysisData, present_models


def months_between(later: dt.date, earlier: dt.date) -> float:
    return (later - earlier).days / 30.44


def staleness_analysis(data: AnalysisData, cutoffs: dict[str, str] | None = None) -> dict[str, Any]:
    history = data.momentum_history
    if len(history) == 0 or len(data.holdings) == 0:
        return {"rows": [], "curves": []}
    asof = dt.date.fromisoformat(data.asof) if data.asof else None
    hist = history.pivot_table(index="issuer_id", columns="lag_months", values="mom_12_1_z")
    lags = sorted(hist.columns.tolist())
    holdings = data.holdings.dropna(subset=["issuer_id"])
    cells = [("MOMENTUM", "B", "offline"), ("MOMENTUM", "C", "connected")]
    curves = []
    rows = []
    for c in range(len(cells)):
        prompt, stage, label = cells[c]
        frame = holdings[(holdings["prompt_id"] == prompt) & (holdings["stage"] == stage)]
        if stage == "C":
            searched = set(data.valid[(data.valid["stage"] == "C") & (data.valid["search_count"].fillna(0) > 0)]["call_id"])
            frame = frame[frame["call_id"].isin(searched)]
            label = "connected (search invoked)"
        models = present_models(data, frame)
        for m in range(len(models)):
            sub = frame[frame["model_requested"] == models[m]]
            if sub["call_id"].nunique() < 2:
                continue
            values = []
            for k in range(len(lags)):
                exposure = sub["issuer_id"].map(hist[lags[k]])
                weights = sub["weight_norm"].where(exposure.notna())
                book = (exposure * weights).groupby(sub["call_id"]).sum() / weights.groupby(sub["call_id"]).sum()
                values.append(float(book.mean()) if book.notna().any() else None)
            clean = []
            for k in range(len(values)):
                clean.append(-np.inf if values[k] is None else values[k])
            best = int(np.argmax(clean))
            meta = data.model_meta(models[m])
            cutoff = (cutoffs or {}).get(models[m]) or meta.get("knowledge_cutoff")
            cutoff_lag = None
            if cutoff and asof:
                cutoff_date = dt.date.fromisoformat(str(cutoff)[:7] + "-15")
                cutoff_lag = round(months_between(asof, cutoff_date), 1)
            curves.append({"model": models[m], "cell": label, "lags": lags, "values": values})
            rows.append({"model": models[m], "cell": label, "provider": meta.get("provider"),
                         "implied_lag_months": int(lags[best]), "peak_value": values[best],
                         "value_at_t": values[0] if len(values) else None,
                         "stated_cutoff": cutoff, "stated_cutoff_lag_months": cutoff_lag,
                         "n_books": int(sub["call_id"].nunique())})
    measure_dates = {}
    if "measure_date" in history.columns:
        pairs = history.drop_duplicates(subset=["lag_months"])[["lag_months", "measure_date"]]
        lag_list = pairs["lag_months"].tolist()
        date_list = pairs["measure_date"].tolist()
        for i in range(len(lag_list)):
            measure_dates[int(lag_list[i])] = date_list[i]
    return {"rows": rows, "curves": curves, "measure_dates": measure_dates, "lags": lags}

