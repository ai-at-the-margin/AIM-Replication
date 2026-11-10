"""`aim verify` (BUILD_BRIEF §0.2, Phase 0).

1. Confirms every configured model id against the providers' model-list endpoints.
2. Makes one search-enabled test call per provider and checks that the search
   queries are captured by the adapter.
3. Probes WRDS table schemas and *effective* latest dates; picks primary/fallback
   sources per input and runs the special checks.
4. Writes docs/PHASE0_VERIFICATION.md and processed/phase0_state.json.

Missing credentials or an unreachable service are recorded, never fatal: the
pipeline halts only when a *required* input has no working source.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable
from typing import Any

from .prompts import experiment_version, prompt_version
from .providers import api_key_for, make_adapter
from .providers.base import Transport, TransportError
from .settings import CONFIG_DIR, Config, Workspace, load_yaml
from .utils import get_logger, read_json, utc_now, utc_now_iso, write_json
from .wrds_io.connect import WRDS_HOST, WRDS_PORT, WrdsClient
from .wrds_io.freshness import effective_latest_date
from .wrds_io.schema import write_resolved
from .wrds_io.verify import TableProbe, choose_sources, map_compustat_exchanges, probe_table, special_checks

log = get_logger(__name__)

SEARCH_TEST_PROMPT = ("Use web search to find the most recent closing price of Apple Inc. (AAPL). "
                      "Answer in one sentence and name the date of the price.")
SEARCH_TEST_MODEL = {"openai": "gpt-6.1-sol", "anthropic": "claude-opus-5-5"}


async def verify_providers(config: Config, transport_factory: Callable[[], Transport],
                           search_test: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {}
    transport = transport_factory()
    try:
        models = config.model_list(include_optional=True)
        providers: dict[str, list[str]] = {}
        for model in models:
            providers.setdefault(model["provider"], []).append(model["id"])
        for provider, model_ids in providers.items():
            entry: dict[str, Any] = {"key_present": False, "models_ok": [], "models_missing": [],
                                     "list_error": None, "search_test": None}
            key = api_key_for(provider, config)
            entry["key_present"] = key is not None or transport.name == "simulated"
            if not entry["key_present"]:
                entry["list_error"] = f"no API key ({config.provider(provider).get('env_key')})"
                out[provider] = entry
                continue
            adapter = make_adapter(provider, config, transport, key)
            try:
                listed = set(await adapter.list_models())
                for model_id in model_ids:
                    if model_id in listed:
                        entry["models_ok"].append(model_id)
                    else:
                        entry["models_missing"].append(model_id)
            except TransportError as exc:
                entry["list_error"] = str(exc)[:300]
            except Exception as exc:
                entry["list_error"] = f"{exc.__class__.__name__}: {exc}"[:300]
            if search_test and SEARCH_TEST_MODEL.get(provider) in entry["models_ok"]:
                entry["search_test"] = await _search_test(config, adapter, provider)
            out[provider] = entry
    finally:
        await transport.aclose()
    return out


async def _search_test(config: Config, adapter: Any, provider: str) -> dict[str, Any]:
    model = SEARCH_TEST_MODEL[provider]
    request = adapter.build_request(SEARCH_TEST_PROMPT, model, True, {})
    try:
        raw = await adapter.send(request)
        normalised = adapter.normalise(raw)
    except Exception as exc:
        return {"model": model, "ok": False, "error": str(exc)[:300]}
    queries = []
    for i in range(len(normalised.tool_events)):
        if normalised.tool_events[i].query_text:
            queries.append(normalised.tool_events[i].query_text)
    return {"model": model, "ok": len(queries) > 0, "model_returned": normalised.model_returned,
            "search_events": len(normalised.tool_events), "queries_captured": queries[:5],
            "stop_reason": normalised.stop_reason}


def verify_wrds(config: Config, client: WrdsClient | None = None, today: dt.date | None = None) -> dict[str, Any]:
    today = today or dt.date.today()
    client = client or WrdsClient()
    result: dict[str, Any] = {"host": f"{WRDS_HOST}:{WRDS_PORT}", "connected": False, "error": None}
    if not client.connect():
        result["error"] = client.error
        result["sources"] = choose_sources({}, config.sources, today)
        return result
    result["connected"] = True
    tables = config.schema.get("tables", {})
    probes: dict[str, TableProbe] = {}
    keys = list(tables.keys())
    for i in range(len(keys)):
        log.info("probing %s ...", keys[i])
        probes[keys[i]] = probe_table(client, keys[i], tables[keys[i]], today)
    resolved: dict[str, Any] = {}
    for i in range(len(keys)):
        resolved[keys[i]] = probes[keys[i]].as_dict()
    write_resolved(resolved)
    result["probes"] = resolved
    result["sources"] = choose_sources(probes, config.sources, today)
    exchanges_cfg = load_yaml(CONFIG_DIR / "exchanges.yaml")
    ex_probe = probes.get("comp_ex_codes")
    result["exchg_map"] = map_compustat_exchanges(client, ex_probe, exchanges_cfg) if ex_probe else {}
    result["special"] = special_checks(client, today)
    client.close()
    return result


def verify_wrds_synthetic(config: Config, source: Any, today: dt.date) -> dict[str, Any]:
    """Demo equivalent: the same freshness rule and source selection on the synthetic tables."""
    from .demo.companies import EXCHANGE_EXCHG

    probes: dict[str, Any] = {}
    for key, region in (("comp_secd", "na"), ("comp_g_secd", "global")):
        counts = source.freshness_counts(region)
        frame = source.world.prices[source.world.prices["region"] == region]
        all_counts = frame.groupby("date").size().rename("n").reset_index()
        fresh = effective_latest_date(all_counts, today)
        probes[key] = {"ok": True, "library": "synthetic", "table": key, "columns": {}, "missing": [],
                       "effective_latest_date": str(fresh.effective_latest_date),
                       "raw_max_date": str(fresh.raw_max_date), "future_rows_discarded": fresh.future_rows,
                       "freshness_detail": fresh.detail, "recent_dates": int(len(counts))}
    sources = []
    plan = [
        ("prices_na", "comp_secd", False, probes["comp_secd"]["effective_latest_date"], ""),
        ("prices_global", "comp_g_secd", False, probes["comp_g_secd"]["effective_latest_date"], ""),
        ("fx", "comp_g_exrt_dly", False, str(today - dt.timedelta(days=2)), ""),
        ("rf", "ff_factors_daily", False, "2026-09-30", "forward-filled to the as-of date (rf_filled)"),
        ("fundamentals_na", "snapshot_na", False, None, ""),
        ("fundamentals_global", "comp_fund_global", True, None, "snapshot_global: no global Snapshot table found"),
        ("forward_earnings", "ibes_statsum", False, None, ""),
        ("security_master", "ciq_master", False, None, ""),
        ("gics", "comp_company", False, None, ""),
        ("index_membership", "comp_idxcst", True, None, "ds_msci_acwi: no MSCI ACWI list; ACWI proxy used"),
        ("finratio", "wrds_finratio", False, None, ""),
        ("news", "ravenpack", False, None, ""),
        ("crsp_validation", None, False, "2025-12-31", "synthetic world has no CRSP; validation skipped"),
    ]
    inputs = config.sources.get("inputs", {})
    for i in range(len(plan)):
        name, chosen, fallback, latest, note = plan[i]
        spec = inputs.get(name, {})
        status = "ok" if chosen else ("HALT" if spec.get("required") else "unavailable")
        sources.append({"input": name, "source_used": chosen, "fallback_used": fallback,
                        "effective_latest_date": latest, "required": bool(spec.get("required")),
                        "status": status, "notes": note})
    exchg_map = {}
    codes = list(EXCHANGE_EXCHG.keys())
    for i in range(len(codes)):
        exchg_map[str(EXCHANGE_EXCHG[codes[i]])] = codes[i]
    return {"host": "synthetic world", "connected": True, "error": None, "probes": probes, "sources": sources,
            "exchg_map": exchg_map, "special": {"note": "synthetic demo: CRSP/Datastream checks not applicable"}}


def run_verify(ws: Workspace, config: Config, transport_factory: Callable[[], Transport],
               wrds_result: dict[str, Any] | None = None, providers: bool = True, wrds: bool = True,
               search_test: bool = True) -> dict[str, Any]:
    state: dict[str, Any] = read_json(ws.processed / "phase0_state.json", default={}) or {}
    state["workspace"] = ws.name
    state["experiment_version"] = experiment_version(config)
    state["prompt_version"] = prompt_version(config)
    state["verified_ts_utc"] = utc_now_iso()
    if providers:
        state["providers"] = asyncio.run(verify_providers(config, transport_factory, search_test))
        state["providers_ts_utc"] = utc_now_iso()
    if wrds:
        state["wrds"] = wrds_result if wrds_result is not None else verify_wrds(config)
        state["wrds_ts_utc"] = utc_now_iso()
    state["halt"] = _halts(state)
    write_json(ws.processed / "phase0_state.json", state)
    write_report(ws, config, state)
    return state


def _halts(state: dict[str, Any]) -> list[str]:
    out = []
    sources = (state.get("wrds") or {}).get("sources") or []
    for i in range(len(sources)):
        if sources[i].get("status") == "HALT":
            out.append(f"required input {sources[i]['input']} has no working source")
    return out


def is_fresh(ws: Workspace, config: Config, scope: str, max_age_hours: float = 24.0) -> bool:
    state = read_json(ws.processed / "phase0_state.json", default={}) or {}
    stamp = state.get(f"{scope}_ts_utc")
    if not stamp or state.get("experiment_version") != experiment_version(config):
        return False
    try:
        age = utc_now() - dt.datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return age.total_seconds() < max_age_hours * 3600


def write_report(ws: Workspace, config: Config, state: dict[str, Any]) -> None:
    lines = ["# Phase 0 verification", "",
             f"Generated {state.get('verified_ts_utc')} by `aim verify` (workspace: **{ws.name}**).", ""]
    if ws.is_demo:
        lines += ["> **Synthetic demo workspace.** Providers are simulated and WRDS is replaced by a synthetic "
                  "world. Nothing here verifies real services.", ""]
    lines += [f"- experiment_version: `{state.get('experiment_version')}`",
              f"- prompt_version: `{state.get('prompt_version')}`", ""]
    halts = state.get("halt") or []
    lines.append("## Verdict")
    lines.append("")
    if halts:
        lines.append("**HALT**: " + "; ".join(halts))
    else:
        lines.append("Every required input has a working source." if state.get("wrds", {}).get("connected")
                     else "WRDS not verified yet (see below).")
    lines.append("")
    lines.append("## Providers")
    lines.append("")
    providers = state.get("providers") or {}
    names = list(providers.keys())
    for i in range(len(names)):
        p = providers[names[i]]
        lines.append(f"### {names[i]}")
        lines.append("")
        lines.append(f"- API key present: {p.get('key_present')}")
        if p.get("list_error"):
            lines.append(f"- model list: **error** {p['list_error']}")
        else:
            lines.append(f"- models confirmed: {', '.join(p.get('models_ok') or []) or 'none'}")
            missing = p.get("models_missing") or []
            lines.append(f"- models missing: {', '.join(missing) if missing else 'none'}")
        test = p.get("search_test")
        if test:
            lines.append(f"- search test ({test.get('model')}): {'OK' if test.get('ok') else 'FAILED'}; "
                         f"events={test.get('search_events')}; queries={test.get('queries_captured')}"
                         + (f"; error={test.get('error')}" if test.get("error") else ""))
        lines.append("")
    wrds = state.get("wrds") or {}
    lines.append("## WRDS")
    lines.append("")
    lines.append(f"- host: {wrds.get('host')}")
    lines.append(f"- connected: {wrds.get('connected')}" + (f" (error: {wrds.get('error')})" if wrds.get("error") else ""))
    lines.append("")
    probes = wrds.get("probes") or {}
    if probes:
        lines.append("| logical table | ok | physical table | effective latest | raw max | future rows dropped | note |")
        lines.append("|---|---|---|---|---|---|---|")
        keys = list(probes.keys())
        for i in range(len(keys)):
            p = probes[keys[i]]
            lines.append(f"| {keys[i]} | {p.get('ok')} | {p.get('library')}.{p.get('table')} | "
                         f"{p.get('effective_latest_date') or ''} | {p.get('raw_max_date') or ''} | "
                         f"{p.get('future_rows_discarded') if p.get('future_rows_discarded') is not None else ''} | "
                         f"{(p.get('error') or p.get('freshness_detail') or '')[:120]} |")
        lines.append("")
    sources = wrds.get("sources") or []
    if sources:
        lines.append("### Source per input")
        lines.append("")
        lines.append("| input | status | source used | fallback | effective latest | notes |")
        lines.append("|---|---|---|---|---|---|")
        for i in range(len(sources)):
            s = sources[i]
            lines.append(f"| {s['input']} | {s['status']} | {s.get('source_used') or ''} | {s.get('fallback_used')} | "
                         f"{s.get('effective_latest_date') or ''} | {(s.get('notes') or '')[:160]} |")
        lines.append("")
    special = wrds.get("special")
    if special:
        lines.append("### Special checks")
        lines.append("")
        keys = list(special.keys())
        for i in range(len(keys)):
            lines.append(f"- {keys[i]}: {special[keys[i]]}")
        lines.append("")
    if not wrds.get("connected") and not ws.is_demo:
        lines += ["### How to finish this check", "",
                  "Run `aim verify` on a machine that can reach WRDS (PostgreSQL on "
                  f"`{WRDS_HOST}:{WRDS_PORT}`), with `WRDS_USERNAME` (and optionally `WRDS_PASSWORD`) set "
                  "or a `~/.pgpass`. Approve the Duo push on first connection.", ""]
    path = ws.docs_dir / "PHASE0_VERIFICATION.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
