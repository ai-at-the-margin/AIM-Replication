"""Figure 1: name convergence across the four free-form framings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from .style import INK_2, SEQUENTIAL, SERIES, save, short_model

# Jaccard is bounded by 1, so an absolute tolerance suffices for rounding noise.
CI_ROUNDOFF = 1e-12


def _error_distance(mean: float, bound: float | None, lower: bool, context: str) -> float:
    if bound is None:
        return 0.0
    distance = mean - bound if lower else bound - mean
    if not np.isfinite(distance) or distance < -CI_ROUNDOFF:
        side = "lower" if lower else "upper"
        raise ValueError(f"{context}: invalid {side} confidence bound {bound!r} for mean {mean!r}")
    return max(0.0, distance)


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    stage = result.get("overlap", {}).get("A", {})
    if not stage:
        return None
    prompts = ["L1", "L2", "L3", "L4"]
    flagship_label = "OpenAI–Anthropic flagship pair" if result.get("cohort") == "expanded" else "Flagship pair"
    groups = [("a_flagships", flagship_label), ("b_cross_provider", "Cross-provider (all)"),
              ("c_within_provider", "Within provider"), ("d_within_model", "Within model")]
    rows = []
    distances = []
    for p in range(len(prompts)):
        cell = stage.get(prompts[p]) or {}
        for g in range(len(groups)):
            stat = cell.get(groups[g][0]) or {}
            rows.append({"prompt_id": prompts[p], "comparison": groups[g][1], "mean": stat.get("mean"),
                         "lo": stat.get("lo"), "hi": stat.get("hi")})
            m = stat.get("mean")
            context = f"{prompts[p]} {groups[g][1]}"
            if m is None:
                m = np.nan
            distances.append((_error_distance(m, stat.get("lo"), True, context),
                              _error_distance(m, stat.get("hi"), False, context)))
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    width = 0.19
    x = np.arange(len(prompts))
    for g in range(len(groups)):
        means = []
        errs = [[], []]
        for p in range(len(prompts)):
            i = p * len(groups) + g
            mean = rows[i]["mean"]
            means.append(mean if mean is not None else np.nan)
            lower, upper = distances[i]
            errs[0].append(lower)
            errs[1].append(upper)
        ax.bar(x + (g - 1.5) * width, means, width * 0.9, color=SERIES[g], label=groups[g][1],
               yerr=errs, error_kw={"elinewidth": 0.8, "ecolor": INK_2, "capsize": 2})
    ax.set_xticks(x, prompts)
    ax.set_ylabel("mean rep-pair Jaccard")
    ax.set_ylim(0, 1)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title("Name convergence by framing (95% bootstrap CIs)")
    l4 = stage.get("L4") or {}
    models = l4.get("models") or []
    heat = l4.get("heatmap") or []
    ax = axes[1]
    if models and heat:
        matrix = np.array(heat, dtype=float)
        im = ax.imshow(matrix, cmap=SEQUENTIAL, vmin=0, vmax=max(0.8, np.nanmax(matrix)))
        labels = []
        for i in range(len(models)):
            labels.append(short_model(models[i]))
        ax.set_xticks(range(len(models)), labels, rotation=60, ha="right", fontsize=7)
        ax.set_yticks(range(len(models)), labels, fontsize=7)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
        ax.set_title("L4 model x model overlap (diagonal = self-stability)")
    else:
        ax.axis("off")
    fig.tight_layout()
    return save(fig, folder, "fig1_overlap", rows, synthetic)
