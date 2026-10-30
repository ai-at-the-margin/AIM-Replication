"""Figure 3: how measured exposures change across the four framings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from .style import FACTOR_LABELS, SERIES, save

FACTORS = ["value", "momentum", "quality", "size", "lowvol"]


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    rows = result.get("exposures", {}).get("by_framing_all", [])
    if len(rows) == 0:
        return None
    prompts = ["L1", "L2", "L3", "L4"]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    ax = axes[0]
    for f in range(len(FACTORS)):
        values = []
        for p in range(len(prompts)):
            value = np.nan
            for i in range(len(rows)):
                if rows[i]["prompt_id"] == prompts[p] and rows[i]["factor"] == FACTORS[f]:
                    value = rows[i]["cross_model_mean"] if rows[i]["cross_model_mean"] is not None else np.nan
            values.append(value)
        ax.plot(prompts, values, marker="o", color=SERIES[f], linewidth=2, markersize=5, label=FACTOR_LABELS[FACTORS[f]])
        ax.annotate(FACTOR_LABELS[FACTORS[f]], (3, values[-1]), xytext=(6, 0), textcoords="offset points",
                    fontsize=7, va="center", color="#52514e")
    ax.axhline(0, color="#c3c2b7", linewidth=0.8)
    ax.set_ylabel("cross-model mean loading")
    ax.set_title("Factor tilt across framings (L1 -> L4)")
    ax.legend(fontsize=7, loc="lower left")
    noise = result.get("exposures", {}).get("prompt_effect_vs_noise", [])
    ax = axes[1]
    labels = []
    values = []
    for i in range(len(noise)):
        labels.append(FACTOR_LABELS.get(noise[i]["factor"], noise[i]["factor"]))
        values.append(noise[i]["swing_over_noise"] or 0)
    ax.bar(labels, values, 0.55, color=SERIES[0])
    ax.axhline(1.0, color="#d03b3b", linewidth=1.0, label="swing = single-run noise")
    for i in range(len(noise)):
        se = noise[i].get("swing_over_se")
        if se is not None:
            ax.text(i, values[i], f"SEx {se:.1f}", ha="center", va="bottom", fontsize=7, color="#52514e")
    ax.set_ylabel("swing / single-run noise")
    ax.set_title("Framing effect versus run-to-run noise")
    ax.legend(fontsize=7)
    fig.tight_layout()
    return save(fig, folder, "fig3_framing", rows, synthetic)
