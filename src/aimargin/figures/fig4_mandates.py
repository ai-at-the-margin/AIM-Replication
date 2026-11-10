"""Figure 4: mandate loadings and each model's Δ in the requested factor (search off)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from .style import DIVERGING, FACTOR_LABELS, SERIES, save, short_model

FACTORS = ["value", "momentum", "quality", "size", "lowvol"]
MANDATES = ["VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"]
TARGET = {"VALUE": "value", "QUALITY": "quality", "MOMENTUM": "momentum"}


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    heat = result.get("mandates", {}).get("heatmap_all", {}).get("rows", [])
    deltas = result.get("mandates", {}).get("deltas", [])
    if len(heat) == 0:
        return None
    matrix = np.full((len(MANDATES), len(FACTORS)), np.nan)
    for r in range(len(heat)):
        if heat[r]["mandate"] in MANDATES:
            for c in range(len(FACTORS)):
                value = heat[r].get(FACTORS[c])
                if value is not None:
                    matrix[MANDATES.index(heat[r]["mandate"]), c] = value
    finite = matrix[np.isfinite(matrix)]
    if len(finite) == 0:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    ax = axes[0]
    limit = max(0.6, float(np.max(np.abs(finite))))
    ax.imshow(matrix, cmap=DIVERGING, vmin=-limit, vmax=limit, aspect="auto")
    for r in range(matrix.shape[0]):
        for c in range(matrix.shape[1]):
            if np.isfinite(matrix[r, c]):
                ax.text(c, r, f"{matrix[r, c]:+.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(matrix[r, c]) > limit * 0.6 else "#0b0b0b")
        target = TARGET.get(MANDATES[r])
        if target in FACTORS:
            ax.add_patch(Rectangle((FACTORS.index(target) - 0.5, r - 0.5), 1, 1, fill=False, linewidth=2,
                                   edgecolor="#0b0b0b"))
    labels = []
    for c in range(len(FACTORS)):
        labels.append(FACTOR_LABELS[FACTORS[c]])
    ax.set_xticks(range(len(FACTORS)), labels)
    ax.set_yticks(range(len(MANDATES)), ["Value", "Quality", "Momentum", "Unconstrained"])
    ax.set_title("Mean loading per mandate x factor (boxed = target)")
    ax = axes[1]
    models = []
    for i in range(len(deltas)):
        if deltas[i]["model"] not in models:
            models.append(deltas[i]["model"])
    x = np.arange(len(models))
    width = 0.27
    for s in range(3):
        mandate = MANDATES[s]
        values = []
        errs = [[], []]
        for m in range(len(models)):
            value = np.nan
            lo = 0.0
            hi = 0.0
            for i in range(len(deltas)):
                if deltas[i]["model"] == models[m] and deltas[i]["mandate"] == mandate and deltas[i]["delta"] is not None:
                    value = deltas[i]["delta"]
                    lo = value - deltas[i]["lo"] if deltas[i]["lo"] is not None else 0.0
                    hi = deltas[i]["hi"] - value if deltas[i]["hi"] is not None else 0.0
            values.append(value)
            errs[0].append(lo)
            errs[1].append(hi)
        ax.bar(x + (s - 1) * width, values, width * 0.9, color=SERIES[s], label=TARGET[mandate],
               yerr=errs, error_kw={"elinewidth": 0.7, "capsize": 1.5})
    names = []
    for m in range(len(models)):
        names.append(short_model(models[m]))
    ax.set_xticks(x, names, rotation=55, ha="right", fontsize=7)
    ax.axhline(0, color="#c3c2b7", linewidth=0.8)
    ax.set_ylabel("target lift vs own Unconstrained (sd)")
    ax.set_title("Directed response by model (95% CIs)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    return save(fig, folder, "fig4_mandates", deltas, synthetic)
