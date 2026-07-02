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
