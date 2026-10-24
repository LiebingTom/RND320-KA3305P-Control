"""Reusable GUI pieces: channel cards, live plots, profile editor."""

from __future__ import annotations

import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLCDNumber,
    QPushButton, QVBoxLayout, QWidget,
)

from src import profile
from src.gui import theme


def with_alpha(color: str, alpha: int):
    c = pg.mkColor(color)
    c.setAlpha(alpha)
    return c


def label(text: str = "", name: str | None = None) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    return lbl


def lcd(digits: int, color: str, height: int = 62) -> QLCDNumber:
    w = QLCDNumber(digits)
    w.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
    w.setSmallDecimalPoint(True)
    w.setFrameShape(QFrame.Shape.NoFrame)
    w.setMinimumHeight(height)
    w.setStyleSheet(f"color: {color};")
    return w


def spin(decimals: int, maximum: float, step: float, suffix: str) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(0.0, maximum)
    s.setSingleStep(step)
    s.setSuffix(f" {suffix}")
    s.setKeyboardTracking(False)
    s.setAlignment(Qt.AlignmentFlag.AlignRight)
    s.setMinimumWidth(92)
    s.setLocale(QLocale.c())
    return s


# =========================================================================== channel card

class ChannelCard(QFrame):
    """Readout and controls of one channel. CH3 is shown as a fixed, non-remote output."""

    apply_setpoint = Signal(int, float, float)        # ch, V, I
    apply_protection = Signal(int, float, float)      # ch, OVP, OCP
    output_toggled = Signal(int, bool)                # ch, on

    def __init__(self, ch: int, controllable: bool = True, fixed: tuple[float, float] | None = None):
        super().__init__()
        self.ch = ch
        self.color = theme.CHANNEL_COLORS[ch]
        self.controllable = controllable
        self.setObjectName("card")
        self._output_on = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(8)

        # header: name, CV/CC badge, output button
        head = QHBoxLayout()
        name = label(f"CH{ch}", "title")
        name.setStyleSheet(f"color: {self.color};")
        head.addWidget(name)
        self.mode_badge = label("--", "badge")
        head.addWidget(self.mode_badge)
        head.addStretch()
        self.out_btn = QPushButton("OFF")
        self.out_btn.setObjectName("outOff")
        self.out_btn.setFixedWidth(70)
        self.out_btn.clicked.connect(lambda: self.output_toggled.emit(self.ch, not self._output_on))
        head.addWidget(self.out_btn)
        root.addLayout(head)

        # readouts
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        self.v_lcd = lcd(4, self.color)
        self.i_lcd = lcd(4, self.color)
        grid.addWidget(self.v_lcd, 0, 0)
        grid.addWidget(label("V", "dim"), 0, 1, Qt.AlignmentFlag.AlignBottom)
        grid.setColumnMinimumWidth(2, 14)
        grid.addWidget(self.i_lcd, 0, 3)
        grid.addWidget(label("A", "dim"), 0, 4, Qt.AlignmentFlag.AlignBottom)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(3, 1)
        self.p_label = label("-- W", "dim")
        self.set_label = label("", "dim")
        info = QHBoxLayout()
        info.addWidget(self.set_label)
        info.addStretch()
        info.addWidget(self.p_label)
        root.addLayout(grid)
        root.addLayout(info)

        if not controllable:
            v, i = fixed or (0.0, 0.0)
            self.v_lcd.display(f"{v:05.2f}")
            self.i_lcd.display(f"{i:.3f}")
            for w in (self.v_lcd, self.i_lcd):
                w.setStyleSheet(f"color: {self.color}; background: transparent;")
            self.mode_badge.setText("FIXED")
            self._badge(theme.DIM)
            self.out_btn.hide()
            self.set_label.setText("Not remote-controllable — values are nominal, not measured.")
            self.set_label.setWordWrap(True)
            self.p_label.hide()
            root.addStretch()
            return

        # setpoint row
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        self.v_spin = spin(2, 30.0, 0.1, "V")
        self.i_spin = spin(3, 5.0, 0.01, "A")
        self.set_btn = QPushButton("Set")
        self.set_btn.clicked.connect(self._emit_setpoint)
        for s in (self.v_spin, self.i_spin):
            s.lineEdit().returnPressed.connect(self._emit_setpoint)
        form.addWidget(label("Limit", "dim"), 0, 0)
        form.addWidget(self.v_spin, 0, 1)
        form.addWidget(self.i_spin, 0, 2)
        form.addWidget(self.set_btn, 0, 3)

        self.ovp_spin = spin(2, 31.0, 0.1, "V")
        self.ocp_spin = spin(3, 5.1, 0.01, "A")
        self.prot_btn = QPushButton("Set")
        self.prot_btn.clicked.connect(
            lambda: self.apply_protection.emit(self.ch, self.ovp_spin.value(), self.ocp_spin.value()))
        form.addWidget(label("OVP / OCP", "dim"), 1, 0)
        form.addWidget(self.ovp_spin, 1, 1)
        form.addWidget(self.ocp_spin, 1, 2)
        form.addWidget(self.prot_btn, 1, 3)
        root.addLayout(form)

        self.set_connected(False)

    def _badge(self, color: str):
        self.mode_badge.setStyleSheet(f"background: {color}; color: {theme.BG};")

    def _emit_setpoint(self):
        self.apply_setpoint.emit(self.ch, self.v_spin.value(), self.i_spin.value())

    def set_connected(self, connected: bool):
        if not self.controllable:
            return
        for w in (self.v_spin, self.i_spin, self.set_btn, self.ovp_spin, self.ocp_spin, self.prot_btn, self.out_btn):
            w.setEnabled(connected)
        if not connected:
            self.v_lcd.display("--.--")
            self.i_lcd.display("-.---")
            self.mode_badge.setText("--")
            self._badge(theme.BORDER)
            self.p_label.setText("-- W")

    def set_slave(self, slave: bool):
        """In series/parallel tracking CH2 is master and CH1 settings are ignored by the device."""
        for w in (self.v_spin, self.i_spin, self.set_btn):
            w.setEnabled(not slave)
        self.v_spin.setToolTip("CH2 is master in tracking mode" if slave else "")

    def set_profile_running(self, running: bool):
        for w in (self.v_spin, self.i_spin, self.set_btn):
            w.setEnabled(not running)
        self.set_btn.setToolTip("Profile running on this channel" if running else "")

    def set_output_controls(self, per_channel: bool):
        self.out_btn.setVisible(per_channel)

    def update_measurement(self, v: float, i: float, cv: bool, on: bool):
        self.v_lcd.display(f"{v:05.2f}")
        self.i_lcd.display(f"{i:.3f}")
        self.p_label.setText(f"{v * i:.3f} W")
        self.mode_badge.setText("CV" if cv else "CC")
        self._badge(theme.ON if cv else theme.WARN)
        self._output_on = on
        self.out_btn.setText("ON" if on else "OFF")
        self.out_btn.setObjectName("outOn" if on else "outOff")
        self.out_btn.style().unpolish(self.out_btn)
        self.out_btn.style().polish(self.out_btn)

    def update_setpoint(self, v: float, i: float, fill_spins: bool):
        self.set_label.setText(f"set {v:.2f} V · {i:.3f} A")
        if fill_spins:
            self.v_spin.setValue(v)
            self.i_spin.setValue(i)

    def update_protection(self, ovp: float, ocp: float):
        self.ovp_spin.setValue(ovp)
        self.ocp_spin.setValue(ocp)


