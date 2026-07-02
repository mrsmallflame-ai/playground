"""Video acquisition and frame preprocessing.

``VideoSource`` wraps ``cv2.VideoCapture`` with an iterator interface and
exposes the properties the rest of the pipeline needs (fps, dimensions).
``preprocess_frame`` normalises frames so the detector behaves consistently
under varying lighting: colour-space conversion to HSV, Gaussian noise
reduction, and value-channel equalisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


@dataclass(frozen=True)
class Frame:
    index: int
    time_s: float
    image: np.ndarray  # BGR


class VideoSource:
    """Iterates over the frames of a video file."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if not Path(self.path).exists():
            raise FileNotFoundError(f"video not found: {self.path}")
        self._cap = cv2.VideoCapture(self.path)
        if not self._cap.isOpened():
            raise IOError(f"could not open video: {self.path}")
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def frames(self) -> Iterator[Frame]:
        index = 0
        while True:
            ok, image = self._cap.read()
            if not ok:
                break
            yield Frame(index=index, time_s=index / self.fps, image=image)
            index += 1

    def release(self) -> None:
        self._cap.release()

    def __enter__(self) -> "VideoSource":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def preprocess_frame(image: np.ndarray, blur_kernel: int = 5) -> np.ndarray:
    """Return an HSV frame ready for colour-based segmentation.

    Steps: Gaussian blur to suppress sensor noise, BGR→HSV conversion, and
    histogram equalisation of the value channel so exposure differences
    between clips (and within a clip, e.g. passing clouds) matter less.
    """
    if blur_kernel % 2 == 0:
        blur_kernel += 1
    blurred = cv2.GaussianBlur(image, (blur_kernel, blur_kernel), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    v = cv2.equalizeHist(v)
    return cv2.merge((h, s, v))


def threshold_disc(hsv: np.ndarray, lower: tuple[int, int, int], upper: tuple[int, int, int]) -> np.ndarray:
    """Binary mask of pixels inside the disc's HSV colour range.

    Morphological opening then closing removes speckle noise and fills small
    holes so the disc appears as one solid blob.
    """
    mask = cv2.inRange(hsv, np.array(lower, np.uint8), np.array(upper, np.uint8))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask
