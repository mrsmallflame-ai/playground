"""Smoke tests for chart construction (no display needed — Agg figures)."""

import matplotlib

matplotlib.use("Agg")

from frisbee_analytics.viz.plots import metrics_bar_figure, progress_figure, trajectory_figure
from test_storage import make_record


def test_trajectory_figure_single_throw_has_no_legend():
    fig = trajectory_figure([make_record()])
    ax = fig.axes[0]
    assert ax.get_legend() is None
    assert len(ax.lines) >= 1


def test_trajectory_figure_multiple_throws_has_legend():
    fig = trajectory_figure([make_record("a"), make_record("b")])
    assert fig.axes[0].get_legend() is not None


def test_metrics_bar_figure_builds():
    fig = metrics_bar_figure([make_record("a"), make_record("b")])
    assert len(fig.axes) == 4


def test_progress_figure_builds():
    fig = progress_figure([make_record(f"t{i}") for i in range(3)])
    assert len(fig.axes) == 2
