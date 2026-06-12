# settings.py - Console10 Slider config loader
#
# Mirrors the console10-oled-panel / smarttoolbox convention: every module reads
# config through here, never touches config.json directly. config.json is
# OPTIONAL - the defaults below are a complete, working configuration.

import json

_config = None


def load():
    global _config
    loaded = {}
    try:
        with open("/config.json", "r") as f:
            loaded = json.load(f)
        print("[settings] Loaded /config.json")
    except OSError:
        print("[settings] No /config.json - using defaults")
    except ValueError as e:
        print(f"[settings] config.json parse error: {e} - using defaults")

    merged = _defaults()
    merged.update(loaded)
    _config = merged
    return _config


def get(key, fallback=None):
    if _config is None:
        load()
    return _config.get(key, fallback)


def _defaults():
    return {
        "channel": "data",       # "data" (needs boot.py) | "console" (shares REPL)
        "i2c_addr": "0x30",      # Adafruit STEMMA QT slide pot (seesaw) default
        "analog_pin": 18,         # seesaw analog pin the wiper is wired to
        "adc_max": 1023,          # full-scale ADC count (seesaw slide pot is 0..1023)
        "invert": False,          # flip slider direction if min/max feel reversed
        "smoothing": 0.3,         # EMA factor 0..1 (0 = raw; lower = smoother/slower)
        "deadband": 4,            # min raw-count change before we emit (anti-jitter)
        "rate_limit": 0.03,       # min seconds between change emits (~30/s cap)
        "heartbeat": 5.0,         # re-emit the current value every N s even if idle
        "debug": True,
    }
