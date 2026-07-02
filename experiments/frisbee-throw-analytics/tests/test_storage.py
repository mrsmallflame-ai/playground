"""Tests for the persistent session store."""

from frisbee_analytics.models import FlightTrack, ThrowMetrics, ThrowRecord, TrackPoint
from frisbee_analytics.storage import SessionStore


def make_record(name: str = "throw-1") -> ThrowRecord:
    track = FlightTrack(fps=30.0, frame_width=640, frame_height=360, metres_per_px=0.0137)
    for i in range(5):
        track.append(TrackPoint(i, i / 30.0, 10.0 * i, 200.0 - i, 9.5))
    return ThrowRecord(
        name=name,
        video_path="/videos/throw.mp4",
        recorded_at="2026-07-02T10:00:00+00:00",
        track=track,
        metrics=ThrowMetrics(release_angle_deg=18.5, release_speed_px_s=290.0),
    )


def test_save_and_load_roundtrip(tmp_path):
    store = SessionStore(tmp_path)
    store.save_throw("morning", make_record())
    store.save_throw("morning", make_record("throw-2"))

    throws = store.load_session("morning")
    assert [t.name for t in throws] == ["throw-1", "throw-2"]
    assert throws[0].metrics.release_angle_deg == 18.5
    assert len(throws[0].track) == 5
    assert throws[0].track.metres_per_px == 0.0137


def test_sessions_are_isolated(tmp_path):
    store = SessionStore(tmp_path)
    store.save_throw("a", make_record())
    store.save_throw("b", make_record())
    assert store.list_sessions() == ["a", "b"]
    assert len(store.load_session("a")) == 1


def test_missing_session_is_empty(tmp_path):
    assert SessionStore(tmp_path).load_session("nope") == []


def test_delete_session(tmp_path):
    store = SessionStore(tmp_path)
    store.save_throw("gone", make_record())
    store.delete_session("gone")
    assert store.list_sessions() == []


def test_session_names_are_sanitised(tmp_path):
    store = SessionStore(tmp_path)
    store.save_throw("../evil name!", make_record())
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert files[0].parent == tmp_path
    assert ".." not in files[0].name
