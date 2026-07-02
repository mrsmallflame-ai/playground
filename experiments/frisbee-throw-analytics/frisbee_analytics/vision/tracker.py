"""Disc detection and tracking.

Detection is colour-based: the disc is segmented in the preprocessed HSV
frame, candidate blobs are filtered by area and circularity, and the blob
closest to the predicted position (constant-velocity model from the last
two detections) wins. Positions are collected into a ``FlightTrack``
time-series for the analysis engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..models import FlightTrack, TrackPoint
from ..video.pipeline import VideoSource, preprocess_frame, threshold_disc

# Regulation ultimate disc diameter, used to calibrate a pixel→metre scale.
DISC_DIAMETER_M = 0.274


@dataclass
class TrackerConfig:
    # Default range targets a bright/white disc: any hue, low saturation,
    # high value. Tune for coloured discs.
    hsv_lower: tuple[int, int, int] = (0, 0, 200)
    hsv_upper: tuple[int, int, int] = (179, 60, 255)
    min_area_px: float = 40.0
    max_area_frac: float = 0.05  # ignore blobs above this fraction of frame
    min_circularity: float = 0.6
    # Reject detections further than this many disc-radii from prediction.
    max_jump_radii: float = 12.0
    blur_kernel: int = 5


@dataclass
class _Candidate:
    x: float
    y: float
    radius: float
    circularity: float


class DiscTracker:
    """Stateful frame-by-frame tracker producing a FlightTrack."""

    def __init__(self, config: TrackerConfig | None = None):
        self.config = config or TrackerConfig()
        self._history: list[TrackPoint] = []

    def _candidates(self, mask: np.ndarray, frame_area: float) -> list[_Candidate]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        found: list[_Candidate] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.config.min_area_px or area > frame_area * self.config.max_area_frac:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity < self.config.min_circularity:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            found.append(_Candidate(x=x, y=y, radius=radius, circularity=circularity))
        return found

    def _predict(self) -> tuple[float, float] | None:
        """Constant-velocity prediction from the last two detections."""
        if len(self._history) < 2:
            return None
        a, b = self._history[-2], self._history[-1]
        return 2 * b.x - a.x, 2 * b.y - a.y

    def process(self, image: np.ndarray, frame_index: int, time_s: float) -> TrackPoint | None:
        hsv = preprocess_frame(image, self.config.blur_kernel)
        mask = threshold_disc(hsv, self.config.hsv_lower, self.config.hsv_upper)
        candidates = self._candidates(mask, float(image.shape[0] * image.shape[1]))
        if not candidates:
            return None

        predicted = self._predict()
        if predicted is None and self._history:
            predicted = (self._history[-1].x, self._history[-1].y)

        if predicted is None:
            # First detection: prefer the most circular blob.
            best = max(candidates, key=lambda c: c.circularity)
        else:
            best = min(candidates, key=lambda c: (c.x - predicted[0]) ** 2 + (c.y - predicted[1]) ** 2)
            jump = np.hypot(best.x - predicted[0], best.y - predicted[1])
            if best.radius > 0 and jump > self.config.max_jump_radii * max(best.radius, 4.0):
                return None  # implausible jump — likely a false positive

        point = TrackPoint(frame_index=frame_index, time_s=time_s, x=best.x, y=best.y, radius_px=best.radius)
        self._history.append(point)
        return point


def track_video(path: str | Path, config: TrackerConfig | None = None) -> FlightTrack:
    """Run the tracker over a whole video and return its flight track."""
    tracker = DiscTracker(config)
    with VideoSource(path) as source:
        track = FlightTrack(fps=source.fps, frame_width=source.width, frame_height=source.height)
        for frame in source.frames():
            point = tracker.process(frame.image, frame.index, frame.time_s)
            if point is not None:
                track.append(point)

    radii = [p.radius_px for p in track.points if p.radius_px > 0]
    if radii:
        track.metres_per_px = DISC_DIAMETER_M / (2 * float(np.median(radii)))
    return track
