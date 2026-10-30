"""`aim report`: docs/RESULTS.md with our numbers next to the paper's headline numbers."""

from __future__ import annotations

from typing import Any

from .settings import Workspace
from .utils import read_json, utc_now_iso


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):+.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _note(row: dict[str, Any]) -> str:
    if row.get("ours") is None:
        return "not measured yet (needs the relevant stage collected / exposures built)"
    diff = row.get("difference")
    base = row.get("note") or ""
    if diff is None:
        return base
    size = abs(diff)
    verdict = "close to the paper" if size < 0.1 else ("same direction, different size" if (row["paper"] or 0) * row["ours"] > 0
                                                       else "different sign: investigate")
    return (verdict + (". " + base if base else "")).strip()


def write_results(ws: Workspace) -> str:
    result = read_json(ws.outputs / "analysis.json", default={}) or {}
    lines = ["# Results", "", f"Generated {utc_now_iso()} from `outputs/analysis.json` (workspace: **{ws.name}**, "
             f"as-of {result.get('asof')}, universe {result.get('universe')}).", ""]
    if ws.is_demo:
        lines += ["> **Synthetic demo.** Every number below comes from simulated model responses and a synthetic "
                  "market. It demonstrates the pipeline end to end; it is not a research finding.", ""]
    lines += ["## Our numbers next to the paper's headline numbers", "",
              "The paper's figures are sanity checks, not targets. 'Note' gives an automatic first reading of each "
              "difference; the team should replace it with the substantive explanation before circulating.", "",
              "| Metric | Paper | Ours | Difference | Note |", "|---|---|---|---|---|"]
    rows = result.get("paper_comparison", [])
    for i in range(len(rows)):
        r = rows[i]
        lines.append(f"| {r['label']} | {_fmt(r['paper'])} | {_fmt(r['ours'])} | {_fmt(r['difference'])} | {_note(r)} |")
    lines.append("")
    ops = result.get("ops", {})
    lines += ["## Collection", "", "| Stage | Planned | Collected | Completed | Valid | Cost (USD) |", "|---|---|---|---|---|---|"]
    stages = ops.get("by_stage", [])
    for i in range(len(stages)):
        s = stages[i]
        lines.append(f"| {s['stage']} | {s['planned']:,} | {s['collected']:,} | {s['completed']:,} | {s['valid']:,} | "
                     f"{s['cost_usd']:.2f} |")
    lines.append("")
    rate = ops.get("resolution_rate")
    lines.append(f"Resolution rate: {rate:.2%}" if rate is not None else "Resolution rate: n/a")
    lines.append("")
    staleness = result.get("staleness", {}).get("rows", [])
    if staleness:
        lines += ["## Extension: implied information date", "",
                  "| Model | Cell | Implied lag (months) | Stated cutoff | Cutoff lag (months) |", "|---|---|---|---|---|"]
        for i in range(len(staleness)):
            s = staleness[i]
            lines.append(f"| {s['model']} | {s['cell']} | {s['implied_lag_months']} | {s.get('stated_cutoff') or 'n/a'} | "
                         f"{s.get('stated_cutoff_lag_months') if s.get('stated_cutoff_lag_months') is not None else 'n/a'} |")
        lines.append("")
    crowd = result.get("crowding", {}).get("cells", [])
    if crowd:
        c = crowd[0]
        lines += ["## Extension: the AI crowd book", "",
                  f"Across {c['n_books']:,} valid books the aggregate book holds {c['concentration'].get('n_names')} names; "
                  f"effective N = {c['concentration'].get('effective_n') or 0:.1f} versus "
                  f"{c['universe_concentration'].get('effective_n') or 0:.1f} for the cap-weighted universe.", ""]
    lines += ["## Figures", "", "PNG + CSV pairs live in `outputs/figures/` (git-ignored for live data).", ""]
    text = "\n".join(lines)
    path = ws.docs_dir / "RESULTS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)
