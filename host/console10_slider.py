# console10_slider.py - host-side reader for the Console10 Slider.
#
# Opens the QT Py's USB *data* serial port and yields the slider readings the
# firmware streams (one JSON object per line). This is the inbound mirror of
# console10-oled-panel's Console10Screen; keep it tiny so any host app (an MQTT
# bridge, a WLED controller, a logger) can import it.
#
# Requires: pyserial  (pip install pyserial)

import json

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
    """Best-guess the data port: the higher-numbered Adafruit COM port."""
    devs = [d for d, _ in find_ports()]
    if not devs:
        return None

    def _num(d):
        return int(d.replace("COM", "")) if d.startswith("COM") else 0

    return sorted(devs, key=_num)[-1]
