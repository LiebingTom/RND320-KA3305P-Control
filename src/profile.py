"""Setpoint profiles: a sequence of timed segments executed on one channel.

Each segment lasts `duration` seconds and moves V and I to its targets:
    jump  - change to the targets at the segment start and hold them
    ramp  - move linearly from the previous values to the targets over the duration
A target of None means "unchanged" (e.g. ramp only the voltage, keep the current limit).
`output` ("keep" / "on" / "off") is applied at the segment start, after the setpoints.
The first segment starts from the channel's setpoints at run start. After the last
segment the final values are held.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

TRANSITIONS = ("jump", "ramp")
OUTPUTS = ("keep", "on", "off")
PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"
_LEGACY_TRANSITIONS = {"step": "jump"}


@dataclass
class Segment:
    duration: float                # s
    transition: str = "jump"
    v: float | None = None         # None = keep previous value
    i: float | None = None
    output: str = "keep"


def parse_duration(text: str) -> float:
    """'hh:mm:ss', 'mm:ss' or plain seconds -> seconds."""
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"invalid duration {text!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    if seconds < 0:
        raise ValueError(f"negative duration {text!r}")
    return seconds


def format_duration(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def parse_value(text: str | float | None) -> float | None:
    """Empty cell -> None (unchanged), otherwise float."""
    if text is None or (isinstance(text, str) and not text.strip()):
        return None
    return float(text)


def normalize_transition(name: str) -> str:
    name = name.strip()
    return _LEGACY_TRANSITIONS.get(name, name)


def validate(segments: list[Segment], v_max: float = 30.0, i_max: float = 5.0):
    if not segments:
        raise ValueError("Profile is empty")
    for n, s in enumerate(segments, 1):
        if s.transition not in TRANSITIONS:
            raise ValueError(f"Row {n}: transition must be one of {TRANSITIONS}")
        if s.output not in OUTPUTS:
            raise ValueError(f"Row {n}: output must be one of {OUTPUTS}")
        if s.duration < 0:
            raise ValueError(f"Row {n}: negative duration")
        if s.v is not None and not 0 <= s.v <= v_max:
            raise ValueError(f"Row {n}: {s.v} V outside 0..{v_max} V")
        if s.i is not None and not 0 <= s.i <= i_max:
            raise ValueError(f"Row {n}: {s.i} A outside 0..{i_max} A")


def total_duration(segments: list[Segment]) -> float:
    return sum(s.duration for s in segments)


def _targets(segments: list[Segment], v0: float, i0: float):
    """Yield (segment, V from, I from, V target, I target) with 'unchanged' resolved."""
    v_prev, i_prev = v0, i0
    for s in segments:
        v = v_prev if s.v is None else s.v
        i = i_prev if s.i is None else s.i
        yield s, v_prev, i_prev, v, i
        v_prev, i_prev = v, i


def setpoint_at(segments: list[Segment], t: float, v0: float, i0: float) -> tuple[float, float, int]:
    """Setpoints at `t` seconds after start and the index of the active segment
    (len(segments) once the profile is finished)."""
    start = 0.0
    v_end, i_end = v0, i0
    for n, (s, v_from, i_from, v, i) in enumerate(_targets(segments, v0, i0)):
        end = start + s.duration
        if t < end:
            if s.transition == "jump":
                return v, i, n
            frac = (t - start) / s.duration
            return v_from + (v - v_from) * frac, i_from + (i - i_from) * frac, n
        start, v_end, i_end = end, v, i
    return v_end, i_end, len(segments)


def breakpoints(segments: list[Segment], v0: float = 0.0, i0: float = 0.0):
    """Exact piecewise-linear curve (t, v, i arrays) for plotting; jumps appear as vertical lines."""
    t, vs, is_ = [0.0], [v0], [i0]
    start = 0.0
    for s, _, _, v, i in _targets(segments, v0, i0):
        if s.transition == "jump":
            t.append(start); vs.append(v); is_.append(i)
        start += s.duration
        t.append(start); vs.append(v); is_.append(i)
    return np.array(t), np.array(vs), np.array(is_)


def segment_starts(segments: list[Segment]) -> list[float]:
    return list(np.cumsum([0.0] + [s.duration for s in segments[:-1]]))


# ------------------------------------------------------------------ CSV

CSV_HEADER = ["duration", "transition", "voltage_V", "current_A", "output"]


def _fmt(value: float | None, decimals: int) -> str:
    return "" if value is None else f"{value:.{decimals}f}"


def save_csv(path: Path | str, segments: list[Segment]):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for s in segments:
            w.writerow([format_duration(s.duration), s.transition, _fmt(s.v, 2), _fmt(s.i, 3), s.output])


def load_csv(path: Path | str) -> list[Segment]:
    """Empty voltage/current cells mean 'unchanged'. Also reads the old 'mode' column (step -> jump)."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    segments = [Segment(duration=parse_duration(r["duration"]),
                        transition=normalize_transition(r.get("transition") or r.get("mode") or "jump"),
                        v=parse_value(r["voltage_V"]), i=parse_value(r["current_A"]),
                        output=(r.get("output") or "keep").strip()) for r in rows]
    validate(segments)
    return segments


def to_dicts(segments: list[Segment]) -> list[dict]:
    return [asdict(s) | {"duration": format_duration(s.duration)} for s in segments]
