"""Reasoning vs delivery (BUILD_BRIEF §8.10).

Within each mandate cell: delivered target exposure regressed on reasoning length
(per 100 words) and on whether the reasoning mentions the constraint. OLS with
HC1 standard errors; no claim of causality.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .data import MANDATE_TARGET, AnalysisData

MENTION_PATTERNS = {
    "VALUE": r"price[- ]to[- ]book|p/?b\b|p/?e\b|price[- ]to[- ]earnings|cash[- ]flow yield|cheap|valuation|value",
    "QUALITY": r"\broe\b|\broa\b|return on (equity|assets)|leverage|stable earnings|quality",
    "MOMENTUM": r"momentum|12[- ]month|twelve[- ]month|past year|excluding the (most )?recent month|price performance",
}


def ols_hc1(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n, k = X.shape
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    xtx_inv = np.linalg.pinv(X.T @ X)
    meat = X.T @ (X * (resid ** 2)[:, None])
    cov = xtx_inv @ meat @ xtx_inv * (n / max(1, n - k))
    return coef, np.sqrt(np.clip(np.diag(cov), 0.0, None))


def reasoning_analysis(data: AnalysisData) -> dict[str, Any]:
    frame = data.pexp[data.pexp["stage"].isin(["B", "C"])].merge(data.responses, on="call_id", how="left")
    rows = []
    for mandate in ("VALUE", "QUALITY", "MOMENTUM"):
        target = MANDATE_TARGET[mandate]
        cell = frame[(frame["prompt_id"] == mandate) & frame[target].notna()]
        cell = cell[cell["reasoning_word_count"].fillna(0) > 0]
        if len(cell) < 8:
            rows.append({"mandate": mandate, "n": int(len(cell)), "note": "too few books with reasoning text"})
            continue
        pattern = re.compile(MENTION_PATTERNS[mandate], re.I)
        mentions = []
        texts = cell["reasoning_text"].fillna("").tolist()
        for i in range(len(texts)):
            mentions.append(1.0 if pattern.search(texts[i]) else 0.0)
        mention_arr = np.array(mentions)
        words = cell["reasoning_word_count"].to_numpy(dtype=float) / 100.0
        y = cell[target].to_numpy(dtype=float)
        X = np.column_stack([np.ones(len(y)), words, mention_arr])
        if np.std(mention_arr) == 0:
            X = X[:, :2]
        coef, se = ols_hc1(y, X)
        row: dict[str, Any] = {"mandate": mandate, "target": target, "n": int(len(y)),
                               "share_mentioning": float(mention_arr.mean()),
                               "coef_words_per_100": float(coef[1]), "se_words": float(se[1]),
                               "corr_words": float(np.corrcoef(words, y)[0, 1]) if np.std(words) > 0 else None}
        if X.shape[1] == 3:
            row["coef_mentions"] = float(coef[2])
            row["se_mentions"] = float(se[2])
            row["mean_if_mentions"] = float(y[mention_arr == 1].mean()) if (mention_arr == 1).any() else None
            row["mean_if_not"] = float(y[mention_arr == 0].mean()) if (mention_arr == 0).any() else None
        points = []
        for i in range(len(y)):
            points.append({"words": float(words[i] * 100), "exposure": float(y[i]), "mentions": bool(mention_arr[i])})
        row["points"] = points
        rows.append(row)
    return {"rows": rows}
