"""Figure 6: share of connected calls invoking web search, by model and prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from .style import SEQUENTIAL, save, short_model


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    inv = result.get("search", {}).get("invocation", {})
    rows = inv.get("rows", [])
    if len(rows) == 0:
        return None
    models = inv.get("models", [])
    prompts = inv.get("prompts", [])
    matrix = np.full((len(models), len(prompts)), np.nan)
    for i in range(len(rows)):
        share = rows[i]["share_invoked"]
        if share is not None:
            matrix[models.index(rows[i]["model"]), prompts.index(rows[i]["prompt_id"])] = share * 100
    if not np.isfinite(matrix).any():
        return None
    fig, ax = plt.subplots(figsize=(10, 0.6 * len(models) + 1.6))
    im = ax.imshow(matrix, cmap=SEQUENTIAL, vmin=0, vmax=100, aspect="auto")
    for r in range(matrix.shape[0]):
        for c in range(matrix.shape[1]):
            if np.isfinite(matrix[r, c]):
                ax.text(c, r, f"{matrix[r, c]:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if matrix[r, c] > 55 else "#0b0b0b")
    ax.axvline(3.5, color="#0b0b0b", linewidth=1.2)
    labels = []
    for i in range(len(models)):
        labels.append(short_model(models[i]))
    ax.set_yticks(range(len(models)), labels)
    ax.set_xticks(range(len(prompts)), prompts, fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="% of calls with known search status")
    ax.set_title("Share of calls that used web search (%): free-form | mandates")
    fig.tight_layout()
    return save(fig, folder, "fig6_invocation", rows, synthetic)
