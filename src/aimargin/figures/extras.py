"""Extension figures: crowd book, factor-space map, implied information date, compliance funnel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from .style import MUTED, PROVIDER, PROVIDER_LABEL, SERIES, save, short_model


def crowding(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    cells = result.get("crowding", {}).get("cells", [])
    if len(cells) == 0:
        return None
    top = cells[0]["top"][:15]
    fig, ax = plt.subplots(figsize=(9, 5))
    names = []
    crowd = []
    universe = []
    for i in range(len(top)):
        names.append(str(top[i]["name"])[:28])
        crowd.append(top[i]["crowd_weight"] * 100)
        universe.append((top[i]["universe_weight"] or 0) * 100)
    y = np.arange(len(names))[::-1]
    ax.barh(y + 0.18, crowd, 0.34, color=SERIES[0], label="AI crowd book")
    ax.barh(y - 0.18, universe, 0.34, color="#c3c2b7", label="cap-weighted universe")
    ax.set_yticks(y, names, fontsize=7)
    ax.set_xlabel("weight (%)")
    ax.legend(fontsize=7)
    ax.set_title("AI crowd book vs the market: top 15 names (all valid books)")
    fig.tight_layout()
    return save(fig, folder, "ext_crowding", top, synthetic)


def factor_space(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    space = result.get("factor_space", {})
    points = space.get("pca", {}).get("points", [])
    pairs = space.get("names_vs_factors", {})
    if len(points) == 0:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axes[0]
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        by_provider.setdefault(point["provider"], []).append(point)
    for provider, books in by_provider.items():
        xs = []
        ys = []
        for book in books:
            xs.append(book["pc1"])
            ys.append(book["pc2"])
        ax.scatter(xs, ys, s=9, alpha=0.45, color=PROVIDER.get(provider, MUTED),
                   label=PROVIDER_LABEL.get(provider, provider), edgecolors="none")
    explained = space.get("pca", {}).get("explained", [0, 0])
    ax.set_xlabel(f"PC1 ({explained[0] * 100:.0f}% of variance)")
    ax.set_ylabel(f"PC2 ({explained[1] * 100:.0f}%)" if len(explained) > 1 else "PC2")
    ax.legend(fontsize=7)
    ax.set_title("Every book in factor space (PCA of loadings)")
    ax = axes[1]
    bins = pairs.get("bins", [])
    centres = []
    means = []
    lo = []
    hi = []
    for i in range(len(bins)):
        centres.append((bins[i]["lo"] + bins[i]["hi"]) / 2)
        means.append(bins[i]["mean_factor_distance"])
        lo.append(bins[i]["p25"])
        hi.append(bins[i]["p75"])
    ax.fill_between(centres, lo, hi, color=SERIES[0], alpha=0.12, linewidth=0)
    ax.plot(centres, means, marker="o", color=SERIES[0], linewidth=2, markersize=5)
    ax.set_xlabel("name distance (1 - Jaccard)")
    ax.set_ylabel("factor distance (Euclidean, sd)")
    corr = pairs.get("corr")
    ax.set_title(f"Different names, similar positions? (corr = {corr:.2f})" if corr is not None else "Names vs factors")
    fig.tight_layout()
    return save(fig, folder, "ext_factor_space", bins, synthetic)


def staleness(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    data = result.get("staleness", {})
    curves = data.get("curves", [])
    if len(curves) == 0:
        return None
    fig, ax = plt.subplots(figsize=(9, 4.6))
    count = 0
    for i in range(len(curves)):
        if "offline" not in curves[i]["cell"]:
            continue
        values = []
        for k in range(len(curves[i]["values"])):
            values.append(np.nan if curves[i]["values"][k] is None else curves[i]["values"][k])
        color = SERIES[count % len(SERIES)]
        ax.plot(curves[i]["lags"], values, color=color, linewidth=1.6, label=short_model(curves[i]["model"]))
        count += 1
    ax.axhline(0, color="#c3c2b7", linewidth=0.8)
    ax.set_xlabel("momentum measured k months before the as-of date")
    ax.set_ylabel("mean book 12-1 momentum (sd)")
    ax.set_title("Implied information date: offline Momentum-mandate books")
    ax.legend(fontsize=6.5, ncol=2)
    fig.tight_layout()
    return save(fig, folder, "ext_staleness", data.get("rows", []), synthetic)


def compliance(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    funnel = result.get("compliance", {}).get("funnel", [])
    if len(funnel) == 0:
        return None
    fig, ax = plt.subplots(figsize=(9, 4))
    for i in range(len(funnel)):
        steps = funnel[i]["steps"]
        labels = []
        values = []
        for k in range(len(steps)):
            labels.append(steps[k]["step"])
            values.append(steps[k]["share"] * 100)
        ax.plot(labels, values, marker="o", color=SERIES[i], linewidth=2, label=funnel[i]["mandate"].title())
    ax.set_ylabel("books still passing (%)")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=7)
    ax.set_title("Mandate compliance funnel (cumulative)")
    fig.tight_layout()
    return save(fig, folder, "ext_compliance_funnel", funnel, synthetic)
