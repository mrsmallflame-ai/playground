"""Kinematics engine: derives performance metrics from a flight track.

The engine is viewpoint-aware. A single camera only ever measures the
*projection* of the flight onto its image plane, so the physics used must
match the camera geometry:

- **Side-ish views** (gravity visible in the image plane): the apparent
  gravity vector is estimated from the track's own acceleration and the
  coordinates are rotated so gravity points straight down. Release angle
  is then measured against the true horizon no matter how the camera was
  rolled or tilted — a phone held at 30° gives the same numbers as a
  level tripod.
- **Overhead views** (camera looks down at the field): gravity is along
  the camera axis and invisible, so side-view metrics would be nonsense.
  Instead the engine reports ground-plane motion: throw distance, ground
  speed, and the lateral curve of the flight. Release angle is undefined
  and reported as 0.

``analyse_track(track, view="auto")`` classifies the view automatically
from two physical signatures — the parabolic sag a visible gravity leaves
in the path, and the apparent disc-size change as it flies toward/away
from an overhead camera — and can be overridden with ``view="side"`` or
``view="overhead"`` when the user knows the setup.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

import numpy as np

from ..models import FlightTrack, ThrowMetrics, TrackPoint

# Points used to fit the release velocity at the start of flight.
RELEASE_WINDOW = 10

# Auto view classification: a visible gravity bends the path into an arc
# whose height is a sizeable fraction of the chord; overhead flights are
# near-straight but the disc's apparent size changes with its height.
ARC_RATIO_SIDE = 0.08
RADIUS_RANGE_OVERHEAD = 0.15

# Estimated camera rolls below this are treated as a level camera. The
# floor is deliberately generous: aerodynamic drag and small tracker
# biases add a few degrees of horizontal acceleration that tilt the
# *apparent* gravity vector, so only clearly rolled footage is corrected.
MIN_ROLL_DEG = 8.0


def _velocities(track: FlightTrack) -> list[tuple[float, float, float]]:
    """Per-point (vx, vy_up, speed) in px/s via central differences."""
    pts = track.points
    out: list[tuple[float, float, float]] = []
    for i in range(len(pts)):
        lo = max(0, i - 1)
        hi = min(len(pts) - 1, i + 1)
        dt = pts[hi].time_s - pts[lo].time_s
        if dt <= 0:
            out.append((0.0, 0.0, 0.0))
            continue
        vx = (pts[hi].x - pts[lo].x) / dt
        vy_up = -(pts[hi].y - pts[lo].y) / dt  # flip image axis: up positive
        out.append((vx, vy_up, math.hypot(vx, vy_up)))
    return out


def _theil_sen_slope(ts: list[float], vs: list[float]) -> float:
    """Median of pairwise slopes — robust to isolated bad points."""
    slopes = [
        (vs[j] - vs[i]) / (ts[j] - ts[i])
        for i in range(len(ts))
        for j in range(i + 1, len(ts))
        if ts[j] > ts[i]
    ]
    return statistics.median(slopes) if slopes else 0.0


def _release_velocity(track: FlightTrack, gravity_aware: bool) -> tuple[float, float]:
    """Velocity (vx, vy_up) at the moment of release.

    Tracker output near acquisition can contain an outlier or two, and a
    single bad point wrecks any short-window average. Horizontal velocity
    is therefore fit with Theil–Sen (a median is unmoved by one outlier).
    In side view the vertical velocity is the ``t = 0`` derivative of a
    quadratic least-squares fit, which accounts for gravity's bend across
    the window instead of averaging it in as bias; overhead there is no
    in-plane gravity, so Theil–Sen serves both axes.
    """
    pts = track.points[: min(RELEASE_WINDOW, len(track.points))]
    t0 = pts[0].time_s
    ts = [p.time_s - t0 for p in pts]
    xs = [p.x for p in pts]
    ys_up = [-p.y for p in pts]

    vx = _theil_sen_slope(ts, xs)
    if gravity_aware and len(pts) >= 4:
        vy = float(np.polyfit(ts, ys_up, 2)[1])
    else:
        vy = _theil_sen_slope(ts, ys_up)
    return vx, vy


def _fit_acceleration(track: FlightTrack) -> tuple[float, float, float, float]:
    """Acceleration (ax, ay) in image coordinates, px/s², from quadratic
    fits of x(t) and y(t) over the whole track, with 1σ uncertainties
    (from the fit covariance) so callers can tell signal from noise."""
    ts = [p.time_s for p in track.points]
    cx, cov_x = np.polyfit(ts, [p.x for p in track.points], 2, cov=True)
    cy, cov_y = np.polyfit(ts, [p.y for p in track.points], 2, cov=True)
    ax, ay = 2.0 * float(cx[0]), 2.0 * float(cy[0])
    sig_ax = 2.0 * float(np.sqrt(max(cov_x[0, 0], 0.0)))
    sig_ay = 2.0 * float(np.sqrt(max(cov_y[0, 0], 0.0)))
    return ax, ay, sig_ax, sig_ay


def _chord_and_deviation(pts: list[TrackPoint]) -> tuple[float, float]:
    """(chord length, max perpendicular deviation of the path from it)."""
    dx = pts[-1].x - pts[0].x
    dy = pts[-1].y - pts[0].y
    chord = math.hypot(dx, dy)
    if chord <= 0:
        return 0.0, 0.0
    deviation = max(
        abs((p.x - pts[0].x) * dy - (p.y - pts[0].y) * dx) / chord for p in pts
    )
    return chord, deviation


def _radius_rel_range(pts: list[TrackPoint]) -> float:
    """Spread of the disc's apparent size across the flight, relative to
    its median — large when the disc flies toward/away from the camera."""
    radii = [p.radius_px for p in pts if p.radius_px > 0]
    if len(radii) < 5:
        return 0.0
    lo, mid, hi = np.percentile(radii, [10, 50, 90])
    return float((hi - lo) / mid) if mid > 0 else 0.0


def _resolve_view(track: FlightTrack, requested: str, arc_ratio: float) -> str:
    if requested in ("side", "overhead"):
        return requested
    if requested != "auto":
        raise ValueError(f"view must be 'auto', 'side' or 'overhead', not {requested!r}")
    if arc_ratio >= ARC_RATIO_SIDE:
        return "side"  # the path sags like something gravity is pulling on
    if _radius_rel_range(track.points) >= RADIUS_RANGE_OVERHEAD:
        return "overhead"  # size change = motion along the camera axis
    # Ambiguous (e.g. a fast flat throw): side view is by far the common
    # filming setup, and its metrics degrade gracefully.
    return "side"


def _rotated(track: FlightTrack, angle_rad: float) -> FlightTrack:
    """Rotate all points about the first one by ``angle_rad``."""
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    x0, y0 = track.points[0].x, track.points[0].y
    points = [
        TrackPoint(
            frame_index=p.frame_index,
            time_s=p.time_s,
            x=x0 + (p.x - x0) * cos_a - (p.y - y0) * sin_a,
            y=y0 + (p.x - x0) * sin_a + (p.y - y0) * cos_a,
            radius_px=p.radius_px,
        )
        for p in track.points
    ]
    return FlightTrack(
        points=points,
        fps=track.fps,
        frame_width=track.frame_width,
        frame_height=track.frame_height,
        metres_per_px=track.metres_per_px,
    )


def analyse_track(track: FlightTrack, view: str = "auto") -> ThrowMetrics:
    """Compute the full metric set for one tracked throw.

    ``view`` is ``"auto"`` (classify the camera geometry from the track),
    ``"side"`` or ``"overhead"``.
    """
    if len(track.points) < 3:
        return ThrowMetrics(flight_duration_s=track.duration_s())

    chord, deviation = _chord_and_deviation(track.points)
    arc_ratio = deviation / chord if chord > 0 else 0.0
    resolved = _resolve_view(track, view, arc_ratio)

    if resolved == "side":
        # Angle of the apparent gravity vector away from image-down;
        # rotating the track by it puts the true horizon along x. Only
        # trusted when gravity visibly bends the path (with no bend the
        # fitted acceleration is noise and its direction is meaningless)
        # AND the estimated roll is statistically significant — otherwise
        # tracker noise would "correct" a level camera into a tilted one.
        roll = 0.0
        if arc_ratio >= ARC_RATIO_SIDE and len(track.points) >= 6:
            ax, ay, sig_ax, sig_ay = _fit_acceleration(track)
            roll = math.atan2(ax, ay)
            mag_sq = ax * ax + ay * ay
            sig_roll = (
                math.sqrt((sig_ax * ay) ** 2 + (sig_ay * ax) ** 2) / mag_sq
                if mag_sq > 0
                else math.inf
            )
            if abs(math.degrees(roll)) < MIN_ROLL_DEG or abs(roll) < 2.0 * sig_roll:
                roll = 0.0
        work = _rotated(track, roll) if roll else track
        metrics = _side_metrics(work)
        metrics.camera_roll_deg = math.degrees(roll)
    else:
        metrics = _overhead_metrics(track)
    metrics.view = resolved
    return metrics


def _side_metrics(track: FlightTrack) -> ThrowMetrics:
    pts = track.points
    vels = _velocities(track)

    first, last = pts[0], pts[-1]
    dx = last.x - first.x
    dy_up = -(last.y - first.y)

    path_length = sum(
        math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y)
        for i in range(len(pts) - 1)
    )
    net_displacement = math.hypot(dx, dy_up)
    straightness = net_displacement / path_length if path_length > 0 else 0.0
    _, deviation = _chord_and_deviation(pts)

    rvx, rvy = _release_velocity(track, gravity_aware=True)
    release_speed = math.hypot(rvx, rvy)
    release_angle = math.degrees(math.atan2(rvy, abs(rvx))) if release_speed > 0 else 0.0

    speeds = [v[2] for v in vels]
    peak_speed = max(speeds)
    mean_speed = statistics.fmean(speeds)

    scale = track.metres_per_px
    return ThrowMetrics(
        release_angle_deg=release_angle,
        horizontal_displacement_px=abs(dx),
        vertical_displacement_px=dy_up,
        path_length_px=path_length,
        peak_speed_px_s=peak_speed,
        mean_speed_px_s=mean_speed,
        release_speed_px_s=release_speed,
        flight_duration_s=track.duration_s(),
        peak_speed_m_s=peak_speed * scale,
        release_speed_m_s=release_speed * scale,
        horizontal_displacement_m=abs(dx) * scale,
        straightness=straightness,
        lateral_deviation_px=deviation,
    )


def _overhead_metrics(track: FlightTrack) -> ThrowMetrics:
    """Ground-plane metrics for a camera looking down at the field.

    Both image axes are ground axes here: displacement is the ground-plane
    throw distance, speeds are ground speeds, and the flight's curve shows
    up as lateral deviation from the release→end chord. Elevation-related
    quantities (release angle, vertical displacement) are undefined.
    """
    pts = track.points
    vels = _velocities(track)

    chord, deviation = _chord_and_deviation(pts)
    path_length = sum(
        math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y)
        for i in range(len(pts) - 1)
    )
    straightness = chord / path_length if path_length > 0 else 0.0

    rvx, rvy = _release_velocity(track, gravity_aware=False)
    release_speed = math.hypot(rvx, rvy)

    speeds = [v[2] for v in vels]
    peak_speed = max(speeds)
    mean_speed = statistics.fmean(speeds)

    scale = track.metres_per_px
    return ThrowMetrics(
        release_angle_deg=0.0,
        horizontal_displacement_px=chord,
        vertical_displacement_px=0.0,
        path_length_px=path_length,
        peak_speed_px_s=peak_speed,
        mean_speed_px_s=mean_speed,
        release_speed_px_s=release_speed,
        flight_duration_s=track.duration_s(),
        peak_speed_m_s=peak_speed * scale,
        release_speed_m_s=release_speed * scale,
        horizontal_displacement_m=chord * scale,
        straightness=straightness,
        lateral_deviation_px=deviation,
    )


@dataclass
class ConsistencyReport:
    """Spread of key metrics across multiple attempts of the same throw."""

    n_throws: int = 0
    release_angle_mean: float = 0.0
    release_angle_stdev: float = 0.0
    release_speed_mean: float = 0.0
    release_speed_stdev: float = 0.0
    duration_mean: float = 0.0
    duration_stdev: float = 0.0
    # 0–100 score: 100 = identical throws. Penalises relative spread.
    consistency_score: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def consistency_report(metrics: list[ThrowMetrics]) -> ConsistencyReport:
    """Summarise throw-to-throw variation over a set of attempts."""
    if not metrics:
        return ConsistencyReport()
    angles = [m.release_angle_deg for m in metrics]
    speeds = [m.release_speed_px_s for m in metrics]
    durations = [m.flight_duration_s for m in metrics]

    def spread(values: list[float]) -> float:
        return statistics.stdev(values) if len(values) > 1 else 0.0

    angle_sd = spread(angles)
    speed_sd = spread(speeds)
    duration_sd = spread(durations)

    # Relative variation, mapped onto 0–100. Angle spread is compared to a
    # 15° tolerance; speed and duration to 25% of their means.
    penalties = [min(1.0, angle_sd / 15.0)]
    if statistics.fmean(speeds) > 0:
        penalties.append(min(1.0, speed_sd / (0.25 * statistics.fmean(speeds))))
    if statistics.fmean(durations) > 0:
        penalties.append(min(1.0, duration_sd / (0.25 * statistics.fmean(durations))))
    score = 100.0 * (1.0 - statistics.fmean(penalties))

    return ConsistencyReport(
        n_throws=len(metrics),
        release_angle_mean=statistics.fmean(angles),
        release_angle_stdev=angle_sd,
        release_speed_mean=statistics.fmean(speeds),
        release_speed_stdev=speed_sd,
        duration_mean=statistics.fmean(durations),
        duration_stdev=duration_sd,
        consistency_score=score,
    )
