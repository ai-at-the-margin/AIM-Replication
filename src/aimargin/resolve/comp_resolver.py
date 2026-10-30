"""Compustat fallback: exact (tic, exchange) on comp.security / comp.g_security rows."""

from __future__ import annotations

from .ciq_resolver import Match, match_ticker
from .master import SecurityMaster
from .normalise import ParsedTicker


def match_compustat(master: SecurityMaster, parsed: ParsedTicker, raw_name: str | None) -> Match | None:
    return match_ticker(master, parsed, raw_name, sources=("comp",))
