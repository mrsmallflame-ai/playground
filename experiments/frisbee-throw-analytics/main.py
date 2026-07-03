#!/usr/bin/env python3
"""Entry point.

Default (no arguments) launches the desktop GUI. A headless CLI mode is
available for scripted analysis:

    python main.py                      # GUI
    python main.py analyze throw.mp4    # print metrics for one video
    python main.py overlay throw.mp4 out.mp4   # write annotated video
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frisbee throw analytics")
    sub = parser.add_subparsers(dest="command")

    p_analyze = sub.add_parser("analyze", help="analyse one video, print metrics as JSON")
    p_analyze.add_argument("video")
    p_analyze.add_argument(
        "--view",
        choices=["auto", "side", "overhead"],
        default="auto",
        help="camera geometry; 'auto' classifies it from the flight path",
    )

    p_overlay = sub.add_parser("overlay", help="render flight-path overlay video")
    p_overlay.add_argument("video")
    p_overlay.add_argument("output")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        from frisbee_analytics.analysis import analyse_track
        from frisbee_analytics.vision import track_video

        track = track_video(args.video)
        if len(track) < 3:
            print("error: could not track the disc in this video", file=sys.stderr)
            return 1
        metrics = analyse_track(track, view=args.view)
        print(json.dumps({"tracked_frames": len(track), **metrics.to_dict()}, indent=2))
        return 0

    if args.command == "overlay":
        from frisbee_analytics.vision import track_video
        from frisbee_analytics.viz.overlay import render_overlay_video

        track = track_video(args.video)
        out = render_overlay_video(args.video, track, args.output)
        print(f"wrote {out}")
        return 0

    from frisbee_analytics.gui.app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
