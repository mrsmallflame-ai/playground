"""End-to-end tests: synthetic video → tracker → metrics.

Covers the adversarial cases the tracker must survive: white disc on a
white/sky background (appearance cue useless), tilted camera angles where
the disc projects as an ellipse, and throws in either direction.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from generate_sample import generate  # noqa: E402

from frisbee_analytics.analysis import analyse_track
from frisbee_analytics.vision import track_video
from frisbee_analytics.vision.tracker import DISC_DIAMETER_M


def make_video(tmp_path_factory, name: str, **kwargs) -> Path:
    path = tmp_path_factory.mktemp("videos") / f"{name}.mp4"
    kwargs.setdefault("angle_deg", 20.0)
    kwargs.setdefault("speed_px_s", 320.0)
    kwargs.setdefault("n_frames", 50)
    generate(str(path), **kwargs)
    return path


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    return make_video(tmp_path_factory, "grass")


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


def test_white_disc_on_white_background(tmp_path_factory):
    """Appearance segmentation alone cannot separate disc from background
    here — the motion cue has to carry the detection."""
    video = make_video(tmp_path_factory, "white", background="white")
    track = track_video(video)
    assert len(track) >= 25
    metrics = analyse_track(track)
    assert metrics.release_angle_deg == pytest.approx(20.0, abs=6.0)
    assert metrics.release_speed_px_s == pytest.approx(320.0, rel=0.2)


def test_white_disc_on_sky_background(tmp_path_factory):
    video = make_video(tmp_path_factory, "sky", background="sky")
    track = track_video(video)
    assert len(track) >= 25
    assert analyse_track(track).release_angle_deg == pytest.approx(20.0, abs=6.0)


def test_tilted_camera_elliptical_disc(tmp_path_factory):
    """From a low/side camera angle the disc projects as a thin ellipse;
    the shape filter must not reject it."""
    video = make_video(tmp_path_factory, "tilted", aspect=0.4)
    track = track_video(video)
    assert len(track) >= 25
    metrics = analyse_track(track)
    assert metrics.release_angle_deg == pytest.approx(20.0, abs=6.0)
    # Major axis equals the true diameter regardless of tilt, so the
    # pixel scale must stay calibrated even edge-on.
    assert track.metres_per_px == pytest.approx(DISC_DIAMETER_M / 20.0, rel=0.3)


def test_tilted_disc_on_white_background(tmp_path_factory):
    """Both failure modes at once: camouflaged and elliptical."""
    video = make_video(tmp_path_factory, "tilted-white", background="white", aspect=0.5)
    track = track_video(video)
    assert len(track) >= 20
    assert analyse_track(track).release_angle_deg == pytest.approx(20.0, abs=8.0)


def test_near_edge_on_disc_on_white_background(tmp_path_factory):
    """Hardest case: a ~2 px sliver at ~20 grey-levels of contrast. Its
    motion signature is a handful of pixels per frame (the disc mostly
    self-overlaps as it travels along its own major axis)."""
    video = make_video(tmp_path_factory, "edge-white", background="white", aspect=0.25)
    track = track_video(video)
    assert len(track) >= 20
    metrics = analyse_track(track)
    assert metrics.release_angle_deg == pytest.approx(20.0, abs=8.0)
    assert metrics.release_speed_px_s == pytest.approx(320.0, rel=0.2)


def test_leftward_throw(tmp_path_factory):
    """Throws filmed from the opposite side move right-to-left."""
    video = make_video(tmp_path_factory, "leftward", leftward=True)
    track = track_video(video)
    assert len(track) >= 25
    xs = [p.x for p in track.points]
    assert xs[0] > xs[-1], "disc should move leftward"
    metrics = analyse_track(track)
    assert metrics.release_angle_deg == pytest.approx(20.0, abs=6.0)
    assert metrics.horizontal_displacement_px > 0


def test_rolled_camera_video(tmp_path_factory):
    """Footage from a tilted phone: release angle must be measured against
    the true horizon, recovered from the direction of apparent gravity."""
    video = make_video(tmp_path_factory, "rolled", roll_deg=25.0)
    track = track_video(video)
    assert len(track) >= 25
    metrics = analyse_track(track)
    assert metrics.view == "side"
    assert abs(metrics.camera_roll_deg) == pytest.approx(25.0, abs=5.0)
    assert metrics.release_angle_deg == pytest.approx(20.0, abs=6.0)


def test_top_down_video(tmp_path_factory):
    """Camera looking straight down: gravity is invisible, so the analysis
    must switch to ground-plane metrics instead of inventing an angle."""
    video = make_video(tmp_path_factory, "topdown", view="topdown")
    track = track_video(video)
    assert len(track) >= 25
    metrics = analyse_track(track)
    assert metrics.view == "overhead"
    assert metrics.release_angle_deg == 0.0
    assert metrics.release_speed_px_s == pytest.approx(320.0, rel=0.15)
    assert metrics.lateral_deviation_px == pytest.approx(12.0, abs=6.0)
    assert metrics.straightness > 0.95


def test_top_down_on_white_background_with_override(tmp_path_factory):
    """On low-contrast footage the disc-size trend that auto-detection
    relies on is unreadable, so the user states the geometry explicitly.
    The ground-plane metrics must still come out right."""
    video = make_video(tmp_path_factory, "topdown-white", view="topdown", background="white")
    track = track_video(video)
    assert len(track) >= 25
    metrics = analyse_track(track, view="overhead")
    assert metrics.view == "overhead"
    assert metrics.release_angle_deg == 0.0
    assert metrics.release_speed_px_s == pytest.approx(320.0, rel=0.2)


def test_track_roundtrip_serialisation(sample_video):
    from frisbee_analytics.models import FlightTrack

    track = track_video(sample_video)
    restored = FlightTrack.from_dict(track.to_dict())
    assert len(restored) == len(track)
    assert restored.points[0] == track.points[0]
    assert restored.metres_per_px == track.metres_per_px
