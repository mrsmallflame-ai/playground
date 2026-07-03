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
| `video/pipeline.py` | Video acquisition + preprocessing (Gaussian denoise, BGR→HSV, morphological thresholding). |
| `vision/tracker.py` | Disc detection fusing a motion cue (double frame-differencing) with colour segmentation, validated by a tilt-invariant ellipse shape model; tracking with constant-velocity prediction, jump gating, coasting, and stagnation escape. Calibrates a px→m scale from the fitted ellipse's major axis. |
| `analysis/metrics.py` | Viewpoint-aware kinematics engine: auto-classifies side vs overhead camera geometry, corrects camera roll from the apparent gravity direction, then derives release angle/speed, displacements, path length, straightness, lateral deviation (arc height / flight curve), duration, and a multi-throw consistency report. |
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
python main.py analyze throw.mp4 --view overhead   # force top-down analysis
python main.py overlay throw.mp4 out.mp4    # headless: annotated video

# No footage? Generate a synthetic throw:
python tools/generate_sample.py sample.mp4 --angle 20 --speed 320
python tools/generate_sample.py tilted.mp4 --roll 25          # tilted camera
python tools/generate_sample.py above.mp4 --view topdown      # camera overhead

# Tests (headless-safe):
python -m pytest tests/
```

The default tracker targets a bright/white disc (low saturation, high value in
HSV). For coloured discs, adjust `TrackerConfig.hsv_lower/hsv_upper` in
`frisbee_analytics/vision/tracker.py`.

## Notes

- **Detection fuses two independent cues.** Double frame-differencing
  (`|f_t−f_{t−1}| ∧ |f_t−f_{t−2}|`) finds the disc by its motion — which is
  what makes a white disc against a white wall or sky trackable — and also
  suppresses ghosts at just-vacated positions by construction. HSV colour
  segmentation trims motion blobs to disc pixels and can continue a track
  when motion cues degrade. Per frame the tracker tries motion∧appearance,
  motion, then appearance.
- **Shape filtering is tilt-invariant.** A disc projects to an ellipse from
  any camera angle, so candidates are scored by how well they fill a fitted
  ellipse (not circularity, which rejects edge-on views). The ellipse's major
  axis equals the disc diameter from any viewpoint, which keeps the px→m
  calibration (vs. the regulation 0.274 m diameter) viewpoint-independent.
- **New tracks may only start from motion-backed detections** — a static
  white blob that passes the colour and shape filters would otherwise pin the
  prediction gate and lock the real disc out. A stagnation check drops any
  "track" that stops moving, since a disc in flight never does.
- **Release velocity is fit robustly**: Theil–Sen (median of pairwise slopes)
  horizontally, and the `t = 0` derivative of a quadratic fit vertically, so
  one bad point near acquisition can't wreck it and gravity's bend across the
  window is modelled rather than averaged in as bias.
- **The analysis is viewpoint-aware.** A single camera measures the flight's
  projection, so the physics must match the geometry. In side-ish views the
  apparent gravity vector is estimated from the track's own acceleration and
  the coordinates are rotated so release angle is measured against the true
  horizon — a phone held at 25° gives the same numbers as a level tripod
  (corrections only engage for clearly tilted footage, ≥ ~8°, because drag
  and tracker bias tilt the apparent gravity by a few degrees). Overhead
  views have no in-plane gravity, so the engine switches to ground-plane
  metrics: throw distance, ground speed, and the flight's lateral curve.
- **View auto-classification** uses two physical signatures: the parabolic
  sag gravity leaves in a side-view path, and the apparent disc-size change
  as it rises toward an overhead camera. Ambiguous footage (e.g. a fast,
  flat throw, or low-contrast overhead video where the size trend is
  unreadable) defaults to side view; `--view side|overhead` overrides it.
- Flight-path velocities elsewhere use central differences over the tracked
  time-series — noticeably less noisy than adjacent-frame deltas.
- Verified on a 34-scenario synthetic matrix (grass/white/sky backgrounds ×
  face-on/tilted/near-edge-on discs × both throw directions × 140–320 px/s ×
  5–40° release × camera rolls up to 40° × top-down views): all tracked
  ≥ 34/50 frames with release angle within a few degrees, speed within ~5 %,
  roll recovered within ~3°, and overhead curve within ~1 px. The hardest
  tracking case — a ~2 px edge-on sliver at ~20 grey-levels of contrast
  against white — tracks 44/50 frames.
- Future: the modular split leaves room for an ESP32 + IMU capture path
  (Bluetooth) feeding real motion data into the same `analysis` engine.
