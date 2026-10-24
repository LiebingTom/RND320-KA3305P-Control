"""Profile tab: segment table, CSV load/save, preview dialog and per-channel run controls."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src import profile
from src.gui import theme
from src.gui.widgets import label
from src.profile import Segment


class DurationAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [profile.format_duration(v) if v >= 0 else "" for v in values]


# =========================================================================== preview dialog

class ProfilePreviewDialog(QDialog):
    """Planned voltage and current over time; optionally one segment highlighted."""

    def __init__(self, segments: list[Segment], highlight: int | None = None, color: str = theme.TEXT,
                 v0: float = 0.0, i0: float = 0.0, parent=None):
        super().__init__(parent)
        title = "Profile preview" + (f" — row {highlight + 1}" if highlight is not None else "")
        self.setWindowTitle(title)
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(label(
            f"Total {profile.format_duration(profile.total_duration(segments))} · "
            f"starts from the channel's setpoints at run start (shown here as {v0:g} V / {i0:g} A) · "
            "last values are held at the end.", "dim"))

        glw = pg.GraphicsLayoutWidget()
        layout.addWidget(glw)
        t, v, i = profile.breakpoints(segments, v0, i0)
        starts = profile.segment_starts(segments)
        plots = []
        for row, (name, unit, data) in enumerate((("Voltage", "V", v), ("Current", "A", i))):
            p = glw.addPlot(row=row, col=0, axisItems={"bottom": DurationAxis(orientation="bottom")})
            p.setLabel("left", name, units=unit)
            p.showGrid(x=True, y=True, alpha=0.15)
            p.plot(t, data, pen=pg.mkPen(color, width=2))
            for n, (seg, start) in enumerate(zip(segments, starts)):
                if seg.output != "keep":
                    on = seg.output == "on"
                    p.addItem(pg.InfiniteLine(
                        pos=start, angle=90, pen=pg.mkPen(theme.ON if on else theme.OFF, width=1,
                                                          style=Qt.PenStyle.DotLine),
                        label="ON" if on else "OFF", labelOpts={"position": 0.95,
                                                                "color": theme.ON if on else theme.OFF}))
            if highlight is not None and 0 <= highlight < len(segments):
                region = pg.LinearRegionItem(
                    (starts[highlight], starts[highlight] + segments[highlight].duration),
                    movable=False, brush=pg.mkBrush(255, 255, 255, 28), pen=pg.mkPen(None))
                p.addItem(region)
            if plots:
                p.setXLink(plots[0])
            plots.append(p)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)


# =========================================================================== panel

class ProfilePanel(QWidget):
    run_requested = Signal(int, object)     # ch, list[Segment]
    stop_requested = Signal(int)

    COLUMNS = ("Duration [hh:mm:ss]", "Transition", "V [V]", "I [A]", "Output", "")
    HEADER_TIPS = ("How long this row lasts (hh:mm:ss, mm:ss or seconds)",
                   "jump: change V/I at the row start and hold · ramp: move linearly from the previous values",
                   "Voltage target; empty = unchanged", "Current limit target; empty = unchanged",
                   "Switch the channel output at the row start", "")

    def __init__(self, channels: tuple[int, ...] = (1, 2)):
        super().__init__()
        layout = QVBoxLayout(self)

        note = label("Each row runs for its duration and moves <b>V and I together</b> to its targets: "
                     "<b>jump</b> changes them at the row start, <b>ramp</b> moves them linearly from the previous "
                     "values. Leave V or I <b>empty to keep it unchanged</b> (e.g. ramp only the voltage). "
                     "Output on/off is applied at the row start. The first row starts from the channel's "
                     "current setpoints; the last values are held.", "dim")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        for col, tip in enumerate(self.HEADER_TIPS):
            self.table.horizontalHeaderItem(col).setToolTip(tip)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._update_total)
        layout.addWidget(self.table)

        bar = QHBoxLayout()
        for text, slot in (("Add row", lambda: self.add_row()), ("Remove", self.remove_rows),
                           ("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1)),
                           ("Load CSV…", self.load_csv), ("Save CSV…", self.save_csv),
                           ("Preview", lambda: self.show_preview(None))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch()
        self.total_label = label("", "dim")
        bar.addWidget(self.total_label)
        layout.addLayout(bar)

        # run controls per channel
        self.run_btns: dict[int, QPushButton] = {}
        self.progress: dict[int, QProgressBar] = {}
        self.state_labels: dict[int, QLabel] = {}
        self._running: dict[int, bool] = {}
        self._totals: dict[int, float] = {}
        self._counts: dict[int, int] = {}
        for ch in channels:
            row = QHBoxLayout()
            color = theme.CHANNEL_COLORS[ch]
            b = QPushButton(f"▶  Run on CH{ch}")
            b.setMinimumWidth(150)
            b.setStyleSheet(f"color: {color};")
            b.clicked.connect(lambda _=False, ch=ch: self._run_clicked(ch))
            bar_ = QProgressBar()
            bar_.setTextVisible(False)
            bar_.setFixedHeight(8)
            bar_.setStyleSheet(f"QProgressBar {{ background: {theme.BG}; border: 1px solid {theme.BORDER};"
                               f" border-radius: 4px; }} QProgressBar::chunk {{ background: {color};"
                               f" border-radius: 3px; }}")
            state = label("idle", "dim")
            state.setMinimumWidth(320)
            row.addWidget(b)
            row.addWidget(bar_, 1)
            row.addWidget(state)
            layout.addLayout(row)
            self.run_btns[ch], self.progress[ch], self.state_labels[ch] = b, bar_, state
            self._running[ch] = False
        self.set_connected(False)

    # ------------------------------------------------------------------ table

    def add_row(self, duration: str = "00:01:00", transition: str = "jump", v: float | None = None,
                i: float | None = None, output: str = "keep", at: int | None = None):
        row = self.table.rowCount() if at is None else at
        self.table.blockSignals(True)
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(duration))
        transition_box = QComboBox()
        transition_box.addItems(profile.TRANSITIONS)
        transition_box.setCurrentText(profile.normalize_transition(transition))
        transition_box.currentTextChanged.connect(self._update_total)
        self.table.setCellWidget(row, 1, transition_box)
        for col, value in ((2, "" if v is None else f"{v:.2f}"), (3, "" if i is None else f"{i:.3f}")):
            item = QTableWidgetItem(value)
            item.setToolTip("empty = unchanged")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, col, item)
        out_box = QComboBox()
        out_box.addItems(profile.OUTPUTS)
        out_box.setCurrentText(output)
        out_box.currentTextChanged.connect(lambda _t, box=out_box: self._color_output(box))
        self._color_output(out_box)
        self.table.setCellWidget(row, 4, out_box)
        show = QPushButton("Show")
        show.clicked.connect(lambda _=False, btn=show: self.show_preview(self.table.indexAt(btn.pos()).row()))
        self.table.setCellWidget(row, 5, show)
        self.table.blockSignals(False)
        self._update_total()

    @staticmethod
    def _color_output(box: QComboBox):
        color = {"on": theme.ON, "off": theme.OFF}.get(box.currentText(), theme.TEXT)
        box.setStyleSheet(f"color: {color};")

    def remove_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)
        self._update_total()

    def _move(self, delta: int):
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        rows = self.rows()
        rows.insert(target, rows.pop(row))
        self.set_rows(rows)
        self.table.selectRow(target)

    def rows(self) -> list[dict]:
        """Raw table content (for settings.json), also when not all cells are valid."""
        out = []
        for r in range(self.table.rowCount()):
            text = lambda col: self.table.item(r, col).text().strip() if self.table.item(r, col) else ""
            out.append({"duration": text(0), "transition": self.table.cellWidget(r, 1).currentText(),
                        "v": text(2), "i": text(3), "output": self.table.cellWidget(r, 4).currentText()})
        return out

    def set_rows(self, rows: list[dict]):
        self.table.setRowCount(0)
        for r in rows:
            def num(key):
                try:
                    return profile.parse_value(r.get(key))
                except (TypeError, ValueError):
                    return None
            self.add_row(str(r.get("duration", "00:01:00")), r.get("transition") or r.get("mode") or "jump",
                         num("v"), num("i"), r.get("output", "keep"))

    def segments(self) -> list[Segment]:
        """Parsed segments; raises ValueError naming the bad row."""
        segments = []
        for n, r in enumerate(self.rows(), 1):
            try:
                segments.append(Segment(duration=profile.parse_duration(r["duration"]),
                                        transition=r["transition"], v=profile.parse_value(r["v"]),
                                        i=profile.parse_value(r["i"]), output=r["output"]))
            except ValueError as e:
                raise ValueError(f"Row {n}: {e}") from None
        return segments

    def _update_total(self, *_):
        try:
            total = profile.total_duration(self.segments())
            self.total_label.setText(f"{self.table.rowCount()} rows · total {profile.format_duration(total)}")
        except ValueError as e:
            self.total_label.setText(f"⚠ {e}")

    # ------------------------------------------------------------------ CSV / preview

    def load_csv(self):
        profile.PROFILE_DIR.mkdir(exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Load profile", str(profile.PROFILE_DIR), "CSV (*.csv)")
        if not path:
            return
        try:
            self.set_rows(profile.to_dicts(profile.load_csv(path)))
        except (OSError, KeyError, ValueError) as e:
            QMessageBox.warning(self, "Load profile", f"Could not load {path}:\n{e}")

    def save_csv(self):
        try:
            segments = self.segments()
        except ValueError as e:
            QMessageBox.warning(self, "Save profile", str(e))
            return
        profile.PROFILE_DIR.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save profile", str(profile.PROFILE_DIR / "profile.csv"),
                                              "CSV (*.csv)")
        if path:
            profile.save_csv(path, segments)

    def show_preview(self, highlight: int | None):
        try:
            segments = self.segments()
            profile.validate(segments)
        except ValueError as e:
            QMessageBox.warning(self, "Preview", str(e))
            return
        ProfilePreviewDialog(segments, highlight, parent=self).exec()

    # ------------------------------------------------------------------ run state

    def set_connected(self, connected: bool):
        for ch, b in self.run_btns.items():
            b.setEnabled(connected or self._running[ch])

    def _run_clicked(self, ch: int):
        if self._running[ch]:
            self.stop_requested.emit(ch)
            return
        try:
            segments = self.segments()
            profile.validate(segments)
        except ValueError as e:
            QMessageBox.warning(self, "Run profile", str(e))
            return
        self._totals[ch] = profile.total_duration(segments)
        self._counts[ch] = len(segments)
        self.run_requested.emit(ch, segments)

    def set_running(self, ch: int, running: bool, text: str = ""):
        self._running[ch] = running
        b = self.run_btns[ch]
        b.setText(f"■  Stop CH{ch}" if running else f"▶  Run on CH{ch}")
        b.setObjectName("danger" if running else "")
        b.setStyleSheet("" if running else f"color: {theme.CHANNEL_COLORS[ch]};")
        b.style().unpolish(b)
        b.style().polish(b)
        if running:
            self.progress[ch].setValue(0)
        if text:
            self.state_labels[ch].setText(text)

    def set_progress(self, ch: int, index: int, elapsed: float):
        total = self._totals.get(ch, 0.0)
        self.progress[ch].setValue(int(1000 * min(elapsed / total, 1.0)) if total else 1000)
        self.progress[ch].setMaximum(1000)
        n = self._counts.get(ch, 0)
        row = f"row {min(index + 1, n)}/{n}"
        self.state_labels[ch].setText(
            f"{row} · {profile.format_duration(elapsed)} / {profile.format_duration(total)}")
