"""Where the money would go (extension): regional mix by framing and provider, against the universe."""

from __future__ import annotations

from typing import Any

from .data import AnalysisData

REGIONS = {
    "United States": ["USA"],
    "Europe": ["GBR", "FRA", "DEU", "CHE", "NLD", "DNK", "SWE", "ESP", "ITA", "FIN", "NOR", "BEL", "IRL", "AUT", "PRT"],
    "Japan": ["JPN"],
    "China & HK": ["CHN", "HKG"],
    "Taiwan & Korea": ["TWN", "KOR"],
    "Other": [],
}


def region_of(country: Any) -> str:
    text = str(country) if country is not None else ""
    names = list(REGIONS.keys())
    for i in range(len(names)):
        if text in REGIONS[names[i]]:
            return names[i]
    return "Other"


def geography_analysis(data: AnalysisData) -> dict[str, Any]:
    holdings = data.holdings[data.holdings["language"] == "en"].copy()
    if len(holdings) == 0:
        return {"regions": list(REGIONS.keys()), "rows": [], "universe": {}}
    regions = []
    countries = holdings["country"].tolist()
    for i in range(len(countries)):
        regions.append(region_of(countries[i]))
    holdings["region"] = regions
    rows = []
    groups = holdings.groupby(["stage", "prompt_id", "provider"])
    keys = list(groups.groups.keys())
    for k in range(len(keys)):
        cell = groups.get_group(keys[k])
        n_books = max(1, cell["call_id"].nunique())
        row: dict[str, Any] = {"stage": keys[k][0], "prompt_id": keys[k][1], "provider": keys[k][2],
                               "n_books": int(cell["call_id"].nunique())}
        mix = cell.groupby("region")["weight_norm"].sum() / n_books
        names = list(REGIONS.keys())
        for i in range(len(names)):
            row[names[i]] = float(mix.get(names[i], 0.0))
        rows.append(row)
    universe: dict[str, float] = {}
    if len(data.exposures):
        uni = data.exposures[data.exposures["in_estimation_universe"] == True].copy()  # noqa: E712
        uni_regions = []
        uni_countries = uni["country"].tolist()
        for i in range(len(uni_countries)):
            uni_regions.append(region_of(uni_countries[i]))
        uni["region"] = uni_regions
        totals = uni.groupby("region")["mcap_usd"].sum()
        grand = float(totals.sum()) if len(totals) else 0.0
        names = list(REGIONS.keys())
        for i in range(len(names)):
            universe[names[i]] = float(totals.get(names[i], 0.0)) / grand if grand > 0 else 0.0
    adr_rows = []
    groups = holdings.groupby("provider")
    keys = list(groups.groups.keys())
    for k in range(len(keys)):
        cell = groups.get_group(keys[k])
        foreign = cell[cell["country"].fillna("") != "USA"]
        adr_rows.append({"provider": keys[k], "foreign_picks": int(len(foreign)),
                         "share_via_us_listing": float(foreign["is_us_listed"].fillna(False).mean()) if len(foreign) else None})
    return {"regions": list(REGIONS.keys()), "rows": rows, "universe": universe, "foreign_via_us_listing": adr_rows}
