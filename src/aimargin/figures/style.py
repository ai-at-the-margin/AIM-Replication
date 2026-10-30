"""Shared figure style: validated categorical palette, blue<->red diverging map, hairline axes."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
PROVIDER = {"openai": "#2a78d6", "anthropic": "#eb6834"}
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
DIVERGING = LinearSegmentedColormap.from_list("aim_div", ["#104281", "#3987e5", "#f0efec", "#e66767", "#a32f2f"])
SEQUENTIAL = LinearSegmentedColormap.from_list("aim_seq", ["#f4f8fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])
FACTOR_LABELS = {"size": "Size", "value": "Value", "quality": "Quality", "momentum": "Momentum", "lowvol": "Low-Vol",
                 "beta": "Beta", "resvol": "ResVol", "mom_12_1": "Mom 12-1", "value_blend": "Value (blend)"}
SYNTHETIC_NOTE = "SYNTHETIC DEMO DATA: simulated models and markets, not research results"


def setup() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2, "axes.titlesize": 10,
        "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.grid": False, "grid.color": GRID,
        "grid.linewidth": 0.6, "legend.frameon": False, "figure.dpi": 150, "savefig.dpi": 160,
        "axes.spines.top": False, "axes.spines.right": False,
    })


def save(fig: plt.Figure, folder: Path, name: str, table: pd.DataFrame | list | None, synthetic: bool,
         source: str = "Source: aimargin replication pipeline") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    note = source + ("   |   " + SYNTHETIC_NOTE if synthetic else "")
    fig.text(0.01, 0.005, note, fontsize=7, color=MUTED if not synthetic else "#d03b3b", ha="left", va="bottom")
    path = folder / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    if table is not None:
        frame = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
        frame.to_csv(folder / f"{name}.csv", index=False)
    return path


def short_model(model: str) -> str:
    return model.replace("claude-", "c-").replace("gpt-", "g-")
