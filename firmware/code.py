# code.py - Console10 Slider main entry point (CircuitPython)
#
# Project: console10-slider-panel  (Adafruit QT Py RP2040 + STEMMA QT slide pot)
#
# ROLE
# ----
# This board is a *dumb input device*. The RP2040 has no radio of its own, so it
# can't reach the MQTT broker directly - instead it reads the slider over I2C and
# STREAMS the value over USB serial. A host process (see ../host/) reads that
# stream and republishes it to MQTT. The board never touches the network.
#
# Wire format (one JSON object per line, on the USB *data* channel):
#   {"value": 0.42, "pct": 42, "raw": 430}
#   - value : 0.0..1.0 normalized position
#   - pct   : 0..100 integer (convenience for HA / dashboards)
#   - raw   : 0..adc_max raw ADC count
# Emitted on change (past a deadband, rate-limited) plus a periodic heartbeat so
# late host starts and retained MQTT topics always have a fresh value.
#
# Libraries (install with circup):
#   circup install adafruit_seesaw
#
# Reminder: the dedicated USB "data" channel only exists if boot.py ran AND the
# board was power-cycled after boot.py was copied. If it's missing we fall back
# to the console channel (values then share the wire with REPL/log output).

import time
import json
import usb_cdc
import settings
import slider

print("\n=== Console10 Slider v0.1 ===")
cfg = settings.load()
slider.init(cfg)

# --- pick the serial channel to emit on -------------------------------------
_channel = cfg.get("channel", "data")
if _channel == "data" and usb_cdc.data is not None:
    _serial = usb_cdc.data
    print("[serial] Emitting on USB data channel")
else:
    if _channel == "data":
        print("[serial] usb_cdc.data is None - did boot.py run + power-cycle?")
        print("[serial] Falling back to the console channel.")
    _serial = usb_cdc.console
    print("[serial] Emitting on USB console channel")

_debug = cfg.get("debug", True)
_deadband = cfg.get("deadband", 4)
_rate = cfg.get("rate_limit", 0.03)
_heartbeat = cfg.get("heartbeat", 5.0)


def emit(raw, val):
    line = json.dumps({"value": round(val, 3), "pct": int(round(val * 100)), "raw": raw}) + "\n"
    try:
        _serial.write(line.encode("utf-8"))
    except Exception as e:
        print("[emit] error: {}".format(e))


_last_raw = -9999
_last_emit = 0.0
_last_hb = 0.0

print("[main] Entering main loop")
while True:
    try:
        now = time.monotonic()
        raw, val = slider.read()

        changed = abs(raw - _last_raw) >= _deadband
        due_heartbeat = (now - _last_hb) >= _heartbeat

        if (changed and (now - _last_emit) >= _rate) or due_heartbeat:
            emit(raw, val)
            _last_raw = raw
            _last_emit = now
            _last_hb = now
            if _debug and changed:
                print("[slider] raw={} value={}".format(raw, round(val, 3)))

        time.sleep(0.01)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("[main] error: {}".format(e))
        time.sleep(0.2)
