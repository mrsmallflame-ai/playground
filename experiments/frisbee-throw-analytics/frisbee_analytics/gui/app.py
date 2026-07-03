"""Desktop GUI: upload videos, analyse throws, compare, review sessions.

Layout: a left panel manages the session and its list of analysed throws;
the right side is a notebook with the trajectory view, metric comparison,
session progress, and a numeric summary. Video processing runs on a worker
thread so the interface stays responsive.
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..analysis import analyse_track, consistency_report
from ..models import ThrowRecord
from ..storage import SessionStore
from ..viz.plots import metrics_bar_figure, progress_figure, trajectory_figure
from ..vision import track_video


class App(tk.Tk):
    def __init__(self, store: SessionStore | None = None):
        super().__init__()
        self.title("Frisbee Throw Analytics")
        self.geometry("1100x700")
        self.store = store or SessionStore()
        self.session_name = "default"
        self.records: list[ThrowRecord] = self.store.load_session(self.session_name)
        self._build()
        self._refresh_throw_list()

    # ── layout ────────────────────────────────────────────────────────────
    def _build(self) -> None:
        left = ttk.Frame(self, padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left, text="Session").pack(anchor="w")
        self.session_var = tk.StringVar(value=self.session_name)
        self.session_box = ttk.Combobox(
            left, textvariable=self.session_var,
            values=self.store.list_sessions() or [self.session_name],
        )
        self.session_box.pack(fill=tk.X, pady=(0, 8))
        self.session_box.bind("<<ComboboxSelected>>", lambda _e: self._switch_session())

        ttk.Button(left, text="Import video…", command=self._import_video).pack(fill=tk.X)
        ttk.Button(left, text="New session", command=self._new_session).pack(fill=tk.X, pady=(4, 8))

        ttk.Label(left, text="Throws (select to compare)").pack(anchor="w")
        self.throw_list = tk.Listbox(left, selectmode=tk.EXTENDED, width=28, height=24)
        self.throw_list.pack(fill=tk.BOTH, expand=True)
        self.throw_list.bind("<<ListboxSelect>>", lambda _e: self._refresh_views())

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(left, textvariable=self.status_var, wraplength=200).pack(anchor="w", pady=4)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.tab_frames: dict[str, ttk.Frame] = {}
        for name in ("Trajectories", "Compare metrics", "Session progress", "Summary"):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=name)
            self.tab_frames[name] = frame
        self.summary_text = tk.Text(self.tab_frames["Summary"], wrap="word", font=("TkFixedFont",))
        self.summary_text.pack(fill=tk.BOTH, expand=True)

    # ── session / import actions ──────────────────────────────────────────
    def _switch_session(self) -> None:
        self.session_name = self.session_var.get().strip() or "default"
        self.records = self.store.load_session(self.session_name)
        self._refresh_throw_list()

    def _new_session(self) -> None:
        name = simpledialog.askstring("New session", "Session name:", parent=self)
        if not name:
            return
        self.session_var.set(name)
        self._switch_session()
        self.session_box["values"] = sorted(set(self.store.list_sessions()) | {name})

    def _import_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a throw video",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")],
        )
        if not path:
            return
        self.status_var.set(f"Processing {Path(path).name}…")
        threading.Thread(target=self._process_video, args=(path,), daemon=True).start()

    def _process_video(self, path: str) -> None:
        try:
            track = track_video(path)
            if len(track) < 3:
                raise ValueError("could not track the disc — check lighting/colour thresholds")
            record = ThrowRecord(
                name=f"{Path(path).stem} #{len(self.records) + 1}",
                video_path=path,
                recorded_at=datetime.now(timezone.utc).isoformat(),
                track=track,
                metrics=analyse_track(track),
            )
            self.store.save_throw(self.session_name, record)
            self.records.append(record)
            self.after(0, self._on_processed, record)
        except Exception as exc:  # surfaced to the user, not swallowed
            self.after(0, lambda: self.status_var.set(f"Failed: {exc}"))

    def _on_processed(self, record: ThrowRecord) -> None:
        self.status_var.set(f"Analysed {record.name}")
        self._refresh_throw_list()

    # ── views ─────────────────────────────────────────────────────────────
    def _selected_records(self) -> list[ThrowRecord]:
        selected = [self.records[i] for i in self.throw_list.curselection()]
        return selected or self.records

    def _refresh_throw_list(self) -> None:
        self.throw_list.delete(0, tk.END)
        for record in self.records:
            self.throw_list.insert(tk.END, record.name)
        self._refresh_views()

    def _embed_figure(self, tab: str, figure) -> None:
        frame = self.tab_frames[tab]
        for child in frame.winfo_children():
            child.destroy()
        canvas = FigureCanvasTkAgg(figure, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _refresh_views(self) -> None:
        records = self._selected_records()
        if not records:
            return
        self._embed_figure("Trajectories", trajectory_figure(records))
        self._embed_figure("Compare metrics", metrics_bar_figure(records))
        self._embed_figure("Session progress", progress_figure(self.records))
        self._refresh_summary(records)

    def _refresh_summary(self, records: list[ThrowRecord]) -> None:
        lines = []
        for record in records:
            m = record.metrics
            angle_line = (
                f"   release angle      {m.release_angle_deg:7.1f} °"
                if m.view == "side"
                else "   release angle          n/a (overhead view)"
            )
            lines += [
                f"── {record.name} ({record.recorded_at[:19]})",
                f"   camera view        {m.view:>7}"
                + (f"  (roll {m.camera_roll_deg:+.1f}°)" if m.camera_roll_deg else ""),
                angle_line,
                f"   release speed      {m.release_speed_px_s:7.1f} px/s"
                + (f"  (~{m.release_speed_m_s:.1f} m/s)" if m.release_speed_m_s else ""),
                f"   peak speed         {m.peak_speed_px_s:7.1f} px/s",
                f"   flight duration    {m.flight_duration_s:7.2f} s",
                f"   horiz displacement {m.horizontal_displacement_px:7.1f} px",
                f"   vert displacement  {m.vertical_displacement_px:7.1f} px",
                f"   straightness       {m.straightness:7.2f}",
                f"   lateral deviation  {m.lateral_deviation_px:7.1f} px"
                + ("  (flight curve)" if m.view == "overhead" else "  (arc height)"),
                "",
            ]
        if len(records) > 1:
            report = consistency_report([r.metrics for r in records])
            lines += [
                f"── Consistency across {report.n_throws} throws",
                f"   score              {report.consistency_score:7.0f} / 100",
                f"   angle spread       {report.release_angle_stdev:7.1f} ° (mean {report.release_angle_mean:.1f})",
                f"   speed spread       {report.release_speed_stdev:7.1f} px/s (mean {report.release_speed_mean:.1f})",
                f"   duration spread    {report.duration_stdev:7.2f} s (mean {report.duration_mean:.2f})",
            ]
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", "\n".join(lines) or "No throws yet — import a video.")


def run() -> None:
    try:
        app = App()
    except tk.TclError as exc:
        raise SystemExit(f"Could not start GUI (is a display available?): {exc}")
    app.mainloop()
