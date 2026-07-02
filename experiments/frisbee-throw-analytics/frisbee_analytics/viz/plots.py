"""Statistical charts (matplotlib figures, embeddable in Tkinter).

Palette and chart chrome follow a validated categorical palette: series
hues are assigned in fixed slot order (never cycled per-chart), grids and
axes are recessive hairlines, and text stays in ink colours rather than
series colours.
"""

from __future__ import annotations

from matplotlib.figure import Figure

from ..models import ThrowRecord

# Categorical slots, fixed order (light mode). A 9th+ throw reuses slot
# order deliberately only after all eight are exhausted.
SERIES = [
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
    "#e87ba4",  # magenta
    "#eb6834",  # orange
]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(BASELINE)
        ax.spines[spine].set_linewidth(0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.title.set_color(INK)
    ax.xaxis.label.set_color(INK_MUTED)
    ax.yaxis.label.set_color(INK_MUTED)


def _new_figure(width: float = 6.4, height: float = 4.0) -> Figure:
    fig = Figure(figsize=(width, height), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    return fig


def trajectory_figure(records: list[ThrowRecord]) -> Figure:
    """Flight paths of one or more throws in image coordinates."""
    fig = _new_figure()
    ax = fig.add_subplot(111)
    for i, record in enumerate(records):
        pts = record.track.points
        color = SERIES[i % len(SERIES)]
        ax.plot(
            [p.x for p in pts],
            [p.y for p in pts],
            color=color,
            linewidth=2,
            label=record.name,
        )
        if pts:
            ax.plot(pts[0].x, pts[0].y, "o", color=color, markersize=8,
                    markeredgecolor=SURFACE, markeredgewidth=2)
    ax.invert_yaxis()  # image coordinates: y grows downward
    ax.set_title("Flight trajectories (dot = release)")
    ax.set_xlabel("x (px)")
    ax.set_ylabel("y (px)")
    if len(records) >= 2:
        legend = ax.legend(fontsize=8, framealpha=0.9)
        for text in legend.get_texts():
            text.set_color(INK)
    _style_axes(ax)
    fig.tight_layout()
    return fig


def metrics_bar_figure(records: list[ThrowRecord]) -> Figure:
    """Side-by-side comparison of key metrics across throws."""
    fig = _new_figure()
    metric_defs = [
        ("Release angle (°)", lambda m: m.release_angle_deg),
        ("Release speed (px/s)", lambda m: m.release_speed_px_s),
        ("Duration (s)", lambda m: m.flight_duration_s),
        ("Straightness", lambda m: m.straightness),
    ]
    axes = fig.subplots(2, 2)
    names = [r.name for r in records]
    colors = [SERIES[i % len(SERIES)] for i in range(len(records))]
    for ax, (title, getter) in zip(axes.flat, metric_defs):
        values = [getter(r.metrics) for r in records]
        ax.bar(names, values, color=colors, width=0.6)
        ax.set_title(title, fontsize=9)
        ax.tick_params(axis="x", labelrotation=20)
        _style_axes(ax)
    fig.tight_layout()
    return fig


def progress_figure(records: list[ThrowRecord]) -> Figure:
    """Release speed and angle over the throws of a session, in order."""
    fig = _new_figure()
    xs = list(range(1, len(records) + 1))
    ax1 = fig.add_subplot(211)
    ax1.plot(xs, [r.metrics.release_speed_px_s for r in records],
             color=SERIES[0], linewidth=2, marker="o", markersize=5)
    ax1.set_title("Release speed across session (px/s)")
    _style_axes(ax1)

    ax2 = fig.add_subplot(212)
    ax2.plot(xs, [r.metrics.release_angle_deg for r in records],
             color=SERIES[1], linewidth=2, marker="o", markersize=5)
    ax2.set_title("Release angle across session (°)")
    ax2.set_xlabel("throw #")
    _style_axes(ax2)
    fig.tight_layout()
    return fig
