"""Outcome classes and weight normalisation (BUILD_BRIEF §6.3)."""

from __future__ import annotations

OUTCOMES = ["valid", "insufficient_names", "excess_names", "format_failure", "refusal", "api_error"]
REQUIRED_NAMES = 10


def classify_parse(method: str, n_holdings: int, is_refusal: bool) -> str:
    """Pre-resolution status: refusal / format_failure / parsed."""
    if is_refusal:
        return "refusal"
    if method == "none" or n_holdings == 0:
        return "format_failure"
    return "parsed"


def classify_outcome(parse_status: str, n_distinct_issuers: int) -> str:
    """Final outcome once holdings are collapsed to issuers.

    Unresolved holdings count as distinct issuers here: the outcome describes the
    model's answer, not our resolver.
    """
    if parse_status in ("refusal", "format_failure", "api_error"):
        return parse_status
    if n_distinct_issuers < REQUIRED_NAMES:
        return "insufficient_names"
    if n_distinct_issuers > REQUIRED_NAMES:
        return "excess_names"
    return "valid"


def normalise_weights(raw_weights: list[float | None]) -> tuple[list[float], bool, float | None]:
    """Model weights if every one is a positive number, else equal weights.

    Returns (weights summing to 1, weights_provided, raw weight sum or None).
    """
    n = len(raw_weights)
    if n == 0:
        return [], False, None
    positive = True
    total = 0.0
    have_any = False
    for i in range(n):
        value = raw_weights[i]
        if value is None or value <= 0:
            positive = False
        else:
            total += value
            have_any = True
    raw_sum = total if have_any else None
    out: list[float] = []
    if positive and total > 0:
        for i in range(n):
            out.append(raw_weights[i] / total)
        return out, True, raw_sum
    for _i in range(n):
        out.append(1.0 / n)
    return out, False, raw_sum
