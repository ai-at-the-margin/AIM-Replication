"""Forced-discovery arm (BUILD_BRIEF §11 Phase 7): a timestamped WRDS screen the model must choose from.

`aim discovery screen` writes the candidate set (top N by our momentum, value or
quality score at T) and the exact prompt text, so the arm can be collected later
with the same compliance tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .prompts import build_prompt
from .settings import Config, Workspace
from .store.db import Store
from .utils import utc_now_iso, write_json

FACTOR_FOR = {"MOMENTUM": "momentum", "VALUE": "value", "QUALITY": "quality"}


def build_screen(ws: Workspace, config: Config, store: Store, asof: str, universe: str, mandate: str,
                 top: int = 100, min_mcap: float = 5e9) -> dict[str, Any]:
    factor = FACTOR_FOR[mandate]
    frame = store.query(
        f"SELECT e.issuer_id, d.name, e.gics_sector, e.country, e.mcap_usd, e.{factor} AS score "
        "FROM exposures e JOIN descriptors d USING (asof_date, universe, issuer_id) "
        f"WHERE e.asof_date = ? AND e.universe = ? AND e.in_estimation_universe AND e.mcap_usd >= ? "
        f"AND e.{factor} IS NOT NULL ORDER BY e.{factor} DESC LIMIT ?", [asof, universe, min_mcap, top])
    lines = []
    records = frame.to_dict("records")
    for i in range(len(records)):
        lines.append(f"{i + 1}. {records[i]['name']} ({records[i]['country']}, sector {records[i]['gics_sector']})")
    base = build_prompt(config, mandate, "en").text
    prompt = (base + "\n\nYou must choose all ten holdings from the following candidate list, which was screened "
              f"from the investable universe on {asof} by {factor}. Do not add names that are not on the list.\n\n"
              + "\n".join(lines))
    folder = ws.outputs / "discovery"
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"generated_ts_utc": utc_now_iso(), "asof": asof, "universe": universe, "mandate": mandate,
               "factor": factor, "top": top, "candidates": records, "prompt_text": prompt}
    path: Path = folder / f"screen_{mandate.lower()}_{asof}.json"
    write_json(path, payload)
    return {"path": str(path), "candidates": len(records)}