# =========================================================================== live plots

class _Series:
    """Growing float buffer without per-sample reallocation."""

    def __init__(self):
        self._data = np.empty(1024)
        self.n = 0

    def append(self, value: float):
        if self.n == len(self._data):
            self._data = np.resize(self._data, 2 * len(self._data))
        self._data[self.n] = value
        self.n += 1

    @property
    def data(self) -> np.ndarray:
        return self._data[: self.n]

    def clear(self):
        self.n = 0


WINDOWS = {"1 min": 60, "5 min": 300, "15 min": 900, "1 h": 3600, "6 h": 21600, "All": None}


class PlotPanel(QWidget):
    """Voltage and current over time, one trace per channel, shared time axis."""

    def __init__(self, fixed_ch3: tuple[float, float] | None = (5.0, 3.0)):
        super().__init__()
        pg.setConfigOptions(antialias=True, background=theme.PANEL, foreground=theme.DIM)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.addWidget(label("Window", "dim"))
        self.window_box = QComboBox()
        self.window_box.addItems(WINDOWS)
        self.window_box.setCurrentText("5 min")
        bar.addWidget(self.window_box)
        self.follow = QCheckBox("Follow")
        self.follow.setChecked(True)
        bar.addWidget(self.follow)
        bar.addSpacing(16)
        self.visible: dict[int, QCheckBox] = {}
        for ch in (1, 2, 3):
            cb = QCheckBox(f"CH{ch}")
            cb.setChecked(ch != 3)    # CH3 is only a nominal line, off by default
            cb.setStyleSheet(f"color: {theme.CHANNEL_COLORS[ch]};")
            cb.toggled.connect(self._apply_visibility)
            self.visible[ch] = cb
            bar.addWidget(cb)
        bar.addStretch()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)
        bar.addWidget(self.clear_btn)
        layout.addLayout(bar)

        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)
        self.v_plot = self.glw.addPlot(row=0, col=0, axisItems={"bottom": pg.DateAxisItem()})
        self.i_plot = self.glw.addPlot(row=1, col=0, axisItems={"bottom": pg.DateAxisItem()})
        self.i_plot.setXLink(self.v_plot)
        for plot, name, unit in ((self.v_plot, "Voltage", "V"), (self.i_plot, "Current", "A")):
            plot.setLabel("left", name, units=unit)
            plot.showGrid(x=True, y=True, alpha=0.15)
            plot.setClipToView(True)
            plot.setDownsampling(auto=True, mode="peak")
            plot.addLegend(offset=(10, 5), labelTextColor=theme.TEXT, brush=pg.mkBrush(theme.BG + "c0"))
            plot.getViewBox().sigRangeChangedManually.connect(lambda *_: self.follow.setChecked(False))

        self.t = _Series()
        self.v = {ch: _Series() for ch in (1, 2)}
        self.i = {ch: _Series() for ch in (1, 2)}
        self.v_curves, self.i_curves = {}, {}
        for ch in (1, 2):
            pen = pg.mkPen(theme.CHANNEL_COLORS[ch], width=2)
            self.v_curves[ch] = self.v_plot.plot(name=f"CH{ch}", pen=pen)
            self.i_curves[ch] = self.i_plot.plot(name=f"CH{ch}", pen=pen)

        # CH3 cannot be measured: nominal values as dashed lines
        self.plan_curves: dict[int, tuple] = {}
        self.ch3_lines = []
        if fixed_ch3:
            pen = pg.mkPen(theme.CHANNEL_COLORS[3], width=1.5, style=Qt.PenStyle.DashLine)
            for plot, value, unit in ((self.v_plot, fixed_ch3[0], "V"), (self.i_plot, fixed_ch3[1], "A max")):
                line = pg.InfiniteLine(pos=value, angle=0, pen=pen,
                                       label=f"CH3 fixed {value:g} {unit}",
                                       labelOpts={"position": 0.98, "color": theme.CHANNEL_COLORS[3], "anchors": [(1, 1), (1, 1)]})
                plot.addItem(line)
                self.ch3_lines.append(line)
        self._apply_visibility()

    def add(self, t: float, voltage: dict[int, float], current: dict[int, float]):
        self.t.append(t)
        for ch in (1, 2):
            self.v[ch].append(voltage.get(ch, np.nan))
            self.i[ch].append(current.get(ch, np.nan))

    def redraw(self):
        if not self.t.n:
            return
        t = self.t.data
        for ch in (1, 2):
            self.v_curves[ch].setData(t, self.v[ch].data)
            self.i_curves[ch].setData(t, self.i[ch].data)
        if self.follow.isChecked():
            window = WINDOWS[self.window_box.currentText()]
            now = time.time()
            start = t[0] if window is None else now - window
            self.v_plot.setXRange(start, now, padding=0.01)
            for plot in (self.v_plot, self.i_plot):
                plot.enableAutoRange(axis="y")

    def show_plan(self, ch: int, t0: float, segments, v0: float, i0: float):
        """Overlay the planned profile of channel `ch` starting at wall-clock time `t0`."""
        self.clear_plan(ch)
        t, v, i = profile.breakpoints(segments, v0, i0)
        pen = pg.mkPen(with_alpha(theme.CHANNEL_COLORS[ch], 110), width=1.5, style=Qt.PenStyle.DashLine)
        curves = (self.v_plot.plot(t + t0, v, pen=pen), self.i_plot.plot(t + t0, i, pen=pen))
        for c in curves:
            c.setVisible(self.visible[ch].isChecked())
        self.plan_curves[ch] = curves

    def clear_plan(self, ch: int):
        for plot, c in zip((self.v_plot, self.i_plot), self.plan_curves.pop(ch, ())):
            plot.removeItem(c)

    def clear(self):
        for ch in list(self.plan_curves):
            self.clear_plan(ch)
        self.t.clear()
        for ch in (1, 2):
            self.v[ch].clear()
            self.i[ch].clear()
            self.v_curves[ch].setData([], [])
            self.i_curves[ch].setData([], [])

    def state(self) -> dict:
        return {"window": self.window_box.currentText(), "follow": self.follow.isChecked(),
                "visible": {str(ch): cb.isChecked() for ch, cb in self.visible.items()}}

    def restore(self, state: dict):
        if state["window"] in WINDOWS:
            self.window_box.setCurrentText(state["window"])
        self.follow.setChecked(state["follow"])
        for ch, cb in self.visible.items():
            cb.setChecked(state["visible"].get(str(ch), cb.isChecked()))

    def _apply_visibility(self):
        for ch in (1, 2):
            on = self.visible[ch].isChecked()
            self.v_curves[ch].setVisible(on)
            self.i_curves[ch].setVisible(on)
            for c in self.plan_curves.get(ch, ()):
                c.setVisible(on)
        for line in self.ch3_lines:
            line.setVisible(self.visible[3].isChecked())
