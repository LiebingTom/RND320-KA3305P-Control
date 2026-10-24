"""Background thread that owns the serial connection.

All device access goes through a job queue that runs in this thread, so the GUI never
blocks on serial I/O and measurements and commands never interleave on the wire.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QThread, Signal

from src import profile
from src.datalog import CsvLogger
from src.ka3305p import KA3305P

SETPOINT_REFRESH_EVERY = 5   # re-read setpoints every n polls (front panel, RCL, VASTEP change them)
PROFILE_MIN_UPDATE = 0.2     # s between setpoint updates of a running ramp
PROFILE_PROGRESS_EVERY = 0.5 # s between progress signals


@dataclass
class _ProfileRun:
    segments: list[profile.Segment]
    t0: float                       # time.monotonic() at start
    v0: float
    i0: float
    index: int = -1                 # active segment
    sent: tuple[float, float] | None = None
    last_send: float = 0.0
    last_progress: float = 0.0


class DeviceWorker(QThread):
    connected = Signal(str, object)          # idn, protocol
    disconnected = Signal()
    measured = Signal(object)                # Measurement
    setpoints = Signal(object)               # {ch: (Vset, Iset)}
    protection = Signal(object)              # {ch: (OVP, OCP)}
    logging_changed = Signal(str)            # file path, "" when stopped
    profile_started = Signal(int, float, float, float)   # ch, wall-clock start, V0, I0
    profile_progress = Signal(int, int, float)           # ch, segment index, elapsed s
    profile_finished = Signal(int, str)                  # ch, "done" / "stopped" / error text
    error = Signal(str)

    def __init__(self, port: str, interval: float = 0.5, parent=None):
        super().__init__(parent)
        self.port = port
        self.interval = interval
        self.dev: KA3305P | None = None
        self._jobs: queue.Queue[Callable[[KA3305P], None]] = queue.Queue()
        self._running = True
        self._logger: CsvLogger | None = None
        self._setpoints: dict[int, tuple[float, float]] = {}
        self._runs: dict[int, _ProfileRun] = {}

    # ------------------------------------------------------------------ API for the GUI thread

    def submit(self, job: Callable[[KA3305P], None]):
        """Queue `job(dev)` to run in the worker thread."""
        self._jobs.put(job)

    def stop(self):
        self._running = False

    def start_logging(self):
        self.submit(lambda dev: self._start_logging())

    def stop_logging(self):
        self.submit(lambda dev: self._stop_logging())

    def refresh_setpoints(self):
        self.submit(lambda dev: self._read_setpoints())

    def refresh_protection(self):
        self.submit(lambda dev: self._read_protection())

    def start_profile(self, ch: int, segments: list[profile.Segment]):
        self.submit(lambda dev: self._start_profile(ch, segments))

    def stop_profile(self, ch: int):
        self.submit(lambda dev: self._end_profile(ch, "stopped"))

    def stop_all_profiles(self):
        self.submit(lambda dev: [self._end_profile(ch, "stopped") for ch in list(self._runs)])

    # ------------------------------------------------------------------ thread

    def run(self):
        try:
            self.dev = KA3305P(self.port)
        except Exception as e:
            self.error.emit(f"Connect to {self.port} failed: {e}")
            self.disconnected.emit()
            return

        self.connected.emit(self.dev.idn, self.dev.protocol)
        self._safe(self._read_setpoints)
        self._safe(self._read_protection)

        polls = 0
        next_poll = time.monotonic()
        while self._running:
            while not self._jobs.empty():
                job = self._jobs.get_nowait()
                self._safe(lambda: job(self.dev))

            for ch in list(self._runs):
                try:
                    self._step_profile(ch)
                except Exception as e:
                    self._end_profile(ch, f"aborted: {e}")

            if time.monotonic() >= next_poll:
                next_poll += self.interval
                if next_poll < time.monotonic():      # fell behind, don't burst
                    next_poll = time.monotonic() + self.interval
                polls += 1
                if polls % SETPOINT_REFRESH_EVERY == 0:
                    self._safe(self._read_setpoints)
                self._safe(self._poll)
            self.msleep(10)

        for ch in list(self._runs):
            self._end_profile(ch, "stopped")
        self._stop_logging()
        self.dev.disconnect()
        self.disconnected.emit()

    def _safe(self, fn: Callable[[], None]):
        try:
            fn()
        except Exception as e:
            self.error.emit(str(e))

    def _poll(self):
        m = self.dev.measure()
        if self._logger:
            rows = {ch: run.index + 1 for ch, run in self._runs.items()}
            self._logger.write(m, self._setpoints, rows)
        self.measured.emit(m)

    # ------------------------------------------------------------------ profiles

    def _start_profile(self, ch: int, segments: list[profile.Segment]):
        self._end_profile(ch, "stopped")
        v0, i0 = self.dev.get_voltage_setting(ch), self.dev.get_current_setting(ch)
        self._runs[ch] = _ProfileRun(segments=segments, t0=time.monotonic(), v0=v0, i0=i0)
        self.profile_started.emit(ch, time.time(), v0, i0)

    def _end_profile(self, ch: int, reason: str):
        if self._runs.pop(ch, None) is not None:
            self.profile_finished.emit(ch, reason)
            self._safe(self._read_setpoints)

    def _step_profile(self, ch: int):
        run = self._runs[ch]
        now = time.monotonic()
        elapsed = now - run.t0
        v, i, index = profile.setpoint_at(run.segments, elapsed, run.v0, run.i0)
        target = (round(v, self.dev.protocol.v_decimals), round(i, self.dev.protocol.i_decimals))
        entered = index != run.index

        if target != run.sent and (entered or now - run.last_send >= PROFILE_MIN_UPDATE):
            if run.sent is None or target[0] != run.sent[0]:
                self.dev.set_voltage(ch, target[0])
            if run.sent is None or target[1] != run.sent[1]:
                self.dev.set_current(ch, target[1])
            run.sent, run.last_send = target, now
            self._setpoints[ch] = target        # keep the logged setpoints current during ramps

        if entered:
            # apply output actions of every segment entered since the last step (short ones may be skipped over)
            for seg in run.segments[run.index + 1: index + 1]:
                if seg.output != "keep":
                    on = seg.output == "on"
                    if self.dev.supports("output_channel"):
                        self.dev.set_channel_output(ch, on)
                    else:
                        self.dev.set_output(on)
            run.index = index

        if entered or now - run.last_progress >= PROFILE_PROGRESS_EVERY:
            run.last_progress = now
            self.profile_progress.emit(ch, index, elapsed)
        if index >= len(run.segments):
            self._end_profile(ch, "done")

    def _read_setpoints(self):
        self._setpoints = {ch: (self.dev.get_voltage_setting(ch), self.dev.get_current_setting(ch))
                           for ch in self.dev.protocol.channels}
        self.setpoints.emit(dict(self._setpoints))

    def _read_protection(self):
        if not (self.dev.supports("get_ovp") and self.dev.supports("get_ocp")):
            return
        levels = {ch: (self.dev.get_ovp_level(ch), self.dev.get_ocp_level(ch))
                  for ch in self.dev.protocol.channels}
        self.protection.emit(levels)

    def _start_logging(self):
        self._stop_logging()
        self._logger = CsvLogger(channels=self.dev.protocol.channels)
        self.logging_changed.emit(str(self._logger.path))

    def _stop_logging(self):
        if self._logger:
            self._logger.close()
            self._logger = None
            self.logging_changed.emit("")
