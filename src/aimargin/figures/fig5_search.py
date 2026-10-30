"""Figure 5: momentum exposure with search off vs available, by task and by model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from .style import PROVIDER, save, short_model


def _dumbbell(ax: plt.Axes, labels: list[str], before: list[float | None], after: list[float | None],
              notes: list[str], colors: list[str]) -> None:
    for i in range(len(labels)):
        y = len(labels) - 1 - i
        b = before[i]
        a = after[i]
        if b is not None and a is not None:
            ax.annotate("", xy=(a, y), xytext=(b, y),
                        arrowprops={"arrowstyle": "-|>", "color": colors[i], "lw": 1.8, "shrinkA": 3, "shrinkB": 5})
        if b is not None:
            ax.plot(b, y, "o", color="#0b0b0b", markersize=6)
        if a is not None:
            ax.plot(a, y, "o", markerfacecolor="white", markeredgecolor=colors[i], markersize=8, markeredgewidth=2)
        ax.text(1.02, y, notes[i], transform=ax.get_yaxis_transform(), fontsize=7, color="#898781", va="center")
    ax.set_yticks(range(len(labels)), list(reversed(labels)))
    ax.axvline(0, color="#c3c2b7", linewidth=0.8)
    ax.xaxis.grid(True)


def render(result: dict[str, Any], folder: Path, synthetic: bool) -> Path | None:
    momentum = result.get("search", {}).get("momentum", {})
    tasks = momentum.get("by_task", [])
    models = momentum.get("momentum_mandate_by_model", [])
    if len(tasks) == 0:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    labels = []
    before = []
    after = []
    notes = []
    colors = []
    for i in range(len(tasks)):
        labels.append(tasks[i]["task"])
        before.append(tasks[i]["offline"]["mean"])
        after.append(tasks[i]["connected"]["mean"])
        share = tasks[i].get("share_invoked")
        notes.append("" if share is None else f"{share * 100:.0f}% searched")
        change = (after[-1] or 0) - (before[-1] or 0)
        colors.append("#d03b3b" if change > 0.2 else "#2a78d6")
    _dumbbell(axes[0], labels, before, after, notes, colors)
    axes[0].set_xlabel("momentum loading")
    axes[0].set_title("What search availability changes, by task")
    labels = []
    before = []
    after = []
    notes = []
    colors = []
    for i in range(len(models)):
        labels.append(short_model(models[i]["model"]))
        before.append(models[i]["offline"]["mean"])
        after.append(models[i]["connected"]["mean"])
        share = models[i].get("share_invoked")
        notes.append("" if share is None else f"{share * 100:.0f}% searched")
        colors.append(PROVIDER.get(models[i].get("provider"), "#898781") if (share or 0) > 0 else "#898781")
    _dumbbell(axes[1], labels, before, after, notes, colors)
    axes[1].set_xlabel("momentum loading, Momentum mandate")
    axes[1].set_title("The Momentum mandate, by model")
    fig.suptitle("Filled = search off (baseline); open = search available", fontsize=8, color="#52514e", y=0.99)
    fig.tight_layout()
    table = []
    for i in range(len(tasks)):
        table.append({"task": tasks[i]["task"], "offline": tasks[i]["offline"]["mean"],
                      "connected": tasks[i]["connected"]["mean"], "share_invoked": tasks[i].get("share_invoked")})
    return save(fig, folder, "fig5_search", table, synthetic)
