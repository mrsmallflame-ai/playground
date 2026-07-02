"""End-to-end tests: synthetic video → tracker → metrics."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from generate_sample import generate  # noqa: E402

from frisbee_analytics.analysis import analyse_track
from frisbee_analytics.vision import track_video
from frisbee_analytics.vision.tracker import DISC_DIAMETER_M


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("videos") / "throw.mp4"
    generate(str(path), angle_deg=20.0, speed_px_s=320.0, n_frames=50)
    return path


def test_tracker_follows_disc(sample_video):
    track = track_video(sample_video)
    # The disc is visible in nearly every frame; expect most to be tracked.
    assert len(track) >= 30
    xs = [p.x for p in track.points]
    assert xs == sorted(xs), "disc should move steadily rightward"


def test_pixel_scale_calibrated(sample_video):
    track = track_video(sample_video)
    # Disc radius drawn at 10 px → scale should be ~0.274 / 20 m per px.
    assert track.metres_per_px == pytest.approx(DISC_DIAMETER_M / 20.0, rel=0.25)


def test_end_to_end_metrics(sample_video):
    track = track_video(sample_video)
    metrics = analyse_track(track)
    assert metrics.release_angle_deg == pytest.approx(20.0, abs=4.0)
    assert metrics.release_speed_px_s == pytest.approx(320.0, rel=0.15)
    assert metrics.flight_duration_s > 0.5
    assert 0.9 <= metrics.straightness <= 1.0


def test_track_roundtrip_serialisation(sample_video):
    from frisbee_analytics.models import FlightTrack

    track = track_video(sample_video)
    restored = FlightTrack.from_dict(track.to_dict())
    assert len(restored) == len(track)
    assert restored.points[0] == track.points[0]
    assert restored.metres_per_px == track.metres_per_px
