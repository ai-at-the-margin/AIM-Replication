"""`aim demo`: the full pipeline on simulated models and a synthetic market.

verify -> plan (dry run) -> collect A/B/C -> parse -> resolve -> factors (ACWI proxy
and US broad) -> exposures -> analyze -> figures -> report -> dashboard export.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import shutil
import time
from typing import Any

import pandas as pd

from ..analysis.run import run_all
from ..collect.planner import plan, plan_stage
from ..collect.runner import Runner
from ..context import DEMO_ASOF, Context
from ..dashboard.export import export
from ..discovery import build_screen
from ..figures import render_all
from ..phase0 import run_verify, verify_wrds_synthetic
from ..pipeline import (
    build_factors,
    compute_exposures,
    load_master,
    parse_calls,
    resolve_holdings,
    save_master,
)
from ..report import write_results
from ..utils import get_logger, write_json
from .simulator import PROFILES

log = get_logger(__name__)


def _write_gold(ctx: Context, sample: int = 240) -> int:
    transport = ctx._transport
    if transport is None or len(transport.gold) == 0:
        return 0
    events = ctx.store.query("SELECT call_id, event_idx, query_text FROM search_events WHERE query_text IS NOT NULL")
    rows = []
    records = events.to_dict("records")
    for i in range(len(records)):
        kind = transport.gold.get((records[i]["call_id"], records[i]["query_text"]))
        if kind is not None:
            rows.append({"call_id": records[i]["call_id"], "event_idx": records[i]["event_idx"],
                         "query_text": records[i]["query_text"], "gold_class": kind,
                         "labeller": "simulator (synthetic gold)"})
    frame = pd.DataFrame(rows)
    if len(frame) > sample:
        frame = frame.sample(n=sample, random_state=7)
    frame.to_csv(ctx.ws.manual / "query_labels_gold.csv", index=False)
    return len(frame)


def run_demo(ctx: Context, fresh: bool = False, draws: int | None = None) -> dict[str, Any]:
    started = time.time()
    if fresh and ctx.ws.root.exists():
        ctx.close()
        shutil.rmtree(ctx.ws.root)
        ctx._store = None
        ctx._world = None
        ctx._transport = None
    ctx.ws.ensure()
    summary: dict[str, Any] = {"workspace": str(ctx.ws.root)}
    world = ctx.world()
    log.info("demo world ready: %d issuers", len(world.company_frame))
    wrds_result = verify_wrds_synthetic(ctx.config, ctx.source(), DEMO_ASOF + dt.timedelta(days=1))
    run_verify(ctx.ws, ctx.config, ctx.transport_factory(), wrds_result)
    stages = ["A", "B", "C"]
    for s in range(len(stages)):
        specs = plan_stage(ctx.config, stages[s])
        runner = Runner(ctx.ws, ctx.config, ctx.store, ctx.transport_factory(), f"demo-{stages[s]}", None,
                        require_keys=False, unthrottled=True)
        result = asyncio.run(runner.run(specs))
        summary[f"collect_{stages[s]}"] = result.as_dict()
        log.info("stage %s: %s", stages[s], result.as_dict())
    write_json(ctx.ws.processed / "collection_window.json",
               {"start": DEMO_ASOF.isoformat(), "end": DEMO_ASOF.isoformat(), "configured": {}})
    summary["gold_labels"] = _write_gold(ctx)
    summary["parse"] = parse_calls(ctx.store)
    master = load_master(ctx.ws)
    if master is None:
        master = ctx.source().security_master(DEMO_ASOF)
        save_master(ctx.ws, master, DEMO_ASOF)
    summary["resolve"] = resolve_holdings(ctx.ws, ctx.store, master)
    for universe in ("us_broad", "acwi_proxy"):
        factor_summary = build_factors(ctx.ws, ctx.config, ctx.store, ctx.source(), DEMO_ASOF, universe)
        summary[f"factors_{universe}"] = {"universe_count": factor_summary.get("universe_count"),
                                          "capweighted_check": factor_summary.get("capweighted_universe_exposure")}
    asof = DEMO_ASOF.isoformat()
    summary["exposures"] = compute_exposures(ctx.store, asof, "acwi_proxy")
    write_json(ctx.ws.processed / "crsp_validation.json",
               {"pass": None, "note": "synthetic demo world has no CRSP counterpart"})
    planned: dict[str, int] = {}
    all_specs = plan(ctx.config, stages)
    for i in range(len(all_specs)):
        planned[all_specs[i].stage] = planned.get(all_specs[i].stage, 0) + 1
    cutoffs = {}
    keys = list(PROFILES.keys())
    for i in range(len(keys)):
        cutoffs[keys[i]] = PROFILES[keys[i]]["knowledge"]
    result = run_all(ctx.ws, ctx.config, ctx.store, asof, "acwi_proxy", planned, draws, cutoffs, master)
    summary["figures"] = len(render_all(result, ctx.ws.figures, True))
    summary["results_md"] = write_results(ctx.ws)
    try:
        summary["discovery"] = build_screen(ctx.ws, ctx.config, ctx.store, asof, "acwi_proxy", "MOMENTUM", 100)
    except Exception as exc:
        summary["discovery"] = f"skipped: {exc}"
    summary["dashboard"] = str(export(ctx.ws, ctx.config, ctx.store))
    summary["seconds"] = round(time.time() - started, 1)
    return summary
