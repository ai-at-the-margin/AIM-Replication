"""Mandate responses (BUILD_BRIEF §8.4, Figure 4).

Δ_{m,s} = mean target-factor loading under mandate s minus the same model's
UNCONSTRAINED mean, with bootstrap CIs and a permutation p-value.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .bootstrap import diff_ci, permutation_p
from .data import ALL_FACTOR_COLS, MANDATE_TARGET, MANDATES, AnalysisData, present_models
from .overlap import issuer_sets, jaccard


def heatmap(frame: pd.DataFrame, models: list[str] | None = None) -> dict[str, Any]:
    sub = frame if models is None else frame[frame["model_requested"].isin(models)]
    rows = []
    for m in range(len(MANDATES)):
        cell = sub[sub["prompt_id"] == MANDATES[m]]
        row: dict[str, Any] = {"mandate": MANDATES[m], "n": int(len(cell))}
        for f in range(len(ALL_FACTOR_COLS)):
            if ALL_FACTOR_COLS[f] in cell.columns and len(cell) > 0:
                model_means = cell.groupby("model_requested")[ALL_FACTOR_COLS[f]].mean()
                row[ALL_FACTOR_COLS[f]] = float(model_means.mean()) if len(model_means) else None
        rows.append(row)
    return {"rows": rows, "targets": MANDATE_TARGET}


def deltas(data: AnalysisData, frame: pd.DataFrame, draws: int, rng: np.random.Generator,
           perm_draws: int = 2000) -> list[dict[str, Any]]:
    rows = []
    models = present_models(data, frame)
    for m in range(len(models)):
        sub = frame[frame["model_requested"] == models[m]]
        base = sub[sub["prompt_id"] == "UNCONSTRAINED"]
        for s in range(len(MANDATES)):
            mandate = MANDATES[s]
            target = MANDATE_TARGET.get(mandate)
            if target is None:
                continue
            cell = sub[sub["prompt_id"] == mandate]
            a = cell[target].to_numpy(dtype=float)
            b = base[target].to_numpy(dtype=float)
            ci = diff_ci(a, b, draws, rng)
            rows.append({"model": models[m], "provider": data.model_meta(models[m]).get("provider"),
                         "mandate": mandate, "target": target,
                         "mandate_mean": float(np.nanmean(a)) if len(a) else None,
                         "unconstrained_mean": float(np.nanmean(b)) if len(b) else None,
                         "delta": ci["diff"], "lo": ci["lo"], "hi": ci["hi"],
                         "p_perm": permutation_p(a, b, min(perm_draws, 2000), rng), "n_mandate": ci["n_a"],
                         "n_unconstrained": ci["n_b"]})
    return rows


def mandate_overlap(data: AnalysisData, frame_valid: pd.DataFrame) -> list[dict[str, Any]]:
    """Mean Jaccard between books of different mandates, within each model."""
    sets = issuer_sets(data.holdings)
    rows = []
    for a in range(len(MANDATES)):
        for b in range(len(MANDATES)):
            values = []
            models = present_models(data, frame_valid)
            for m in range(len(models)):
                left = frame_valid[(frame_valid["model_requested"] == models[m]) & (frame_valid["prompt_id"] == MANDATES[a])]["call_id"].tolist()
                right = frame_valid[(frame_valid["model_requested"] == models[m]) & (frame_valid["prompt_id"] == MANDATES[b])]["call_id"].tolist()
                for i in range(len(left)):
                    for j in range(len(right)):
                        if a == b and j <= i:
                            continue
                        values.append(jaccard(sets.get(left[i], set()), sets.get(right[j], set())))
            rows.append({"mandate_a": MANDATES[a], "mandate_b": MANDATES[b],
                         "jaccard": float(np.mean(values)) if len(values) else None})
    return rows


def mandate_analysis(data: AnalysisData, draws: int, rng: np.random.Generator) -> dict[str, Any]:
    offline = data.pexp[(data.pexp["stage"] == "B")]
    return {
        "heatmap_all": heatmap(offline),
        "heatmap_flagships": heatmap(offline, data.flagships()),
        "deltas": deltas(data, offline, draws, rng),
        "book_overlap": mandate_overlap(data, data.valid[data.valid["stage"] == "B"]),
    }
