# Fader — data formats

Two hops: the board emits over **USB serial**, and the host bridge republishes to
**MQTT** (and Home Assistant). For the full HA discovery/identity rules see
[`HA_INTEGRATION.md`](HA_INTEGRATION.md).

## 1. USB serial (board → host)

The firmware writes **one JSON object per line** (`\n`-terminated, UTF-8) to the
USB **data** channel. Every line carries the board's stable device `id` so the
host can attribute it to the right fader regardless of which port it came in on:

```json
{"id": "a1b2c3", "value": 0.42, "pct": 42, "raw": 430}
```

| Field | Range | Meaning |
|-------|-------|---------|
| `id` | 6 hex | stable per-board id (RP2040 chip uid, last 3 bytes) |
| `value` | 0.0–1.0 | normalized slider position |
| `pct` | 0–100 | integer percent (this is what HA gets) |
| `raw` | 0–`adc_max` | raw seesaw ADC count (default `adc_max` = 1023) |

At boot the firmware also emits a one-time identity line so a late-starting host
learns the id immediately:

```json
{"hello": 1, "id": "a1b2c3", "fw": "1.0"}
```

**When values emit:** on change past a `deadband` (anti-jitter), rate-limited to
~30/s, **plus** a `heartbeat` re-emit every few seconds even when idle — so a
late host start and retained MQTT topics always carry a fresh value. Smoothing
(EMA), invert, deadband, and heartbeat are set in `config.json` (see
`firmware/config.example.json`).

**Channels:** the firmware emits on the dedicated USB **data** port (needs
`boot.py` + a power-cycle). Without it, it falls back to the **console** port,
where its own log output shares the wire — the host reader skips non-JSON lines.
For multi-board hosts the bridge identifies each board's data channel by probing
for this JSON (see `host/console10_slider.py:discover_faders`).

## 2. MQTT (host bridge → broker / Home Assistant)

`host/fader_mqtt_bridge.py` derives a per-device identity from `id` and publishes
on three topics (device id `a1b2c3` shown):

```
knighthometech/fader_a1b2c3/position                              # state: integer 0..100
knighthometech/fader_a1b2c3/status                               # availability: online|offline
homeassistant/sensor/knighthometech_fader_a1b2c3_position/config # retained HA discovery
```

| Topic | Payload | Retain |
|-------|---------|--------|
| `…/position` | bare integer `0`–`100`, on change | yes (default; `--no-position-retain` / `POSITION_RETAIN=0` to disable) |
| `…/status` | `online` / `offline` (offline via LWT) | yes |
| `homeassistant/sensor/…/config` | discovery JSON (see HA_INTEGRATION.md) | yes |

- **Broker:** must be the one Home Assistant's MQTT integration uses (often HA's
  authenticated Mosquitto add-on, separate from a shared lab broker). Set in
  `host/.env` (`MQTT_BROKER`/`MQTT_PORT`/`MQTT_USERNAME`/`MQTT_PASSWORD`) or CLI
  flags; defaults to `192.168.4.51:1883`.
- **Namespace:** `MQTT_PREFIX` (default `knighthometech`) and
  `HA_DISCOVERY_PREFIX` (default `homeassistant`).

Example consumer (paho-mqtt) — read every fader's live value:

```python
client.subscribe("knighthometech/+/position")
# msg.topic   -> 'knighthometech/fader_a1b2c3/position'
# msg.payload -> b'42'
```

Migration note: this replaces the old single-device topic
`console10/slider/value` (JSON). `host/slider_mqtt_bridge.py` is now a thin shim
that forwards to `fader_mqtt_bridge.py`.
