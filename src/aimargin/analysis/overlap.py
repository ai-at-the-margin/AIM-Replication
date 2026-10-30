"""Name overlap (BUILD_BRIEF §8.1, Figure 1): Jaccard on issuer sets over rep pairs.

Reported per framing: (a) the two flagships, (b) all OpenAI x Anthropic model
pairs, (c) within-provider cross-model pairs, (d) within-model pairs, plus the
model x model heatmap (diagonal = within-model self-stability).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .bootstrap import cross_pair_mean_draws, resample_counts, within_pair_mean_draws
from .data import AnalysisData, present_models


def issuer_sets(holdings: pd.DataFrame) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    calls = holdings["call_id"].tolist()
    issuers = holdings["issuer_id"].tolist()
    raws = holdings["raw_ticker"].tolist()
    for i in range(len(calls)):
        key = issuers[i] if issuers[i] is not None and issuers[i] == issuers[i] else f"raw:{raws[i]}"
        out.setdefault(calls[i], set()).add(str(key))
    return out


def jaccard_matrix(call_ids: list[str], sets: dict[str, set[str]]) -> np.ndarray:
    vocab: dict[str, int] = {}
    for i in range(len(call_ids)):
        members = sorted(sets.get(call_ids[i], set()))
        for j in range(len(members)):
            if members[j] not in vocab:
                vocab[members[j]] = len(vocab)
    incidence = np.zeros((len(call_ids), max(1, len(vocab))))
    for i in range(len(call_ids)):
        members = sets.get(call_ids[i], set())
        for name in members:
            incidence[i, vocab[name]] = 1.0
    inter = incidence @ incidence.T
    sizes = incidence.sum(axis=1)
    union = sizes[:, None] + sizes[None, :] - inter
    with np.errstate(invalid="ignore", divide="ignore"):
        jac = np.where(union > 0, inter / union, 0.0)
    return jac


def jaccard(a: set[str], b: set[str]) -> float:
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def _ci(draws_values: np.ndarray, point: float) -> dict[str, float | None]:
    finite = draws_values[np.isfinite(draws_values)]
    if len(finite) == 0:
        return {"mean": point, "lo": None, "hi": None}
    return {"mean": point, "lo": float(np.quantile(finite, 0.025)), "hi": float(np.quantile(finite, 0.975))}


def overlap_for_cells(data: AnalysisData, valid: pd.DataFrame, sets: dict[str, set[str]], draws: int,
                      rng: np.random.Generator) -> dict[str, Any]:
    models = present_models(data, valid)
    index: dict[str, list[int]] = {}
    call_ids: list[str] = []
    for m in range(len(models)):
        ids = valid[valid["model_requested"] == models[m]]["call_id"].tolist()
        positions = []
        for i in range(len(ids)):
            positions.append(len(call_ids))
            call_ids.append(ids[i])
        index[models[m]] = positions
    if len(call_ids) < 2:
        return {"models": models, "heatmap": [], "a_flagships": None, "b_cross_provider": None,
                "c_within_provider": None, "d_within_model": None}
    J = jaccard_matrix(call_ids, sets)
    counts = {}
    for m in range(len(models)):
        counts[models[m]] = resample_counts(len(index[models[m]]), draws, rng)
    heat = []
    groups: dict[str, list[tuple[np.ndarray, float, float]]] = {"cross": [], "within_provider": [], "within_model": []}
    for a in range(len(models)):
        row = []
        for b in range(len(models)):
            ia = index[models[a]]
            ib = index[models[b]]
            block = J[np.ix_(ia, ib)]
            if a == b:
                n = len(ia)
                value = float((block.sum() - np.trace(block)) / (n * (n - 1))) if n > 1 else None
            else:
                value = float(block.mean()) if block.size else None
            row.append(value)
            if a < b and len(ia) > 0 and len(ib) > 0:
                draws_ab = cross_pair_mean_draws(block, counts[models[a]], counts[models[b]])
                same = data.model_meta(models[a])["provider"] == data.model_meta(models[b])["provider"]
                groups["within_provider" if same else "cross"].append((draws_ab, value, len(ia) * len(ib)))
            if a == b and len(ia) > 1:
                draws_aa = within_pair_mean_draws(block, counts[models[a]])
                groups["within_model"].append((draws_aa, value, len(ia) * (len(ia) - 1)))
        heat.append(row)
    out: dict[str, Any] = {"models": models, "heatmap": heat}
    for key, label in (("cross", "b_cross_provider"), ("within_provider", "c_within_provider"),
                       ("within_model", "d_within_model")):
        items = groups[key]
        if len(items) == 0:
            out[label] = None
            continue
        weights = np.array([0.0] * len(items))
        stack = []
        points = []
        for i in range(len(items)):
            weights[i] = items[i][2]
            stack.append(items[i][0])
            points.append(items[i][1] if items[i][1] is not None else np.nan)
        stack_arr = np.vstack(stack)
        w = weights / weights.sum()
        point = float(np.nansum(np.array(points) * w))
        pooled = np.nansum(stack_arr * w[:, None], axis=0)
        out[label] = _ci(pooled, point)
        out[label]["n_pairs"] = int(weights.sum())
    flagships = data.flagships()
    fa = None
    fb = None
    for i in range(len(flagships)):
        if data.model_meta(flagships[i])["provider"] == "openai":
            fa = flagships[i]
        elif data.model_meta(flagships[i])["provider"] == "anthropic":
            fb = flagships[i]
    if fa in index and fb in index and len(index[fa]) > 0 and len(index[fb]) > 0:
        block = J[np.ix_(index[fa], index[fb])]
        out["a_flagships"] = _ci(cross_pair_mean_draws(block, counts[fa], counts[fb]), float(block.mean()))
        out["a_flagships"]["pair"] = [fa, fb]
    else:
        out["a_flagships"] = None
    return out


def overlap_analysis(data: AnalysisData, draws: int, rng: np.random.Generator) -> dict[str, Any]:
    sets = issuer_sets(data.holdings)
    out: dict[str, Any] = {}
    stages = sorted(data.valid["stage"].dropna().unique().tolist())
    for s in range(len(stages)):
        stage = stages[s]
        frame = data.valid[(data.valid["stage"] == stage) & (data.valid["language"] == "en")]
        prompts = sorted(frame["prompt_id"].dropna().unique().tolist())
        stage_out: dict[str, Any] = {}
        for p in range(len(prompts)):
            cells = frame[frame["prompt_id"] == prompts[p]]
            stage_out[prompts[p]] = overlap_for_cells(data, cells, sets, draws, rng)
        out[stage] = stage_out
    return out
