"""Figures 1-7 and extension figures; each saved as PNG with its underlying CSV."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils import get_logger
from . import (
    extras,
    fig1_overlap,
    fig2_profiles,
    fig3_framing,
    fig4_mandates,
    fig5_search,
    fig6_invocation,
    fig7_queries,
)
from .style import setup

log = get_logger(__name__)


def render_all(result: dict[str, Any], folder: Path, synthetic: bool) -> list[Path]:
    setup()
    renderers = [fig1_overlap.render, fig2_profiles.render, fig3_framing.render, fig4_mandates.render,
                 fig5_search.render, fig6_invocation.render, fig7_queries.render, extras.crowding,
                 extras.factor_space, extras.staleness, extras.compliance]
    written: list[Path] = []
    for i in range(len(renderers)):
        try:
            path = renderers[i](result, folder, synthetic)
            if path is not None:
                written.append(path)
        except Exception as exc:  # one broken figure never stops the others
            log.warning("figure %s failed: %s", renderers[i].__module__, exc)
    return written
