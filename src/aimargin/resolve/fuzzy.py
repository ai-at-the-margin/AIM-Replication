"""Company-name matching (BUILD_BRIEF §6.4 step 4)."""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from .master import SecurityMaster
from .normalise import name_key

ACCEPT_SCORE = 92.0
REVIEW_SCORE = 75.0


def _initials(text: str | None) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).split()
    out = ""
    for i in range(len(words)):
        out += words[i][0]
    return out


def is_acronym(short: str | None, full: str | None) -> bool:
    """'TSMC' for Taiwan Semiconductor Manufacturing Company, 'LVMH', 'AMD' ..."""
    token = re.sub(r"[^a-z0-9]+", "", str(short or "").lower())
    if not (2 <= len(token) <= 6) or " " in str(short or "").strip():
        return False
    candidates = [_initials(full), _initials(name_key(full))]
    for i in range(len(candidates)):
        if len(candidates[i]) >= 2 and (candidates[i].startswith(token) or token.startswith(candidates[i])):
            return True
    return False


def name_similarity(a: str | None, b: str | None) -> float:
    ka = name_key(a)
    kb = name_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 100.0
    if is_acronym(a, b) or is_acronym(b, a):
        return 90.0
    return float(max(fuzz.token_set_ratio(ka, kb), fuzz.ratio(ka, kb)))


def best_name_match(master: SecurityMaster, raw_name: str | None, limit: int = 3) -> list[tuple[str, float, list[int]]]:
    """Top company-name matches as (name_key, score, row indices)."""
    key = name_key(raw_name)
    if not key or len(master.names) == 0:
        return []
    results = process.extract(key, master.names, scorer=fuzz.token_set_ratio, limit=limit)
    out = []
    for i in range(len(results)):
        matched, score, _ = results[i]
        # token_set_ratio is generous with subsets; temper it with plain ratio.
        blended = 0.7 * float(score) + 0.3 * float(fuzz.ratio(key, matched))
        if key == matched:
            blended = 100.0
        out.append((matched, blended, master.name_rows.get(matched, [])))
    out.sort(key=lambda item: -item[1])
    return out
