# slider.py - read the Adafruit STEMMA QT slide potentiometer over I2C (seesaw)
#
# Hardware: Adafruit STEMMA QT Slide Potentiometer (the non-NeoPixel version).
# It is NOT a raw analog pot - an ATtiny running Adafruit's "seesaw" firmware
# reads the wiper and exposes it over I2C. Default address 0x30; the wiper is on
# seesaw analog pin 18. We talk to it with the adafruit_seesaw library:
#
#   circup install adafruit_seesaw
#
# We return both the raw ADC count (0..adc_max) and a normalized 0.0..1.0 value,
# with optional direction-invert and an exponential-moving-average smoother to
# tame the analog jitter inherent to a potentiometer.

import board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.analoginput import AnalogInput

_ss = None
_pot = None
_adc_max = 1023
_invert = False
_smoothing = 0.0
_ema = None


def _coerce_addr(addr):
    if isinstance(addr, str):
        return int(addr, 0)
    return addr


def init(cfg):
    """Bring up the seesaw and bind the analog input to the wiper pin."""
    global _ss, _pot, _adc_max, _invert, _smoothing
    addr = _coerce_addr(cfg.get("i2c_addr", 0x30))
    pin = cfg.get("analog_pin", 18)
    _adc_max = cfg.get("adc_max", 1023)
    _invert = bool(cfg.get("invert", False))
    _smoothing = float(cfg.get("smoothing", 0.0) or 0.0)

    # board.STEMMA_I2C() targets the dedicated STEMMA QT connector; fall back to
    # the generic board.I2C() on boards that don't define the helper.
    try:
        i2c = board.STEMMA_I2C()
    except AttributeError:
        i2c = board.I2C()

    try:
        _ss = Seesaw(i2c, addr=addr)
    except Exception as e:
        print(f"[slider] seesaw not found at {hex(addr)} - check the STEMMA QT cable: {e}")
        raise
    _pot = AnalogInput(_ss, pin)
    print(f"[slider] seesaw @ {hex(addr)} pin {pin} adc_max {_adc_max} invert {_invert}")


def read_raw():
    """Raw ADC count, 0..adc_max, with direction-invert applied."""
    v = _pot.value
    if _invert:
        v = _adc_max - v
    # Clamp defensively - noise can occasionally read just past the rails.
    if v < 0:
        v = 0
    elif v > _adc_max:
        v = _adc_max
    return v


def read():
    """Return (raw_int, value_float). value_float is 0.0..1.0.

    Applies an EMA smoother when `smoothing` > 0: ema += alpha * (sample - ema).
    A larger alpha follows the slider faster; a smaller one is smoother but lags.
    """
    global _ema
    raw = read_raw()
    if _smoothing > 0.0:
        if _ema is None:
            _ema = float(raw)
        else:
            _ema += _smoothing * (raw - _ema)
        smoothed = int(_ema + 0.5)
    else:
        smoothed = raw
    return smoothed, (smoothed / _adc_max if _adc_max else 0.0)
