"""Main window of the KA3305P control GUI."""

from __future__ import annotations

import os
import time

from PySide6.QtCore import QByteArray, QLocale, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from src.gui import settings
from src.gui.profile_panel import ProfilePanel
from src.gui.widgets import ChannelCard, PlotPanel, label
from src.gui.worker import DeviceWorker
from src.ka3305p import Measurement, find_ports
from src.profile import validate as validate_profile
from src.protocols import Protocol, Tracking

CH3_FIXED = (5.0, 3.0)


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 10, 14, 12)
    return frame, lay


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RND 320-KA3305P Control")
        self.resize(1400, 860)
        self.worker: DeviceWorker | None = None
        self.protocol: Protocol | None = None
        self._fill_spins = True
        self._any_output_on = False
        self._channel_on: dict[int, bool] = {}
        self._poll_times: list[float] = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(10)

        root.addWidget(self._build_connection_bar())

        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)

        # left: controls
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 4, 0)
        left_lay.setSpacing(10)
        left_lay.addWidget(self._build_global_card())
        self.cards = {1: ChannelCard(1), 2: ChannelCard(2), 3: ChannelCard(3, controllable=False, fixed=CH3_FIXED)}
        for c in self.cards.values():
            left_lay.addWidget(c)
        for ch in (1, 2):
            self.cards[ch].apply_setpoint.connect(self._set_setpoint)
            self.cards[ch].apply_protection.connect(self._set_protection)
            self.cards[ch].output_toggled.connect(self._set_channel_output)
        left_lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(420)
        body.addWidget(scroll)

        # right: plots + profile
        self.tabs = QTabWidget()
        self.plots = PlotPanel(fixed_ch3=CH3_FIXED)
        monitor = QWidget()
        mon_lay = QVBoxLayout(monitor)
        mon_lay.addWidget(self.plots)
        self.tabs.addTab(monitor, "Monitor")
        self.profile = ProfilePanel()
        self.profile.run_requested.connect(self._run_profile)
        self.profile.stop_requested.connect(lambda ch: self.worker and self.worker.stop_profile(ch))
        self._profile_segments: dict[int, list] = {}
        self.tabs.addTab(self.profile, "Profile")
        body.addWidget(self.tabs, 1)

        self.status_conn = QLabel("Disconnected")
        self.status_rate = QLabel("")
        self.statusBar().addWidget(self.status_conn)
        self.statusBar().addPermanentWidget(self.status_rate)

        self.redraw_timer = QTimer(self)
        self.redraw_timer.timeout.connect(self.plots.redraw)
        self.redraw_timer.start(250)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._all_off)

        self._set_connected(False)
        self._refresh_ports()
        self._restore_settings()

    # ================================================================== layout builders

    def _build_connection_bar(self) -> QFrame:
        frame, lay = card()
        row = QHBoxLayout()
        lay.addLayout(row)
        title = label("RND 320-KA3305P", "title")
        row.addWidget(title)
        row.addSpacing(18)

        row.addWidget(label("Port", "dim"))
        self.port_box = QComboBox()
        self.port_box.setMinimumWidth(110)
        row.addWidget(self.port_box)
        refresh = QPushButton("⟳")
        refresh.setToolTip("Rescan serial ports")
        refresh.setFixedWidth(34)
        refresh.clicked.connect(self._refresh_ports)
        row.addWidget(refresh)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setMinimumWidth(100)
        self.connect_btn.clicked.connect(self._toggle_connection)
        row.addWidget(self.connect_btn)
        self.idn_label = label("", "dim")
        row.addWidget(self.idn_label)
        row.addStretch()

        row.addWidget(label("Poll", "dim"))
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 60.0)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setSingleStep(0.1)
        self.interval_spin.setValue(0.5)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.setLocale(QLocale.c())
        self.interval_spin.valueChanged.connect(self._set_interval)
        row.addWidget(self.interval_spin)
        row.addSpacing(12)

        self.rec_btn = QPushButton("●  REC")
        self.rec_btn.setObjectName("rec")
        self.rec_btn.setCheckable(True)
        self.rec_btn.setToolTip("Log measurements to CSV in ./logs")
        self.rec_btn.toggled.connect(self._toggle_logging)
        row.addWidget(self.rec_btn)
        self.log_label = label("", "dim")
        self.log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.log_label)
        self.open_logs_btn = QPushButton("Open logs")
        self.open_logs_btn.clicked.connect(self._open_logs)
        row.addWidget(self.open_logs_btn)
        return frame

    def _build_global_card(self) -> QFrame:
        frame, lay = card()

        self.output_btn = QPushButton("OUTPUT  OFF")
        self.output_btn.setObjectName("outOff")
        self.output_btn.setMinimumHeight(46)
        self.output_btn.setToolTip("All outputs on/off (OUT). Esc = all off.")
        self.output_btn.clicked.connect(lambda: self._set_output(not self._any_output_on))
        lay.addWidget(self.output_btn)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        grid.addWidget(label("Mode", "dim"), 0, 0)
        self.track_box = QComboBox()
        self.track_box.addItems(["Independent", "Series", "Parallel"])
        self.track_box.activated.connect(self._set_tracking)
        grid.addWidget(self.track_box, 0, 1, 1, 3)

        # these states cannot be read back on V4.0 -> buttons show the last command sent
        self.ovp_btn = self._toggle("OVP", "Over-voltage protection (state not readable, shows last command)")
        self.ocp_btn = self._toggle("OCP", "Over-current protection (state not readable, shows last command)")
        self.beep_btn = self._toggle("Beep", "Beeper on/off (state not readable, shows last command)")
        self.lock_btn = self._toggle("Lock", "Lock front panel (state not readable, shows last command)")
        self.ovp_btn.toggled.connect(lambda on: self._job(lambda d: d.set_ovp(on)))
        self.ocp_btn.toggled.connect(lambda on: self._job(lambda d: d.set_ocp(on)))
        self.beep_btn.toggled.connect(lambda on: self._job(lambda d: d.set_beep(on)))
        self.lock_btn.toggled.connect(lambda on: self._job(lambda d: d.lock_panel() if on else d.unlock_panel()))
        for col, b in enumerate((self.ovp_btn, self.ocp_btn, self.beep_btn, self.lock_btn)):
            grid.addWidget(b, 1, col)

        grid.addWidget(label("Memory", "dim"), 2, 0)
        mem_row = QHBoxLayout()
        mem_row.setSpacing(4)
        self.mem_btns = []
        for m in range(1, 6):
            b = QPushButton(f"M{m}")
            b.setToolTip(f"Recall setpoints from memory {m}")
            b.setMinimumWidth(38)
            b.setStyleSheet("padding: 5px 4px;")
            b.clicked.connect(lambda _=False, m=m: self._recall(m))
            mem_row.addWidget(b)
            self.mem_btns.append(b)
        self.save_btn = QPushButton("Save…")
        self.save_btn.setToolTip("Store current setpoints into a memory slot")
        self.save_btn.clicked.connect(self._save_memory)
        mem_row.addWidget(self.save_btn)
        grid.addLayout(mem_row, 2, 1, 1, 3)
        lay.addLayout(grid)
        return frame

    @staticmethod
    def _toggle(text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(True)
        b.setToolTip(tip)
        return b

    # ================================================================== connection

    def _refresh_ports(self):
        current = self.port_box.currentText()
        self.port_box.clear()
        self.port_box.addItems(find_ports())
        if current:
            self.port_box.setCurrentText(current)

    def _toggle_connection(self):
        if self.worker:
            self.worker.stop()
            self.connect_btn.setEnabled(False)
            return
        port = self.port_box.currentText()
        if not port:
            return
        self.worker = DeviceWorker(port, self.interval_spin.value())
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.measured.connect(self._on_measurement)
        self.worker.setpoints.connect(self._on_setpoints)
        self.worker.protection.connect(self._on_protection)
        self.worker.logging_changed.connect(self._on_logging_changed)
        self.worker.error.connect(self._on_error)
        self.worker.profile_started.connect(self._on_profile_started)
        self.worker.profile_progress.connect(self.profile.set_progress)
        self.worker.profile_finished.connect(self._on_profile_finished)
        self.connect_btn.setEnabled(False)
        self.status_conn.setText(f"Connecting to {port}…")
        self.worker.start()

    def _on_connected(self, idn: str, protocol: Protocol):
        self.protocol = protocol
        self._fill_spins = True
        self.idn_label.setText(f"{idn}   ·   protocol {protocol.name}")
        self.status_conn.setText(f"Connected · {self.worker.port}")
        self._set_connected(True)
        per_channel = protocol.supports("output_channel")
        for ch in (1, 2):
            self.cards[ch].set_output_controls(per_channel)
        self.lock_btn.setEnabled(protocol.supports("lock"))
        self._apply_toggles()
        if self.rec_btn.isChecked():
            self.worker.start_logging()

    def _on_disconnected(self):
        self.worker.wait()
        self.worker = None
        self.protocol = None
        self.idn_label.setText("")
        self.status_conn.setText("Disconnected")
        self.status_rate.setText("")
        self._set_connected(False)

    def _set_connected(self, connected: bool):
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.port_box.setEnabled(not connected)
        for w in (self.output_btn, self.track_box, self.ovp_btn, self.ocp_btn, self.beep_btn,
                  self.lock_btn, self.save_btn, *self.mem_btns):
            w.setEnabled(connected)
        for ch in (1, 2):
            self.cards[ch].set_connected(connected)
        self.profile.set_connected(connected)
        if not connected:
            self._show_output(False)

    # ================================================================== device callbacks

    def _on_measurement(self, m: Measurement):
        for ch in (1, 2):
            self.cards[ch].update_measurement(m.voltage[ch], m.current[ch], m.status.cv[ch], m.status.output[ch])
        self._show_output(any(m.status.output.values()))
        self._channel_on = dict(m.status.output)
        if m.status.tracking is not None:
            self.track_box.setCurrentIndex(int(m.status.tracking))
            self.cards[1].set_slave(m.status.tracking != Tracking.INDEPENDENT)
        self.plots.add(m.t, m.voltage, m.current)

        self._poll_times = [t for t in self._poll_times if m.t - t < 5.0] + [m.t]
        if len(self._poll_times) > 1:
            rate = (len(self._poll_times) - 1) / (self._poll_times[-1] - self._poll_times[0])
            self.status_rate.setText(f"{rate:.1f} samples/s")

    def _on_setpoints(self, sp: dict[int, tuple[float, float]]):
        for ch, (v, i) in sp.items():
            self.cards[ch].update_setpoint(v, i, self._fill_spins)
        self._fill_spins = False

    def _on_protection(self, levels: dict[int, tuple[float, float]]):
        for ch, (ovp, ocp) in levels.items():
            self.cards[ch].update_protection(ovp, ocp)

    def _on_logging_changed(self, path: str):
        self.log_label.setText(os.path.basename(path) if path else "")
        self.log_label.setToolTip(path)

    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"⚠ {msg}", 6000)
        if not self.worker or not self.worker.dev:
            QMessageBox.warning(self, "Connection", msg)

    def _show_output(self, on: bool):
        self._any_output_on = on
        self.output_btn.setText("OUTPUT  ON" if on else "OUTPUT  OFF")
        self.output_btn.setObjectName("outOn" if on else "outOff")
        self.output_btn.style().unpolish(self.output_btn)
        self.output_btn.style().polish(self.output_btn)

    # ================================================================== commands (run in worker thread)

    def _job(self, fn):
        if self.worker:
            self.worker.submit(fn)

    def _set_setpoint(self, ch: int, v: float, i: float):
        def job(dev):
            dev.set_voltage(ch, v)
            dev.set_current(ch, i)
            self.worker._read_setpoints()
        self._job(job)

    def _set_protection(self, ch: int, ovp: float, ocp: float):
        def job(dev):
            dev.set_ovp_level(ch, ovp)
            dev.set_ocp_level(ch, ocp)
            self.worker._read_protection()
        self._job(job)

    def _set_output(self, on: bool):
        self._job(lambda dev: dev.set_output(on))

    def _set_channel_output(self, ch: int, on: bool):
        self._job(lambda dev: dev.set_channel_output(ch, on))

    def _all_off(self):
        if self.worker:
            self.worker.stop_all_profiles()
        self._set_output(False)
        self.statusBar().showMessage("All outputs off (Esc)", 3000)

    def _set_tracking(self, index: int):
        def job(dev):
            dev.set_tracking(index)
            self.worker._read_setpoints()
        self._job(job)

    def _recall(self, mem: int):
        def job(dev):
            dev.recall(mem)
            time.sleep(0.2)
            self.worker._read_setpoints()
        self._fill_spins = True
        self._job(job)

    def _save_memory(self):
        items = [f"M{m}" for m in range(1, 6)]
        item, ok = QInputDialog.getItem(self, "Save setpoints", "Overwrite memory slot:", items, 0, False)
        if ok:
            mem = int(item[1:])
            self._job(lambda dev: dev.save(mem))

    def _set_interval(self, value: float):
        if self.worker:
            self.worker.interval = value

    # ================================================================== profiles

    def _run_profile(self, ch: int, segments: list):
        if not (self.worker and self.protocol):
            return
        try:
            validate_profile(segments, self.protocol.v_max, self.protocol.i_max)
        except ValueError as e:
            QMessageBox.warning(self, "Run profile", str(e))
            return
        if not self._channel_on.get(ch, False) and not any(s.output == "on" for s in segments):
            box = QMessageBox(QMessageBox.Icon.Question, "Run profile",
                              f"CH{ch} output is off and no row switches it on, so the profile would only "
                              "change setpoints without any output.", parent=self)
            switch_on = box.addButton("Switch on at start", QMessageBox.ButtonRole.AcceptRole)                 if segments[0].output == "keep" else None
            box.addButton("Run anyway", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is cancel:
                return
            if box.clickedButton() is switch_on:
                segments[0].output = "on"
        self._profile_segments[ch] = segments
        if not self.rec_btn.isChecked():
            self.rec_btn.setChecked(True)       # a profile run is always logged
        self.worker.start_profile(ch, segments)

    def _on_profile_started(self, ch: int, t0: float, v0: float, i0: float):
        self.profile.set_running(ch, True, f"started from {v0:.2f} V / {i0:.3f} A")
        self.cards[ch].set_profile_running(True)
        self.plots.show_plan(ch, t0, self._profile_segments[ch], v0, i0)

    def _on_profile_finished(self, ch: int, reason: str):
        text = {"done": "done — holding last values", "stopped": "stopped — holding current values"}.get(reason, reason)
        self.profile.set_running(ch, False, text)
        self.cards[ch].set_profile_running(False)
        self.statusBar().showMessage(f"CH{ch} profile {text}", 6000)

    # ================================================================== logging

    def _toggle_logging(self, on: bool):
        if self.worker and self.worker.dev:
            self.worker.start_logging() if on else self.worker.stop_logging()

    def _open_logs(self):
        from src.datalog import LOG_DIR
        LOG_DIR.mkdir(exist_ok=True)
        os.startfile(LOG_DIR)

    # ================================================================== close

    # ================================================================== settings

    def _toggle_buttons(self) -> dict[str, QPushButton]:
        return {"ovp": self.ovp_btn, "ocp": self.ocp_btn, "beep": self.beep_btn, "lock": self.lock_btn}

    def _restore_settings(self):
        s = settings.load()
        if s["port"] and self.port_box.findText(s["port"]) >= 0:
            self.port_box.setCurrentText(s["port"])
        self.interval_spin.setValue(s["poll_interval_s"])
        if s["window_geometry"]:
            self.restoreGeometry(QByteArray.fromBase64(s["window_geometry"].encode()))
        self.plots.restore(s["plot"])
        for key, btn in self._toggle_buttons().items():
            btn.blockSignals(True)          # restore display only; sent to the device on connect
            btn.setChecked(s["toggles"][key])
            btn.blockSignals(False)
        self.profile.set_rows(s["profile"])

    def _save_settings(self):
        settings.save({
            "port": self.port_box.currentText(),
            "poll_interval_s": self.interval_spin.value(),
            "window_geometry": self.saveGeometry().toBase64().data().decode(),
            "plot": self.plots.state(),
            "toggles": {key: btn.isChecked() for key, btn in self._toggle_buttons().items()},
            "profile": self.profile.rows(),
        })

    def _apply_toggles(self):
        """OVP/OCP/beep/lock can't be read back, so push the remembered state to the device."""
        ovp, ocp, beep, lock = (b.isChecked() for b in self._toggle_buttons().values())

        def job(dev):
            dev.set_ovp(ovp)
            dev.set_ocp(ocp)
            dev.set_beep(beep)
            if dev.supports("lock"):
                dev.lock_panel() if lock else dev.unlock_panel()
        self._job(job)

    def closeEvent(self, event):
        if self.worker and self._any_output_on:
            answer = QMessageBox.question(
                self, "Outputs are on", "Switch all outputs off before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Yes:
                self._set_output(False)
        if self.worker:
            self.worker.disconnected.disconnect()
            self.worker.stop()
            self.worker.wait(3000)
        self._save_settings()
        event.accept()
