"""Unit tests for the kinematics engine on synthetic tracks."""

import math

import pytest

from frisbee_analytics.analysis import analyse_track, consistency_report
from frisbee_analytics.models import FlightTrack, ThrowMetrics, TrackPoint


def projectile_track(
    angle_deg: float = 30.0,
    speed: float = 300.0,
    gravity: float = 200.0,
    fps: float = 30.0,
    n: int = 40,
    y0: float = 300.0,
) -> FlightTrack:
    """Ideal projectile in image coordinates (y down)."""
    track = FlightTrack(fps=fps, frame_width=640, frame_height=360)
    vx = speed * math.cos(math.radians(angle_deg))
    vy = speed * math.sin(math.radians(angle_deg))
    for i in range(n):
        t = i / fps
        track.append(TrackPoint(
            frame_index=i,
            time_s=t,
            x=vx * t,
            y=y0 - (vy * t - 0.5 * gravity * t * t),
            radius_px=10.0,
        ))
    return track


def test_release_angle_recovered():
    metrics = analyse_track(projectile_track(angle_deg=25.0))
    assert metrics.release_angle_deg == pytest.approx(25.0, abs=2.0)


def test_negative_release_angle_for_downward_throw():
    metrics = analyse_track(projectile_track(angle_deg=-10.0))
    assert metrics.release_angle_deg < 0


def test_release_speed_recovered():
    metrics = analyse_track(projectile_track(speed=300.0))
    assert metrics.release_speed_px_s == pytest.approx(300.0, rel=0.05)


def test_flight_duration():
    track = projectile_track(fps=30.0, n=31)  # 30 intervals at 30 fps = 1 s
    assert analyse_track(track).flight_duration_s == pytest.approx(1.0)


def test_displacements():
    track = projectile_track(angle_deg=0.0, speed=100.0, gravity=0.0, n=31)
    metrics = analyse_track(track)
    assert metrics.horizontal_displacement_px == pytest.approx(100.0, rel=0.01)
    assert metrics.vertical_displacement_px == pytest.approx(0.0, abs=1e-6)
    assert metrics.straightness == pytest.approx(1.0)


def test_metric_units_scale():
    track = projectile_track(speed=300.0)
    track.metres_per_px = 0.01
    metrics = analyse_track(track)
    assert metrics.release_speed_m_s == pytest.approx(metrics.release_speed_px_s * 0.01)


def test_too_short_track_yields_zero_metrics():
    track = FlightTrack()
    track.append(TrackPoint(0, 0.0, 0.0, 0.0))
    metrics = analyse_track(track)
    assert metrics.release_speed_px_s == 0.0
    assert metrics.flight_duration_s == 0.0


def test_consistency_identical_throws_scores_100():
    m = analyse_track(projectile_track())
    report = consistency_report([m, m, m])
    assert report.n_throws == 3
    assert report.consistency_score == pytest.approx(100.0)


def test_consistency_varied_throws_scores_lower():
    metrics = [
        analyse_track(projectile_track(angle_deg=a, speed=s))
        for a, s in [(10.0, 200.0), (35.0, 320.0), (22.0, 260.0)]
    ]
    report = consistency_report(metrics)
    assert 0.0 <= report.consistency_score < 90.0
    assert report.release_angle_stdev > 5.0


def test_consistency_empty():
    assert consistency_report([]).n_throws == 0


def test_metrics_roundtrip():
    m = analyse_track(projectile_track())
    assert ThrowMetrics.from_dict(m.to_dict()) == m


# ── camera-angle handling ──────────────────────────────────────────────────


def rotate_track(track: FlightTrack, deg: float, cx: float = 320.0, cy: float = 180.0) -> FlightTrack:
    """Simulate a rolled camera: rotate all points about the frame centre."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    rotated = FlightTrack(fps=track.fps, frame_width=track.frame_width,
                          frame_height=track.frame_height, metres_per_px=track.metres_per_px)
    for p in track.points:
        rotated.append(TrackPoint(
            frame_index=p.frame_index,
            time_s=p.time_s,
            x=cx + (p.x - cx) * c - (p.y - cy) * s,
            y=cy + (p.x - cx) * s + (p.y - cy) * c,
            radius_px=p.radius_px,
        ))
    return rotated


def overhead_track(speed: float = 300.0, curve: float = 12.0, fps: float = 30.0, n: int = 40) -> FlightTrack:
    """Camera looking straight down: near-straight path with a lateral
    curve, disc apparently growing then shrinking as it rises and falls."""
    track = FlightTrack(fps=fps, frame_width=640, frame_height=360)
    total = (n - 1) / fps
    for i in range(n):
        t = i / fps
        p = t / total
        bump = 4.0 * p * (1.0 - p)
        track.append(TrackPoint(
            frame_index=i, time_s=t,
            x=speed * t,
            y=200.0 + curve * bump,
            radius_px=10.0 * (1.0 + 0.35 * bump),
        ))
    return track


def test_rolled_camera_recovers_true_release_angle():
    rolled = rotate_track(projectile_track(angle_deg=25.0), 30.0)
    m = analyse_track(rolled)
    assert m.view == "side"
    assert abs(m.camera_roll_deg) == pytest.approx(30.0, abs=2.0)
    assert m.release_angle_deg == pytest.approx(25.0, abs=2.0)


def test_level_camera_reports_no_roll():
    m = analyse_track(projectile_track(angle_deg=25.0))
    assert m.view == "side"
    assert m.camera_roll_deg == 0.0


def test_overhead_view_detected_and_measured():
    m = analyse_track(overhead_track())
    assert m.view == "overhead"
    assert m.release_angle_deg == 0.0
    assert m.vertical_displacement_px == 0.0
    assert m.release_speed_px_s == pytest.approx(300.0, rel=0.1)
    assert m.lateral_deviation_px == pytest.approx(12.0, abs=2.0)
    assert m.horizontal_displacement_px > 300.0


def test_view_override_wins_over_auto():
    assert analyse_track(overhead_track(), view="side").view == "side"
    assert analyse_track(projectile_track(), view="overhead").view == "overhead"


def test_invalid_view_rejected():
    with pytest.raises(ValueError):
        analyse_track(projectile_track(), view="sideways")


def test_side_view_reports_arc_height():
    m = analyse_track(projectile_track(angle_deg=25.0))
    # A projectile arc bulges above its chord by g·T²/8.
    assert m.lateral_deviation_px == pytest.approx(200.0 * 1.3**2 / 8.0, rel=0.1)
