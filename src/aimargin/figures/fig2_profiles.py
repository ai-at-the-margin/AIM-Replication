"""Figure 2: factor loadings by model and the sector mix (free-form, Stage A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from .style import DIVERGING, FACTOR_LABELS, SERIES, save, short_model

FACTORS = ["value", "momentum", "quality", "size", "lowvol", "beta"]


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    rows = result.get("exposures", {}).get("by_model_stage_a", [])
    if len(rows) == 0:
        return None
    models = []
    for i in range(len(rows)):
        if rows[i]["model"] not in models:
            models.append(rows[i]["model"])
    matrix = np.full((len(models) + 1, len(FACTORS)), np.nan)
    for i in range(len(rows)):
        if rows[i]["factor"] in FACTORS and rows[i]["mean"] is not None:
            matrix[models.index(rows[i]["model"]), FACTORS.index(rows[i]["factor"])] = rows[i]["mean"]
    matrix[-1] = np.nanmean(matrix[:-1], axis=0)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), gridspec_kw={"width_ratios": [1.0, 1.15]})
    ax = axes[0]
    limit = max(0.6, float(np.nanmax(np.abs(matrix))))
    im = ax.imshow(matrix, cmap=DIVERGING, vmin=-limit, vmax=limit, aspect="auto")
    for r in range(matrix.shape[0]):
        for c in range(matrix.shape[1]):
            if np.isfinite(matrix[r, c]):
                ax.text(c, r, f"{matrix[r, c]:+.2f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(matrix[r, c]) > limit * 0.6 else "#0b0b0b",
                        fontweight="bold" if r == matrix.shape[0] - 1 else "normal")
    labels = []
    for i in range(len(models)):
        labels.append(short_model(models[i]))
    labels.append("mean")
    factor_labels = []
    for i in range(len(FACTORS)):
        factor_labels.append(FACTOR_LABELS[FACTORS[i]])
    ax.set_yticks(range(len(labels)), labels, fontsize=7)
    ax.set_xticks(range(len(FACTORS)), factor_labels)
    ax.axhline(len(models) - 0.5, color="#0b0b0b", linewidth=1.0)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03, label="loading (sd)")
    ax.set_title("Factor loadings by model, free-form (Stage A)")
    mix = result.get("exposures", {}).get("sector_mix_stage_a", {})
    sectors = mix.get("sectors", [])
    mix_rows = mix.get("rows", [])
    ax = axes[1]
    bottom = np.zeros(len(mix_rows))
    x = np.arange(len(mix_rows))
    for s in range(len(sectors)):
        values = []
        for r in range(len(mix_rows)):
            values.append(mix_rows[r].get(sectors[s], 0.0))
        color = SERIES[s] if s < len(SERIES) else "#c3c2b7"
        if sectors[s] == "Other":
            color = "#c3c2b7"
        ax.bar(x, values, 0.7, bottom=bottom, color=color, label=sectors[s], edgecolor="white", linewidth=0.6)
        bottom = bottom + np.array(values)
    names = []
    for r in range(len(mix_rows)):
        names.append(short_model(mix_rows[r]["model"]))
    ax.set_xticks(x, names, rotation=55, ha="right", fontsize=7)
    ax.set_ylabel("portfolio weight share")
    ax.set_ylim(0, 1)
    ax.legend(fontsize=6.5, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.32))
    ax.set_title("Sector mix (top GICS sectors)")
    fig.tight_layout()
    return save(fig, folder, "fig2_profiles", rows, synthetic)
