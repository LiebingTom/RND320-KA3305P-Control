# RND320-KA3305P-Control

Python driver and Qt GUI for the RND 320-KA3305P (Korad KA3305P clone) lab power supply.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_gui.py          # or: python -m src.gui
```

The USB port shows up as a plain CDC serial port (VID 0416 / PID 5011), no driver needed.

## Structure

| File | Content |
|---|---|
| `src/protocols.py` | Command sets per firmware version + STATUS? decoder |
| `src/ka3305p.py` | `KA3305P` driver class (thread-safe) |
| `src/datalog.py` | CSV logger (`logs/`) |
| `src/profile.py` | Profile segments, timing math, CSV load/save |
| `src/gui/` | PySide6 + pyqtgraph GUI; serial I/O runs in `worker.py` thread |
| `datasheets/` | Manuals and datasheets: download links in [`datasheets/README.md`](datasheets/README.md) (PDFs git-ignored) |
| `settings.json` | GUI state (port, poll rate, plot view, OVP/OCP/beep/lock, profile), git-ignored |

```python
from src.ka3305p import KA3305P

with KA3305P("COM10") as psu:
    psu.set_voltage(1, 3.3)
    psu.set_current(1, 0.5)
    psu.set_channel_output(1, True)
    print(psu.measure())
```

## Profiles

The Profile tab runs a sequence of rows on one channel (`▶ Run on CH1` / `▶ Run on CH2`;
both channels can run at the same time, each with a snapshot of the table at start).

| Column | Meaning |
|---|---|
| Duration | `hh:mm:ss`, `mm:ss` or seconds |
| Transition | `jump`: change V/I at the row start and hold · `ramp`: linear from the previous values to V/I |
| V / I | target setpoints, always moved together; empty = unchanged (e.g. ramp only V) |
| Output | `keep` / `on` / `off`, applied at the row start (after the setpoints) |
| Show | preview of the whole profile with that row highlighted |

- The first row starts from the channel's setpoints at run start; after the last row the values are held.
- The output is only switched by rows with `on`/`off`. If the channel is off and no row switches it on,
  Run asks first ("Switch on at start" / "Run anyway" / Cancel).
- Ramps are executed in software (setpoint update when the 10 mV / 1 mA rounded value changes, at most every 0.2 s).
- Running a profile starts REC automatically; the CSV gets a `profileN_row` column. The planned curve is
  drawn dashed in the monitor plots. Esc stops all profiles and switches all outputs off.
- Profiles can be saved/loaded as CSV (`profiles/`, columns `duration,transition,voltage_V,current_A,output`).

## Firmware versions

The firmware is detected from `*IDN?`. To support a new version, add a `Protocol`
to `PROTOCOLS` in `src/protocols.py` (copy the closest one with `dataclasses.replace`).

| Version | Source | Tested |
|---|---|---|
| V4.0 | RND manual V5.10 + hardware test | yes (SN 05243251) |
| V5.10 | RND manual | no |
| V2.0 | Korad KA3000 manual | no |

## Findings on V4.0

- Replies end with `\n`, query latency ~10 ms, full measurement (V/I both channels + status) ~70 ms.
- `*IDN?` works, `*DIN?` (manual typo) does not. Unknown commands are silently ignored.
- `STATUS?` returns one raw byte + `\n`:
  bit 0/1 CH1/CH2 CV(1)/CC(0), bit 2-3 tracking (00 indep, 01 series, 10 parallel), bit 6/7 CH1/CH2 output.
- `OUTCH`, `OCPSET/OVPSET` (set + query), `VSTEP/VUP/VDOWN`, `ISTEP/IUP/IDOWN`, `VASTEP/VASTOP` work.
- `BEEP`, `LOCK`, `OVP`, `OCP` are accepted, but their state is not readable via `STATUS?`
  (GUI buttons show the last command sent, stored in `settings.json` and re-sent on connect).
  `BEEP`, `OVP`, `OCP` confirmed working.
- CH3 (fixed 5 V / 3 A) is not reachable over the interface.
