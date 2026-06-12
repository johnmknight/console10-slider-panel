# console10_slider.py - host-side reader for the Console10 Slider.
#
# Opens the QT Py's USB *data* serial port and yields the slider readings the
# firmware streams (one JSON object per line). This is the inbound mirror of
# console10-oled-panel's Console10Screen; keep it tiny so any host app (an MQTT
# bridge, a WLED controller, a logger) can import it.
#
# Requires: pyserial  (pip install pyserial)

import json
import time
from collections import OrderedDict
import concurrent.futures as _futures

import serial                       # pyserial
from serial.tools import list_ports

ADAFRUIT_VID = 0x239A


class Console10Slider:
    """A connection to one Console10 Slider over USB serial."""

    def __init__(self, port, baudrate=115200, timeout=1.0):
        """port: serial device, e.g. 'COM7' (Windows) or '/dev/ttyACM1' (Linux).

        Point this at the firmware's DATA channel - the second serial port the
        board exposes once boot.py has enabled it (see find_ports()).
        """
        self._ser = serial.Serial(port, baudrate, timeout=timeout)

    def readings(self):
        """Yield each slider reading as a dict: {"value", "pct", "raw"}.

        Blocks on the serial port. Non-JSON lines (only seen on the console
        fallback channel, where firmware log output shares the wire) are skipped.
        """
        while True:
            raw_line = self._ser.readline()
            if not raw_line:
                continue  # read timeout - just keep waiting
            text = raw_line.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except ValueError:
                continue  # skip log noise / partial lines
            if isinstance(obj, dict) and "value" in obj:
                yield obj

    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def find_ports():
    """Return [(device, description), ...] for likely Console10 Slider ports.

    A QT Py running the firmware exposes TWO serial ports (console + data). This
    lists Adafruit ports; the DATA channel is usually the higher-numbered one.
    """
    found = []
    for p in list_ports.comports():
        is_adafruit = (p.vid == ADAFRUIT_VID) or (
            p.manufacturer and "Adafruit" in p.manufacturer
        )
        if is_adafruit:
            found.append((p.device, p.description))
    return found


def pick_data_port():
    """Best-guess the data port: the higher-numbered Adafruit COM port.

    Single-board heuristic kept for back-compat. For multiple boards use
    discover_faders(), which is robust because it probes for the channel that
    actually emits fader JSON instead of guessing by COM number.
    """
    devs = [d for d, _ in find_ports()]
    if not devs:
        return None
    return sorted(devs, key=_com_num)[-1]


# --- multi-device discovery -------------------------------------------------
# A QT Py running the firmware exposes TWO CDC ports (console + data) that share
# ONE USB serial_number; only the DATA channel emits fader JSON. To support
# several faders on one host we group ports by serial_number and probe each
# board's ports to find the one that answers - far more robust than the
# "highest COM" guess, which collapses with more than one board.

def _com_num(dev):
    """Sort key: COMx on Windows, /dev/ttyACMx on Linux -> trailing integer."""
    digits = "".join(ch for ch in dev if ch.isdigit())
    return int(digits) if digits else 0


def _uid_from_serial(sn):
    """Fallback device id from the board's stable USB serial (last 6 hex).

    Used only for firmware that predates the emitted id; the firmware-supplied
    id is always preferred so it matches the chip uid the board reports.
    """
    hexchars = "".join(c for c in (sn or "") if c in "0123456789abcdefABCDEF")
    return (hexchars[-6:] or "000000").lower()


def _adafruit_ports():
    """[(device, serial_number, description), ...] for Adafruit USB serial ports."""
    out = []
    for p in list_ports.comports():
        is_adafruit = (p.vid == ADAFRUIT_VID) or (
            p.manufacturer and "Adafruit" in p.manufacturer
        )
        if is_adafruit:
            out.append((p.device, p.serial_number, p.description))
    return out


def _probe_uid(port, baudrate=115200, timeout=6.0):
    """Open `port` briefly; identify whether it's a fader DATA channel.

    Returns:
      - the device id string  if the firmware emits one (boot `hello` or a value line);
      - ""                    if it IS a data channel but the firmware predates the id;
      - None                  if nothing fader-shaped arrives (console channel / no board).
    `timeout` must exceed the firmware heartbeat so an idle slider still answers.
    """
    try:
        ser = serial.Serial(port, baudrate, timeout=0.3)
    except (OSError, serial.SerialException):
        return None
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            try:
                obj = json.loads(raw.decode("utf-8", "replace").strip())
            except ValueError:
                continue
            if isinstance(obj, dict) and ("value" in obj or obj.get("hello")):
                return str(obj.get("id", ""))   # "" -> data channel, pre-id firmware
    finally:
        try:
            ser.close()
        except Exception:
            pass
    return None


def discover_faders(baudrate=115200, probe_timeout=6.0):
    """Find every connected fader's DATA port + device id.

    Returns [(data_port, uid, serial_number), ...]. Probes all candidate ports
    in parallel so discovery takes ~one heartbeat regardless of how many boards
    are plugged in.
    """
    groups = OrderedDict()
    for dev, sn, _desc in _adafruit_ports():
        groups.setdefault(sn, []).append(dev)

    all_ports = [d for devs in groups.values() for d in devs]
    if not all_ports:
        return []

    uids = {}
    with _futures.ThreadPoolExecutor(max_workers=len(all_ports)) as ex:
        futs = {ex.submit(_probe_uid, d, baudrate, probe_timeout): d for d in all_ports}
        for fut in _futures.as_completed(futs):
            d = futs[fut]
            try:
                uids[d] = fut.result()
            except Exception:
                uids[d] = None

    faders = []
    for sn, devs in groups.items():
        # Only boards whose data channel actually emits fader JSON count - this
        # ignores other Adafruit boards on the bus (e.g. the OLED-panel QT Py).
        # A "" answer means a data channel on pre-id firmware -> fall back to the
        # stable USB-serial-derived id.
        hit = next(
            ((d, uids[d]) for d in sorted(devs, key=_com_num, reverse=True) if uids.get(d) is not None),
            None,
        )
        if hit:
            port, uid = hit
            faders.append((port, uid or _uid_from_serial(sn), sn))
    return faders
