"""CSV logging of KA3305P measurements."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.ka3305p import Measurement

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class CsvLogger:
    """One row per measurement: time, measured V/I/P, setpoints, CV/CC and output state per channel."""

    def __init__(self, path: Path | str | None = None, channels: tuple[int, ...] = (1, 2)):
        if path is None:
            LOG_DIR.mkdir(exist_ok=True)
            path = LOG_DIR / f"ka3305p_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self.path = Path(path)
        self.channels = channels
        self.t0: float | None = None
        self._file = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)

        header = ["timestamp", "t_s"]
        for ch in channels:
            header += [f"V{ch}_V", f"I{ch}_A", f"P{ch}_W", f"Vset{ch}_V", f"Iset{ch}_A", f"mode{ch}", f"out{ch}"]
        header += ["tracking", "status_raw"] + [f"profile{ch}_row" for ch in channels]
        self._writer.writerow(header)

    def write(self, m: Measurement, setpoints: dict[int, tuple[float, float]] | None = None,
              profile_rows: dict[int, int] | None = None):
        """`setpoints` maps channel -> (Vset, Iset), `profile_rows` channel -> active profile row (1-based);
        missing entries are left empty."""
        if self.t0 is None:
            self.t0 = m.t
        row = [datetime.fromtimestamp(m.t).isoformat(timespec="milliseconds"), f"{m.t - self.t0:.3f}"]
        for ch in self.channels:
            v, i = m.voltage[ch], m.current[ch]
            vset, iset = (setpoints or {}).get(ch, ("", ""))
            row += [f"{v:.2f}", f"{i:.3f}", f"{v * i:.4f}", vset, iset,
                    "CV" if m.status.cv[ch] else "CC", int(m.status.output[ch])]
        tracking = m.status.tracking.name.lower() if m.status.tracking is not None else ""
        row += [tracking, f"0x{m.status.raw:02X}"] + [(profile_rows or {}).get(ch, "") for ch in self.channels]
        self._writer.writerow(row)
        self._file.flush()

    def close(self):
        self._file.close()
