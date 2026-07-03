#!/usr/bin/env python3
"""Generate a synthetic throw video: a white disc on a projectile arc.

Supports adversarial scenarios for tracker testing: white or sky
backgrounds (disc colour ≈ background colour), tilted camera angles
(the disc renders as an ellipse), and right-to-left throws.

    python tools/generate_sample.py sample.mp4 --angle 20 --speed 320
    python tools/generate_sample.py hard.mp4 --background white --aspect 0.4 --leftward
"""

from __future__ import annotations

import argparse
import math

import cv2
import numpy as np

BACKGROUNDS = {
    "grass": (40, 110, 50),
    "white": (232, 232, 232),
    "sky": (235, 206, 135),  # BGR sky blue
}


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
    background: str = "grass",
    aspect: float = 1.0,
    leftward: bool = False,
    view: str = "side",
    roll_deg: float = 0.0,
    curve_px: float = 12.0,
    seed: int = 7,
) -> str:
    """Render a throw. ``aspect`` is the minor/major axis ratio of the disc
    as seen by the camera (1.0 = face-on circle, small = near edge-on).

    ``view="topdown"`` renders a camera looking straight down: the path is
    near-straight with a lateral curve of ``curve_px`` and the disc's
    apparent size swells mid-flight as it rises toward the camera.
    ``roll_deg`` rotates the whole scene, simulating a tilted camera.
    """
    rng = np.random.default_rng(seed)
    base = BACKGROUNDS[background]
    # Static noisy background so segmentation has something to reject.
    bg = np.full((height, width, 3), base, np.uint8)
    noise = rng.integers(-14, 14, size=(height, width, 3))
    bg = np.clip(bg.astype(int) + noise, 0, 255).astype(np.uint8)

    x0 = width - 40.0 if leftward else 40.0
    y0 = height * (0.5 if view == "topdown" else 0.72)
    direction = -1.0 if leftward else 1.0
    vx = direction * speed_px_s * math.cos(math.radians(angle_deg))
    vy = speed_px_s * math.sin(math.radians(angle_deg))  # up
    total_t = n_frames / fps

    roll = math.radians(roll_deg)
    cos_r, sin_r = math.cos(roll), math.sin(roll)
    cx, cy = width / 2.0, height / 2.0

    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    try:
        for i in range(n_frames):
            t = i / fps
            if view == "topdown":
                p = t / total_t
                x = x0 + direction * speed_px_s * t
                y = y0 + 4.0 * curve_px * p * (1.0 - p)
                dxdt = direction * speed_px_s
                dydt = 4.0 * curve_px * (1.0 - 2.0 * p) / total_t
                # The disc rises toward the camera mid-flight → looks bigger.
                r_major = disc_radius * (1.0 + 0.35 * 4.0 * p * (1.0 - p))
            else:
                x = x0 + vx * t
                y = y0 - (vy * t - 0.5 * gravity_px_s2 * t * t)
                dxdt = vx
                dydt = -(vy - gravity_px_s2 * t)
                r_major = float(disc_radius)
            if roll_deg:
                x, y = (
                    cx + (x - cx) * cos_r - (y - cy) * sin_r,
                    cy + (x - cx) * sin_r + (y - cy) * cos_r,
                )
                dxdt, dydt = (
                    dxdt * cos_r - dydt * sin_r,
                    dxdt * sin_r + dydt * cos_r,
                )
            frame = bg.copy()
            r = int(round(r_major))
            minor = max(2, int(round(r_major * aspect)))
            if -r < x < width + r and -r < y < height + r:
                # Align the ellipse's major axis with the flight direction.
                rot = math.degrees(math.atan2(dydt, dxdt))
                center = (int(x), int(y))
                cv2.ellipse(frame, center, (r, minor), rot, 0, 360, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.ellipse(frame, center, (r, minor), rot, 0, 360, (210, 210, 210), 1, cv2.LINE_AA)
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
    parser.add_argument("--background", choices=sorted(BACKGROUNDS), default="grass")
    parser.add_argument("--aspect", type=float, default=1.0, help="disc minor/major ratio (camera tilt)")
    parser.add_argument("--leftward", action="store_true", help="throw right-to-left")
    parser.add_argument("--view", choices=["side", "topdown"], default="side")
    parser.add_argument("--roll", type=float, default=0.0, help="camera roll, degrees")
    parser.add_argument("--curve", type=float, default=12.0, help="lateral curve for topdown view, px")
    args = parser.parse_args()
    generate(
        args.output,
        angle_deg=args.angle,
        speed_px_s=args.speed,
        n_frames=args.frames,
        background=args.background,
        aspect=args.aspect,
        leftward=args.leftward,
        view=args.view,
        roll_deg=args.roll,
        curve_px=args.curve,
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
