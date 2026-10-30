"""Mandate compliance (BUILD_BRIEF §8.11).

A book passes when: target exposure > +0.25σ (no target for UNCONSTRAINED), no
weight above 15%, at least four GICS sectors, every holding >= $5bn market cap.
Missing data fails its criterion and is reported as such.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .data import MANDATE_TARGET, MANDATES, AnalysisData, present_models

CRITERIA = ["target_exposure", "max_weight", "min_sectors", "min_mcap"]


def book_checks(data: AnalysisData, settings: dict[str, Any]) -> pd.DataFrame:
    pexp = data.pexp[data.pexp["prompt_id"].isin(MANDATES) & data.pexp["stage"].isin(["B", "C"])]
    if len(pexp) == 0:
        return pd.DataFrame()
    exposures = data.exposures.set_index("issuer_id") if len(data.exposures) else pd.DataFrame()
    holdings = data.holdings
    rows = []
    records = pexp.to_dict("records")
    for i in range(len(records)):
        r = records[i]
        book = holdings[holdings["call_id"] == r["call_id"]]
        target = MANDATE_TARGET.get(r["prompt_id"])
        value = r.get(target) if target else None
        pass_target = True if target is None else (value is not None and pd.notna(value)
                                                   and float(value) > float(settings["target_exposure_min"]))
        weights = book.groupby("issuer_id")["weight_norm"].sum() if len(book) else pd.Series(dtype=float)
        pass_weight = bool(len(weights) > 0 and float(weights.max()) <= float(settings["max_weight"]) + 1e-9)
        sectors = book["gics_sector"].dropna().astype(str).nunique()
        pass_sectors = sectors >= int(settings["min_sectors"])
        caps = []
        issuers = book["issuer_id"].dropna().unique().tolist()
        missing_cap = bool(book["issuer_id"].isna().any())
        for k in range(len(issuers)):
            if len(exposures) and issuers[k] in exposures.index:
                caps.append(exposures.at[issuers[k], "mcap_usd"])
            else:
                missing_cap = True
        pass_mcap = (not missing_cap) and len(caps) > 0 and float(pd.Series(caps).min()) >= float(settings["min_mcap_usd"])
        rows.append({"call_id": r["call_id"], "model": r["model_requested"], "prompt_id": r["prompt_id"],
                     "stage": r["stage"], "search_invoked": bool((r.get("search_count") or 0) > 0),
                     "target_value": value, "target_exposure": pass_target, "max_weight": pass_weight,
                     "min_sectors": pass_sectors, "min_mcap": pass_mcap,
                     "pass_all": pass_target and pass_weight and pass_sectors and pass_mcap})
    return pd.DataFrame(rows)


def compliance_analysis(data: AnalysisData, settings: dict[str, Any]) -> dict[str, Any]:
    checks = book_checks(data, settings)
    if len(checks) == 0:
        return {"rows": [], "funnel": []}
    checks["search_state"] = "offline"
    checks.loc[checks["stage"] == "C", "search_state"] = "connected_not_invoked"
    checks.loc[(checks["stage"] == "C") & checks["search_invoked"], "search_state"] = "connected_invoked"
    rows = []
    models = present_models(data, checks.rename(columns={"model": "model_requested"}))
    for m in range(len(models)):
        for state in ("offline", "connected_invoked", "connected_not_invoked"):
            for p in range(len(MANDATES)):
                cell = checks[(checks["model"] == models[m]) & (checks["search_state"] == state)
                              & (checks["prompt_id"] == MANDATES[p])]
                if len(cell) == 0:
                    continue
                row = {"model": models[m], "search_state": state, "mandate": MANDATES[p], "n": int(len(cell)),
                       "pass_all": float(cell["pass_all"].mean())}
                for c in range(len(CRITERIA)):
                    row[CRITERIA[c]] = float(cell[CRITERIA[c]].mean())
                rows.append(row)
    funnel = []
    for p in range(len(MANDATES)):
        cell = checks[checks["prompt_id"] == MANDATES[p]]
        if len(cell) == 0:
            continue
        mask = pd.Series(True, index=cell.index)
        steps = [{"step": "books", "share": 1.0, "n": int(len(cell))}]
        for c in range(len(CRITERIA)):
            mask = mask & cell[CRITERIA[c]]
            steps.append({"step": CRITERIA[c], "share": float(mask.mean()), "n": int(mask.sum())})
        funnel.append({"mandate": MANDATES[p], "steps": steps})
    return {"rows": rows, "funnel": funnel, "criteria": CRITERIA, "settings": settings}
