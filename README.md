# console10-slider-panel

**STEMMA QT slide-potentiometer** controls on **Adafruit QT Py RP2040** boards,
bridged to **MQTT + Home Assistant**. Each board reads its slider over I²C and
streams the value over **USB serial**; a host **bridge** turns every connected
board into a read-only Home Assistant **sensor** via MQTT Discovery. The
input-side sibling of [`console10-oled-panel`](../console10-oled-panel).

> **Why a host bridge, not WiFi:** the RP2040 has **no radio**, so it can't reach
> MQTT itself. The board stays a dumb USB input device that announces a stable
> per-board id; the host bridge does all MQTT/HA work. (A QT Py *ESP32-S3* could
> publish natively with `adafruit_minimqtt` — that's the smarttoolbox pattern —
> if you'd rather drop the host hop later.)

**Status:** working on hardware (CircuitPython 10.2.1) and published. Now with
**multiple-device support** and **Home Assistant MQTT Discovery** — confirmed
live in HA as a read-only `%` sensor.

## How it works

```
[slider]--I2C-->[QT Py RP2040]--USB serial-->[host bridge]--MQTT-->[broker]-->[Home Assistant]
                  emits id+value           per-device identity,
                                           discovery, availability
```

- **Firmware** emits its RP2040 chip uid (6 hex, e.g. `a1b2c3`) with every value.
- **Host bridge** (`host/fader_mqtt_bridge.py`) auto-discovers all plugged faders;
  per device it derives a stable identity, publishes a retained HA Discovery
  config (read-only `%` **sensor** — *not* a number, the fader is the source of
  truth), tracks availability with an MQTT Last Will, and publishes the integer
  position 0–100 on change. Plug another fader in and it appears on the next rescan.

Full topic/identity rules: [`docs/HA_INTEGRATION.md`](docs/HA_INTEGRATION.md).
Wire + MQTT formats: [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Hardware

| Part | Notes |
|------|-------|
| Adafruit **QT Py RP2040** | RP2040, STEMMA QT port, USB-C. No wireless. Stable chip uid → device id. |
| Adafruit **STEMMA QT Slide Potentiometer** (non-NeoPixel) | seesaw (ATtiny) over I²C, addr `0x30`, wiper on seesaw analog pin 18 |
| STEMMA QT — STEMMA QT cable | Plug-and-play; no soldering |

The slide pot is **not** a raw analog pot — an ATtiny ("seesaw") reads the wiper
and exposes it over I²C, so the QT Py reads it with `adafruit_seesaw`
(`Seesaw(i2c, 0x30)` → `AnalogInput(ss, 18)`).

## Quick start

### 1. Flash a board

Flash CircuitPython first (drag the `.uf2` onto the `RPI-RP2` bootloader drive),
then:

```sh
pip install circup            # once, recommended (auto-installs the I2C lib)
python tools/flash_firmware.py
```

It finds the `CIRCUITPY` drive, copies the firmware, installs `adafruit_seesaw`,
and reminds you to **power-cycle** (the dedicated USB data channel only appears
after a hard reset). Repeat per board.

### 2. Set up the host bridge

The bridge runs wherever the faders plug in. Pick your platform:

```sh
# Linux / Raspberry Pi  — venv + deps + .env + systemd service (auto-start on boot)
./install/install.sh

# Windows — venv + deps + .env + a logon Scheduled Task
./install/install.ps1
```

Both seed `host/.env` from the example — set your **Home Assistant** broker +
auth there (see step 3). Then the bridge auto-detects every plugged-in fader and
publishes. Add `--no-service`
/ `-NoService` to skip the autostart and run manually instead:

```sh
./install/run_bridge.sh            # or  ./install/run_bridge.ps1
./install/run_bridge.sh --list     # show connected faders + their topics
```

### 3. Home Assistant

**Point the bridge at HA's own MQTT broker.** Discovery only reaches HA via the
broker its MQTT integration uses (Settings → Devices & Services → MQTT) — that's
often a *different* broker from your other lab devices, and HA's Mosquitto add-on
usually needs auth. Set `MQTT_BROKER` + `MQTT_USERNAME`/`MQTT_PASSWORD` in
`host/.env`.

With that, each fader auto-appears as a **device** ("Knight Home Tech Fader")
with a read-only **Position** `%` sensor — no YAML. Rename in HA as you like.
Verify on that broker:

```sh
mosquitto_sub -h <ha-broker> -t 'knighthometech/#' -v          # state + status
mosquitto_sub -h <ha-broker> -t 'homeassistant/sensor/#' -v    # retained discovery
```

## Layout

```
firmware/   CircuitPython for the QT Py RP2040 (copy to CIRCUITPY)
  boot.py            enables the dedicated USB data serial channel
  code.py            read slider + chip uid -> emit JSON over serial
  settings.py        loads /config.json (optional; defaults included)
  slider.py          seesaw slide-pot read + smoothing/invert/deadband
  config.example.json
  diag_pin_scan.py   one-off seesaw analog-pin scanner
host/       Host-side bridge + reader
  fader_mqtt_bridge.py   multi-device MQTT + Home Assistant Discovery bridge  <- main
  ha_fader.py            identity + discovery-payload helpers (per the spec)
  console10_slider.py    serial reader + multi-board data-port discovery
  slider_monitor.py      MQTT subscriber test app (live per-fader bars)
  slider_mqtt_bridge.py  deprecated shim -> fader_mqtt_bridge.py
  .env.example           broker / namespace / name config
tools/
  flash_firmware.py      copy firmware to CIRCUITPY + circup install
install/
  install.sh / install.ps1            cross-platform host setup
  run_bridge.sh / run_bridge.ps1      venv-activating runners
  console10-fader-bridge.service      systemd unit template
docs/
  HA_INTEGRATION.md      Home Assistant identity/discovery/availability spec
  PROTOCOL.md            USB-serial + MQTT formats
```

## Follow-ups

- **Faceplate** — carried by the Console10 DSKY panel (`../Console10`).
- **Native MQTT (no host)** — an ESP32-S3 variant running `adafruit_minimqtt`.
- **Other consumers** — `knighthometech/+/position` can also drive WLED
  brightness, a HA `input_number`, etc. as thin subscribers.
