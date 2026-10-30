"""Cost model: dry-run estimates and per-call actual cost (BUILD_BRIEF §1.4)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..settings import Config
from .planner import CallSpec


def call_cost(model_cfg: dict[str, Any], provider_cfg: dict[str, Any], input_tokens: float | None,
              output_tokens: float | None, searches: float | None = 0, via_batch: bool = False) -> float:
    """USD cost of one call from token usage (missing usage counts as zero)."""
    price_in = float(model_cfg.get("price_in_per_m") or 0.0)
    price_out = float(model_cfg.get("price_out_per_m") or 0.0)
    tokens_in = float(input_tokens or 0.0)
    tokens_out = float(output_tokens or 0.0)
    cost = tokens_in * price_in / 1e6 + tokens_out * price_out / 1e6
    if via_batch:
        cost = cost * float(provider_cfg.get("batch_discount", 1.0))
    search_fee = float(provider_cfg.get("search_price_per_1k_calls", 0.0)) / 1000.0
    cost += float(searches or 0.0) * search_fee
    return round(cost, 6)


def _input_tokens_for(text: str, language: str) -> float:
    if language == "zh":
        return float(len(text)) * 1.1 + 20.0
    return float(len(text)) / 3.8 + 20.0


def measured_usage(calls: pd.DataFrame | None) -> dict[tuple[str, bool], dict[str, float]]:
    """Mean usage per (model, search_enabled) from completed calls, if there are >= 2."""
    out: dict[tuple[str, bool], dict[str, float]] = {}
    if calls is None or len(calls) == 0:
        return out
    done = calls[calls["status"] == "completed"]
    if len(done) == 0:
        return out
    grouped = done.groupby(["model_requested", "search_enabled"])
    keys = list(grouped.groups.keys())
    for i in range(len(keys)):
        group = grouped.get_group(keys[i])
        if len(group) < 2:
            continue
        out[(str(keys[i][0]), bool(keys[i][1]))] = {
            "input_tokens": float(group["input_tokens"].fillna(0).mean()),
            "output_tokens": float(group["output_tokens"].fillna(0).mean()),
            "search_count": float(group["search_count"].fillna(0).mean()),
            "n": float(len(group)),
        }
    return out


def estimate_spec(config: Config, spec: CallSpec, measured: dict | None = None,
                  via_batch: bool = False) -> dict[str, Any]:
    model_cfg = config.model(spec.model_requested)
    provider_cfg = config.provider(spec.provider)
    assumptions = config.experiment.get("token_assumptions", {})
    key = (spec.model_requested, bool(spec.search_enabled))
    basis = "assumption"
    if measured and key in measured:
        usage = measured[key]
        tokens_in = usage["input_tokens"]
        tokens_out = usage["output_tokens"]
        searches = usage["search_count"]
        basis = f"measured(n={int(usage['n'])})"
    else:
        tokens_in = _input_tokens_for(spec.prompt_text, spec.language)
        by_role = assumptions.get("output_tokens_by_role", {})
        tokens_out = float(by_role.get(spec.role, 3000))
        searches = 0.0
        if spec.search_enabled:
            rate = float(assumptions.get("search_invocation_rate_assumed", 0.6))
            searches = rate * float(assumptions.get("searches_per_call_when_enabled", 4))
            tokens_in += searches * float(assumptions.get("search_content_tokens_per_search", 3500))
    cost = call_cost(model_cfg, provider_cfg, tokens_in, tokens_out, searches, via_batch)
    return {
        "est_input_tokens": tokens_in, "est_output_tokens": tokens_out, "est_searches": searches,
        "est_cost_usd": cost, "basis": basis, "price_verified": bool(model_cfg.get("price_verified", False)),
    }


def estimate_plan(config: Config, specs: list[CallSpec], calls: pd.DataFrame | None = None,
                  batch_stages: list[str] | None = None) -> pd.DataFrame:
    """One row per planned call with its estimate; aggregate with ``summarise_estimate``."""
    measured = measured_usage(calls)
    batch_stages = batch_stages or []
    rows = []
    for i in range(len(specs)):
        spec = specs[i]
        estimate = estimate_spec(config, spec, measured, via_batch=spec.stage in batch_stages)
        row = {
            "call_id": spec.call_id, "stage": spec.stage, "provider": spec.provider,
            "model": spec.model_requested, "prompt_id": spec.prompt_id, "language": spec.language,
            "search_enabled": spec.search_enabled, "arm": spec.arm,
        }
        row.update(estimate)
        rows.append(row)
    return pd.DataFrame(rows)


def summarise_estimate(estimate: pd.DataFrame) -> pd.DataFrame:
    if estimate is None or len(estimate) == 0:
        return pd.DataFrame(columns=["stage", "model", "n_calls", "est_cost_usd"])
    summary = estimate.groupby(["stage", "provider", "model"], as_index=False).agg(
        n_calls=("call_id", "count"),
        est_input_tokens=("est_input_tokens", "sum"),
        est_output_tokens=("est_output_tokens", "sum"),
        est_searches=("est_searches", "sum"),
        est_cost_usd=("est_cost_usd", "sum"),
        price_verified=("price_verified", "min"),
    )
    return summary.sort_values(["stage", "provider", "model"]).reset_index(drop=True)
