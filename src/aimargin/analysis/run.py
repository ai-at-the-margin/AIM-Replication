"""`aim analyze`: run every analysis, write outputs/analysis.json and CSV tables."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..settings import Config, Workspace
from ..store.db import Store
from ..utils import get_logger, read_json, utc_now_iso, write_json
from .attention import attention_analysis
from .compliance import compliance_analysis
from .consensus import consensus_analysis
from .crowding import crowding_analysis
from .data import FACTOR_COLS, load
from .exposure_stats import by_framing, by_model, dispersion_vs_overlap, prompt_effect_vs_noise, sector_mix
from .factor_space import factor_space_analysis
from .generations import generation_analysis
from .geography import geography_analysis
from .language import language_analysis
from .mandates import mandate_analysis
from .ops import drops, ops_analysis
from .overlap import overlap_analysis
from .query_classify import query_analysis
from .reasoning import reasoning_analysis
from .refusals import refusal_analysis
from .search_usage import search_analysis
from .staleness import staleness_analysis
from .weighting import weighting_analysis

log = get_logger(__name__)

PAPER = {
    "jaccard_L1": 0.69, "jaccard_L4": 0.38,
    "freeform_size": 0.55, "freeform_quality": 0.49, "freeform_momentum": -0.31, "freeform_value": -0.06,
    "lowvol_L1": 0.37, "lowvol_L4": -0.06,
    "value_unconstrained": -0.12, "value_mandate": 0.77,
    "quality_unconstrained": 0.67, "quality_mandate": 0.63,
    "momentum_unconstrained": -0.35, "momentum_mandate_offline": -0.38,
    "momentum_mandate_connected": 0.43, "momentum_mandate_invoked_lo": 0.53, "momentum_mandate_invoked_hi": 0.98,
    "single_stock_value": 0.80, "single_stock_unconstrained": 0.76, "single_stock_quality": 0.35,
    "lookup_in_book": 0.62, "refusal_L1": 0.26, "refusal_other_max": 0.02,
}


def _get(rows: list[dict[str, Any]], **match: Any) -> dict[str, Any] | None:
    keys = list(match.keys())
    for i in range(len(rows)):
        ok = True
        for k in range(len(keys)):
            if rows[i].get(keys[k]) != match[keys[k]]:
                ok = False
                break
        if ok:
            return rows[i]
    return None


def paper_comparison(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(metric: str, label: str, ours: Any, note: str = "") -> None:
        paper = PAPER.get(metric)
        diff = None if ours is None or paper is None else float(ours) - float(paper)
        rows.append({"metric": metric, "label": label, "paper": paper, "ours": None if ours is None else float(ours),
                     "difference": diff, "note": note})

    overlap_a = result.get("overlap", {}).get("A", {})
    for p in ("L1", "L4"):
        cross = (overlap_a.get(p) or {}).get("b_cross_provider") or {}
        add(f"jaccard_{p}", f"Cross-provider Jaccard, {p}", cross.get("mean"),
            "paper: 6 providers' flagships; ours: all OpenAI x Anthropic model pairs")
    flag = result.get("exposures", {}).get("freeform_flagships_pooled", {})
    for f in ("size", "quality", "momentum", "value"):
        add(f"freeform_{f}", f"Free-form {f} loading (flagships)", flag.get(f))
    framing = result.get("exposures", {}).get("by_framing_flagships", [])
    for p in ("L1", "L4"):
        row = _get(framing, prompt_id=p, factor="lowvol")
        add(f"lowvol_{p}", f"Low-Vol loading, {p}", row.get("cross_model_mean") if row else None)
    heat = result.get("mandates", {}).get("heatmap_flagships", {}).get("rows", [])
    for mandate, factor, key_m, key_u in (("VALUE", "value", "value_mandate", "value_unconstrained"),
                                          ("QUALITY", "quality", "quality_mandate", "quality_unconstrained"),
                                          ("MOMENTUM", "momentum", "momentum_mandate_offline", "momentum_unconstrained")):
        m_row = _get(heat, mandate=mandate)
        u_row = _get(heat, mandate="UNCONSTRAINED")
        add(key_m, f"{mandate.title()} mandate: {factor} loading (offline)", m_row.get(factor) if m_row else None)
        add(key_u, f"Unconstrained: {factor} loading (offline)", u_row.get(factor) if u_row else None)
    momentum = result.get("search", {}).get("momentum", {}).get("by_task", [])
    mom_row = _get(momentum, task="Momentum mandate")
    if mom_row:
        add("momentum_mandate_connected", "Momentum mandate, search available (pooled)",
            mom_row["connected"].get("mean"))
    invoked = []
    by_model = result.get("search", {}).get("momentum", {}).get("momentum_mandate_by_model", [])
    for i in range(len(by_model)):
        if (by_model[i].get("share_invoked") or 0) >= 0.5 and by_model[i]["connected"].get("mean") is not None:
            invoked.append(by_model[i]["connected"]["mean"])
    add("momentum_mandate_invoked_lo", "Momentum mandate, models that searched (min)", min(invoked) if invoked else None)
    add("momentum_mandate_invoked_hi", "Momentum mandate, models that searched (max)", max(invoked) if invoked else None)
    queries = result.get("queries", {}).get("by_prompt", [])
    for mandate, key in (("VALUE", "single_stock_value"), ("UNCONSTRAINED", "single_stock_unconstrained"),
                         ("QUALITY", "single_stock_quality")):
        row = _get(queries, prompt_id=mandate)
        add(key, f"Single-stock checks, {mandate.title()} queries", row.get("single_stock_check") if row else None)
    lookups = result.get("queries", {}).get("lookup_to_portfolio", [])
    shares = []
    for i in range(len(lookups)):
        if lookups[i].get("share") is not None:
            shares.append(lookups[i]["share"])
    add("lookup_in_book", "Single-stock lookups naming a stock in the final book", float(np.mean(shares)) if shares else None,
        "paper: one provider's quote lookups; ours: mean over providers")
    pooled = result.get("refusals", {}).get("pooled_offline", [])
    l1 = _get(pooled, prompt_id="L1")
    add("refusal_L1", "No usable portfolio at L1 (refusal share)", l1.get("refusal") if l1 else None)
    others = []
    for i in range(len(pooled)):
        if pooled[i]["prompt_id"] != "L1":
            others.append(pooled[i]["refusal"])
    add("refusal_other_max", "Max refusal share at other prompts", max(others) if others else None)
    return rows


def pooled_means(frame: pd.DataFrame) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for f in range(len(FACTOR_COLS)):
        column = FACTOR_COLS[f]
        out[column] = float(frame.groupby("model_requested")[column].mean().mean()) if len(frame) else None
    return out


def run_all(ws: Workspace, config: Config, store: Store, asof: str | None, universe: str,
            planned: dict[str, int], draws: int | None = None, cutoffs: dict[str, str] | None = None,
            master: pd.DataFrame | None = None) -> dict[str, Any]:
    settings = config.experiment.get("analysis", {})
    draws = int(draws or settings.get("bootstrap_draws", 2000))
    rng = np.random.default_rng(int(settings.get("seed", 1)))
    from .query_classify import classify_all

    classify_all(store, master)
    data = load(store, config, asof, universe)
    result: dict[str, Any] = {"generated_ts_utc": utc_now_iso(), "asof": asof, "universe": universe,
                              "workspace": ws.name, "bootstrap_draws": draws}
    log.info("overlap ...")
    result["overlap"] = overlap_analysis(data, draws, rng)
    log.info("consensus ...")
    result["consensus"] = consensus_analysis(data, float(settings.get("consensus_threshold", 0.5)))
    stage_a = data.pexp[(data.pexp["stage"] == "A") & (data.pexp["language"] == "en")]
    flags = data.flagships()
    log.info("exposures ...")
    framing_all = by_framing(data, stage_a, draws, rng)
    framing_flag = by_framing(data, stage_a, draws, rng, flags)
    result["exposures"] = {
        "by_model_stage_a": by_model(data, stage_a, draws, rng),
        "by_framing_all": framing_all,
        "by_framing_flagships": framing_flag,
        "sector_mix_stage_a": sector_mix(data, stage_a),
        "prompt_effect_vs_noise": prompt_effect_vs_noise(stage_a),
        "dispersion_vs_overlap": dispersion_vs_overlap(framing_all, result["overlap"].get("A", {})),
        "freeform_flagships_pooled": pooled_means(stage_a[stage_a["model_requested"].isin(flags)]),
        "freeform_all_pooled": pooled_means(stage_a),
        "equal_weight_stage_a": pooled_means(data.pexp_equal[data.pexp_equal["stage"] == "A"]),
    }
    log.info("mandates ...")
    result["mandates"] = mandate_analysis(data, draws, rng)
    log.info("search ...")
    result["search"] = search_analysis(data, draws, rng)
    result["queries"] = query_analysis(store, ws.manual / "query_labels_gold.csv")
    result["refusals"] = refusal_analysis(data)
    result["compliance"] = compliance_analysis(data, settings.get("compliance", {
        "target_exposure_min": 0.25, "max_weight": 0.15, "min_sectors": 4, "min_mcap_usd": 5e9}))
    result["reasoning"] = reasoning_analysis(data)
    result["generations"] = generation_analysis(data)
    result["language"] = language_analysis(data)
    result["attention"] = attention_analysis(data)
    log.info("extensions ...")
    result["crowding"] = crowding_analysis(data)
    result["factor_space"] = factor_space_analysis(data, rng)
    result["weighting"] = weighting_analysis(data)
    result["geography"] = geography_analysis(data)
    result["staleness"] = staleness_analysis(data, cutoffs)
    result["ops"] = ops_analysis(data, store, planned)
    result["drops"] = drops(store)
    result["factor_runs"] = read_json(ws.processed / "factor_runs.json", default={})
    result["resolution_summary"] = read_json(ws.processed / "resolution_summary.json", default={})
    result["paper_comparison"] = paper_comparison(result)
    write_json(ws.outputs / "analysis.json", result)
    _write_tables(ws, result)
    return result


def _write_tables(ws: Workspace, result: dict[str, Any]) -> None:
    ws.tables.mkdir(parents=True, exist_ok=True)
    tables = {
        "exposures_by_model_stage_a.csv": result["exposures"]["by_model_stage_a"],
        "exposures_by_framing.csv": result["exposures"]["by_framing_all"],
        "mandate_deltas.csv": result["mandates"]["deltas"],
        "refusals.csv": result["refusals"]["cells"],
        "compliance.csv": result["compliance"]["rows"],
        "generations.csv": result["generations"]["rows"],
        "weighting.csv": result["weighting"]["rows"],
        "staleness.csv": result["staleness"]["rows"],
        "paper_comparison.csv": result["paper_comparison"],
        "ops_by_model_stage.csv": result["ops"]["by_model_stage"],
        "attention.csv": result["attention"].get("rows", []),
    }
    names = list(tables.keys())
    for i in range(len(names)):
        pd.DataFrame(tables[names[i]]).to_csv(ws.tables / names[i], index=False)
