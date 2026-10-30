"""Factor-space map and 'different names, similar positions' (extension).

1. PCA of portfolio exposure vectors: where every book sits in factor space.
2. For random pairs of books from different models: name distance (1 - Jaccard)
   against factor distance (Euclidean on the six loadings). A flat relationship
   means books that share few names can still carry the same position.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .data import FACTOR_COLS, AnalysisData
from .overlap import issuer_sets, jaccard


def pca_map(frame: pd.DataFrame, limit: int = 2500, rng: np.random.Generator | None = None) -> dict[str, Any]:
    data = frame.dropna(subset=FACTOR_COLS)
    if len(data) < 5:
        return {"points": [], "explained": [], "loadings": []}
    if len(data) > limit and rng is not None:
        data = data.iloc[rng.choice(len(data), limit, replace=False)]
    X = data[FACTOR_COLS].to_numpy(dtype=float)
    mean = X.mean(axis=0)
    Xc = X - mean
    _, s, vt = np.linalg.svd(Xc, full_matrices=False)
    explained = (s ** 2) / max(1e-12, (s ** 2).sum())
    coords = Xc @ vt[:2].T
    points = []
    records = data[["call_id", "model_requested", "provider", "prompt_id", "stage", "search_count"]].to_dict("records")
    for i in range(len(records)):
        points.append({"call_id": records[i]["call_id"], "model": records[i]["model_requested"],
                       "provider": records[i]["provider"], "prompt_id": records[i]["prompt_id"],
                       "stage": records[i]["stage"], "searched": bool((records[i]["search_count"] or 0) > 0),
                       "pc1": float(coords[i, 0]), "pc2": float(coords[i, 1])})
    loadings = []
    for k in range(min(2, len(vt))):
        row = {"component": f"PC{k + 1}", "explained": float(explained[k])}
        for f in range(len(FACTOR_COLS)):
            row[FACTOR_COLS[f]] = float(vt[k, f])
        loadings.append(row)
    return {"points": points, "explained": explained[:4].tolist(), "loadings": loadings}


def name_vs_factor_distance(data: AnalysisData, frame: pd.DataFrame, n_pairs: int,
                            rng: np.random.Generator) -> dict[str, Any]:
    books = frame.dropna(subset=FACTOR_COLS).reset_index(drop=True)
    if len(books) < 10:
        return {"pairs": [], "bins": [], "corr": None}
    sets = issuer_sets(data.holdings)
    X = books[FACTOR_COLS].to_numpy(dtype=float)
    models = books["model_requested"].tolist()
    prompts = books["prompt_id"].tolist()
    ids = books["call_id"].tolist()
    pairs = []
    attempts = 0
    while len(pairs) < n_pairs and attempts < n_pairs * 5:
        attempts += 1
        i = int(rng.integers(0, len(books)))
        j = int(rng.integers(0, len(books)))
        if i == j or models[i] == models[j] or prompts[i] != prompts[j]:
            continue
        name_distance = 1.0 - jaccard(sets.get(ids[i], set()), sets.get(ids[j], set()))
        factor_distance = float(np.sqrt(((X[i] - X[j]) ** 2).sum()))
        pairs.append({"name_distance": name_distance, "factor_distance": factor_distance, "prompt_id": prompts[i]})
    frame_pairs = pd.DataFrame(pairs)
    if len(frame_pairs) < 5:
        return {"pairs": pairs, "bins": [], "corr": None}
    corr = float(np.corrcoef(frame_pairs["name_distance"], frame_pairs["factor_distance"])[0, 1])
    slope = float(np.polyfit(frame_pairs["name_distance"], frame_pairs["factor_distance"], 1)[0])
    bins = []
    edges = np.linspace(0.0, 1.0, 11)
    for b in range(10):
        mask = (frame_pairs["name_distance"] >= edges[b]) & (frame_pairs["name_distance"] < edges[b + 1] + (1e-9 if b == 9 else 0))
        cell = frame_pairs[mask]
        if len(cell) == 0:
            continue
        bins.append({"lo": float(edges[b]), "hi": float(edges[b + 1]), "n": int(len(cell)),
                     "mean_factor_distance": float(cell["factor_distance"].mean()),
                     "p25": float(cell["factor_distance"].quantile(0.25)),
                     "p75": float(cell["factor_distance"].quantile(0.75))})
    sample = frame_pairs.sample(n=min(600, len(frame_pairs)), random_state=1).to_dict("records")
    return {"pairs": sample, "bins": bins, "corr": corr, "slope": slope, "n_pairs": int(len(frame_pairs))}


def factor_space_analysis(data: AnalysisData, rng: np.random.Generator) -> dict[str, Any]:
    frame = data.pexp[data.pexp["language"] == "en"]
    return {
        "pca": pca_map(frame, rng=rng),
        "names_vs_factors": name_vs_factor_distance(data, frame[frame["stage"] == "A"], 4000, rng),
    }
