"""Shared data models passed between the pipeline stages.

Coordinates use image conventions: ``x`` grows rightward, ``y`` grows
*downward*. The analysis engine flips the vertical axis where physical
"up" matters (e.g. release angle), so everything outside this module can
reason in normal physics terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class TrackPoint:
    """Disc position in a single video frame."""

    frame_index: int
    time_s: float
    x: float
    y: float
    radius_px: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackPoint":
        return cls(**data)


@dataclass
class FlightTrack:
    """Time-series of disc positions for one throw."""

    points: list[TrackPoint] = field(default_factory=list)
    fps: float = 30.0
    frame_width: int = 0
    frame_height: int = 0
    # Pixel-to-metre scale. Calibrated from the disc's apparent size when
    # available (a regulation disc is 0.274 m across); 0 means "unknown".
    metres_per_px: float = 0.0

    def append(self, point: TrackPoint) -> None:
        self.points.append(point)

    def __len__(self) -> int:
        return len(self.points)

    def duration_s(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].time_s - self.points[0].time_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [p.to_dict() for p in self.points],
            "fps": self.fps,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "metres_per_px": self.metres_per_px,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlightTrack":
        return cls(
            points=[TrackPoint.from_dict(p) for p in data.get("points", [])],
            fps=data.get("fps", 30.0),
            frame_width=data.get("frame_width", 0),
            frame_height=data.get("frame_height", 0),
            metres_per_px=data.get("metres_per_px", 0.0),
        )


@dataclass
class ThrowMetrics:
    """Performance metrics derived from a single tracked throw.

    ``view`` records which camera geometry the analysis assumed: "side"
    (gravity visible in the image plane; release angle is elevation above
    the true horizon after camera-roll correction) or "overhead" (camera
    looks down; metrics describe ground-plane motion and release angle is
    not defined, reported as 0).
    """

    view: str = "side"
    # Apparent camera roll, estimated from the direction of gravity in the
    # image. 0 for overhead views.
    camera_roll_deg: float = 0.0
    # Peak perpendicular deviation of the flight path from the straight
    # release→end chord: arc height in side view, flight curve overhead.
    lateral_deviation_px: float = 0.0
    release_angle_deg: float = 0.0
    horizontal_displacement_px: float = 0.0
    vertical_displacement_px: float = 0.0
    path_length_px: float = 0.0
    peak_speed_px_s: float = 0.0
    mean_speed_px_s: float = 0.0
    release_speed_px_s: float = 0.0
    flight_duration_s: float = 0.0
    # Metric-unit estimates; 0 when no pixel scale was calibrated.
    peak_speed_m_s: float = 0.0
    release_speed_m_s: float = 0.0
    horizontal_displacement_m: float = 0.0
    # How straight the flight path is: 1.0 = perfectly straight line.
    straightness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThrowMetrics":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class ThrowRecord:
    """One analysed throw: its source, track, and derived metrics."""

    name: str
    video_path: str
    recorded_at: str  # ISO 8601
    track: FlightTrack
    metrics: ThrowMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "video_path": self.video_path,
            "recorded_at": self.recorded_at,
            "track": self.track.to_dict(),
            "metrics": self.metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThrowRecord":
        return cls(
            name=data["name"],
            video_path=data.get("video_path", ""),
            recorded_at=data.get("recorded_at", ""),
            track=FlightTrack.from_dict(data.get("track", {})),
            metrics=ThrowMetrics.from_dict(data.get("metrics", {})),
        )
