"""English vs Mandarin (BUILD_BRIEF §8.7, optional arm)."""

from __future__ import annotations

from typing import Any

import numpy as np

from .data import FACTOR_COLS, AnalysisData, present_models
from .overlap import issuer_sets, jaccard


def language_analysis(data: AnalysisData) -> dict[str, Any]:
    stage_a = data.holdings[data.holdings["stage"] == "A"]
    if "zh" not in set(stage_a["language"].dropna().tolist()):
        return {"available": False, "note": "Mandarin arm not collected (optional_arms.mandarin.enabled = false)"}
    sets = issuer_sets(data.holdings)
    rows = []
    models = present_models(data, stage_a)
    for m in range(len(models)):
        row: dict[str, Any] = {"model": models[m]}
        for language in ("en", "zh"):
            cell = stage_a[(stage_a["model_requested"] == models[m]) & (stage_a["language"] == language)]
            total = max(1, len(cell))
            row[f"{language}_china_a"] = float(cell["is_china_a_share"].fillna(False).sum()) / total
            row[f"{language}_hk"] = float(cell["is_hk_listed"].fillna(False).sum()) / total
            row[f"{language}_us"] = float(cell["is_us_listed"].fillna(False).sum()) / total
            exp = data.pexp[(data.pexp["stage"] == "A") & (data.pexp["model_requested"] == models[m])
                            & (data.pexp["language"] == language)]
            for f in range(len(FACTOR_COLS)):
                row[f"{language}_{FACTOR_COLS[f]}"] = float(exp[FACTOR_COLS[f]].mean()) if len(exp) else None
        en_ids = data.valid[(data.valid["stage"] == "A") & (data.valid["model_requested"] == models[m])
                            & (data.valid["language"] == "en")]["call_id"].tolist()
        zh_ids = data.valid[(data.valid["stage"] == "A") & (data.valid["model_requested"] == models[m])
                            & (data.valid["language"] == "zh")]["call_id"].tolist()
        values = []
        for i in range(len(en_ids)):
            for j in range(len(zh_ids)):
                values.append(jaccard(sets.get(en_ids[i], set()), sets.get(zh_ids[j], set())))
        row["jaccard_en_zh"] = float(np.mean(values)) if values else None
        rows.append(row)
    return {"available": True, "rows": rows}
