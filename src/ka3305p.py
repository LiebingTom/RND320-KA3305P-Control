"""Driver for the RND 320-KA3305P (Korad KA3305P) lab power supply.

Serial settings (manual p. 10): 9600 baud, 8N1, no flow control, commands end with CR,
replies end with LF. The USB port enumerates as a CDC serial device (VID 0416, PID 5011).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from src.protocols import DEFAULT_PROTOCOL, Protocol, Status, Tracking, protocol_for_idn

log = logging.getLogger(__name__)

USB_VID_PID = (0x0416, 0x5011)


class KA3305PError(IOError):
    """Communication with the device failed (no or malformed reply)."""


@dataclass(frozen=True)
class Measurement:
    t: float                      # time.time() of the reading
    voltage: dict[int, float]     # channel -> measured V
    current: dict[int, float]     # channel -> measured A
    status: Status


def find_ports() -> list[str]:
    """Serial ports, KA3305P-like USB devices first."""
    ports = list(list_ports.comports())
    ports.sort(key=lambda p: (p.vid, p.pid) != USB_VID_PID)
    return [p.device for p in ports]


class KA3305P:
    WRITE_DELAY = 0.05   # s, pause after a set command so the device can process it

    def __init__(self, port: str = "COM1", protocol: Protocol | None = None, timeout: float = 0.5):
        """Open the port and pick the protocol from *IDN? unless one is given explicitly."""
        self.port = port
        self.timeout = timeout
        self.ser: serial.Serial | None = None
        self.idn = ""
        self.protocol = protocol or DEFAULT_PROTOCOL
        self._lock = threading.RLock()   # serialises access when used from several threads

        self.connect()
        self.idn = self.identify()
        if protocol is None:
            self.protocol = protocol_for_idn(self.idn)
        log.info("Connected to %s on %s, protocol %s", self.idn, port, self.protocol.name)

    # ------------------------------------------------------------------ connection

    def connect(self):
        """Open serial connection to the KA3305P."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def disconnect(self):
        """Close the serial connection."""
        with self._lock:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = None

    def is_connected(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.disconnect()

    # ------------------------------------------------------------------ low level

    def send(self, cmd: str):
        """Send one command (CR is appended)."""
        with self._lock:
            log.debug(">> %s", cmd)
            self.ser.write(f"{cmd}\r".encode("ascii"))
            time.sleep(self.WRITE_DELAY)

    def query(self, cmd: str) -> str:
        """Send a query and return the reply line without LF."""
        with self._lock:
            self.ser.reset_input_buffer()
            self.ser.write(f"{cmd}\r".encode("ascii"))
            reply = self.ser.readline()
        log.debug("<< %s -> %r", cmd, reply)
        if not reply.endswith(b"\n"):
            raise KA3305PError(f"No reply to {cmd!r} (got {reply!r})")
        return reply.decode("ascii").strip()

    def query_float(self, cmd: str) -> float:
        reply = self.query(cmd)
        try:
            return float(reply)
        except ValueError:
            raise KA3305PError(f"Unexpected reply to {cmd!r}: {reply!r}") from None

    def _send_key(self, key: str, **kwargs):
        self.send(self.protocol.cmd(key, **kwargs))

    def _check_channel(self, ch: int):
        if ch not in self.protocol.channels:
            raise ValueError(f"Channel {ch} is not remote-controllable (valid: {self.protocol.channels})")

    def _check_range(self, value: float, vmax: float, unit: str):
        if not 0 <= value <= vmax:
            raise ValueError(f"{value} {unit} out of range 0..{vmax} {unit}")

    def supports(self, key: str) -> bool:
        return self.protocol.supports(key)

    # ------------------------------------------------------------------ identification / status

    def identify(self) -> str:
        return self.query(self.protocol.cmd("idn"))

    def status(self) -> Status:
        """STATUS? replies with one raw byte + LF; the byte itself may be 0x0A, so read 2 bytes."""
        with self._lock:
            self.ser.reset_input_buffer()
            self.ser.write(f"{self.protocol.cmd('status')}\r".encode("ascii"))
            reply = self.ser.read(2)
        if len(reply) != 2 or reply[1:] != b"\n":
            raise KA3305PError(f"Bad STATUS? reply {reply!r}")
        return self.protocol.decode_status(reply[0])

    def measure(self) -> Measurement:
        """Read measured V and I of all channels plus status (about 60 ms)."""
        voltage, current = {}, {}
        with self._lock:
            t = time.time()
            for ch in self.protocol.channels:
                voltage[ch] = self.read_voltage(ch)
                current[ch] = self.read_current(ch)
            status = self.status()
        return Measurement(t=t, voltage=voltage, current=current, status=status)

    # ------------------------------------------------------------------ setpoints

    def set_voltage(self, ch: int, value: float):
        self._check_channel(ch)
        self._check_range(value, self.protocol.v_max, "V")
        self._send_key("set_voltage", ch=ch, value=value)

    def set_current(self, ch: int, value: float):
        self._check_channel(ch)
        self._check_range(value, self.protocol.i_max, "A")
        self._send_key("set_current", ch=ch, value=value)

    def get_voltage_setting(self, ch: int) -> float:
        self._check_channel(ch)
        return self.query_float(self.protocol.cmd("get_voltage_set", ch=ch))

    def get_current_setting(self, ch: int) -> float:
        self._check_channel(ch)
        return self.query_float(self.protocol.cmd("get_current_set", ch=ch))

    def read_voltage(self, ch: int) -> float:
        self._check_channel(ch)
        return self.query_float(self.protocol.cmd("get_voltage_out", ch=ch))

    def read_current(self, ch: int) -> float:
        self._check_channel(ch)
        return self.query_float(self.protocol.cmd("get_current_out", ch=ch))

    # ------------------------------------------------------------------ outputs

    def enable_output(self):
        """Switch all outputs on (OUT1)."""
        self._send_key("output", on=1)

    def disable_output(self):
        """Switch all outputs off (OUT0)."""
        self._send_key("output", on=0)

    def set_output(self, on: bool):
        self._send_key("output", on=on)

    def set_channel_output(self, ch: int, on: bool):
        """Switch a single channel (OUTCH, not on all firmwares)."""
        self._check_channel(ch)
        self._send_key("output_channel", ch=ch, on=on)

    # ------------------------------------------------------------------ protection

    def set_ocp(self, on: bool):
        """Over-current protection on/off (applies to both channels)."""
        self._send_key("ocp", on=on)

    def set_ovp(self, on: bool):
        """Over-voltage protection on/off (applies to both channels)."""
        self._send_key("ovp", on=on)

    def set_ocp_level(self, ch: int, value: float):
        self._check_channel(ch)
        self._check_range(value, self.protocol.i_max * 1.02, "A")
        self._send_key("set_ocp", ch=ch, value=value)

    def set_ovp_level(self, ch: int, value: float):
        self._check_channel(ch)
        self._check_range(value, self.protocol.v_max * 1.04, "V")
        self._send_key("set_ovp", ch=ch, value=value)

    def get_ocp_level(self, ch: int) -> float:
        self._check_channel(ch)
        return self.query_float(self.protocol.cmd("get_ocp", ch=ch))

    def get_ovp_level(self, ch: int) -> float:
        self._check_channel(ch)
        return self.query_float(self.protocol.cmd("get_ovp", ch=ch))

    # ------------------------------------------------------------------ panel / modes

    def lock_panel(self):
        self._send_key("lock", on=1)

    def unlock_panel(self):
        self._send_key("lock", on=0)

    def set_beep(self, on: bool):
        self._send_key("beep", on=on)

    def set_tracking(self, mode: Tracking | int):
        """0 independent, 1 series, 2 parallel. In series/parallel CH2 is master."""
        self._send_key("track", mode=int(Tracking(mode)))

    def recall(self, mem: int):
        """Load setpoints from memory M1..M5."""
        if mem not in self.protocol.memories:
            raise ValueError(f"Memory {mem} not in {self.protocol.memories}")
        self._send_key("recall", mem=mem)

    def save(self, mem: int):
        """Store current setpoints into memory M1..M5 (overwrites it)."""
        if mem not in self.protocol.memories:
            raise ValueError(f"Memory {mem} not in {self.protocol.memories}")
        self._send_key("save", mem=mem)

    # ------------------------------------------------------------------ manual / automatic stepping

    def set_voltage_step(self, ch: int, value: float):
        self._check_channel(ch)
        self._send_key("set_voltage_step", ch=ch, value=value)

    def voltage_up(self, ch: int):
        self._check_channel(ch)
        self._send_key("voltage_up", ch=ch)

    def voltage_down(self, ch: int):
        self._check_channel(ch)
        self._send_key("voltage_down", ch=ch)

    def set_current_step(self, ch: int, value: float):
        self._check_channel(ch)
        self._send_key("set_current_step", ch=ch, value=value)

    def current_up(self, ch: int):
        self._check_channel(ch)
        self._send_key("current_up", ch=ch)

    def current_down(self, ch: int):
        self._check_channel(ch)
        self._send_key("current_down", ch=ch)

    def voltage_autostep(self, ch: int, start: float, stop: float, step: float, dwell: float):
        """Device-internal voltage ramp: start..stop in `step` V every `dwell` s."""
        self._check_channel(ch)
        self._send_key("voltage_autostep", ch=ch, start=start, stop=stop, step=step, dwell=dwell)

    def voltage_autostop(self, ch: int):
        self._check_channel(ch)
        self._send_key("voltage_autostop", ch=ch)

    def current_autostep(self, ch: int, start: float, stop: float, step: float, dwell: float):
        """Device-internal current ramp: start..stop in `step` A every `dwell` s."""
        self._check_channel(ch)
        self._send_key("current_autostep", ch=ch, start=start, stop=stop, step=step, dwell=dwell)

    def current_autostop(self, ch: int):
        self._check_channel(ch)
        self._send_key("current_autostop", ch=ch)
