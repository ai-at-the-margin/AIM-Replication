"""Load one analysis-ready view of the database."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..settings import Config
from ..store.db import Store

BASELINE_PROVIDERS = {"openai", "anthropic"}

FACTOR_COLS = ["size", "value", "quality", "momentum", "lowvol", "beta"]
ALL_FACTOR_COLS = ["size", "value", "quality", "momentum", "lowvol", "resvol", "beta", "mom_12_1", "value_blend"]
FREEFORM = ["L1", "L2", "L3", "L4"]
MANDATES = ["VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"]
MANDATE_TARGET = {"VALUE": "value", "QUALITY": "quality", "MOMENTUM": "momentum"}


@dataclass
class AnalysisData:
    calls: pd.DataFrame
    valid: pd.DataFrame
    holdings: pd.DataFrame
    pexp: pd.DataFrame
    pexp_equal: pd.DataFrame
    exposures: pd.DataFrame
    search: pd.DataFrame
    responses: pd.DataFrame
    momentum_history: pd.DataFrame
    models: list[dict[str, Any]]
    asof: str | None
    universe: str
    model_order: list[str] = field(default_factory=list)

    def model_meta(self, model_id: str) -> dict[str, Any]:
        for i in range(len(self.models)):
            if self.models[i]["id"] == model_id:
                return self.models[i]
        return {"id": model_id, "provider": "unknown", "role": "unknown"}

    def flagships(self) -> list[str]:
        out = []
        for i in range(len(self.models)):
            if self.models[i].get("role") == "flagship":
                out.append(self.models[i]["id"])
        return out


def load(store: Store, config: Config, asof: str | None, universe: str = "acwi_proxy",
         *, cohort: str = "baseline") -> AnalysisData:
    models = []
    model_ids = set()
    providers = dict.fromkeys(("openai", "anthropic"))
    for model in config.model_list(include_optional=True):
        provider = model["provider"]
        if cohort == "expanded" or provider in BASELINE_PROVIDERS:
            models.append(model)
            model_ids.add(model["id"])
            providers[provider] = None
    calls = store.query(
        "SELECT c.*, p.outcome, p.parse_status, p.parse_method, p.n_names_raw, p.n_issuers, "
        "p.weights_provided, p.weight_sum_raw FROM calls c LEFT JOIN portfolios p USING (call_id)")
    calls = calls[calls["model_requested"].isin(model_ids)].copy()
    call_ids = calls["call_id"]
    # Older baseline calls have counts but no separate invocation flag.
    invocation = calls["search_invoked"].astype("boolean")
    legacy = calls["provider"].isin(BASELINE_PROVIDERS) & calls["search_count"].notna()
    calls["search_invoked"] = invocation.mask(invocation.isna() & legacy, calls["search_count"].gt(0))
    calls.loc[calls["search_enabled"].eq(False), "search_invoked"] = False  # noqa: E712
    calls["outcome"] = calls["outcome"].fillna("unparsed")
    valid = calls[calls["outcome"] == "valid"].copy()
    holdings = store.query(
        "SELECT h.*, c.stage, c.provider, c.model_requested, c.prompt_id, c.language, c.search_enabled, c.rep "
        "FROM holdings h JOIN calls c USING (call_id) JOIN portfolios p USING (call_id) WHERE p.outcome = 'valid'")
    holdings = holdings[holdings["call_id"].isin(call_ids)]
    if asof is not None:
        pexp_all = store.query("SELECT * FROM portfolio_exposures WHERE asof_date = ? AND universe = ?",
                               [asof, universe])
        exposures = store.query("SELECT * FROM exposures WHERE asof_date = ? AND universe = ?", [asof, universe])
        momentum_history = store.query("SELECT * FROM momentum_history WHERE asof_date = ?", [asof])
    else:
        pexp_all = store.query("SELECT * FROM portfolio_exposures WHERE 1 = 0")
        exposures = store.query("SELECT * FROM exposures WHERE 1 = 0")
        momentum_history = store.query("SELECT * FROM momentum_history WHERE 1 = 0")
    meta_cols = ["call_id", "stage", "provider", "model_requested", "role", "generation", "size_class",
                 "prompt_id", "prompt_family", "language", "rep", "search_enabled", "search_count", "search_invoked", "search_tool_version"]
    pexp = pexp_all[pexp_all["weighting"] == "model"].merge(valid[meta_cols], on="call_id", how="inner")
    pexp_equal = pexp_all[pexp_all["weighting"] == "equal"].merge(valid[meta_cols], on="call_id", how="inner")
    search = store.query(
        "SELECT s.*, c.stage, c.provider, c.model_requested, c.prompt_id, c.search_tool_version "
        "FROM search_events s JOIN calls c USING (call_id)")
    responses = store.query("SELECT call_id, reasoning_word_count, reasoning_text FROM responses")
    search = search[search["call_id"].isin(call_ids)]
    responses = responses[responses["call_id"].isin(call_ids)]
    order = []
    roles = ["flagship", "mainstream", "mid", "small", "previous_flagship", "two_back", "consumer_proxy"]
    for provider in providers:
        for r in range(len(roles)):
            for i in range(len(models)):
                if models[i]["provider"] == provider and models[i].get("role") == roles[r]:
                    order.append(models[i]["id"])
    return AnalysisData(calls=calls, valid=valid, holdings=holdings, pexp=pexp, pexp_equal=pexp_equal,
                        exposures=exposures, search=search, responses=responses,
                        momentum_history=momentum_history, models=models, asof=asof, universe=universe,
                        model_order=order)


def present_models(data: AnalysisData, frame: pd.DataFrame) -> list[str]:
    have = set(frame["model_requested"].tolist()) if "model_requested" in frame.columns else set()
    out = []
    for i in range(len(data.model_order)):
        if data.model_order[i] in have:
            out.append(data.model_order[i])
    return out
