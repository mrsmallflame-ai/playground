"""Flight-path overlay rendering on top of the original video frames."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..models import FlightTrack
from ..video.pipeline import VideoSource

TRAIL_COLOR = (214, 120, 42)  # BGR of series blue #2a78d6
DISC_COLOR = (72, 73, 227)    # BGR of series red #e34948


def draw_track_overlay(image: np.ndarray, track: FlightTrack, upto_frame: int) -> np.ndarray:
    """Draw the tracked path (up to a frame index) onto a copy of the frame."""
    out = image.copy()
    visible = [p for p in track.points if p.frame_index <= upto_frame]
    if len(visible) >= 2:
        pts = np.array([[int(p.x), int(p.y)] for p in visible], np.int32)
        cv2.polylines(out, [pts], isClosed=False, color=TRAIL_COLOR, thickness=2, lineType=cv2.LINE_AA)
    if visible:
        last = visible[-1]
        radius = max(int(last.radius_px), 6)
        cv2.circle(out, (int(last.x), int(last.y)), radius, DISC_COLOR, 2, cv2.LINE_AA)
    return out


def render_overlay_video(video_path: str | Path, track: FlightTrack, out_path: str | Path) -> Path:
    """Write a copy of the video with the flight path drawn on every frame."""
    out_path = Path(out_path)
    with VideoSource(video_path) as source:
        writer = cv2.VideoWriter(
            str(out_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            source.fps,
            (source.width, source.height),
        )
        try:
            for frame in source.frames():
                writer.write(draw_track_overlay(frame.image, track, frame.index))
        finally:
            writer.release()
    return out_path
