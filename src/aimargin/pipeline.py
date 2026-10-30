"""Stage orchestration shared by the CLI and the demo: parse -> resolve -> factors -> exposures."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from .factors.build import build_factor_exposures, portfolio_exposures
from .parse.extract import extract_portfolio
from .parse.refusal import rule_refusal
from .parse.validate import classify_outcome, classify_parse, normalise_weights
from .resolve.crosslist import ensure_manual_files
from .resolve.master import SecurityMaster
from .resolve.normalise import ticker_key
from .resolve.resolver import Resolver
from .settings import Config, Workspace
from .store.db import Store
from .utils import get_logger, read_json, write_json
from .wrds_io.source import DataSource

log = get_logger(__name__)


def parse_calls(store: Store, force: bool = False) -> dict[str, int]:
    """Extract portfolios from every completed call (raw text is never modified)."""
    calls = store.query(
        "SELECT c.call_id, c.status, c.provider_refusal_flag, c.error, r.final_text "
        "FROM calls c LEFT JOIN responses r USING (call_id)")
    done = set()
    if not force:
        values = store.query("SELECT call_id FROM portfolios")["call_id"].tolist()
        for i in range(len(values)):
            done.add(values[i])
    counts: dict[str, int] = {}
    portfolio_rows = []
    holding_rows = []
    parsed_ids = []
    records = calls.to_dict("records")
    for i in range(len(records)):
        r = records[i]
        if r["call_id"] in done:
            continue
        parsed_ids.append(r["call_id"])
        if r["status"] != "completed":
            portfolio_rows.append({"call_id": r["call_id"], "parse_status": "api_error", "parse_method": "none",
                                   "outcome": "api_error", "n_names_raw": 0, "weights_provided": False,
                                   "notes": str(r.get("error") or "")[:500]})
            counts["api_error"] = counts.get("api_error", 0) + 1
            continue
        text = r.get("final_text") or ""
        result = extract_portfolio(text)
        flag = bool(r.get("provider_refusal_flag")) if r.get("provider_refusal_flag") is not None else False
        refusal, matches = rule_refusal(text, len(result.holdings), flag)
        status = classify_parse(result.method, len(result.holdings), refusal)
        raw_weights = []
        for k in range(len(result.holdings)):
            raw_weights.append(result.holdings[k].weight)
        weights, provided, raw_sum = normalise_weights(raw_weights)
        for k in range(len(result.holdings)):
            h = result.holdings[k]
            holding_rows.append({
                "call_id": r["call_id"], "position_idx": k, "raw_ticker": h.ticker, "raw_exchange": h.exchange,
                "raw_name": h.name, "raw_weight": h.weight, "weight_norm": weights[k],
                "weight_equal": 1.0 / len(result.holdings), "resolution_status": "pending",
            })
        notes = "; ".join(result.notes + matches)[:1000]
        portfolio_rows.append({
            "call_id": r["call_id"], "parse_status": status, "parse_method": result.method, "outcome": status,
            "refusal_rule": refusal, "n_names_raw": len(result.holdings), "weights_provided": provided,
            "weight_sum_raw": raw_sum, "notes": notes,
        })
        counts[status] = counts.get(status, 0) + 1
    if len(parsed_ids) > 0:
        for start in range(0, len(parsed_ids), 500):
            chunk = parsed_ids[start:start + 500]
            marks = ", ".join(["?"] * len(chunk))
            store.delete_where("holdings", f"call_id IN ({marks})", chunk)
    store.upsert("portfolios", portfolio_rows)
    store.upsert("holdings", holding_rows)
    return counts


def save_master(ws: Workspace, master: pd.DataFrame, asof: dt.date) -> None:
    master.to_parquet(ws.processed / "security_master.parquet", index=False)
    write_json(ws.processed / "security_master.json", {"asof": asof.isoformat(), "rows": int(len(master))})


def load_master(ws: Workspace) -> pd.DataFrame | None:
    path = ws.processed / "security_master.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def resolve_holdings(ws: Workspace, store: Store, master: pd.DataFrame) -> dict[str, Any]:
    """Resolve every holding, collapse to issuers and finalise portfolio outcomes."""
    ensure_manual_files(ws.manual)
    resolver = Resolver(SecurityMaster.from_frame(master), ws.manual)
    holdings = store.table("holdings")
    portfolios = store.table("portfolios")
    if len(holdings) == 0:
        return {"holdings": 0}
    rows = holdings.to_dict("records")
    for i in range(len(rows)):
        result = resolver.resolve(rows[i].get("raw_ticker"), rows[i].get("raw_exchange"), rows[i].get("raw_name"))
        rows[i]["resolution_status"] = result.status
        rows[i]["resolution_method"] = result.method
        rows[i]["resolution_confidence"] = result.confidence
        keys = list(result.fields.keys())
        for k in range(len(keys)):
            rows[i][keys[k]] = result.fields[keys[k]]
        if result.status == "unresolved":
            for column in ("issuer_id", "gvkey", "iid", "ciq_companyid", "ciq_tradingitemid", "resolved_name"):
                rows[i][column] = None
    frame = pd.DataFrame(rows)
    frame["duplicate_of"] = None
    stats = {"holdings": len(frame), "resolved": 0, "low_confidence": 0, "unresolved": 0}
    stats["resolved"] = int((frame["resolution_status"] == "resolved").sum())
    stats["low_confidence"] = int((frame["resolution_status"] == "resolved_low_confidence").sum())
    stats["unresolved"] = int((frame["resolution_status"] == "unresolved").sum())
    status_by_call = portfolios.set_index("call_id")["parse_status"].to_dict()
    outcome_rows = []
    groups = frame.groupby("call_id")
    call_ids = list(groups.groups.keys())
    for c in range(len(call_ids)):
        group = groups.get_group(call_ids[c])
        seen: dict[str, int] = {}
        distinct = 0
        resolved = 0
        idx_list = list(group.index)
        for k in range(len(idx_list)):
            row = frame.loc[idx_list[k]]
            if row["issuer_id"] is not None and pd.notna(row["issuer_id"]):
                key = str(row["issuer_id"])
                resolved += 1
            else:
                key = "raw:" + str(ticker_key(row["raw_ticker"]) or row["raw_name"])
            if key in seen:
                frame.at[idx_list[k], "duplicate_of"] = seen[key]
            else:
                seen[key] = int(row["position_idx"])
                distinct += 1
        outcome = classify_outcome(status_by_call.get(call_ids[c], "parsed"), distinct)
        outcome_rows.append({"call_id": call_ids[c], "n_names_resolved": resolved, "n_issuers": distinct,
                             "outcome": outcome})
    store.upsert("holdings", frame)
    updates = pd.DataFrame(outcome_rows)
    merged = portfolios.drop(columns=["n_names_resolved", "n_issuers", "outcome"]).merge(updates, on="call_id",
                                                                                         how="left")
    merged["outcome"] = merged["outcome"].fillna(merged["parse_status"])
    store.upsert("portfolios", merged)
    review_count = resolver.write_review(ws.manual / "ticker_review.csv")
    parsed_mask = frame["call_id"].isin(set(updates["call_id"].tolist()))
    total = int(parsed_mask.sum())
    good = int(frame.loc[parsed_mask, "resolution_status"].isin(["resolved", "resolved_low_confidence"]).sum())
    stats["resolution_rate"] = round(good / total, 4) if total else None
    stats["review_rows"] = review_count
    methods = frame["resolution_method"].value_counts().to_dict()
    stats["methods"] = methods
    write_json(ws.processed / "resolution_summary.json", stats)
    return stats


def held_gvkeys(store: Store) -> list[str]:
    frame = store.query("SELECT DISTINCT gvkey FROM holdings WHERE gvkey IS NOT NULL")
    return frame["gvkey"].astype(str).tolist()


def gvkey_issuer_map(master: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    frame = master.dropna(subset=["gvkey"])
    ciq_first = frame.sort_values("source", key=lambda s: s.map({"ciq": 0, "synthetic": 0, "comp": 1}).fillna(2))
    gvkeys = ciq_first["gvkey"].astype(str).tolist()
    issuers = ciq_first["issuer_id"].tolist()
    for i in range(len(gvkeys)):
        key = gvkeys[i].zfill(6)
        if key not in out and issuers[i] is not None and pd.notna(issuers[i]):
            out[key] = str(issuers[i])
    return out


def build_factors(ws: Workspace, config: Config, store: Store, source: DataSource, asof: dt.date,
                  universe: str) -> dict[str, Any]:
    master = load_master(ws)
    if master is None:
        master = source.security_master(asof)
        save_master(ws, master, asof)
    summary = build_factor_exposures(ws, config, store, source, asof, universe, held_gvkeys(store),
                                     gvkey_issuer_map(master))
    state = read_json(ws.processed / "factor_runs.json", default={}) or {}
    state[f"{summary['asof']}:{universe}"] = summary
    write_json(ws.processed / "factor_runs.json", state)
    return summary


def compute_exposures(store: Store, asof: str, universe: str) -> dict[str, Any]:
    holdings = store.query(
        "SELECT h.*, p.outcome FROM holdings h JOIN portfolios p USING (call_id) "
        "WHERE p.outcome IN ('valid', 'insufficient_names', 'excess_names')")
    exposures = store.query("SELECT * FROM exposures WHERE asof_date = ? AND universe = ?", [asof, universe])
    if len(exposures) == 0:
        raise RuntimeError(f"no exposures for {asof} / {universe}: run `aim factors build` first")
    rows = portfolio_exposures(holdings, exposures, asof, universe)
    store.delete_where("portfolio_exposures", "asof_date = ? AND universe = ?", [asof, universe])
    store.upsert("portfolio_exposures", rows)
    universe_ids = set(exposures[exposures["in_estimation_universe"] == True]["issuer_id"].tolist())  # noqa: E712
    column = "in_universe_acwi" if universe == "acwi_proxy" else "in_universe_us"
    all_holdings = store.table("holdings")
    flags = []
    issuer_values = all_holdings["issuer_id"].tolist()
    for i in range(len(issuer_values)):
        flags.append(issuer_values[i] in universe_ids if issuer_values[i] is not None else None)
    all_holdings[column] = flags
    store.upsert("holdings", all_holdings)
    coverage = pd.DataFrame(rows)
    mean_cov = float(coverage["coverage_weight"].mean()) if len(coverage) else None
    return {"portfolio_rows": len(rows), "mean_coverage_weight": mean_cov}


def latest_factor_run(ws: Workspace, universe: str = "acwi_proxy") -> tuple[str | None, str]:
    state = read_json(ws.processed / "factor_runs.json", default={}) or {}
    best = None
    keys = sorted(state.keys())
    for i in range(len(keys)):
        if keys[i].endswith(":" + universe):
            best = keys[i].split(":")[0]
    return best, universe
