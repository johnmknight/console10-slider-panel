# Console10 Slider — data formats

Two hops: the board emits over **USB serial**, and the host bridge republishes to
**MQTT**.

## 1. USB serial (board → host)

The firmware writes **one JSON object per line** (`\n`-terminated, UTF-8) to the
USB **data** channel:

```json
{"value": 0.42, "pct": 42, "raw": 430}
```

| Field | Range | Meaning |
|-------|-------|---------|
| `value` | 0.0–1.0 | normalized slider position |
| `pct` | 0–100 | integer percent (convenience for HA / dashboards) |
| `raw` | 0–`adc_max` | raw seesaw ADC count (default `adc_max` = 1023) |

**When it emits:** on change past a `deadband` (anti-jitter), rate-limited to
~30/s, **plus** a `heartbeat` re-emit every few seconds even when idle — so a
late host start and a retained MQTT topic always carry a fresh value. Smoothing
(EMA), invert, deadband, and heartbeat are all set in `config.json` (see
`firmware/config.example.json`).

**Channels:** the firmware emits on the dedicated USB **data** port (needs
`boot.py` + a power-cycle). Without it, it falls back to the **console** port,
where its own log output shares the wire — the host reader skips non-JSON lines.

## 2. MQTT (host bridge → broker)

`slider_mqtt_bridge.py` publishes each reading to:

```
console10/slider/value
```

- **Payload:** the same JSON object by default, or a bare `0.0–1.0` number with
  `--scalar`.
- **Retain:** `True` (current-state topic — late subscribers get the last
  position immediately). Disable with `--no-retain`.
- **QoS:** 0 (fine on the LAN); raise with `--qos`.
- **Broker:** defaults to the lab broker `192.168.4.148:1883` (appserv1),
  anonymous. Override via `MQTT_BROKER` / `MQTT_PORT` / `SLIDER_TOPIC` env or the
  CLI flags.

Topic naming follows the homelab convention `<source>/<subsystem>/<signal>`
(all lowercase). Example consumer (paho-mqtt):

```python
client.subscribe("console10/slider/value")
# msg.payload -> b'{"value":0.42,"pct":42,"raw":430}'
```
