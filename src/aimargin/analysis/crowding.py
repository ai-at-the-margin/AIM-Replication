"""The 'AI crowd book' (extension, not in the paper).

If one dollar followed every valid recommendation in a cell, what aggregate book
would result? We report its top names, its active weights against the
cap-weighted estimation universe, its concentration (HHI, effective N) and its
factor exposure. This is the holdings-level view of 'AI at the margin'.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .data import FACTOR_COLS, AnalysisData


def crowd_book(holdings: pd.DataFrame) -> pd.Series:
    """Average weight per issuer across books (each book counts once)."""
    if len(holdings) == 0:
        return pd.Series(dtype=float)
    frame = holdings.dropna(subset=["issuer_id"])
    n_books = holdings["call_id"].nunique()
    weights = frame.groupby("issuer_id")["weight_norm"].sum() / max(1, n_books)
    return weights.sort_values(ascending=False)


def concentration(weights: pd.Series) -> dict[str, float | None]:
    if len(weights) == 0:
        return {"hhi": None, "effective_n": None, "top10_share": None}
    w = weights / weights.sum()
    hhi = float((w ** 2).sum())
    return {"hhi": hhi, "effective_n": 1.0 / hhi if hhi > 0 else None,
            "top10_share": float(w.sort_values(ascending=False).head(10).sum()), "n_names": int(len(w))}


def crowding_analysis(data: AnalysisData) -> dict[str, Any]:
    exposures = data.exposures.set_index("issuer_id") if len(data.exposures) else pd.DataFrame()
    universe_weight = pd.Series(dtype=float)
    if len(exposures):
        cw = exposures["cap_weight"].dropna()
        universe_weight = cw / cw.sum() if cw.sum() > 0 else cw
    names = data.holdings.dropna(subset=["issuer_id"]).groupby("issuer_id")["resolved_name"].agg(
        lambda s: s.mode().iat[0] if len(s.dropna()) else "")
    cells = [("All valid books", data.holdings), ("Stage A (free-form)", data.holdings[data.holdings["stage"] == "A"]),
             ("Stage B (mandates)", data.holdings[data.holdings["stage"] == "B"]),
             ("Stage C (search available)", data.holdings[data.holdings["stage"] == "C"])]
    out_cells = []
    for c in range(len(cells)):
        label, frame = cells[c]
        frame = frame[frame["language"] == "en"]
        book = crowd_book(frame)
        if len(book) == 0:
            continue
        top = book.head(25)
        rows = []
        ids = list(top.index)
        for i in range(len(ids)):
            uw = float(universe_weight.get(ids[i], 0.0)) if len(universe_weight) else None
            rows.append({"issuer_id": ids[i], "name": names.get(ids[i], ids[i]), "crowd_weight": float(top.iat[i]),
                         "universe_weight": uw,
                         "active_weight": float(top.iat[i]) - (uw or 0.0),
                         "overweight_ratio": float(top.iat[i]) / uw if uw else None,
                         "sector": str(exposures.at[ids[i], "gics_sector"]) if len(exposures) and ids[i] in exposures.index else None})
        factors: dict[str, float | None] = {}
        if len(exposures):
            for f in range(len(FACTOR_COLS)):
                column = FACTOR_COLS[f]
                values = exposures[column].reindex(book.index)
                ok = values.notna()
                factors[column] = float((values[ok] * book[ok]).sum() / book[ok].sum()) if ok.any() else None
        in_universe = float(book[book.index.isin(universe_weight.index)].sum() / book.sum()) if len(universe_weight) else None
        out_cells.append({"cell": label, "n_books": int(frame["call_id"].nunique()), "top": rows,
                          "concentration": concentration(book), "universe_concentration": concentration(universe_weight),
                          "exposures": factors, "share_in_universe": in_universe})
    return {"cells": out_cells}
