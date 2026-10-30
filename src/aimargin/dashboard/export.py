"""Export everything the frontend shows into <workspace>/dashboard/*.json.

Files:
  meta.json          dataset label, synthetic flag, versions, as-of, roster
  status.json        build phases with live acceptance checks, verification, sources, budget
  analysis.json      every analysis (copied from outputs/analysis.json)
  portfolios.json    one row per call (outcome, exposures, cost) for the explorer
  details/<id>.json  per-call detail: response text, holdings, search queries

WRDS licensing (BUILD_BRIEF §10): the live export contains derived exposures for
resolved names only, never raw vendor rows; data/dashboard is git-ignored.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from ..collect.cost import estimate_plan
from ..collect.planner import plan
from ..prompts import FREEFORM_IDS, MANDATE_IDS, build_prompt, experiment_version, prompt_version
from ..settings import REPO_ROOT, Config, Workspace
from ..store.db import Store
from ..utils import read_json, round_or_none, utc_now_iso, write_json

DEVIATIONS = [
    {"item": "Providers", "paper": "16 models, 6 providers", "ours": "12 models, 2 providers (OpenAI, Anthropic)"},
    {"item": "Prompts", "paper": "not published", "ours": "our own frozen prompts (prompt_version hash)"},
    {"item": "Factor model", "paper": "MSCI Barra exposures", "ours": "Barra-style replica built from WRDS"},
    {"item": "Universe", "paper": "global universe (Barra)", "ours": "Compustat ACWI proxy (85% cap per country) unless Datastream has an MSCI list"},
    {"item": "Cap weighting", "paper": "free float", "ours": "full market cap"},
    {"item": "Risk-free rate", "paper": "-", "ours": "Fama-French daily rf, forward-filled past 2026-09-30 (rf_filled)"},
    {"item": "Prices", "paper": "Bloomberg", "ours": "Compustat daily (CRSP only for 2024-2025 validation)"},
    {"item": "Fundamentals", "paper": "Barra", "ours": "Compustat Snapshot point-in-time (fallback: restated, lagged entry)"},
    {"item": "Outcome classes", "paper": "valid vs not", "ours": "adds excess_names (>10 issuers) and api_error"},
]


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict("records")


def phases(ws: Workspace, config: Config, store: Store, planned: dict[str, int]) -> list[dict[str, Any]]:
    state = read_json(ws.processed / "phase0_state.json", default={}) or {}
    factor_runs = read_json(ws.processed / "factor_runs.json", default={}) or {}
    resolution = read_json(ws.processed / "resolution_summary.json", default={}) or {}
    crsp = read_json(ws.processed / "crsp_validation.json", default=None)
    calls = store.query("SELECT stage, model_requested, prompt_id, status FROM calls")
    completed = calls[calls["status"] == "completed"]
    out = []
    providers = state.get("providers") or {}
    providers_ok = len(providers) > 0
    names = list(providers.keys())
    for i in range(len(names)):
        test = providers[names[i]].get("search_test") or {}
        if not test.get("ok") or providers[names[i]].get("models_missing"):
            providers_ok = False
    wrds = state.get("wrds") or {}
    p0 = "done" if providers_ok and wrds.get("connected") and not state.get("halt") else (
        "blocked" if state else "todo")
    out.append({"phase": 0, "name": "aim verify", "status": p0,
                "criteria": [
                    {"text": "Model ids confirmed and search queries captured", "ok": providers_ok},
                    {"text": "WRDS schemas probed, effective dates computed", "ok": bool(wrds.get("connected"))},
                    {"text": "Every required input has a working source", "ok": bool(state) and not state.get("halt")},
                ], "detail": "; ".join(state.get("halt") or []) or (wrds.get("error") or "")})
    design = {"A": 1440, "B": 720, "C": 480}
    plan_ok = planned.get("A") == design["A"] and planned.get("B") == design["B"] and planned.get("C") == design["C"]
    out.append({"phase": 1, "name": "Skeleton and config", "status": "done" if plan_ok else "check",
                "criteria": [{"text": f"Stage A plans 1,440 calls (now {planned.get('A')})", "ok": planned.get("A") == 1440},
                             {"text": f"Stage B plans 720 calls (now {planned.get('B')})", "ok": planned.get("B") == 720},
                             {"text": f"Stage C plans 480 calls (now {planned.get('C')})", "ok": planned.get("C") == 480}]})
    cells = completed.groupby(["stage", "model_requested", "prompt_id"]).size()
    pilot_ok = len(cells) > 0 and int(cells.min()) >= 2
    out.append({"phase": 2, "name": "Adapters and pilot", "status": "done" if pilot_ok else "todo",
                "criteria": [{"text": "--pilot 2 succeeds for every cell, offline and connected", "ok": pilot_ok}]})
    has_factors = len(factor_runs) > 0
    crsp_ok = bool(crsp and crsp.get("pass"))
    out.append({"phase": 3, "name": "WRDS layer and factor engine",
                "status": "done" if has_factors and crsp_ok else ("partial" if has_factors else "todo"),
                "criteria": [{"text": "Factor exposures built and universe sizes logged", "ok": has_factors},
                             {"text": "CRSP validation passes (corr > 0.99, median |diff| < 1bp)", "ok": crsp_ok},
                             {"text": "Point-in-time vs restated comparison produced",
                              "ok": (ws.tables / "pit_vs_restated_acwi_proxy.csv").exists()}]})
    rate = resolution.get("resolution_rate")
    out.append({"phase": 4, "name": "Parsing and resolution",
                "status": "done" if rate is not None and rate >= 0.99 else ("check" if rate is not None else "todo"),
                "criteria": [{"text": f"At least 99% of holdings resolved (now {rate if rate is not None else 'n/a'})",
                              "ok": rate is not None and rate >= 0.99}]})
    collected = {}
    for stage in ("A", "B", "C"):
        collected[stage] = int((completed["stage"] == stage).sum())
    full = collected["A"] >= design["A"] and collected["B"] >= design["B"] and collected["C"] >= design["C"]
    out.append({"phase": 5, "name": "Full collection", "status": "done" if full else ("running" if len(completed) else "todo"),
                "criteria": [
                    {"text": f"Stage A: {collected['A']:,} / 1,440 completed", "ok": collected["A"] >= 1440},
                    {"text": f"Stage B: {collected['B']:,} / 720 completed", "ok": collected["B"] >= 720},
                    {"text": f"Stage C: {collected['C']:,} / 480 completed", "ok": collected["C"] >= 480}]})
    results = (ws.docs_dir / "RESULTS.md").exists()
    out.append({"phase": 6, "name": "Analyses, figures and report", "status": "done" if results else "todo",
                "criteria": [{"text": "RESULTS.md compares our numbers with the paper", "ok": results},
                             {"text": "Figures 1-7 saved as PNG + CSV", "ok": (ws.figures / "fig7_queries.png").exists()}]})
    us_run = False
    keys = list(factor_runs.keys())
    for i in range(len(keys)):
        if keys[i].endswith(":us_broad"):
            us_run = True
    out.append({"phase": 7, "name": "Extensions", "status": "partial" if us_run else "designed",
                "criteria": [{"text": "us_broad universe exposures built", "ok": us_run},
                             {"text": "Forced-discovery screen available (`aim discovery`)",
                              "ok": (ws.outputs / "discovery").exists()},
                             {"text": "Repeat at second and third dates", "ok": len(factor_runs) >= 3}]})
    return out


def export(ws: Workspace, config: Config, store: Store, target: Path | None = None) -> Path:
    target = target or ws.dashboard
    if target.exists():
        shutil.rmtree(target)
    (target / "details").mkdir(parents=True, exist_ok=True)
    specs = plan(config, ["A", "B", "C"])
    planned: dict[str, int] = {}
    for i in range(len(specs)):
        planned[specs[i].stage] = planned.get(specs[i].stage, 0) + 1
    calls_frame = store.query("SELECT * FROM calls")
    estimate = estimate_plan(config, specs, calls_frame, batch_stages=["A", "B"])
    budget = {"estimated_total_usd": float(estimate["est_cost_usd"].sum()) if len(estimate) else 0.0,
              "by_stage": estimate.groupby("stage")["est_cost_usd"].sum().round(2).to_dict() if len(estimate) else {},
              "caps": config.experiment.get("collection", {}).get("budget_cap_usd", {}),
              "spent_usd": float(calls_frame["est_cost_usd"].fillna(0).sum()) if len(calls_frame) else 0.0}
    analysis = read_json(ws.outputs / "analysis.json", default={}) or {}
    roster = []
    models = config.model_list(include_optional=True)
    cutoffs = {}
    if ws.is_demo:
        from ..demo.simulator import PROFILES

        keys = list(PROFILES.keys())
        for i in range(len(keys)):
            cutoffs[keys[i]] = PROFILES[keys[i]]["knowledge"][:7]
    for i in range(len(models)):
        roster.append({"id": models[i]["id"], "provider": models[i]["provider"], "role": models[i].get("role"),
                       "generation": models[i].get("generation"), "size_class": models[i].get("size_class"),
                       "stages": models[i].get("stages"), "optional": bool(models[i].get("optional")),
                       "knowledge_cutoff": models[i].get("knowledge_cutoff") or cutoffs.get(models[i]["id"]),
                       "price_in_per_m": models[i].get("price_in_per_m"),
                       "price_out_per_m": models[i].get("price_out_per_m"),
                       "price_verified": models[i].get("price_verified")})
    prompts = []
    for i in range(len(FREEFORM_IDS)):
        p = build_prompt(config, FREEFORM_IDS[i], "en")
        prompts.append({"id": p.prompt_id, "family": p.family, "label": p.label, "text": p.text})
    for i in range(len(MANDATE_IDS)):
        p = build_prompt(config, MANDATE_IDS[i], "en")
        prompts.append({"id": p.prompt_id, "family": p.family, "label": p.label, "text": p.text})
    meta = {
        "dataset": ws.name, "synthetic": ws.is_demo, "generated_ts_utc": utc_now_iso(),
        "experiment_version": experiment_version(config), "prompt_version": prompt_version(config),
        "asof": analysis.get("asof"), "universe": analysis.get("universe"), "roster": roster, "prompts": prompts,
        "planned": planned, "repo": "AI at the Margin replication",
    }
    write_json(target / "meta.json", meta)
    state = read_json(ws.processed / "phase0_state.json", default={}) or {}
    source_log = store.query("SELECT * FROM source_log ORDER BY asof_date DESC, input")
    status = {
        "phases": phases(ws, config, store, planned), "budget": budget, "planned": planned,
        "verification": state, "source_log": _frame_records(source_log), "deviations": DEVIATIONS,
        "resolution": read_json(ws.processed / "resolution_summary.json", default={}),
        "factor_runs": read_json(ws.processed / "factor_runs.json", default={}),
        "crsp_validation": read_json(ws.processed / "crsp_validation.json", default=None),
        "batches": read_json(ws.processed / "batches.json", default=[]),
    }
    write_json(target / "status.json", status)
    write_json(target / "analysis.json", analysis, indent=None)
    _export_portfolios(store, target, analysis.get("asof"), analysis.get("universe") or "acwi_proxy")
    return target


def _export_portfolios(store: Store, target: Path, asof: str | None, universe: str) -> None:
    calls = store.query(
        "SELECT c.call_id, c.stage, c.provider, c.model_requested, c.role, c.prompt_id, c.language, c.rep, "
        "c.search_enabled, c.search_count, c.status, c.est_cost_usd, c.input_tokens, c.output_tokens, "
        "c.reasoning_tokens, c.latency_s, c.attempts, c.stop_reason, c.model_returned, c.via_batch, "
        "p.outcome, p.parse_method, p.n_names_raw, p.n_issuers, p.weights_provided "
        "FROM calls c LEFT JOIN portfolios p USING (call_id)")
    exposures = store.query("SELECT * FROM portfolio_exposures WHERE weighting = 'model' AND asof_date = ? "
                            "AND universe = ?", [asof, universe]) if asof else pd.DataFrame()
    exp_map: dict[str, dict[str, Any]] = {}
    if len(exposures):
        records = exposures.to_dict("records")
        for i in range(len(records)):
            exp_map[records[i]["call_id"]] = records[i]
    names_frame = store.query("SELECT call_id, raw_ticker, resolved_name FROM holdings ORDER BY call_id, position_idx")
    names_by_call: dict[str, list[str]] = {}
    name_records = _frame_records(names_frame)
    for i in range(len(name_records)):
        parts = names_by_call.setdefault(name_records[i]["call_id"], [])
        parts.append(f"{name_records[i].get('raw_ticker') or ''} {name_records[i].get('resolved_name') or ''}".strip())
    rows = []
    records = _frame_records(calls)
    factor_cols = ["size", "value", "quality", "momentum", "lowvol", "beta", "mom_12_1"]
    for i in range(len(records)):
        r = records[i]
        e = exp_map.get(r["call_id"], {})
        for k in range(len(factor_cols)):
            r[factor_cols[k]] = round_or_none(e.get(factor_cols[k]), 3)
        r["coverage_weight"] = round_or_none(e.get("coverage_weight"), 3)
        r["names"] = " | ".join(names_by_call.get(r["call_id"], []))
        r["est_cost_usd"] = round_or_none(r.get("est_cost_usd"), 5)
        rows.append(r)
    write_json(target / "portfolios.json", rows, indent=None)
    responses = store.query("SELECT call_id, final_text, reasoning_text, reasoning_word_count FROM responses")
    holdings = store.query("SELECT * FROM holdings ORDER BY call_id, position_idx")
    search = store.query("SELECT * FROM search_events ORDER BY call_id, event_idx")
    issuer_exp = store.query("SELECT issuer_id, size, value, quality, momentum, lowvol, beta, mcap_usd FROM exposures "
                             "WHERE asof_date = ? AND universe = ?", [asof, universe]) if asof else pd.DataFrame()
    exp_by_issuer: dict[str, dict[str, Any]] = {}
    if len(issuer_exp):
        recs = issuer_exp.to_dict("records")
        for i in range(len(recs)):
            exp_by_issuer[recs[i]["issuer_id"]] = recs[i]
    resp_map = {}
    recs = _frame_records(responses)
    for i in range(len(recs)):
        resp_map[recs[i]["call_id"]] = recs[i]
    hold_map: dict[str, list[dict[str, Any]]] = {}
    recs = _frame_records(holdings)
    keep = ["position_idx", "raw_ticker", "raw_exchange", "raw_name", "raw_weight", "weight_norm", "issuer_id",
            "resolved_name", "resolved_ticker", "exchange_code", "country", "gics_sector", "is_adr", "is_china_a_share",
            "resolution_method", "resolution_confidence", "resolution_status", "duplicate_of", "in_universe_acwi"]
    for i in range(len(recs)):
        row = {}
        for k in range(len(keep)):
            row[keep[k]] = recs[i].get(keep[k])
        issuer = recs[i].get("issuer_id")
        if issuer and issuer in exp_by_issuer:
            ex = exp_by_issuer[issuer]
            row["exposure"] = {"size": round_or_none(ex.get("size"), 3), "value": round_or_none(ex.get("value"), 3),
                               "quality": round_or_none(ex.get("quality"), 3),
                               "momentum": round_or_none(ex.get("momentum"), 3),
                               "lowvol": round_or_none(ex.get("lowvol"), 3), "beta": round_or_none(ex.get("beta"), 3),
                               "mcap_bn": round_or_none((ex.get("mcap_usd") or 0) / 1e9, 2)}
        hold_map.setdefault(recs[i]["call_id"], []).append(row)
    search_map: dict[str, list[dict[str, Any]]] = {}
    recs = _frame_records(search)
    for i in range(len(recs)):
        urls = json.loads(recs[i].get("result_urls_json") or "[]")
        search_map.setdefault(recs[i]["call_id"], []).append({
            "idx": recs[i]["event_idx"], "type": recs[i]["provider_event_type"], "query": recs[i]["query_text"],
            "class": recs[i].get("query_class"), "caller": recs[i].get("caller"), "n_results": len(urls),
            "error": recs[i].get("error_code"), "mentioned": json.loads(recs[i].get("mentioned_tickers_json") or "[]")})
    for i in range(len(rows)):
        call_id = rows[i]["call_id"]
        resp = resp_map.get(call_id, {})
        detail = {
            "call": rows[i],
            "final_text": (resp.get("final_text") or "")[:12000],
            "reasoning_excerpt": (resp.get("reasoning_text") or "")[:2500],
            "reasoning_word_count": resp.get("reasoning_word_count"),
            "holdings": hold_map.get(call_id, []),
            "searches": search_map.get(call_id, []),
            "exposure": exp_map.get(call_id),
        }
        write_json(target / "details" / f"{call_id}.json", detail, indent=None)


def frontend_dist() -> Path:
    return REPO_ROOT / "frontend" / "dist"
