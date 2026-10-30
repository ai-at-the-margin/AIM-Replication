"""Jaccard, bootstrap helpers and Cohen's kappa."""

from __future__ import annotations

import numpy as np

from aimargin.analysis.bootstrap import (
    cross_pair_mean_draws,
    mean_ci,
    resample_counts,
    within_pair_mean_draws,
)
from aimargin.analysis.overlap import jaccard, jaccard_matrix
from aimargin.analysis.query_classify import classify_rule, cohen_kappa


def test_jaccard_matrix_matches_pairwise():
    sets = {"a": {"x", "y"}, "b": {"y", "z"}, "c": {"x", "y"}}
    J = jaccard_matrix(["a", "b", "c"], sets)
    assert abs(J[0, 1] - jaccard(sets["a"], sets["b"])) < 1e-12
    assert J[0, 2] == 1.0


def test_bootstrap_identity_draw_reproduces_point_estimate():
    rng = np.random.default_rng(0)
    block = rng.random((4, 5))
    ones_a = np.ones((1, 4))
    ones_b = np.ones((1, 5))
    assert abs(cross_pair_mean_draws(block, ones_a, ones_b)[0] - block.mean()) < 1e-12
    square = rng.random((4, 4))
    expected = (square.sum() - np.trace(square)) / 12
    assert abs(within_pair_mean_draws(square, np.ones((1, 4)))[0] - expected) < 1e-12
    counts = resample_counts(4, 10, rng)
    assert (counts.sum(axis=1) == 4).all()
    ci = mean_ci(np.array([1.0, 2.0, 3.0]), 500, rng)
    assert ci["lo"] <= 2.0 <= ci["hi"]


def test_query_rules_and_kappa():
    assert classify_rule("finance: NVDA", []) == "single_stock_check"
    assert classify_rule("best performing stocks past 12 months 2026", []) == "screen_or_list"
    assert classify_rule("MSCI ACWI sector weights", []) == "factor_or_market_data"
    assert classify_rule("Federal Reserve interest rate decision", []) == "macro_news"
    assert classify_rule("Apple stock price today", ["ciq:1"]) == "single_stock_check"
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    assert cohen_kappa(["a", "b"], ["b", "a"]) < 0
