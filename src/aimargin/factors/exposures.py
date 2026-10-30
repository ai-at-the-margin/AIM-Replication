"""Portfolio exposures X_pk = Σ_i w_i x_ik (BUILD_BRIEF §7.4); implementation in build.py."""

from .build import FACTORS, portfolio_exposures

__all__ = ["FACTORS", "portfolio_exposures"]
