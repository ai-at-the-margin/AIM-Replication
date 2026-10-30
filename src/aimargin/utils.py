"""Small shared helpers: logging, hashing, JSON IO, safe numerics."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

_LOGGING_READY = False


def get_logger(name: str) -> logging.Logger:
    global _LOGGING_READY
    if not _LOGGING_READY:
        level = os.environ.get("AIM_LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        _LOGGING_READY = True
    return logging.getLogger(name)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def stable_hash(obj: Any, length: int = 16) -> str:
    """Deterministic short hash of any JSON-serialisable object."""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def write_json(path: Path, data: Any, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=indent, default=_json_default)
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _json_default(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def to_float(value: Any) -> float | None:
    """Parse numbers like '12.5', '12.5%', '$1,000' or 7; anything else is None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def clean_number(value: Any) -> float | None:
    """Like to_float but also maps pandas/numpy NA to None."""
    if value is None:
        return None
    try:
        if value != value:  # NaN check that works for numpy scalars too
            return None
    except Exception:
        pass
    return to_float(value)


def as_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if text == "" or text.lower() in ("none", "nat", "nan"):
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def round_or_none(value: Any, digits: int = 4) -> float | None:
    number = clean_number(value)
    if number is None:
        return None
    return round(number, digits)
