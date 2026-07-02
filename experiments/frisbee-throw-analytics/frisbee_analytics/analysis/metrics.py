"""Kinematics engine: derives performance metrics from a flight track.

All angle/velocity math treats "up" as positive, flipping the image
y-axis. Velocities are estimated with central differences over the
time-series, which is less noisy than adjacent-frame deltas.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from ..models import FlightTrack, ThrowMetrics

# Velocity samples used to estimate release angle/speed. Kept small: the
# further into flight we average, the more gravity biases the angle down.
RELEASE_WINDOW = 3


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


def analyse_track(track: FlightTrack) -> ThrowMetrics:
    """Compute the full metric set for one tracked throw."""
    pts = track.points
    if len(pts) < 3:
        return ThrowMetrics(flight_duration_s=track.duration_s())

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

    # Release: average velocity over the first few tracked frames.
    window = vels[:RELEASE_WINDOW]
    rvx = statistics.fmean(v[0] for v in window)
    rvy = statistics.fmean(v[1] for v in window)
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
