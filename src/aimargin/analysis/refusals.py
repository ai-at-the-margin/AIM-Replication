"""Refusals and output failures (BUILD_BRIEF §8.9). Paper: ~26% at L1, <= 2% elsewhere."""

from __future__ import annotations

from typing import Any

from .data import AnalysisData, present_models

OUTCOMES = ["valid", "insufficient_names", "excess_names", "format_failure", "refusal", "api_error"]


def refusal_analysis(data: AnalysisData) -> dict[str, Any]:
    calls = data.calls[data.calls["stage"].isin(["A", "B", "C"])]
    rows = []
    models = present_models(data, calls)
    prompts = ["L1", "L2", "L3", "L4", "VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"]
    for s in ("A", "B", "C"):
        stage = calls[calls["stage"] == s]
        for p in range(len(prompts)):
            for m in range(len(models)):
                cell = stage[(stage["prompt_id"] == prompts[p]) & (stage["model_requested"] == models[m])
                             & (stage["language"] == "en")]
                if len(cell) == 0:
                    continue
                row: dict[str, Any] = {"stage": s, "prompt_id": prompts[p], "model": models[m], "n": int(len(cell))}
                for o in range(len(OUTCOMES)):
                    row[OUTCOMES[o]] = float((cell["outcome"] == OUTCOMES[o]).mean())
                rows.append(row)
    pooled = []
    for p in range(len(prompts)):
        cell = calls[(calls["prompt_id"] == prompts[p]) & calls["stage"].isin(["A", "B"]) & (calls["language"] == "en")]
        if len(cell) == 0:
            continue
        pooled.append({"prompt_id": prompts[p], "n": int(len(cell)),
                       "refusal": float((cell["outcome"] == "refusal").mean()),
                       "no_usable_portfolio": float((cell["outcome"] != "valid").mean())})
    return {"cells": rows, "pooled_offline": pooled, "paper_benchmark": {"L1": 0.26, "other_max": 0.02}}
