"""Regression tests for saved-cohort rendering and Stage A-only inputs."""

import csv
import json
import warnings

import pytest
from click.testing import CliRunner

from aimargin.cli import main
from aimargin.figures import extras, fig1_overlap, fig4_mandates, fig5_search, fig6_invocation, fig7_queries


def test_figure_cli_routes_each_cohort_to_its_own_directory(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    expanded = outputs / "expanded"
    expanded.mkdir(parents=True)
    (expanded / "analysis.json").write_text(json.dumps({"cohort": "expanded"}))
    (outputs / "analysis.json").write_text(json.dumps({"cohort": "baseline"}))
    observed = []

    def render(result, folder, synthetic):
        observed.append((result["cohort"], folder, synthetic))
        return []

    monkeypatch.setattr("aimargin.figures.render_all", render)
    cli = CliRunner()
    command = ["--data-dir", str(tmp_path), "figures"]
    result = cli.invoke(main, command + ["--cohort", "expanded"])
    assert result.exit_code == 0, result.output
    assert observed == [("expanded", expanded / "figures", False)]
    assert not (outputs / "figures").exists()
    assert not (tmp_path / "processed").exists()
    result = cli.invoke(main, command)
    assert result.exit_code == 0, result.output
    assert observed[-1] == ("baseline", outputs / "figures", False)


def test_missing_expanded_analysis_names_the_required_command(tmp_path):
    result = CliRunner().invoke(main, ["--data-dir", str(tmp_path), "figures", "--cohort", "expanded"])
    assert result.exit_code == 1
    assert "aim analyze --cohort expanded" in result.output
    assert not list(tmp_path.iterdir())


def test_overlap_renders_roundoff_without_changing_exported_bounds(tmp_path):
    stat = {"mean": 0.6323213823213822, "lo": 0.6323213823213820, "hi": 0.6323213823213820}
    result = {"cohort": "expanded", "overlap": {"A": {"L2": {"b_cross_provider": stat}}}}
    assert fig1_overlap.render(result, tmp_path, False) == tmp_path / "fig1_overlap.png"
    with (tmp_path / "fig1_overlap.csv").open() as stream:
        row = next(row for row in csv.DictReader(stream)
                   if row["prompt_id"] == "L2" and row["comparison"] == "Cross-provider (all)")
    assert {key: float(row[key]) for key in stat} == stat


def test_overlap_rejects_materially_displaced_bounds(tmp_path):
    stat = {"mean": 0.63, "lo": 0.4, "hi": 0.6}
    result = {"overlap": {"A": {"L2": {"b_cross_provider": stat}}}}
    with pytest.raises(ValueError, match=r"L2 Cross-provider .*invalid upper confidence bound"):
        fig1_overlap.render(result, tmp_path, False)
    assert not list(tmp_path.iterdir())


def test_stage_a_only_skips_mandate_and_search_figures(tmp_path):
    result = {
        "mandates": {"heatmap_all": {"rows": [{"mandate": "VALUE", "n": 0}]}},
        "search": {"momentum": {"by_task": [{"offline": {"mean": 0.1}, "connected": {"mean": None}}]},
                   "invocation": {"rows": []}},
        "queries": {"by_prompt": []},
    }
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        for renderer in (fig4_mandates, fig5_search, fig6_invocation, fig7_queries):
            assert renderer.render(result, tmp_path, False) is None
    assert not list(tmp_path.iterdir())


def test_factor_space_plots_all_four_providers(tmp_path, monkeypatch):
    result = {"factor_space": {"pca": {"explained": [0.5, 0.3], "points": [
        {"provider": provider, "pc1": 0.1, "pc2": 0.2}
        for provider in ("openai", "anthropic", "deepseek", "kimi")
    ]}}}
    observed = []

    def save(fig, folder, name, rows, synthetic):
        ax = fig.axes[0]
        observed.extend(ax.get_legend_handles_labels()[1])
        assert [len(series.get_offsets()) for series in ax.collections] == [1, 1, 1, 1]
        extras.plt.close(fig)
        return folder / f"{name}.png"

    monkeypatch.setattr(extras, "save", save)
    extras.factor_space(result, tmp_path, False)
    assert observed == ["OpenAI", "Anthropic", "DeepSeek", "Kimi"]
