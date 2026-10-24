"""Firmware-specific command sets for the RND 320-KA3305P / Korad KA3305P.

Every firmware version gets one `Protocol` object holding its command templates,
its limits and its STATUS? decoder. The driver only talks through a protocol,
so supporting another firmware means adding one entry to `PROTOCOLS`.

How to add a version:
    1. Run `*IDN?` on the device, note the version (e.g. "V5.10").
    2. Copy the closest protocol with `dataclasses.replace(...)`, then add,
       drop or change command templates / the status decoder.
    3. Register it in `PROTOCOLS` under the version string.

Templates are plain `str.format` strings without the trailing CR; the driver adds it.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import Callable


class NotSupportedError(RuntimeError):
    """The command does not exist in the device's firmware protocol."""


class Tracking(IntEnum):
    INDEPENDENT = 0
    SERIES = 1
    PARALLEL = 2


@dataclass(frozen=True)
class Status:
    raw: int
    cv: dict[int, bool]           # channel -> True = CV, False = CC
    output: dict[int, bool]       # channel -> output on
    tracking: Tracking | None     # None if the firmware does not report it


@dataclass(frozen=True)
class Protocol:
    name: str
    commands: dict[str, str]
    decode_status: Callable[[int], Status]
    channels: tuple[int, ...] = (1, 2)
    v_max: float = 30.0
    i_max: float = 5.0
    v_decimals: int = 2
    i_decimals: int = 3
    memories: tuple[int, ...] = (1, 2, 3, 4, 5)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def supports(self, key: str) -> bool:
        return key in self.commands

    def cmd(self, key: str, **kwargs) -> str:
        try:
            template = self.commands[key]
        except KeyError:
            raise NotSupportedError(f"'{key}' is not available in protocol {self.name}") from None
        return template.format(**kwargs)


# --------------------------------------------------------------------------- status decoders

def _status_v4(raw: int) -> Status:
    # Verified on V4.0 hardware (2026-10-24):
    #   bit 0/1: CH1/CH2 1=CV 0=CC, bit 2-3: tracking (00 indep, 01 series, 10 parallel),
    #   bit 6/7: CH1/CH2 output on. Bits 4/5 (OVP/OCP per V5.10 manual) did not react to OVP1/OCP1.
    track_bits = (raw >> 2) & 0b11
    tracking = {0b00: Tracking.INDEPENDENT, 0b01: Tracking.SERIES, 0b10: Tracking.PARALLEL}.get(track_bits)
    return Status(
        raw=raw,
        cv={1: bool(raw & 0x01), 2: bool(raw & 0x02)},
        output={1: bool(raw & 0x40), 2: bool(raw & 0x80)},
        tracking=tracking,
    )


def _status_v2(raw: int) -> Status:
    # Korad KA3000 manual V2.0: bit 0/1 CV/CC, bit 6 common output, rest undefined.
    on = bool(raw & 0x40)
    return Status(raw=raw, cv={1: bool(raw & 0x01), 2: bool(raw & 0x02)},
                  output={1: on, 2: on}, tracking=None)


# --------------------------------------------------------------------------- command sets

_BASE_COMMANDS = {
    "idn":               "*IDN?",
    "status":            "STATUS?",
    "set_voltage":       "VSET{ch}:{value:.2f}",
    "set_current":       "ISET{ch}:{value:.3f}",
    "get_voltage_set":   "VSET{ch}?",
    "get_current_set":   "ISET{ch}?",
    "get_voltage_out":   "VOUT{ch}?",
    "get_current_out":   "IOUT{ch}?",
    "output":            "OUT{on:d}",
    "beep":              "BEEP{on:d}",
    "recall":            "RCL{mem:d}",
    "save":              "SAV{mem:d}",
    "ocp":               "OCP{on:d}",
    "ovp":               "OVP{on:d}",
    "track":             "TRACK{mode:d}",
}

_V4_EXTRA = {
    "lock":              "LOCK{on:d}",
    "output_channel":    "OUTCH{ch}:{on:d}",
    "set_ocp":           "OCPSET{ch}:{value:.3f}",
    "set_ovp":           "OVPSET{ch}:{value:.2f}",
    "get_ocp":           "OCPSET{ch}?",
    "get_ovp":           "OVPSET{ch}?",
    "set_voltage_step":  "VSTEP{ch}:{value:.2f}",
    "voltage_up":        "VUP{ch}",
    "voltage_down":      "VDOWN{ch}",
    "set_current_step":  "ISTEP{ch}:{value:.3f}",
    "current_up":        "IUP{ch}",
    "current_down":      "IDOWN{ch}",
    "voltage_autostep":  "VASTEP{ch}:{start},{stop},{step},{dwell}",
    "voltage_autostop":  "VASTOP{ch}",
    "current_autostep":  "IASTEP{ch}:{start},{stop},{step},{dwell}",
    "current_autostop":  "IASTOP{ch}",
}

V4_0 = Protocol(
    name="V4.0",
    commands=_BASE_COMMANDS | _V4_EXTRA,
    decode_status=_status_v4,
    notes=(
        "Tested on RND 320-KA3305P V4.0 SN:05243251.",
        "BEEP/LOCK/OVP/OCP are accepted but their state is not visible in STATUS?. BEEP, OVP and OCP confirmed working.",
        "CH3 (fixed 5 V / 3 A) is not reachable via the interface.",
        "Unknown commands are silently ignored (no reply).",
    ),
)

# Per RND manual "Remote Control Syntax V5.10" - same command list as observed on V4.0.
# Untested on hardware; adjust once a V5.10 unit shows differences.
V5_10 = replace(V4_0, name="V5.10", notes=("From RND manual V5.10, not hardware-tested.",))

# Per Korad KA3000 series manual "Remote Control Syntax V2.0". Untested on hardware.
V2_0 = Protocol(
    name="V2.0",
    commands=dict(_BASE_COMMANDS),
    decode_status=_status_v2,
    notes=("From Korad KA3000 manual V2.0, not hardware-tested.",),
)

PROTOCOLS: dict[str, Protocol] = {
    "2.0": V2_0,
    "4.0": V4_0,
    "5.10": V5_10,
}
DEFAULT_PROTOCOL = V4_0


def protocol_for_idn(idn: str) -> Protocol:
    """Pick the protocol from an *IDN? string like 'RND 320-KA3305P V4.0 SN:05243251'."""
    match = re.search(r"\bV(\d+\.\d+)\b", idn)
    if match and match.group(1) in PROTOCOLS:
        return PROTOCOLS[match.group(1)]
    warnings.warn(f"Unknown firmware in IDN {idn!r}, falling back to {DEFAULT_PROTOCOL.name}")
    return DEFAULT_PROTOCOL
