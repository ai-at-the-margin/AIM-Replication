"""Factor profiles (BUILD_BRIEF §8.3, Figures 2-3)."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .bootstrap import mean_ci
from .data import ALL_FACTOR_COLS, FACTOR_COLS, AnalysisData, present_models

SECTOR_NAMES = {
    "10": "Energy", "15": "Materials", "20": "Industrials", "25": "Consumer Discretionary",
    "30": "Consumer Staples", "35": "Health Care", "40": "Financials", "45": "Information Technology",
    "50": "Communication Services", "55": "Utilities", "60": "Real Estate", "unknown": "Unknown",
}


def sector_name(code: Any) -> str:
    text = str(code).split(".")[0] if code is not None else "unknown"
    return SECTOR_NAMES.get(text, text)


def by_model(data: AnalysisData, frame: pd.DataFrame, draws: int, rng: np.random.Generator) -> list[dict[str, Any]]:
    rows = []
    models = present_models(data, frame)
    for m in range(len(models)):
        sub = frame[frame["model_requested"] == models[m]]
        meta = data.model_meta(models[m])
        for f in range(len(ALL_FACTOR_COLS)):
            if ALL_FACTOR_COLS[f] not in sub.columns:
                continue
            ci = mean_ci(sub[ALL_FACTOR_COLS[f]].to_numpy(dtype=float), draws, rng)
            rows.append({"model": models[m], "provider": meta.get("provider"), "role": meta.get("role"),
                         "factor": ALL_FACTOR_COLS[f], **ci})
    return rows


def by_framing(data: AnalysisData, frame: pd.DataFrame, draws: int, rng: np.random.Generator,
               models: list[str] | None = None) -> list[dict[str, Any]]:
    """Cross-model mean loading per prompt: the mean of each model's mean (models weigh equally)."""
    rows = []
    sub_all = frame if models is None else frame[frame["model_requested"].isin(models)]
    prompts = sorted(sub_all["prompt_id"].dropna().unique().tolist())
    for p in range(len(prompts)):
        sub = sub_all[sub_all["prompt_id"] == prompts[p]]
        for f in range(len(ALL_FACTOR_COLS)):
            column = ALL_FACTOR_COLS[f]
            if column not in sub.columns:
                continue
            model_means = sub.groupby("model_requested")[column].mean().to_numpy(dtype=float)
            ci = mean_ci(sub[column].to_numpy(dtype=float), draws, rng)
            rows.append({"prompt_id": prompts[p], "factor": column,
                         "cross_model_mean": float(np.nanmean(model_means)) if len(model_means) else None,
                         "pooled_mean": ci["mean"], "lo": ci["lo"], "hi": ci["hi"], "n": ci["n"],
                         "cross_model_sd": float(np.nanstd(model_means)) if len(model_means) > 1 else None})
    return rows


def sector_mix(data: AnalysisData, frame: pd.DataFrame, top: int = 8) -> dict[str, Any]:
    models = present_models(data, frame)
    totals: dict[str, float] = {}
    per_model: dict[str, dict[str, float]] = {}
    for m in range(len(models)):
        sub = frame[frame["model_requested"] == models[m]]
        mix: dict[str, float] = {}
        payloads = sub["sector_weights_json"].tolist()
        for i in range(len(payloads)):
            weights = json.loads(payloads[i] or "{}")
            keys = list(weights.keys())
            for k in range(len(keys)):
                name = sector_name(keys[k])
                mix[name] = mix.get(name, 0.0) + float(weights[keys[k]]) / max(1, len(payloads))
                totals[name] = totals.get(name, 0.0) + float(weights[keys[k]])
        per_model[models[m]] = mix
    ranked = sorted(totals.keys(), key=lambda name: -totals[name])
    keep = ranked[:top]
    out_rows = []
    for m in range(len(models)):
        mix = per_model[models[m]]
        row = {"model": models[m]}
        other = 0.0
        names = list(mix.keys())
        for k in range(len(names)):
            if names[k] in keep:
                row[names[k]] = round(mix[names[k]], 4)
            else:
                other += mix[names[k]]
        row["Other"] = round(other, 4)
        out_rows.append(row)
    return {"sectors": keep + ["Other"], "rows": out_rows}


def prompt_effect_vs_noise(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Swing of the cross-model mean across framings relative to single-run and mean noise."""
    rows = []
    prompts = sorted(frame["prompt_id"].dropna().unique().tolist())
    for f in range(len(FACTOR_COLS)):
        column = FACTOR_COLS[f]
        means = []
        noise = []
        sizes = []
        for p in range(len(prompts)):
            sub = frame[frame["prompt_id"] == prompts[p]]
            means.append(sub.groupby("model_requested")[column].mean().mean())
            within = sub.groupby("model_requested")[column].std().dropna()
            if len(within) > 0:
                noise.append(float(within.mean()))
            sizes.append(len(sub))
        if len(means) < 2 or len(noise) == 0:
            continue
        swing = float(np.nanmax(means) - np.nanmin(means))
        single = float(np.mean(noise))
        n_mean = float(np.mean(sizes)) if len(sizes) else 1.0
        rows.append({"factor": column, "swing": swing, "single_run_noise": single,
                     "swing_over_noise": swing / single if single > 0 else None,
                     "swing_over_se": swing / (single / np.sqrt(max(1.0, n_mean))) if single > 0 else None})
    return rows


def dispersion_vs_overlap(framing_rows: list[dict[str, Any]], overlap_stage: dict[str, Any]) -> list[dict[str, Any]]:
    """Cross-model sd of mean exposures next to 1 - mean cross-model Jaccard, per framing."""
    out = []
    prompts = sorted(overlap_stage.keys())
    for p in range(len(prompts)):
        cross = overlap_stage[prompts[p]].get("b_cross_provider") or {}
        within = overlap_stage[prompts[p]].get("c_within_provider") or {}
        jbar = cross.get("mean")
        row: dict[str, Any] = {"prompt_id": prompts[p], "one_minus_jaccard": None if jbar is None else 1 - jbar,
                               "one_minus_jaccard_within_provider": None if within.get("mean") is None else 1 - within["mean"]}
        for i in range(len(framing_rows)):
            if framing_rows[i]["prompt_id"] == prompts[p] and framing_rows[i]["factor"] in FACTOR_COLS:
                row["sd_" + framing_rows[i]["factor"]] = framing_rows[i]["cross_model_sd"]
        out.append(row)
    return out
