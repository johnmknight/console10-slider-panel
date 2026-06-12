# console10-slider-panel

A **STEMMA QT slide-potentiometer** control for a [Console10](../Console10)
mini-rack panel, on an **Adafruit QT Py RP2040**. The board reads the slider over
I²C and streams its value over **USB serial**; a host **MQTT bridge** republishes
it to the homelab broker. The input-side sibling of
[`console10-oled-panel`](../console10-oled-panel).

> **Why a host bridge, not WiFi:** the RP2040 has **no WiFi radio**, so it can't
> reach the MQTT broker itself. It stays a dumb USB input device; the host
> publishes. (A QT Py *ESP32-S3* could publish natively with `adafruit_minimqtt`
> — that's the smarttoolbox pattern — if you'd rather drop the host hop later.)

**Status:** scaffolded — pending on-hardware bring-up.

---

## Hardware

| Part | Notes |
|------|-------|
| Adafruit **QT Py RP2040** | RP2040, STEMMA QT port, USB-C. No wireless. |
| Adafruit **STEMMA QT Slide Potentiometer** (non-NeoPixel) | seesaw (ATtiny) over I²C, addr `0x30`, wiper on seesaw analog pin 18 |
| STEMMA QT — STEMMA QT cable | Plug-and-play; no soldering |

The slide pot is **not** a raw analog pot — an onboard seesaw chip reads the
wiper and exposes it over I²C, so the QT Py reads it with `adafruit_seesaw`
(`Seesaw(i2c, 0x30)` → `AnalogInput(ss, 18)`), no ADC pin wiring.

---

## Bring-up

1. **Flash CircuitPython** onto the QT Py RP2040 (tested on 10.2.1) from
   <https://circuitpython.org/board/adafruit_qtpy_rp2040/>. In bootloader mode
   it's an `RPI-RP2` drive — copy the `.uf2` to it; it reboots as `CIRCUITPY`.
2. **Install the library** with [circup](https://github.com/adafruit/circup):
   ```sh
   circup install adafruit_seesaw
   ```
3. **Copy the firmware** — copy `firmware/*.py` to the root of `CIRCUITPY`
   (`boot.py`, `code.py`, `settings.py`, `slider.py`). Optionally
   `config.json` (copy `config.example.json` → `config.json`); defaults work.
4. **Power-cycle the board** so `boot.py` creates the dedicated USB **data**
   serial port. After this the board exposes two serial ports (console + data);
   read the **data** one.

---

## Run the MQTT bridge (host)

Install deps once:
```sh
pip install -r host/requirements.txt
```

Find the port (data channel = higher-numbered one), then run the bridge:
```sh
python host/slider_mqtt_bridge.py --list
python host/slider_mqtt_bridge.py --verbose        # auto-detect port, lab broker
python host/slider_mqtt_bridge.py --port COM10 --broker 192.168.4.148 --topic console10/slider/value
```

Defaults: broker `192.168.4.148:1883` (appserv1), topic `console10/slider/value`,
retained, QoS 0. Override via flags or `host/.env` (copy `.env.example`).

Verify the value lands on the broker:
```sh
mosquitto_sub -h 192.168.4.148 -t console10/slider/value -v
```

Or consume the slider directly (no MQTT) from your own code:
```python
from console10_slider import Console10Slider, pick_data_port

with Console10Slider(pick_data_port()) as slider:
    for r in slider.readings():
        print(r["value"], r["pct"], r["raw"])
```

The full wire/MQTT formats are in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

---

## Layout

```
firmware/   CircuitPython for the QT Py RP2040 (copy to CIRCUITPY)
  boot.py            enables the dedicated USB data serial channel
  code.py            read slider -> emit JSON value over serial (on change + heartbeat)
  settings.py        loads /config.json (optional; defaults included)
  slider.py          seesaw slide-pot read + smoothing/invert/deadband
  config.example.json
  requirements.txt   circup library list (adafruit_seesaw)
host/       Host-side bridge (runs on the Pi/PC in the rack)
  console10_slider.py    reusable serial reader (yields {value,pct,raw})
  slider_mqtt_bridge.py  reads serial -> publishes to MQTT (paho-mqtt)
  .env.example           broker/topic config
  requirements.txt       pyserial, paho-mqtt
docs/
  PROTOCOL.md            USB-serial + MQTT formats
```

---

## Console10 integration

Meant to live in a Console10 slot as a physical control. Open follow-ups:

- **Faceplate** — a Console10 front plate with a cutout for the slide pot.
- **Consumers** — wire `console10/slider/value` to a real target: WLED brightness
  (the Lights app's Gledopto), a Home Assistant `input_number`/light, or the
  `console10-oled-panel`'s brightness. Each is a thin MQTT subscriber.
- **HA MQTT discovery** — have the bridge publish a discovery config so the
  slider auto-appears as a sensor in Home Assistant.
- **Native MQTT (no host)** — an ESP32-S3 variant that runs `adafruit_minimqtt`
  and publishes directly, dropping the host bridge.
