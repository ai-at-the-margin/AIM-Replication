"""`aim` command-line interface (BUILD_BRIEF §3)."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
import uuid

import click
import pandas as pd

from .context import Context, make_context
from .utils import get_logger, read_json, stable_hash, write_json

log = get_logger("aim")
STAGES = ["A", "B", "C"]


def _ctx(obj: dict) -> Context:
    return obj["ctx"]


def _asof(ctx: Context, value: str | None) -> dt.date:
    return dt.date.fromisoformat(value) if value else ctx.default_asof()


@click.group()
@click.option("--demo", is_flag=True, help="Use the synthetic demo workspace (simulated models + synthetic WRDS).")
@click.option("--data-dir", default=None, help="Live workspace root (default ./data or $AIM_DATA_DIR).")
@click.pass_context
def main(click_ctx: click.Context, demo: bool, data_dir: str | None) -> None:
    """AI at the Margin: LLM-portfolio replication pipeline."""
    if click_ctx.invoked_subcommand == "figures":
        from .settings import get_workspace

        click_ctx.obj = {"figure_workspace": get_workspace("demo" if demo else "live", data_dir)}
        return
    click_ctx.obj = {"ctx": make_context(demo, data_dir)}
    click_ctx.call_on_close(lambda: click_ctx.obj["ctx"].close())


# ------------------------------------------------------------------ Phase 0
@main.command()
@click.option("--providers/--no-providers", default=True)
@click.option("--wrds/--no-wrds", "check_wrds", default=True)
@click.option("--no-search-test", is_flag=True, help="Skip the one paid search call per provider.")
@click.pass_obj
def verify(obj: dict, providers: bool, check_wrds: bool, no_search_test: bool) -> None:
    """Phase 0: confirm models, search capture, WRDS schemas, effective dates and sources."""
    from .phase0 import run_verify, verify_wrds_synthetic

    ctx = _ctx(obj)
    wrds_result = None
    if check_wrds and ctx.demo:
        wrds_result = verify_wrds_synthetic(ctx.config, ctx.source(), ctx.default_asof() + dt.timedelta(days=1))
    state = run_verify(ctx.ws, ctx.config, ctx.transport_factory(), wrds_result, providers, check_wrds,
                       not no_search_test)
    click.echo(f"wrote {ctx.ws.docs_dir / 'PHASE0_VERIFICATION.md'}")
    providers_state = state.get("providers") or {}
    names = list(providers_state.keys())
    for i in range(len(names)):
        p = providers_state[names[i]]
        test = p.get("search_test") or {}
        click.echo(f"  {names[i]:9s} key={p.get('key_present')} confirmed={len(p.get('models_ok') or [])} "
                   f"missing={p.get('models_missing') or []} search_test={test.get('ok')} {p.get('list_error') or ''}")
    wrds = state.get("wrds") or {}
    click.echo(f"  wrds      connected={wrds.get('connected')} {wrds.get('error') or ''}")
    if state.get("halt"):
        click.echo("HALT: " + "; ".join(state["halt"]))
        sys.exit(2)


def _ensure_verified(ctx: Context, scope: str, skip: bool) -> None:
    """BUILD_BRIEF §0.2: verification runs automatically at the start of every pipeline run."""
    from .phase0 import is_fresh, run_verify, verify_wrds_synthetic

    if skip or is_fresh(ctx.ws, ctx.config, scope):
        return
    log.info("running aim verify (%s) first ...", scope)
    wrds_result = None
    if scope == "wrds" and ctx.demo:
        wrds_result = verify_wrds_synthetic(ctx.config, ctx.source(), ctx.default_asof() + dt.timedelta(days=1))
    run_verify(ctx.ws, ctx.config, ctx.transport_factory(), wrds_result, providers=scope == "providers",
               wrds=scope == "wrds", search_test=False)


def _check_batch(specs) -> None:
    from .collect.batch import check_batch_plan

    try:
        check_batch_plan(specs)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


def _plan_collection(ctx: Context, stage: str, pilot: int | None):
    from .collect.planner import plan_stage

    try:
        return plan_stage(ctx.config, stage, pilot)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


# ------------------------------------------------------------- Phases 1, 2, 5
def _dryrun_marker(ctx: Context, stage: str, pilot: int | None):
    return ctx.ws.processed / f"dryrun_{stage}{'_pilot' + str(pilot) if pilot else ''}.json"


@main.command()
@click.option("--stage", type=click.Choice(STAGES), required=True)
@click.option("--dry-run", is_flag=True, help="Show planned calls and estimated cost; required before collecting.")
@click.option("--pilot", type=int, default=None, help="Only the first N repetitions per cell.")
@click.option("--batch", is_flag=True, help="Price Stages A/B at the Batch API discount.")
@click.pass_obj
def plan(obj: dict, stage: str, dry_run: bool, pilot: int | None, batch: bool) -> None:
    """Expand the design into calls and estimate the cost."""
    from .collect.cost import estimate_plan, summarise_estimate

    ctx = _ctx(obj)
    specs = _plan_collection(ctx, stage, pilot)
    if batch:
        _check_batch(specs)
    calls = ctx.store.query("SELECT * FROM calls")
    estimate = estimate_plan(ctx.config, specs, calls, batch_stages=[stage] if batch else [])
    summary = summarise_estimate(estimate)
    with pd.option_context("display.width", 160, "display.max_rows", 200):
        click.echo(summary.to_string(index=False))
    total = float(estimate["est_cost_usd"].sum()) if len(estimate) else 0.0
    click.echo(f"\nStage {stage}: {len(specs):,} planned calls, estimated ${total:,.2f}"
               + (" (batch pricing)" if batch else ""))
    unverified = summary[summary["price_verified"] == False]["model"].tolist()  # noqa: E712
    if len(unverified) > 0:
        click.echo(f"note: placeholder prices (set conservatively) for {', '.join(unverified)}")
    if dry_run:
        ids = []
        for i in range(len(specs)):
            ids.append(specs[i].call_id)
        write_json(_dryrun_marker(ctx, stage, pilot), {"plan_hash": stable_hash(ids), "calls": len(specs),
                                                       "estimated_usd": total})
        click.echo(f"dry run recorded: {_dryrun_marker(ctx, stage, pilot).name}")


@main.command()
@click.option("--stage", type=click.Choice(STAGES), required=True)
@click.option("--pilot", type=int, default=None)
@click.option("--batch", is_flag=True, help="Submit through the providers' Batch APIs (Stages A and B).")
@click.option("--resume", is_flag=True, help="Also retry calls that previously failed with transport errors.")
@click.option("--skip-verify", is_flag=True)
@click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
@click.pass_obj
def collect(obj: dict, stage: str, pilot: int | None, batch: bool, resume: bool, skip_verify: bool, yes: bool) -> None:
    """Send the planned calls (idempotent; resumable)."""
    from .collect import batch as batch_mod
    from .collect.runner import Runner, summarise_calls

    ctx = _ctx(obj)
    specs = _plan_collection(ctx, stage, pilot)
    ids = []
    for i in range(len(specs)):
        ids.append(specs[i].call_id)
    marker = read_json(_dryrun_marker(ctx, stage, pilot), default=None)
    if not ctx.demo and (marker is None or marker.get("plan_hash") != stable_hash(ids)):
        raise click.ClickException(f"run `aim plan --stage {stage}{' --pilot ' + str(pilot) if pilot else ''} "
                                   "--dry-run` first (BUILD_BRIEF §0.4: never spend budget without a dry run)")
    if batch:
        if stage == "C":
            raise click.ClickException("Stage C uses web search and is never batched")
        _check_batch(specs)
    _ensure_verified(ctx, "providers", skip_verify)
    if not yes and not ctx.demo:
        click.confirm(f"Send {len(specs):,} calls for stage {stage} (estimated ${marker['estimated_usd']:,.2f})?",
                      abort=True)
    run_id = f"{stage}-{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    window = dict(ctx.config.experiment.get("collection_window") or {})
    state_path = ctx.ws.processed / "collection_window.json"
    recorded = read_json(state_path, default={}) or {}
    recorded.setdefault("start", dt.date.today().isoformat() if not ctx.demo else ctx.default_asof().isoformat())
    recorded["end"] = dt.date.today().isoformat() if not ctx.demo else ctx.default_asof().isoformat()
    recorded["configured"] = window
    write_json(state_path, recorded)
    if batch:
        transport = ctx.transport_factory()()
        created = asyncio.run(batch_mod.submit(ctx.ws, ctx.config, ctx.store, transport, specs, run_id))
        click.echo(f"submitted {len(created)} batch(es); run `aim batch-poll --stage {stage}` to collect results")
        return
    cap = ctx.config.experiment.get("collection", {}).get("budget_cap_usd", {}).get(stage)
    runner = Runner(ctx.ws, ctx.config, ctx.store, ctx.transport_factory(), run_id,
                    None if ctx.demo else cap, require_keys=not ctx.demo, unthrottled=ctx.demo)
    summary = asyncio.run(runner.run(specs, resume))
    click.echo(json.dumps(summary.as_dict(), indent=2))
    with pd.option_context("display.width", 160, "display.max_rows", 200):
        click.echo(summarise_calls(ctx.store).to_string(index=False))


@main.command("batch-poll")
@click.option("--stage", type=click.Choice(["A", "B"]), required=True)
@click.pass_obj
def batch_poll(obj: dict, stage: str) -> None:
    """Collect finished Batch API results."""
    from .collect import batch as batch_mod
    from .collect.planner import plan_stage

    ctx = _ctx(obj)
    specs = plan_stage(ctx.config, stage)
    by_id = {}
    for i in range(len(specs)):
        by_id[specs[i].call_id] = specs[i]
    counts = asyncio.run(batch_mod.poll(ctx.ws, ctx.config, ctx.store, ctx.transport_factory()(), by_id))
    click.echo(json.dumps(counts))


# --------------------------------------------------------------- Phase 4
@main.command()
@click.option("--force", is_flag=True, help="Re-parse calls that already have a portfolio row.")
@click.pass_obj
def parse(obj: dict, force: bool) -> None:
    """Extract portfolios and classify outcomes."""
    from .pipeline import parse_calls

    click.echo(json.dumps(parse_calls(_ctx(obj).store, force), indent=2))


@main.command()
@click.option("--asof", default=None)
@click.option("--refresh-master", is_flag=True)
@click.pass_obj
def resolve(obj: dict, asof: str | None, refresh_master: bool) -> None:
    """Resolve tickers to trading items and issuers (CIQ first)."""
    from .pipeline import load_master, resolve_holdings, save_master

    ctx = _ctx(obj)
    date = _asof(ctx, asof)
    master = None if refresh_master else load_master(ctx.ws)
    if master is None:
        if not ctx.demo:
            _ensure_verified(ctx, "wrds", False)
        master = ctx.source().security_master(date)
        save_master(ctx.ws, master, date)
    click.echo(json.dumps(resolve_holdings(ctx.ws, ctx.store, master), indent=2, default=str))


# --------------------------------------------------------------- Phase 3
@main.group()
def wrds() -> None:
    """WRDS pulls and validation."""


@wrds.command("pull")
@click.option("--asof", default=None)
@click.option("--universe", type=click.Choice(["acwi_proxy", "us_broad"]), default="acwi_proxy")
@click.pass_obj
def wrds_pull(obj: dict, asof: str | None, universe: str) -> None:
    """Pull and cache the security master and the as-of price snapshot."""
    from .pipeline import save_master

    ctx = _ctx(obj)
    _ensure_verified(ctx, "wrds", False)
    date = _asof(ctx, asof)
    source = ctx.source()
    master = source.security_master(date)
    save_master(ctx.ws, master, date)
    snapshot = source.price_snapshot(date)
    click.echo(f"security master: {len(master):,} trading items; price snapshot {date}: {len(snapshot):,} rows")


@wrds.command("validate-crsp")
@click.option("--n-issuers", default=300, help="Largest US issuers to compare.")
@click.pass_obj
def wrds_validate_crsp(obj: dict, n_issuers: int) -> None:
    """Compare Compustat-built returns with CRSP over 2024-2025 (BUILD_BRIEF §2.6)."""
    from .wrds_io.crsp_validate import run_validation

    ctx = _ctx(obj)
    if ctx.demo:
        write_json(ctx.ws.processed / "crsp_validation.json",
                   {"pass": None, "note": "synthetic demo world has no CRSP counterpart"})
        click.echo("demo: CRSP validation not applicable")
        return
    result = run_validation(ctx.ws, ctx.config, ctx.source(), n_issuers)
    write_json(ctx.ws.processed / "crsp_validation.json", result)
    click.echo(json.dumps(result, indent=2, default=str))


@main.group()
def factors() -> None:
    """Factor exposures."""


@factors.command("build")
@click.option("--asof", default=None)
@click.option("--universe", type=click.Choice(["acwi_proxy", "us_broad"]), default="acwi_proxy")
@click.option("--skip-verify", is_flag=True)
@click.pass_obj
def factors_build(obj: dict, asof: str | None, universe: str, skip_verify: bool) -> None:
    """Build descriptors and standardised exposures for one as-of date and universe."""
    from .pipeline import build_factors

    ctx = _ctx(obj)
    _ensure_verified(ctx, "wrds", skip_verify)
    summary = build_factors(ctx.ws, ctx.config, ctx.store, ctx.source(), _asof(ctx, asof), universe)
    click.echo(json.dumps(summary, indent=2, default=str))


@main.command()
@click.option("--asof", default=None)
@click.option("--universe", type=click.Choice(["acwi_proxy", "us_broad"]), default="acwi_proxy")
@click.pass_obj
def exposures(obj: dict, asof: str | None, universe: str) -> None:
    """Portfolio exposures (model and equal weights)."""
    from .pipeline import compute_exposures, latest_factor_run

    ctx = _ctx(obj)
    date = asof or latest_factor_run(ctx.ws, universe)[0]
    if date is None:
        raise click.ClickException("no factor run found: run `aim factors build` first")
    click.echo(json.dumps(compute_exposures(ctx.store, date, universe), indent=2))


# --------------------------------------------------------------- Phase 6
def _cutoffs(ctx: Context) -> dict[str, str] | None:
    if not ctx.demo:
        return None
    from .demo.simulator import PROFILES

    out = {}
    keys = list(PROFILES.keys())
    for i in range(len(keys)):
        out[keys[i]] = PROFILES[keys[i]]["knowledge"]
    return out


@main.command()
@click.option("--asof", default=None)
@click.option("--universe", type=click.Choice(["acwi_proxy", "us_broad"]), default="acwi_proxy")
@click.option("--draws", type=int, default=None, help="Bootstrap draws (default from experiment.yaml).")
@click.option("--cohort", type=click.Choice(["baseline", "expanded"]), default="baseline")
@click.pass_obj
def analyze(obj: dict, asof: str | None, universe: str, draws: int | None, cohort: str) -> None:
    """Run every analysis; writes outputs/analysis.json and CSV tables."""
    from .analysis.run import run_all
    from .pipeline import latest_factor_run, load_master

    ctx = _ctx(obj)
    date = asof or latest_factor_run(ctx.ws, universe)[0]
    result = run_all(ctx.ws, ctx.config, ctx.store, date, universe, draws, _cutoffs(ctx),
                     load_master(ctx.ws), cohort=cohort)
    click.echo(f"{result['cohort']} analysis written")


@main.command()
@click.option("--cohort", type=click.Choice(["baseline", "expanded"]), default="baseline", show_default=True)
@click.pass_obj
def figures(obj: dict, cohort: str) -> None:
    """Render figures and their CSVs from saved cohort analysis."""
    from .figures import render_all

    ws = obj["figure_workspace"]
    output = ws.outputs if cohort == "baseline" else ws.outputs / "expanded"
    result = read_json(output / "analysis.json", default=None)
    if result is None:
        command = "aim analyze" if cohort == "baseline" else "aim analyze --cohort expanded"
        raise click.ClickException(f"run `{command}` first")
    folder = output / "figures"
    paths = render_all(result, folder, ws.is_demo)
    click.echo(f"{len(paths)} {cohort} figures in {folder}")


@main.command()
@click.pass_obj
def report(obj: dict) -> None:
    """Write docs/RESULTS.md (our numbers next to the paper's)."""
    from .report import write_results

    click.echo(write_results(_ctx(obj).ws))


@main.group()
def dashboard() -> None:
    """Frontend data export and local server."""


@dashboard.command("export")
@click.pass_obj
def dashboard_export(obj: dict) -> None:
    from .dashboard.export import export

    ctx = _ctx(obj)
    click.echo(f"exported to {export(ctx.ws, ctx.config, ctx.store)}")


@dashboard.command("serve")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
@click.pass_obj
def dashboard_serve(obj: dict, host: str, port: int) -> None:
    """Serve the dashboard (demo data is generated on first use if no data exists)."""
    from .dashboard.serve import datasets, serve

    ctx = _ctx(obj)
    if len(datasets()) == 0 or (ctx.demo and not (ctx.ws.dashboard / "meta.json").exists()):
        click.echo("no exported data yet: building the synthetic demo first (about a minute) ...")
        from .demo.run import run_demo

        demo_ctx = make_context(True)
        run_demo(demo_ctx)
        demo_ctx.close()
    ctx.close()
    serve(host, port)


@main.command()
@click.option("--fresh", is_flag=True, help="Delete the demo workspace first.")
@click.option("--draws", type=int, default=None)
@click.pass_obj
def demo(obj: dict, fresh: bool, draws: int | None) -> None:
    """Run the whole pipeline on simulated models and a synthetic market (labelled synthetic everywhere)."""
    from .demo.run import run_demo

    ctx = make_context(True)
    try:
        summary = run_demo(ctx, fresh=fresh, draws=draws)
    finally:
        ctx.close()
    click.echo(json.dumps(summary, indent=2, default=str))


@main.command()
@click.option("--asof", default=None)
@click.option("--universe", type=click.Choice(["acwi_proxy", "us_broad"]), default="acwi_proxy")
@click.option("--draws", type=int, default=None)
@click.pass_obj
def refresh(obj: dict, asof: str | None, universe: str, draws: int | None) -> None:
    """After collection: parse -> resolve -> exposures -> analyze -> figures -> report -> dashboard export."""
    from .analysis.run import run_all
    from .dashboard.export import export
    from .figures import render_all
    from .pipeline import compute_exposures, latest_factor_run, load_master, parse_calls, resolve_holdings
    from .report import write_results

    ctx = _ctx(obj)
    parse_calls(ctx.store)
    master = load_master(ctx.ws)
    if master is not None:
        resolve_holdings(ctx.ws, ctx.store, master)
    date = asof or latest_factor_run(ctx.ws, universe)[0]
    if date is not None:
        compute_exposures(ctx.store, date, universe)
    result = run_all(ctx.ws, ctx.config, ctx.store, date, universe, draws, _cutoffs(ctx), master)
    render_all(result, ctx.ws.figures, ctx.demo)
    write_results(ctx.ws)
    export(ctx.ws, ctx.config, ctx.store)
    click.echo("refreshed analysis, figures, RESULTS.md and dashboard data")


@main.group()
def discovery() -> None:
    """Forced-discovery arm (Phase 7)."""


@discovery.command("screen")
@click.option("--mandate", type=click.Choice(["MOMENTUM", "VALUE", "QUALITY"]), default="MOMENTUM")
@click.option("--top", default=100, type=int)
@click.option("--asof", default=None)
@click.option("--universe", type=click.Choice(["acwi_proxy", "us_broad"]), default="acwi_proxy")
@click.pass_obj
def discovery_screen(obj: dict, mandate: str, top: int, asof: str | None, universe: str) -> None:
    """Write a timestamped candidate screen and the prompt that forces the model to choose from it."""
    from .discovery import build_screen
    from .pipeline import latest_factor_run

    ctx = _ctx(obj)
    date = asof or latest_factor_run(ctx.ws, universe)[0]
    if date is None:
        raise click.ClickException("no factor run found")
    click.echo(json.dumps(build_screen(ctx.ws, ctx.config, ctx.store, date, universe, mandate, top), indent=2))


if __name__ == "__main__":
    main()
