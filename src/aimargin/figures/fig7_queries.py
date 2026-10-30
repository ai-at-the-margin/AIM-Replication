"""Figure 7: what the models search for, by prompt (classified visible queries)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from .style import SERIES, save

LABELS = {"single_stock_check": "single-stock check", "screen_or_list": "screen / list",
          "factor_or_market_data": "index / market data", "macro_news": "macro / news", "other": "other"}
COLORS = {"single_stock_check": SERIES[0], "screen_or_list": SERIES[1], "factor_or_market_data": SERIES[6],
          "macro_news": SERIES[2], "other": "#c3c2b7"}


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    queries = result.get("queries", {})
    rows = queries.get("by_prompt", [])
    if len(rows) == 0:
        return None
    classes = queries.get("classes", list(LABELS.keys()))
    fig, ax = plt.subplots(figsize=(10, 0.5 * len(rows) + 1.8))
    left = np.zeros(len(rows))
    y = np.arange(len(rows))[::-1]
    for c in range(len(classes)):
        values = []
        for r in range(len(rows)):
            values.append(rows[r].get(classes[c], 0.0) * 100)
        ax.barh(y, values, 0.62, left=left, color=COLORS[classes[c]], label=LABELS[classes[c]],
                edgecolor="white", linewidth=0.8)
        for r in range(len(rows)):
            if values[r] >= 9:
                ax.text(left[r] + values[r] / 2, y[r], f"{values[r]:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if classes[c] != "other" else "#0b0b0b")
        left = left + np.array(values)
    labels = []
    for r in range(len(rows)):
        labels.append(rows[r]["prompt_id"])
        ax.text(101, y[r], f"n={rows[r]['n']}", fontsize=7, color="#898781", va="center")
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of search queries (%)")
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=5)
    ax.set_title("What they search for, by prompt (both providers expose queries)")
    fig.tight_layout()
    return save(fig, folder, "fig7_queries", rows, synthetic)
