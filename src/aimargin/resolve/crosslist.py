"""Manual overrides: ticker overrides and the cross-listing exception list."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TICKER_OVERRIDE_COLUMNS = ["raw_ticker", "raw_exchange", "raw_name", "item_id", "gvkey", "iid", "note"]
CROSSLIST_COLUMNS = ["issuer_id", "maps_to_issuer_id", "note"]


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        frame = pd.read_csv(path, dtype=str, comment="#").fillna("")
    except Exception:
        return pd.DataFrame(columns=columns)
    for i in range(len(columns)):
        if columns[i] not in frame.columns:
            frame[columns[i]] = ""
    return frame


def ensure_manual_files(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    templates = {
        "ticker_overrides.csv": TICKER_OVERRIDE_COLUMNS,
        "crosslisting_overrides.csv": CROSSLIST_COLUMNS,
        "query_labels_gold.csv": ["call_id", "event_idx", "query_text", "gold_class", "labeller"],
    }
    names = list(templates.keys())
    for i in range(len(names)):
        path = folder / names[i]
        if not path.exists():
            pd.DataFrame(columns=templates[names[i]]).to_csv(path, index=False)


def load_ticker_overrides(folder: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Key: (RAW_TICKER upper, raw exchange upper or '')."""
    frame = _read_csv(folder / "ticker_overrides.csv", TICKER_OVERRIDE_COLUMNS)
    out: dict[tuple[str, str], dict[str, str]] = {}
    records = frame.to_dict("records")
    for i in range(len(records)):
        key = (str(records[i]["raw_ticker"]).strip().upper(), str(records[i]["raw_exchange"]).strip().upper())
        if key[0] == "" and str(records[i]["raw_name"]).strip() == "":
            continue
        out[key] = records[i]
    return out


def load_crosslist_overrides(folder: Path) -> dict[str, str]:
    frame = _read_csv(folder / "crosslisting_overrides.csv", CROSSLIST_COLUMNS)
    out: dict[str, str] = {}
    records = frame.to_dict("records")
    for i in range(len(records)):
        if records[i]["issuer_id"] and records[i]["maps_to_issuer_id"]:
            out[str(records[i]["issuer_id"]).strip()] = str(records[i]["maps_to_issuer_id"]).strip()
    return out


def apply_crosslist(issuer_id: str | None, overrides: dict[str, str]) -> str | None:
    seen = set()
    current = issuer_id
    while current is not None and current in overrides and current not in seen:
        seen.add(current)
        current = overrides[current]
    return current
