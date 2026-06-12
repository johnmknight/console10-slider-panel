# boot.py - Console10 Slider (CircuitPython; runs once at power-on, before code.py)
#
# WHY THIS FILE EXISTS
# --------------------
# By default the QT Py exposes a single USB serial port - the REPL / console.
# We want a *dedicated* second serial port to stream slider values on, so they
# don't collide with REPL output / tracebacks. usb_cdc.enable(..., data=True)
# enumerates that second "data" channel; code.py writes slider readings to it.
#
# IMPORTANT: boot.py only runs at hard reset / power-up, NOT on a soft reload.
# After copying this file, FULLY POWER-CYCLE the board (unplug/replug or tap
# reset) for the data port to appear. On the host it shows up as an additional
# serial port (Windows: another COMx) - usually the higher-numbered of the two.

import usb_cdc

usb_cdc.enable(console=True, data=True)
