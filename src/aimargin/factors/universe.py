"""Issuer market caps and the two estimation universes (BUILD_BRIEF §2.5)."""

from __future__ import annotations

import pandas as pd


def issue_caps(snapshot: pd.DataFrame, fx_at_t: dict[str, float]) -> pd.DataFrame:
    """Per-issue USD market cap at T (cshoc x prccd x FX)."""
    work = snapshot.copy()
    rates = []
    currencies = work["currency"].tolist()
    for i in range(len(currencies)):
        rates.append(fx_at_t.get(str(currencies[i])))
    work["usd_per_unit"] = pd.to_numeric(pd.Series(rates, index=work.index), errors="coerce")
    work["mcap_usd"] = work["shares"] * work["price"] * work["usd_per_unit"]
    return work


def issuer_caps(issues: pd.DataFrame, companies: pd.DataFrame, gvkey_to_issuer: dict[str, str]) -> pd.DataFrame:
    """Issuer cap = sum over its non-ADR issues (ADR lines only when nothing else exists).

    Also picks the primary issue: the company's priusa/prican/prirow flag when present,
    else the largest issue.
    """
    work = issues.dropna(subset=["mcap_usd"]).copy()
    work = work[work["mcap_usd"] > 0]
    work["is_adr"] = work["tpci"].astype(str) == "F"
    has_local = work.groupby("gvkey")["is_adr"].transform(lambda s: (~s).any())
    work = work[~work["is_adr"] | ~has_local]
    caps = work.groupby("gvkey", as_index=False).agg(mcap_usd=("mcap_usd", "sum"), n_issues=("iid", "count"))
    comp = companies.set_index("gvkey")
    flags = {}
    for column in ("priusa", "prican", "prirow", "loc"):
        flags[column] = comp[column].to_dict() if column in comp.columns else {}
    largest = work.sort_values("mcap_usd").drop_duplicates(subset=["gvkey"], keep="last").set_index("gvkey")
    primary_iids = []
    gvkeys = caps["gvkey"].tolist()
    available: dict[str, set] = {}
    issue_gvkeys = work["gvkey"].tolist()
    issue_iids = work["iid"].tolist()
    for i in range(len(issue_gvkeys)):
        available.setdefault(issue_gvkeys[i], set()).add(str(issue_iids[i]))
    for i in range(len(gvkeys)):
        g = gvkeys[i]
        loc = str(flags["loc"].get(g) or "")
        order = ["priusa", "prican", "prirow"]
        if loc == "CAN":
            order = ["prican", "priusa", "prirow"]
        elif loc not in ("USA", ""):
            order = ["prirow", "priusa", "prican"]
        chosen = None
        for j in range(len(order)):
            value = flags[order[j]].get(g)
            if value is not None and str(value) in available.get(g, set()):
                chosen = str(value)
                break
        if chosen is None:
            chosen = str(largest.loc[g, "iid"]) if g in largest.index else None
        primary_iids.append(chosen)
    caps["primary_iid"] = primary_iids
    issuers = []
    for i in range(len(gvkeys)):
        issuers.append(gvkey_to_issuer.get(gvkeys[i], "gvkey:" + str(gvkeys[i]).zfill(6)))
    caps["issuer_id"] = issuers
    meta = companies[["gvkey", "country", "gics_sector", "name"]].drop_duplicates(subset=["gvkey"])
    caps = caps.merge(meta, on="gvkey", how="left")
    primary_rows = work[["gvkey", "iid", "exchg", "tpci", "currency"]].rename(columns={"iid": "primary_iid"})
    caps = caps.merge(primary_rows, on=["gvkey", "primary_iid"], how="left")
    return caps.drop_duplicates(subset=["gvkey"])


def acwi_proxy(caps: pd.DataFrame, universe_cfg: dict) -> pd.DataFrame:
    """Largest primary common equity per ACWI country until 85% of that country's cap."""
    cfg = universe_cfg["acwi_proxy"]
    countries = list(cfg["countries"]["developed"]) + list(cfg["countries"]["emerging"])
    cut = float(cfg.get("cumulative_mcap_cut", 0.85))
    allowed_tpci = set(cfg.get("tpci", ["0"]))
    work = caps[caps["country"].isin(countries) & caps["tpci"].astype(str).isin(allowed_tpci)].copy()
    work = work.sort_values(["country", "mcap_usd"], ascending=[True, False])
    work["country_total"] = work.groupby("country")["mcap_usd"].transform("sum")
    work["cum_before"] = work.groupby("country")["mcap_usd"].cumsum() - work["mcap_usd"]
    selected = work[work["cum_before"] < cut * work["country_total"]].copy()
    return selected.drop(columns=["country_total", "cum_before"])


def us_broad(caps: pd.DataFrame, issues: pd.DataFrame, universe_cfg: dict) -> pd.DataFrame:
    cfg = universe_cfg["us_broad"]
    exchanges = set()
    values = cfg.get("exchg", [11, 12, 14])
    for i in range(len(values)):
        exchanges.add(str(values[i]))
    tpcis = set(cfg.get("tpci", ["0", "F"]))
    listed = issues[issues["exchg"].astype(str).isin(exchanges) & issues["tpci"].astype(str).isin(tpcis)]
    gvkeys = set(listed["gvkey"].tolist())
    out = caps[caps["gvkey"].isin(gvkeys) & (caps["mcap_usd"] >= float(cfg.get("min_mcap_usd", 3e8)))].copy()
    return out
