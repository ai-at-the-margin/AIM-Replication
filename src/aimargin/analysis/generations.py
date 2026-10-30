"""Model size and generation (BUILD_BRIEF §8.8): profiles and overlap with the flagship."""

from __future__ import annotations

from typing import Any

import numpy as np

from .data import FACTOR_COLS, AnalysisData, present_models
from .overlap import issuer_sets, jaccard


def generation_analysis(data: AnalysisData) -> dict[str, Any]:
    stage_a = data.pexp[(data.pexp["stage"] == "A") & (data.pexp["language"] == "en")]
    valid_a = data.valid[(data.valid["stage"] == "A") & (data.valid["language"] == "en")]
    sets = issuer_sets(data.holdings)
    rows = []
    models = present_models(data, stage_a)
    flagship_by_provider = {}
    for m in range(len(models)):
        meta = data.model_meta(models[m])
        if meta.get("role") == "flagship":
            flagship_by_provider[meta["provider"]] = models[m]
    for m in range(len(models)):
        meta = data.model_meta(models[m])
        sub = stage_a[stage_a["model_requested"] == models[m]]
        row: dict[str, Any] = {"model": models[m], "provider": meta.get("provider"), "role": meta.get("role"),
                               "generation": meta.get("generation"), "size_class": meta.get("size_class"),
                               "n": int(len(sub))}
        for f in range(len(FACTOR_COLS)):
            row[FACTOR_COLS[f]] = float(sub[FACTOR_COLS[f]].mean()) if len(sub) else None
        flagship = flagship_by_provider.get(meta.get("provider"))
        values = []
        if flagship and flagship != models[m]:
            prompts = sorted(valid_a["prompt_id"].unique().tolist())
            for p in range(len(prompts)):
                mine = valid_a[(valid_a["model_requested"] == models[m]) & (valid_a["prompt_id"] == prompts[p])]["call_id"].tolist()
                theirs = valid_a[(valid_a["model_requested"] == flagship) & (valid_a["prompt_id"] == prompts[p])]["call_id"].tolist()
                for i in range(len(mine)):
                    for j in range(len(theirs)):
                        values.append(jaccard(sets.get(mine[i], set()), sets.get(theirs[j], set())))
        row["jaccard_to_flagship"] = float(np.mean(values)) if len(values) else None
        row["factor_distance_to_flagship"] = None
        rows.append(row)
    by_model = {}
    for i in range(len(rows)):
        by_model[rows[i]["model"]] = rows[i]
    for i in range(len(rows)):
        flagship = flagship_by_provider.get(rows[i]["provider"])
        if flagship and flagship in by_model and flagship != rows[i]["model"]:
            diffs = []
            for f in range(len(FACTOR_COLS)):
                a = rows[i][FACTOR_COLS[f]]
                b = by_model[flagship][FACTOR_COLS[f]]
                if a is not None and b is not None:
                    diffs.append((a - b) ** 2)
            rows[i]["factor_distance_to_flagship"] = float(np.sqrt(np.sum(diffs))) if diffs else None
    return {"rows": rows}
