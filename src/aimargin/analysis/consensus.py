"""Consensus names (BUILD_BRIEF §8.2): in >= 50% of a model's repetitions."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .data import AnalysisData, present_models


def issuer_names(holdings: pd.DataFrame) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    frame = holdings.dropna(subset=["issuer_id"])
    grouped = frame.groupby("issuer_id")
    keys = list(grouped.groups.keys())
    for i in range(len(keys)):
        group = grouped.get_group(keys[i])
        names = group["resolved_name"].dropna()
        tickers = group["resolved_ticker"].dropna() if "resolved_ticker" in group.columns else group["raw_ticker"]
        out[str(keys[i])] = {
            "name": str(names.mode().iat[0]) if len(names) else str(keys[i]),
            "ticker": str(tickers.mode().iat[0]) if len(tickers) else "",
            "sector": str(group["gics_sector"].dropna().mode().iat[0]) if group["gics_sector"].notna().any() else "",
            "country": str(group["country"].dropna().mode().iat[0]) if group["country"].notna().any() else "",
        }
    return out


def consensus_analysis(data: AnalysisData, threshold: float) -> dict[str, Any]:
    holdings = data.holdings[data.holdings["language"] == "en"]
    names = issuer_names(data.holdings)
    out: dict[str, Any] = {"threshold": threshold, "by_stage": {}}
    stages = sorted(holdings["stage"].dropna().unique().tolist())
    flagships = data.flagships()
    for s in range(len(stages)):
        stage_frame = holdings[holdings["stage"] == stages[s]]
        prompts = sorted(stage_frame["prompt_id"].dropna().unique().tolist())
        stage_out: dict[str, Any] = {}
        for p in range(len(prompts)):
            frame = stage_frame[(stage_frame["prompt_id"] == prompts[p]) & stage_frame["issuer_id"].notna()]
            models = present_models(data, frame)
            per_model: dict[str, list[dict[str, Any]]] = {}
            sets: dict[str, set[str]] = {}
            for m in range(len(models)):
                sub = frame[frame["model_requested"] == models[m]]
                n_reps = sub["call_id"].nunique()
                shares = sub.drop_duplicates(subset=["call_id", "issuer_id"]).groupby("issuer_id")["call_id"].nunique() / max(1, n_reps)
                chosen = shares[shares >= threshold].sort_values(ascending=False)
                rows = []
                members = set()
                ids = list(chosen.index)
                for i in range(len(ids)):
                    rows.append({"issuer_id": ids[i], "share": round(float(chosen.iat[i]), 3),
                                 **names.get(str(ids[i]), {})})
                    members.add(ids[i])
                per_model[models[m]] = rows
                sets[models[m]] = members
            all_sets = list(sets.values())
            everyone = set.intersection(*all_sets) if len(all_sets) > 0 else set()
            flag_sets = []
            for i in range(len(flagships)):
                if flagships[i] in sets:
                    flag_sets.append(sets[flagships[i]])
            flag_common = set.intersection(*flag_sets) if len(flag_sets) == 2 else set()
            freq = frame.drop_duplicates(subset=["call_id", "issuer_id"]).groupby("issuer_id")["call_id"].nunique()
            total = frame["call_id"].nunique()
            top = freq.sort_values(ascending=False).head(20)
            top_rows = []
            ids = list(top.index)
            for i in range(len(ids)):
                top_rows.append({"issuer_id": ids[i], "share_of_books": round(float(top.iat[i]) / max(1, total), 3),
                                 **names.get(str(ids[i]), {})})
            stage_out[prompts[p]] = {
                "per_model": per_model,
                "flagship_consensus": _named(sorted(flag_common), names),
                "all_model_consensus": _named(sorted(everyone), names),
                "top_names": top_rows, "n_books": int(total),
            }
        out["by_stage"][stages[s]] = stage_out
    return out


def _named(ids: list[str], names: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for i in range(len(ids)):
        entry = {"issuer_id": ids[i]}
        entry.update(names.get(str(ids[i]), {}))
        out.append(entry)
    return out
