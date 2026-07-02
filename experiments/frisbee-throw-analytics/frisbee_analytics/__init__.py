"""Frisbee Throw Analytics.

A desktop sports-analytics application that uses computer vision to analyse
ultimate frisbee throwing mechanics from recorded video footage.

The package is split into independent modules:

- ``video``    — video acquisition and frame preprocessing pipeline (OpenCV)
- ``vision``   — disc detection and tracking, producing time-series positions
- ``analysis`` — kinematics engine deriving performance metrics from tracks
- ``storage``  — persistent local session store for long-term progress
- ``viz``      — flight-path overlays and statistical charts
- ``gui``      — Tkinter desktop interface tying it all together
"""

__version__ = "0.1.0"
