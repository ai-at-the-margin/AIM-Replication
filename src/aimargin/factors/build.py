"""`aim factors build`: universe -> returns -> descriptors -> standardised exposures.

Writes the ``descriptors``, ``exposures`` and ``momentum_history`` tables for one
(as-of date, universe), plus validation tables (cap-weighted zero check,
point-in-time vs restated, WRDS financial-ratio cross-check).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import numpy as np
import pandas as pd

from ..settings import Config, Workspace
from ..store.db import Store
from ..utils import get_logger, utc_now_iso
from ..wrds_io import fx as fx_mod
from ..wrds_io.rf import prepare_rf
from ..wrds_io.source import DataSource
from .descriptors import fundamental_descriptors, market_return, price_descriptors, simple_momentum
from .returns import sanity_filter, to_wide, total_returns
from .standardise import composite, orthogonalise, standardise
from .universe import acwi_proxy, issue_caps, issuer_caps, us_broad

log = get_logger(__name__)
FACTORS = ["size", "value", "quality", "momentum", "lowvol", "resvol", "beta"]


def _first_snapshot(source: DataSource, asof: dt.date, max_back: int = 7) -> tuple[dt.date, pd.DataFrame]:
    for k in range(max_back + 1):
        day = asof - dt.timedelta(days=k)
        snap = source.price_snapshot(day)
        if snap is not None and len(snap) > 0:
            return day, snap
    raise RuntimeError(f"no price snapshot within {max_back} days before {asof}")


def build_factor_exposures(ws: Workspace, config: Config, store: Store, source: DataSource, asof: dt.date,
                           universe_name: str, held_gvkeys: list[str],
                           gvkey_to_issuer: dict[str, str]) -> dict[str, Any]:
    fcfg = config.factors
    lo, hi = fcfg.get("winsor_pct", [0.01, 0.99])
    summary: dict[str, Any] = {"requested_asof": asof.isoformat(), "universe": universe_name}

    T, snapshot = _first_snapshot(source, asof)
    summary["asof"] = T.isoformat()
    hist_days = int(fcfg.get("history", {}).get("universe_trading_days", 950))
    start = T - dt.timedelta(days=int(hist_days * 1.48) + 40)
    fx_rates = source.fx_rates(start, T)
    fx_t = fx_mod.align_to_dates(fx_rates, pd.DatetimeIndex([pd.Timestamp(T)]))
    fx_at_t: dict[str, float] = {}
    row = fx_t.iloc[0]
    currencies = list(row.index)
    for i in range(len(currencies)):
        if pd.notna(row[currencies[i]]):
            fx_at_t[str(currencies[i])] = float(row[currencies[i]])

    companies = source.companies()
    issues = issue_caps(snapshot, fx_at_t)
    missing_fx = issues[issues["usd_per_unit"].isna()]
    if len(missing_fx) > 0:
        store.log_drop("factors", universe_name, "missing_fx_at_asof",
                       f"{len(missing_fx)} issues in currencies {sorted(set(missing_fx['currency'].astype(str)))[:20]}")
    caps = issuer_caps(issues, companies, gvkey_to_issuer)
    if universe_name == "acwi_proxy":
        uni = acwi_proxy(caps, config.universe)
    elif universe_name == "us_broad":
        uni = us_broad(caps, issues, config.universe)
    else:
        raise ValueError(f"unknown universe {universe_name}")
    universe_gvkeys = set(uni["gvkey"].tolist())
    summary["universe_count"] = len(universe_gvkeys)
    log.info("%s universe at %s: %d issuers", universe_name, T, len(universe_gvkeys))

    held = set()
    for i in range(len(held_gvkeys)):
        if held_gvkeys[i]:
            held.add(str(held_gvkeys[i]).zfill(6))
    all_gvkeys = sorted(universe_gvkeys | held)
    known = caps[caps["gvkey"].isin(set(all_gvkeys))].copy()
    missing_held = held - set(known["gvkey"].tolist())
    for g in sorted(missing_held):
        store.log_drop("factors", g, "held_issuer_without_price_at_asof", T.isoformat())
    summary["held_issuers"] = len(held)
    summary["held_without_price"] = len(missing_held)

    prices = source.price_history(all_gvkeys, start, T)
    prices = prices[prices["date"] <= pd.Timestamp(T)]
    dates = pd.DatetimeIndex(sorted(prices["date"].dropna().unique()))
    fx_wide = fx_mod.align_to_dates(fx_rates, dates)
    returns = total_returns(prices, fx_wide)
    returns, flagged = sanity_filter(returns)
    summary["returns_flagged"] = int(len(flagged))
    summary["returns_dropped_reversal"] = int((flagged["action"] == "dropped_reversal").sum()) if len(flagged) else 0
    summary["price_only_share"] = float(returns["price_only"].mean()) if len(returns) else None
    if len(flagged) > 0:
        flagged.to_csv(ws.tables / f"return_flags_{universe_name}_{T}.csv", index=False)

    primary = known[["gvkey", "primary_iid", "issuer_id"]].rename(columns={"primary_iid": "iid"})
    R = to_wide(returns, primary, "ret_usd")
    returns["cap_usd"] = returns["usd_price"] * returns["shares"]
    caps_daily = to_wide(returns, primary, "cap_usd")
    rf_frame = prepare_rf(source.rf_rates(start, T), R.index)
    summary["rf_filled_days"] = int(rf_frame["rf_filled"].sum())
    universe_issuers = known[known["gvkey"].isin(universe_gvkeys)]["issuer_id"].tolist()
    mkt = market_return(R, caps_daily, universe_issuers)
    price_desc = price_descriptors(R, rf_frame["rf"], mkt, pd.Timestamp(T), fcfg)

    years = int(fcfg.get("history", {}).get("fundamentals_years", 7))
    annual = source.fundamentals_annual(all_gvkeys, T, years, pit=True)
    book = source.book_equity(all_gvkeys, T, pit=True)
    caps_usd = known.set_index("issuer_id")["mcap_usd"]
    price_currency = known.set_index("gvkey")["currency"].astype(str).to_dict()
    g2i = known.set_index("gvkey")["issuer_id"].to_dict()
    fund = fundamental_descriptors(annual, book, caps_usd, fx_at_t, g2i, price_currency, fcfg)

    frame = known.set_index("issuer_id")[["gvkey", "primary_iid", "name", "country", "gics_sector", "mcap_usd", "currency"]].copy()
    frame["ln_mcap"] = np.log(frame["mcap_usd"].where(frame["mcap_usd"] > 0))
    frame = frame.join(price_desc, how="left").join(fund, how="left")

    fwd = source.forward_eps(all_gvkeys, T)
    frame["fwd_ep_raw"] = np.nan
    frame["analyst_count"] = np.nan
    if fwd is not None and len(fwd) > 0:
        last_price = returns.sort_values("date").drop_duplicates(subset=["gvkey", "iid"], keep="last")
        price_usd = last_price.merge(primary, on=["gvkey", "iid"]).set_index("issuer_id")["usd_price"]
        records = fwd.to_dict("records")
        for i in range(len(records)):
            issuer = g2i.get(str(records[i]["gvkey"]).zfill(6))
            if issuer is None or issuer not in frame.index:
                continue
            currency = str(records[i].get("currency") or price_currency.get(records[i]["gvkey"]) or "USD")
            rate = fx_at_t.get(currency)
            px = price_usd.get(issuer)
            if rate and px and px > 0 and records[i].get("fwd_eps") is not None:
                frame.loc[issuer, "fwd_ep_raw"] = float(records[i]["fwd_eps"]) * rate / float(px)
            if records[i].get("numest") is not None:
                frame.loc[issuer, "analyst_count"] = float(records[i]["numest"])
    news = source.news_counts(all_gvkeys, T)
    frame["news_count_30d"] = np.nan
    if news is not None and len(news) > 0:
        records = news.to_dict("records")
        for i in range(len(records)):
            issuer = g2i.get(str(records[i]["gvkey"]).zfill(6))
            if issuer in frame.index:
                frame.loc[issuer, "news_count_30d"] = float(records[i]["news_count_30d"])

    universe_mask = frame["gvkey"].isin(universe_gvkeys)
    cap = frame["mcap_usd"]
    z = pd.DataFrame(index=frame.index)

    def std(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.nan, index=frame.index)
        return standardise(frame[column].astype(float), cap, universe_mask, lo, hi)

    z["size"] = std("ln_mcap")
    z["beta"] = std("beta_raw")
    z["momentum"] = std("rstr_raw")
    z["mom_12_1"] = std("mom_12_1_raw")
    w = fcfg["resvol"]["weights"]
    resvol_parts = pd.DataFrame({"dastd": std("dastd_raw"), "cmra": std("cmra_raw"), "hsigma": std("hsigma_raw")})
    resvol_raw = composite(resvol_parts, {"dastd": float(w["dastd"]), "cmra": float(w["cmra"]), "hsigma": float(w["hsigma"])})
    resvol_raw = orthogonalise(resvol_raw, z[["beta", "size"]], universe_mask)
    z["resvol"] = standardise(resvol_raw, cap, universe_mask, lo, hi)
    z["lowvol"] = -z["resvol"]
    z["value"] = std("btop")
    blend = composite(pd.DataFrame({"btop": std("btop"), "etop": std("etop"), "fwd_ep": std("fwd_ep_raw")}))
    z["value_blend"] = standardise(blend, cap, universe_mask, lo, hi)
    z["fwd_ep"] = std("fwd_ep_raw")
    quality_parts = pd.DataFrame({
        "profitability": composite(pd.DataFrame({"roa": std("roa"), "roe": std("roe"), "gpa": std("gpa")})),
        "leverage": -std("debt_assets"),
        "earnings_variability": -std("earn_var"),
        "accruals": -std("accruals"),
    })
    z["quality"] = standardise(composite(quality_parts), cap, universe_mask, lo, hi)

    check: dict[str, float] = {}
    weights = (cap[universe_mask] / cap[universe_mask].sum())
    for i in range(len(FACTORS)):
        values = z.loc[universe_mask, FACTORS[i]]
        ok = values.notna()
        if ok.sum() > 0:
            check[FACTORS[i]] = round(float((values[ok] * weights[ok]).sum() / weights[ok].sum()), 6)
    summary["capweighted_universe_exposure"] = check

    asof_text = T.isoformat()
    desc_rows = []
    exp_rows = []
    issuers = list(frame.index)
    raw_cols = ["beta_raw", "rstr_raw", "mom_12_1_raw", "dastd_raw", "cmra_raw", "hsigma_raw", "btop", "etop",
                "fwd_ep_raw", "roa", "roe", "gpa", "debt_assets", "earn_var", "accruals"]
    total_cap = float(cap[universe_mask].sum())
    for i in range(len(issuers)):
        issuer = issuers[i]
        r = frame.loc[issuer]
        missing = []
        for k in range(len(FACTORS)):
            if pd.isna(z.at[issuer, FACTORS[k]]):
                missing.append(FACTORS[k])
        desc = {
            "asof_date": asof_text, "universe": universe_name, "issuer_id": issuer, "gvkey": r["gvkey"],
            "iid": r["primary_iid"], "name": r["name"], "country": r["country"], "gics_sector": r["gics_sector"],
            "mcap_usd": r["mcap_usd"], "ln_mcap": r["ln_mcap"], "analyst_count": r["analyst_count"],
            "news_count_30d": r["news_count_30d"], "in_estimation_universe": bool(universe_mask.loc[issuer]),
            "source_flags": source.name, "missing_flags": ",".join(missing),
        }
        for k in range(len(raw_cols)):
            target = raw_cols[k] if raw_cols[k].endswith("_raw") else raw_cols[k] + "_raw"
            desc[target] = r.get(raw_cols[k]) if raw_cols[k] in frame.columns else None
        desc["debt_assets_raw"] = r.get("debt_assets")
        desc["earn_var_raw"] = r.get("earn_var")
        desc_rows.append(desc)
        exp = {
            "asof_date": asof_text, "universe": universe_name, "issuer_id": issuer,
            "mcap_usd": r["mcap_usd"], "gics_sector": r["gics_sector"], "country": r["country"],
            "in_estimation_universe": bool(universe_mask.loc[issuer]),
            "cap_weight": float(r["mcap_usd"]) / total_cap if universe_mask.loc[issuer] and total_cap > 0 else None,
            "analyst_count": r["analyst_count"], "news_count_30d": r["news_count_30d"],
            "source_flags": source.name, "missing_flags": ",".join(missing),
        }
        for column in ("size", "value", "value_blend", "quality", "momentum", "mom_12_1", "resvol", "lowvol", "beta", "fwd_ep"):
            value = z.at[issuer, column]
            exp[column] = None if pd.isna(value) else float(value)
        exp_rows.append(exp)
    store.delete_where("descriptors", "asof_date = ? AND universe = ?", [asof_text, universe_name])
    store.delete_where("exposures", "asof_date = ? AND universe = ?", [asof_text, universe_name])
    store.upsert("descriptors", desc_rows)
    store.upsert("exposures", exp_rows)
    summary["issuers_with_exposures"] = len(exp_rows)

    # Momentum measured at earlier dates (for the information-date analysis).
    lags = config.experiment.get("analysis", {}).get("staleness_lags_months", [0, 3, 6, 9, 12])
    rows_until = R.loc[:pd.Timestamp(T)]
    end_pos = len(rows_until) - 1
    hist_rows = []
    for k in range(len(lags)):
        pos = end_pos - int(lags[k]) * 21
        if pos < 260:
            continue
        mom = simple_momentum(rows_until, pos, 252, 21, float(fcfg.get("min_obs_fraction", 0.5)))
        mom = mom.reindex(frame.index)
        mom_z = standardise(mom, cap, universe_mask, lo, hi)
        measure_date = rows_until.index[pos].date().isoformat()
        for i in range(len(issuers)):
            raw_value = mom.get(issuers[i])
            if raw_value is None or pd.isna(raw_value):
                continue
            hist_rows.append({"asof_date": asof_text, "lag_months": int(lags[k]), "measure_date": measure_date,
                              "issuer_id": issuers[i], "mom_12_1": float(raw_value),
                              "mom_12_1_z": None if pd.isna(mom_z.get(issuers[i])) else float(mom_z.get(issuers[i]))})
    store.delete_where("momentum_history", "asof_date = ?", [asof_text])
    store.upsert("momentum_history", hist_rows)

    # Point-in-time vs restated fundamentals (look-ahead bias, BUILD_BRIEF §7.3).
    try:
        annual_r = source.fundamentals_annual(all_gvkeys, T, years, pit=False)
        book_r = source.book_equity(all_gvkeys, T, pit=False)
        fund_r = fundamental_descriptors(annual_r, book_r, caps_usd, fx_at_t, g2i, price_currency, fcfg)
        alt = frame.drop(columns=list(fund.columns), errors="ignore").join(fund_r, how="left")
        value_r = standardise(alt["btop"].astype(float), cap, universe_mask, lo, hi)
        q_parts = pd.DataFrame({
            "profitability": composite(pd.DataFrame({
                "roa": standardise(alt["roa"].astype(float), cap, universe_mask, lo, hi),
                "roe": standardise(alt["roe"].astype(float), cap, universe_mask, lo, hi),
                "gpa": standardise(alt["gpa"].astype(float), cap, universe_mask, lo, hi)})),
            "leverage": -standardise(alt["debt_assets"].astype(float), cap, universe_mask, lo, hi),
            "earnings_variability": -standardise(alt["earn_var"].astype(float), cap, universe_mask, lo, hi),
            "accruals": -standardise(alt["accruals"].astype(float), cap, universe_mask, lo, hi),
        })
        quality_r = standardise(composite(q_parts), cap, universe_mask, lo, hi)
        comparison = []
        for name, pit_values, restated in (("value", z["value"], value_r), ("quality", z["quality"], quality_r)):
            both = pd.concat([pit_values.rename("pit"), restated.rename("restated")], axis=1).dropna()
            if len(both) < 5:
                continue
            diff = (both["pit"] - both["restated"]).abs()
            comparison.append({"factor": name, "n": len(both), "corr": float(both.corr().iloc[0, 1]),
                               "mean_abs_diff": float(diff.mean()), "p90_abs_diff": float(diff.quantile(0.9)),
                               "share_abs_diff_gt_0_25": float((diff > 0.25).mean())})
        table = pd.DataFrame(comparison)
        table.to_csv(ws.tables / f"pit_vs_restated_{universe_name}.csv", index=False)
        summary["pit_vs_restated"] = comparison
    except Exception as exc:
        log.warning("PIT vs restated comparison skipped: %s", exc)
        summary["pit_vs_restated"] = f"skipped: {exc}"

    try:
        ratios = source.finratio(all_gvkeys, T)
        if ratios is not None and len(ratios) > 0:
            ours = frame[["gvkey", "roa", "roe", "debt_assets"]].copy()
            merged = ours.merge(ratios, on="gvkey", suffixes=("_ours", "_wrds"))
            checks = []
            for column in ("roa", "roe", "debt_assets"):
                pair = merged[[column + "_ours", column + "_wrds"]].apply(pd.to_numeric, errors="coerce").dropna()
                if len(pair) >= 10:
                    checks.append({"ratio": column, "n": len(pair),
                                   "spearman": float(pair.rank().corr().iloc[0, 1])})
            pd.DataFrame(checks).to_csv(ws.tables / f"finratio_check_{universe_name}.csv", index=False)
            summary["finratio_rank_corr"] = checks
    except Exception as exc:
        summary["finratio_rank_corr"] = f"skipped: {exc}"

    log_rows = []
    for i in range(len(source.log_rows)):
        entry = dict(source.log_rows[i])
        entry["asof_date"] = asof_text
        entry["logged_ts_utc"] = utc_now_iso()
        entry["input"] = f"{universe_name}:{entry['input']}"
        log_rows.append(entry)
    store.upsert("source_log", log_rows)
    summary["source_log_rows"] = len(log_rows)
    return json.loads(json.dumps(summary, default=str))


def portfolio_exposures(holdings: pd.DataFrame, exposures: pd.DataFrame, asof: str, universe: str) -> list[dict]:
    """X_pk = Σ w_i x_ik over holdings with data (re-normalised per factor), both weightings."""
    columns = ["size", "value", "value_blend", "quality", "momentum", "mom_12_1", "resvol", "lowvol", "beta"]
    if holdings is None or len(holdings) == 0:
        return []
    exp = exposures.set_index("issuer_id")
    usable = holdings[holdings["issuer_id"].notna()].copy()
    out: list[dict] = []
    groups = holdings.groupby("call_id")
    call_ids = list(groups.groups.keys())
    for c in range(len(call_ids)):
        all_rows = groups.get_group(call_ids[c])
        rows = usable[usable["call_id"] == call_ids[c]]
        for weighting, weight_col in (("model", "weight_norm"), ("equal", "weight_equal")):
            book = rows.groupby("issuer_id", as_index=False)[weight_col].sum()
            total_weight = float(all_rows[weight_col].fillna(0).sum())
            record: dict[str, Any] = {"call_id": call_ids[c], "asof_date": asof, "universe": universe,
                                      "weighting": weighting}
            covered_weight = 0.0
            n_covered = 0
            issuer_list = book["issuer_id"].tolist()
            weights = book[weight_col].fillna(0).tolist()
            for k in range(len(columns)):
                num = 0.0
                den = 0.0
                for j in range(len(issuer_list)):
                    if issuer_list[j] in exp.index:
                        value = exp.at[issuer_list[j], columns[k]]
                        if value is not None and pd.notna(value):
                            num += weights[j] * float(value)
                            den += weights[j]
                record[columns[k]] = num / den if den > 0 else None
            sectors: dict[str, float] = {}
            countries: dict[str, float] = {}
            for j in range(len(issuer_list)):
                if issuer_list[j] in exp.index and pd.notna(exp.at[issuer_list[j], "size"]):
                    covered_weight += weights[j]
                    n_covered += 1
                if issuer_list[j] in exp.index:
                    sector = exp.at[issuer_list[j], "gics_sector"]
                    country = exp.at[issuer_list[j], "country"]
                    key_s = str(sector) if sector is not None and pd.notna(sector) else "unknown"
                    key_c = str(country) if country is not None and pd.notna(country) else "unknown"
                    sectors[key_s] = sectors.get(key_s, 0.0) + weights[j]
                    countries[key_c] = countries.get(key_c, 0.0) + weights[j]
            record["coverage_weight"] = covered_weight / total_weight if total_weight > 0 else 0.0
            record["n_covered"] = n_covered
            record["sector_weights_json"] = json.dumps(sectors)
            record["country_weights_json"] = json.dumps(countries)
            out.append(record)
    return out
