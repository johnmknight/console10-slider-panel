# diag_pin_scan.py - one-off diagnostic: find which seesaw analog pin the slide
# pot's wiper is on. Copy over code.py on the board, watch the console while you
# move the slider, note which pXX value tracks the slider, then restore code.py.
import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.analoginput import AnalogInput

print("=== SLIDER PIN SCAN @ 0x30 (move the slider!) ===")
i2c = board.STEMMA_I2C()
ss = Seesaw(i2c, addr=0x30)

# Candidate analog-capable seesaw pins on the ATtiny8x7.
pins = [18, 2, 3, 0, 1, 7, 19, 20]
ins = []
for p in pins:
    try:
        ins.append((p, AnalogInput(ss, p)))
    except Exception as e:
        print("pin", p, "init err:", e)

while True:
    parts = []
    for p, a in ins:
        try:
            parts.append("p{}={:4d}".format(p, a.value))
        except Exception:
            parts.append("p{}=ERR".format(p))
    print(" ".join(parts))
    time.sleep(0.2)
