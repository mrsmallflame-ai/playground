#!/usr/bin/env python3
"""Generate a synthetic throw video: a white disc on a projectile arc
over a textured green background. Useful for demos and end-to-end tests
when no real footage is at hand.

    python tools/generate_sample.py sample.mp4 --angle 20 --speed 320
"""

from __future__ import annotations

import argparse
import math

import cv2
import numpy as np


def generate(
    path: str,
    width: int = 640,
    height: int = 360,
    fps: float = 30.0,
    n_frames: int = 60,
    angle_deg: float = 20.0,
    speed_px_s: float = 320.0,
    gravity_px_s2: float = 220.0,
    disc_radius: int = 10,
    seed: int = 7,
) -> str:
    rng = np.random.default_rng(seed)
    # Static noisy "grass" background so thresholding has something to reject.
    background = np.full((height, width, 3), (40, 110, 50), np.uint8)
    noise = rng.integers(-18, 18, size=(height, width, 3))
    background = np.clip(background.astype(int) + noise, 0, 255).astype(np.uint8)

    x0, y0 = 40.0, height * 0.72
    vx = speed_px_s * math.cos(math.radians(angle_deg))
    vy = speed_px_s * math.sin(math.radians(angle_deg))  # up

    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    try:
        for i in range(n_frames):
            t = i / fps
            x = x0 + vx * t
            y = y0 - (vy * t - 0.5 * gravity_px_s2 * t * t)
            frame = background.copy()
            if -disc_radius < x < width + disc_radius and -disc_radius < y < height + disc_radius:
                cv2.circle(frame, (int(x), int(y)), disc_radius, (250, 250, 250), -1, cv2.LINE_AA)
                cv2.circle(frame, (int(x), int(y)), disc_radius, (200, 200, 200), 1, cv2.LINE_AA)
            writer.write(frame)
    finally:
        writer.release()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--angle", type=float, default=20.0, help="release angle, degrees")
    parser.add_argument("--speed", type=float, default=320.0, help="release speed, px/s")
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args()
    generate(args.output, angle_deg=args.angle, speed_px_s=args.speed, n_frames=args.frames)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
