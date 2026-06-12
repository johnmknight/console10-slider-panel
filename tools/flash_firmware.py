#!/usr/bin/env python3
# flash_firmware.py - one-step firmware install for a Knight Home Tech fader.
#
# Finds the board's CIRCUITPY drive, copies the firmware onto it, installs the
# adafruit_seesaw library with circup (if available), and reminds you to
# power-cycle (the dedicated USB data channel only appears after a hard reset).
#
# Prereqs (done once per board, BEFORE this script):
#   1. Flash CircuitPython (drag the .uf2 onto the RPI-RP2 bootloader drive).
#   2. pip install circup        (optional but recommended; auto-installs the lib)
#
# Usage:
#   python tools/flash_firmware.py            # auto-detect CIRCUITPY
#   python tools/flash_firmware.py --drive E:\        # or point it explicitly
#   python tools/flash_firmware.py --config           # also seed config.json

import argparse
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FW_DIR = os.path.join(REPO, "firmware")

# The runtime firmware (NOT the diag tool, requirements, or example config).
FW_FILES = ["boot.py", "code.py", "settings.py", "slider.py"]


def _is_circuitpy(root):
    # CircuitPython writes boot_out.txt to the CIRCUITPY volume root - a reliable,
    # cross-platform marker that doesn't need volume-label APIs.
    return os.path.isfile(os.path.join(root, "boot_out.txt"))


def find_circuitpy():
    """Return a list of mounted CIRCUITPY drive roots."""
    roots = []
    if os.name == "nt":
        import string
        roots = ["{}:\\".format(c) for c in string.ascii_uppercase]
    else:
        roots = (
            ["/Volumes/CIRCUITPY"]
            + glob.glob("/media/*/CIRCUITPY")
            + glob.glob("/media/*/*/CIRCUITPY")
            + glob.glob("/run/media/*/CIRCUITPY")
        )
    return [r for r in roots if os.path.isdir(r) and _is_circuitpy(r)]


def copy_firmware(drive, with_config=False):
    for name in FW_FILES:
        src = os.path.join(FW_DIR, name)
        if not os.path.isfile(src):
            print("  ! missing {} - skipping".format(src))
            continue
        shutil.copy2(src, os.path.join(drive, name))
        print("  copied {}".format(name))
    if with_config:
        src = os.path.join(FW_DIR, "config.example.json")
        dst = os.path.join(drive, "config.json")
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print("  copied config.example.json -> config.json")


def run_circup():
    circup = shutil.which("circup")
    if not circup:
        print("\ncircup not found - install the library yourself:")
        print("  pip install circup && circup install adafruit_seesaw")
        return
    print("\nInstalling adafruit_seesaw with circup...")
    try:
        subprocess.run([circup, "install", "adafruit_seesaw"], check=False)
    except Exception as e:
        print("  circup failed: {} (run it manually)".format(e))


def main():
    ap = argparse.ArgumentParser(description="Copy fader firmware to a CIRCUITPY board.")
    ap.add_argument("--drive", help="CIRCUITPY drive root (e.g. E:\\ or /media/you/CIRCUITPY)")
    ap.add_argument("--config", action="store_true", help="also seed config.json from the example")
    ap.add_argument("--no-circup", action="store_true", help="skip the circup library install")
    args = ap.parse_args()

    if args.drive:
        drives = [args.drive]
    else:
        drives = find_circuitpy()

    if not drives:
        print("No CIRCUITPY drive found. Flash CircuitPython first, then plug the board in")
        print("(or pass --drive). Bootloader mode shows up as RPI-RP2; that's not it yet.")
        return 1
    if len(drives) > 1:
        print("Multiple CIRCUITPY drives found - flash one board at a time, or use --drive:")
        for d in drives:
            print("  {}".format(d))
        return 1

    drive = drives[0]
    print("Flashing firmware to {}".format(drive))
    copy_firmware(drive, with_config=args.config)
    if not args.no_circup:
        run_circup()

    print("\nDone. POWER-CYCLE the board now (unplug/replug or tap reset) so the")
    print("dedicated USB data channel appears, then run the host bridge:")
    print("  python host/fader_mqtt_bridge.py --list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
