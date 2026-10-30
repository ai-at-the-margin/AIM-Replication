"""Search on vs off (BUILD_BRIEF §8.5-8.6, Figures 5-6).

"Invoked search" means at least one executed search event; tool availability
alone does not count.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .bootstrap import diff_ci, mean_ci
from .data import FREEFORM, MANDATES, AnalysisData, present_models


def invocation(data: AnalysisData) -> dict[str, Any]:
    calls = data.calls[(data.calls["stage"] == "C") & (data.calls["status"] == "completed")]
    models = present_models(data, calls)
    prompts = FREEFORM + MANDATES
    rows = []
    for m in range(len(models)):
        for p in range(len(prompts)):
            cell = calls[(calls["model_requested"] == models[m]) & (calls["prompt_id"] == prompts[p])]
            if len(cell) == 0:
                continue
            invoked = (cell["search_count"].fillna(0) > 0)
            rows.append({"model": models[m], "prompt_id": prompts[p], "n": int(len(cell)),
                         "share_invoked": float(invoked.mean()),
                         "mean_searches_when_invoked": float(cell.loc[invoked, "search_count"].mean()) if invoked.any() else 0.0})
    return {"models": models, "prompts": prompts, "rows": rows}


def on_off(data: AnalysisData, draws: int, rng: np.random.Generator, factor: str = "momentum") -> dict[str, Any]:
    connected = data.pexp[data.pexp["stage"] == "C"]
    models_c = present_models(data, connected)
    offline = data.pexp[data.pexp["stage"].isin(["A", "B"]) & data.pexp["model_requested"].isin(models_c)
                        & (data.pexp["language"] == "en")]
    tasks = [("Free-form (L1-L4)", FREEFORM)]
    for i in range(len(MANDATES)):
        tasks.append((MANDATES[i].title() + " mandate", [MANDATES[i]]))
    by_task = []
    for t in range(len(tasks)):
        label, prompts = tasks[t]
        off = offline[offline["prompt_id"].isin(prompts)][factor].to_numpy(dtype=float)
        on_cell = connected[connected["prompt_id"].isin(prompts)]
        on = on_cell[factor].to_numpy(dtype=float)
        invoked = on_cell[on_cell["search_count"].fillna(0) > 0][factor].to_numpy(dtype=float)
        not_invoked = on_cell[on_cell["search_count"].fillna(0) == 0][factor].to_numpy(dtype=float)
        share = float((on_cell["search_count"].fillna(0) > 0).mean()) if len(on_cell) else None
        by_task.append({"task": label, "offline": mean_ci(off, draws, rng), "connected": mean_ci(on, draws, rng),
                        "connected_invoked": mean_ci(invoked, draws, rng),
                        "connected_not_invoked": mean_ci(not_invoked, draws, rng),
                        "change": diff_ci(on, off, draws, rng), "share_invoked": share})
    by_model = []
    for m in range(len(models_c)):
        off = offline[(offline["model_requested"] == models_c[m]) & (offline["prompt_id"] == "MOMENTUM")][factor]
        on_cell = connected[(connected["model_requested"] == models_c[m]) & (connected["prompt_id"] == "MOMENTUM")]
        by_model.append({"model": models_c[m], "provider": data.model_meta(models_c[m]).get("provider"),
                         "offline": mean_ci(off.to_numpy(dtype=float), draws, rng),
                         "connected": mean_ci(on_cell[factor].to_numpy(dtype=float), draws, rng),
                         "share_invoked": float((on_cell["search_count"].fillna(0) > 0).mean()) if len(on_cell) else None})
    return {"factor": factor, "by_task": by_task, "momentum_mandate_by_model": by_model}


def search_analysis(data: AnalysisData, draws: int, rng: np.random.Generator) -> dict[str, Any]:
    return {
        "invocation": invocation(data),
        "momentum": on_off(data, draws, rng, "momentum"),
        "momentum_12_1": on_off(data, draws, rng, "mom_12_1"),
    }
