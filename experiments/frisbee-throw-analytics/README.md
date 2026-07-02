# frisbee-throw-analytics

> A desktop computer-vision app that analyses ultimate frisbee throwing mechanics from recorded video.

## Idea

Film a throw, feed the clip in, and get objective numbers back: release angle,
flight trajectory, displacement, estimated velocity, flight duration, and
throw-to-throw consistency. The app tracks the disc frame-by-frame with OpenCV,
turns the positions into a time-series, and derives metrics with basic
kinematics — then presents everything in a Tkinter GUI with trajectory plots,
comparison charts, and locally stored training sessions.

## Architecture

Independent modules under `frisbee_analytics/`, one per pipeline stage:

| Module | Responsibility |
| --- | --- |
| `video/pipeline.py` | Video acquisition + preprocessing (Gaussian denoise, BGR→HSV, value equalisation, morphological thresholding). |
| `vision/tracker.py` | Disc detection (colour segmentation → circularity-filtered blobs) and tracking (constant-velocity prediction, jump rejection). Calibrates a px→m scale from the disc's apparent size. |
| `analysis/metrics.py` | Kinematics engine: release angle/speed (central differences), displacements, path length, straightness, duration, and a multi-throw consistency report. |
| `storage/store.py` | Persistent local sessions as human-readable JSON under `~/.frisbee_analytics/`. |
| `viz/plots.py` | Matplotlib charts: trajectories, metric comparison, session progress. |
| `viz/overlay.py` | Flight-path overlay rendered onto the original video. |
| `gui/app.py` | Tkinter desktop UI: import videos, select/compare throws, browse sessions. Processing runs on a worker thread. |

`models.py` holds the shared dataclasses (`TrackPoint`, `FlightTrack`,
`ThrowMetrics`, `ThrowRecord`); everything serialises to plain dicts, which is
what makes the JSON store and future export formats cheap.

## Running it

```bash
pip install -r requirements.txt

python main.py                              # desktop GUI (needs tkinter + display)
python main.py analyze throw.mp4            # headless: metrics as JSON
python main.py overlay throw.mp4 out.mp4    # headless: annotated video

# No footage? Generate a synthetic throw:
python tools/generate_sample.py sample.mp4 --angle 20 --speed 320

# Tests (headless-safe):
python -m pytest tests/
```

The default tracker targets a bright/white disc (low saturation, high value in
HSV). For coloured discs, adjust `TrackerConfig.hsv_lower/hsv_upper` in
`frisbee_analytics/vision/tracker.py`.

## Notes

- Velocities use central differences over the tracked time-series — noticeably
  less noisy than adjacent-frame deltas.
- Release angle is estimated from only the first ~3 velocity samples: averaging
  deeper into the flight lets gravity bias the angle downward.
- The px→m scale comes from the median apparent disc radius vs. the regulation
  0.274 m diameter, so `m/s` figures are estimates, best when the flight is
  roughly perpendicular to the camera.
- Verified end-to-end on synthetic footage: an 18° / 300 px/s generated throw
  measures 16.7° / 293 px/s through the full video → tracker → metrics path.
- Future: the modular split leaves room for an ESP32 + IMU capture path
  (Bluetooth) feeding real motion data into the same `analysis` engine.
