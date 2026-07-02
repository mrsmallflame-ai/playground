"""Disc detection and tracking.

Detection fuses two independent cues so no single one is a point of failure:

- **Motion**: double frame-differencing (``|f_t − f_{t−1}| ∧ |f_t − f_{t−2}|``)
  isolates the moving disc even when its colour matches the background
  (white disc against sky or a white wall). The double difference also
  suppresses "ghosts" at positions the disc has just left.
- **Appearance**: HSV colour segmentation of the preprocessed frame,
  which works when the camera moves (making motion cues unreliable) and
  trims motion blobs down to actual disc pixels.

Per frame the tracker tries masks in order of reliability — motion ∧
appearance, motion only, appearance only — and takes the first that yields
a plausible candidate.

Shape filtering is tilt-invariant: a disc projects to an *ellipse* from any
camera angle, so candidates are validated by how well their contour fills a
fitted ellipse rather than by circularity (which rejects edge-on views).
The ellipse's major axis equals the disc diameter regardless of tilt, which
also makes the pixel→metre calibration viewpoint-independent.

Tracking keeps a constant-velocity model with distance gating, coasts
through short detection gaps, and fully re-acquires after too many misses.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..models import FlightTrack, TrackPoint
from ..video.pipeline import VideoSource, preprocess_frame, threshold_disc

# Regulation ultimate disc diameter, used to calibrate a pixel→metre scale.
DISC_DIAMETER_M = 0.274


@dataclass
class TrackerConfig:
    # Appearance range targets a bright/white disc: any hue, low saturation,
    # high value. Tune for coloured discs; motion detection is colour-free.
    hsv_lower: tuple[int, int, int] = (0, 0, 200)
    hsv_upper: tuple[int, int, int] = (179, 60, 255)
    # Low floor: an edge-on disc travelling along its own major axis leaves
    # a visible-motion region of only ~25 px² (the rest self-overlaps
    # between frames). Speckle this small is rare after blurring, and the
    # shape/gating/stagnation checks handle what remains.
    min_area_px: float = 16.0
    max_area_frac: float = 0.05  # ignore blobs above this fraction of frame
    # Shape: how completely the contour fills its fitted ellipse, and how
    # elongated that ellipse may be (an edge-on disc is a thin sliver).
    min_ellipse_fill: float = 0.55
    max_aspect: float = 8.0
    # Grey-level change required to count as motion between frames. Kept
    # low: a white disc against a white sky may differ by only ~20 levels,
    # and frames are blurred first so sensor noise sits well below this.
    motion_diff_threshold: int = 10
    # Reject detections further than this many disc-radii from prediction
    # (scaled up while coasting through missed frames).
    max_jump_radii: float = 12.0
    # Frames the tracker may coast without a detection before re-acquiring.
    max_misses: int = 8
    # A "track" whose speed stays below this (px/frame) for this many
    # consecutive updates is a static object, not a disc — drop it.
    stagnant_speed_px: float = 0.5
    max_stagnant: int = 6
    blur_kernel: int = 5


@dataclass
class _Candidate:
    x: float
    y: float
    radius: float  # half the fitted-ellipse major axis — tilt-invariant
    fill: float
    area: float


class DiscTracker:
    """Stateful frame-by-frame tracker producing TrackPoints."""

    def __init__(self, config: TrackerConfig | None = None):
        self.config = config or TrackerConfig()
        self._prev_gray: deque[np.ndarray] = deque(maxlen=2)
        self._radii: deque[float] = deque(maxlen=15)
        self._last_pos: tuple[float, float] | None = None
        self._last_frame: int = -1
        self._velocity: tuple[float, float] | None = None  # px per frame
        self._misses: int = 0
        self._stagnant: int = 0

    # ── masks ────────────────────────────────────────────────────────────
    def _motion_mask(self, gray: np.ndarray) -> np.ndarray | None:
        if len(self._prev_gray) < 2:
            return None
        thresh = self.config.motion_diff_threshold
        d1 = cv2.threshold(cv2.absdiff(gray, self._prev_gray[-1]), thresh, 255, cv2.THRESH_BINARY)[1]
        d2 = cv2.threshold(cv2.absdiff(gray, self._prev_gray[-2]), thresh, 255, cv2.THRESH_BINARY)[1]
        mask = cv2.bitwise_and(d1, d2)
        # A low-contrast disc (white on sky, near edge-on) survives the
        # threshold as only a handful of scattered pixels; dilate to
        # consolidate them into one blob a contour can be fitted to, then
        # close to smooth it. No opening — it would erase exactly those
        # faint detections. Speckle that gets inflated instead is rejected
        # by the candidate filters and the prediction gate.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.dilate(mask, kernel)
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # ── candidates ───────────────────────────────────────────────────────
    def _candidates(self, mask: np.ndarray, frame_area: float) -> list[_Candidate]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        found: list[_Candidate] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.config.min_area_px or area > frame_area * self.config.max_area_frac:
                continue
            if len(contour) >= 5:
                (cx, cy), (w, h), _angle = cv2.fitEllipse(contour)
                major, minor = max(w, h), min(w, h)
                if minor <= 0 or major / minor > self.config.max_aspect:
                    continue
                ellipse_area = math.pi * major * minor / 4.0
                fill = min(area / ellipse_area, 1.0) if ellipse_area > 0 else 0.0
            else:
                (cx, cy), radius = cv2.minEnclosingCircle(contour)
                major = 2 * radius
                fill = area / (math.pi * radius * radius) if radius > 0 else 0.0
            if fill < self.config.min_ellipse_fill:
                continue
            found.append(_Candidate(x=cx, y=cy, radius=major / 2.0, fill=fill, area=area))
        return found

    # ── track state ──────────────────────────────────────────────────────
    def _typical_radius(self) -> float:
        return float(np.median(self._radii)) if self._radii else 4.0

    def _predict(self, frame_index: int) -> tuple[float, float] | None:
        if self._last_pos is None:
            return None
        if self._velocity is None:
            return self._last_pos
        gap = frame_index - self._last_frame
        return (
            self._last_pos[0] + self._velocity[0] * gap,
            self._last_pos[1] + self._velocity[1] * gap,
        )

    def _select(
        self, candidates: list[_Candidate], frame_index: int, can_acquire: bool
    ) -> _Candidate | None:
        if not candidates:
            return None
        predicted = self._predict(frame_index)
        if predicted is None:
            if not can_acquire:
                return None
            # Acquisition: prefer the most disc-like (ellipse-filling) blob.
            return max(candidates, key=lambda c: c.fill)
        best = min(candidates, key=lambda c: (c.x - predicted[0]) ** 2 + (c.y - predicted[1]) ** 2)
        jump = math.hypot(best.x - predicted[0], best.y - predicted[1])
        gate = self.config.max_jump_radii * max(self._typical_radius(), 4.0) * (self._misses + 1)
        if jump > gate:
            return None  # implausible jump — likely a false positive
        return best

    def process(self, image: np.ndarray, frame_index: int, time_s: float) -> TrackPoint | None:
        k = self.config.blur_kernel | 1
        gray = cv2.cvtColor(cv2.GaussianBlur(image, (k, k), 0), cv2.COLOR_BGR2GRAY)

        hsv = preprocess_frame(image, self.config.blur_kernel)
        appearance = threshold_disc(hsv, self.config.hsv_lower, self.config.hsv_upper)
        motion = self._motion_mask(gray)
        self._prev_gray.append(gray)

        # A new track may only start from a motion-backed mask: a static
        # false positive (noise blob, cone, line marking) can pass the
        # appearance and shape filters, and once acquired it would pin the
        # prediction gate and lock the real disc out. Appearance alone may
        # *continue* an existing track (e.g. through camera shake, when
        # motion cues degrade), and may start one only in the frames before
        # motion history exists — and then only if it is unambiguous.
        if motion is not None:
            masks = [
                (cv2.bitwise_and(motion, appearance), True, False),
                (motion, True, False),
                (appearance, False, False),
            ]
        else:
            masks = [(appearance, True, True)]

        frame_area = float(image.shape[0] * image.shape[1])
        chosen: _Candidate | None = None
        for mask, can_acquire, needs_unique in masks:
            candidates = self._candidates(mask, frame_area)
            if needs_unique and self._last_pos is None and len(candidates) != 1:
                continue
            chosen = self._select(candidates, frame_index, can_acquire)
            if chosen is not None:
                break

        if chosen is None:
            self._misses += 1
            if self._misses > self.config.max_misses:
                # Lost the disc: drop the stale motion model and re-acquire.
                self._last_pos = None
                self._velocity = None
                self._stagnant = 0
            return None

        if self._last_pos is not None:
            gap = frame_index - self._last_frame
            if gap > 0:
                self._velocity = (
                    (chosen.x - self._last_pos[0]) / gap,
                    (chosen.y - self._last_pos[1]) / gap,
                )
        self._last_pos = (chosen.x, chosen.y)
        self._last_frame = frame_index
        self._misses = 0
        self._radii.append(chosen.radius)

        # Stagnation escape: a disc in flight never sits still, so a track
        # that stops moving is a static object — drop it and re-acquire.
        if self._velocity is not None:
            if math.hypot(*self._velocity) < self.config.stagnant_speed_px:
                self._stagnant += 1
            else:
                self._stagnant = 0
            if self._stagnant > self.config.max_stagnant:
                self._last_pos = None
                self._velocity = None
                self._stagnant = 0
                return None

        return TrackPoint(frame_index=frame_index, time_s=time_s, x=chosen.x, y=chosen.y, radius_px=chosen.radius)


def track_video(path: str | Path, config: TrackerConfig | None = None) -> FlightTrack:
    """Run the tracker over a whole video and return its flight track."""
    tracker = DiscTracker(config)
    with VideoSource(path) as source:
        track = FlightTrack(fps=source.fps, frame_width=source.width, frame_height=source.height)
        for frame in source.frames():
            point = tracker.process(frame.image, frame.index, frame.time_s)
            if point is not None:
                track.append(point)

    # The fitted-ellipse major axis equals the disc diameter from any
    # viewing angle, so this calibration is viewpoint-independent.
    radii = [p.radius_px for p in track.points if p.radius_px > 0]
    if radii:
        track.metres_per_px = DISC_DIAMETER_M / (2 * float(np.median(radii)))
    return track
