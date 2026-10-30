"""How models size positions (extension).

Share of books with usable weights, concentration (HHI, effective N), the largest
position, the share of round-number weights (multiples of 5%), and the rank
correlation between weight and market cap (do models cap-weight in disguise?).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .data import AnalysisData, present_models


def weighting_analysis(data: AnalysisData) -> dict[str, Any]:
    holdings = data.holdings[data.holdings["language"] == "en"]
    caps = data.exposures.set_index("issuer_id")["mcap_usd"] if len(data.exposures) else pd.Series(dtype=float)
    valid = data.valid.set_index("call_id")
    rows = []
    models = present_models(data, holdings)
    for m in range(len(models)):
        sub = holdings[holdings["model_requested"] == models[m]]
        books = sub.groupby("call_id")
        keys = list(books.groups.keys())
        hhis = []
        maxes = []
        rounds = []
        rhos = []
        provided = 0
        for k in range(len(keys)):
            book = books.get_group(keys[k])
            w = book["weight_norm"].fillna(0).to_numpy(dtype=float)
            if w.sum() <= 0:
                continue
            w = w / w.sum()
            hhis.append(float((w ** 2).sum()))
            maxes.append(float(w.max()))
            raw = book["raw_weight"].to_numpy(dtype=float)
            if bool(valid.at[keys[k], "weights_provided"]) if keys[k] in valid.index else False:
                provided += 1
                finite = raw[np.isfinite(raw)]
                if len(finite) > 0:
                    rounds.append(float((np.abs(finite / 5.0 - np.round(finite / 5.0)) < 1e-6).mean()))
                cap_values = book["issuer_id"].map(caps).to_numpy(dtype=float)
                ok = np.isfinite(cap_values) & np.isfinite(raw)
                if ok.sum() >= 5 and np.std(raw[ok]) > 0:
                    rhos.append(float(stats.spearmanr(raw[ok], np.log(cap_values[ok])).statistic))
        n_books = len(keys)
        rows.append({"model": models[m], "provider": data.model_meta(models[m]).get("provider"), "n_books": n_books,
                     "share_weights_provided": provided / n_books if n_books else None,
                     "mean_hhi": float(np.mean(hhis)) if hhis else None,
                     "effective_n": float(np.mean(1.0 / np.array(hhis))) if hhis else None,
                     "mean_max_weight": float(np.mean(maxes)) if maxes else None,
                     "share_round_weights": float(np.mean(rounds)) if rounds else None,
                     "weight_cap_spearman": float(np.nanmean(rhos)) if rhos else None})
    return {"rows": rows}
