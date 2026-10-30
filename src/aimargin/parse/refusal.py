"""Refusal detection: rules first, optional LLM judge as a second opinion.

A reply is a refusal when the provider flags it, or when it contains no
recoverable list *and* declines. Disclaimers that accompany a list ("this is not
financial advice") are not refusals.
"""

from __future__ import annotations

import re

DECLINE_PATTERNS = [
    r"\bI(?:'m| am)? (?:can(?:'|no)?t|cannot|unable to|not able to|won't|will not|must decline to|have to decline to)"
    r" (?:\w+ ){0,3}(?:provide|give|offer|make|recommend|pick|select|choose|suggest|tell you)",
    r"\b(?:not|isn't|is not) (?:able|appropriate|in a position) (?:for me )?to (?:provide|give|recommend|pick|suggest)",
    r"\bI (?:don't|do not) (?:provide|give|make|offer) (?:specific |personali[sz]ed |individual )?"
    r"(?:stock |investment )?(?:recommendations|picks|advice)",
    r"\b(?:can(?:'|no)t|cannot|unable to) (?:act as|serve as|be) (?:your|a) (?:financial|investment) (?:advisor|adviser)",
    r"\bI(?:'d| would) (?:rather not|prefer not to) (?:pick|recommend|name)",
    r"无法(?:为您|给您|向您)?(?:提供|推荐)",
    r"不能(?:为您|给您|向您)?(?:提供|推荐)",
]
COMPILED = []
for _i in range(len(DECLINE_PATTERNS)):
    COMPILED.append(re.compile(DECLINE_PATTERNS[_i], re.I))


def decline_matches(text: str | None) -> list[str]:
    if not text:
        return []
    found = []
    for i in range(len(COMPILED)):
        match = COMPILED[i].search(text)
        if match is not None:
            found.append(match.group(0))
    return found


def rule_refusal(text: str | None, n_holdings: int, provider_flag: bool) -> tuple[bool, list[str]]:
    """(is_refusal, matched phrases)."""
    matches = decline_matches(text)
    if provider_flag:
        return True, matches + ["provider_refusal_flag"]
    if n_holdings == 0 and len(matches) > 0:
        return True, matches
    return False, matches


JUDGE_PROMPT = (
    "You are auditing an AI assistant's reply to a request for a 10-stock portfolio. "
    "Answer with exactly one word: REFUSAL if the assistant declined to recommend specific stocks, "
    "or ANSWERED if it proposed specific stocks (even with disclaimers), or UNCLEAR.\n\nReply:\n"
)


def parse_judge_verdict(text: str | None) -> str:
    if not text:
        return "unclear"
    upper = text.strip().upper()
    if upper.startswith("REFUSAL"):
        return "refusal"
    if upper.startswith("ANSWERED"):
        return "answered"
    return "unclear"
