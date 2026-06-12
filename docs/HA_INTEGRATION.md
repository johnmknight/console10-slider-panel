# Home Assistant Integration — Knight Home Tech Mechanical MQTT Fader

This is the canonical spec for how a fader appears in Home Assistant: topic
structure, MQTT Discovery payload, identity rules, and runtime behavior.

The fader is a **read-only** mechanical control reporting a physical position
**0–100 %**. Home Assistant treats it as a read-only **MQTT Sensor**, not a
controllable slider — the fader is the source of truth.

> **Who publishes:** the QT Py RP2040 has no radio, so the **host bridge**
> (`host/fader_mqtt_bridge.py`) does all MQTT/HA work. The firmware's only job is
> to announce a stable per-device id (its RP2040 chip uid → 6 hex). Everything
> below — discovery, topics, availability, LWT — is the bridge's behavior.

## Which broker

Publish to the broker **Home Assistant's MQTT integration is connected to**
(Settings → Devices & Services → MQTT → Configure). Discovery is just retained
MQTT, so it only reaches HA via *that* broker. In a split homelab this is
commonly HA's bundled **Mosquitto add-on** (authenticated) — a *different* broker
from a shared "lab" broker other devices publish to. The bridge takes the broker
and auth from `host/.env` (`MQTT_BROKER`, `MQTT_USERNAME`, `MQTT_PASSWORD`).

## Use a Sensor, not a Number

Use HA MQTT Discovery with component **`sensor`**, unit **`%`**, read-only. Do
**not** use an MQTT `number` entity — `number` is for values HA can *command*.
The mechanical fader cannot be commanded, so there is no `command_topic`.

## Naming & identity model

HA uses several names/ids that are **not** interchangeable:

| Field | Purpose | Unique? | User-visible? |
|-------|---------|---------|----------------|
| `name` | Friendly display name | No | Yes |
| `unique_id` | HA entity identity | Yes | Mostly hidden |
| `device.identifiers` | HA device identity | Yes per device | Mostly hidden |
| MQTT topic | Where data is published | Yes per device | Hidden |

The friendly name may repeat across devices; `unique_id`,
`device.identifiers`, and the topics must be unique and **stable**.

### Per-device identity (from the chip uid `a1b2c3`)

```
unique_device_id  = a1b2c3                              # RP2040 uid, last 3 bytes hex
device_identifier = knighthometech_fader_a1b2c3         # device.identifiers
entity_unique_id  = knighthometech_fader_a1b2c3_position
```

Derive the uid from a **stable hardware identity** (the RP2040 chip uid here).
Never a hard-coded `slider_001` unless each board is hand-programmed unique.
This logic lives in `host/ha_fader.py` (`FaderIdentity`).

## MQTT topic structure

Root namespace: **`knighthometech`**.

```
State (live value):    knighthometech/fader_a1b2c3/position        # integer 0..100
Availability:          knighthometech/fader_a1b2c3/status          # online | offline
Discovery (config):    homeassistant/sensor/knighthometech_fader_a1b2c3_position/config
```

The word `fader` in the topic has no meaning to HA — it learns what the device
is from the **discovery payload**, not the topic name. The discovery object id
matches the `unique_id` for best compatibility.

## Discovery payload

Published **retained** to the config topic:

```json
{
  "name": "Position",
  "unique_id": "knighthometech_fader_a1b2c3_position",
  "state_topic": "knighthometech/fader_a1b2c3/position",
  "availability_topic": "knighthometech/fader_a1b2c3/status",
  "payload_available": "online",
  "payload_not_available": "offline",
  "unit_of_measurement": "%",
  "state_class": "measurement",
  "icon": "mdi:tune-variant",
  "suggested_display_precision": 0,
  "device": {
    "identifiers": ["knighthometech_fader_a1b2c3"],
    "name": "Knight Home Tech Fader",
    "manufacturer": "Knight Home Tech",
    "model": "Mechanical MQTT Fader",
    "sw_version": "1.0"
  }
}
```

## Runtime behavior

**State:** publish the integer position (0–100) to the state topic. Clamp to
0–100, round to whole numbers, publish **only on change**, debounce ADC noise,
don't flood while moving. (The firmware already deadbands/rate-limits; the bridge
also dedupes on the integer.)

**Availability:** on connect publish `online` (retained) to the status topic.
Configure the MQTT **Last Will & Testament** to publish `offline` (retained) to
the same topic, so HA knows if the bridge dies. Each fader uses its **own MQTT
connection** so each gets its own LWT.

**Boot order (per device):** connect → `online` → retained discovery config →
current position.

## Retain policy

| Message | Retain | Why |
|---------|--------|-----|
| Discovery config | **yes** | HA rediscovers the device after a restart |
| Availability (online/offline) | **yes** | HA knows the last-known availability |
| Position | yes (default) | HA shows the last position immediately after a restart |

Set position retain off (`POSITION_RETAIN=0` / `--no-position-retain`) if you
want fresh-live-only values.

## Updating & deleting

- **Update:** re-publishing the config topic with a changed payload is treated by
  HA as a config update (safe for `model`, `sw_version`, `icon`,
  `suggested_display_precision`). Do **not** change `unique_id`,
  `device.identifiers`, or `state_topic` after release — it orphans the entity.
- **Delete:** publish an **empty retained** payload to the config topic. The
  bridge does this with `--remove` (optionally `--uid <id>` to clear a
  disconnected one) — handy for clearing stale test entities.

## Multiple devices

Each physical fader has a distinct uid → distinct `device.identifiers`,
`unique_id`, and topics, so HA treats them as separate devices even though they
share the friendly name "Knight Home Tech Fader". The bridge auto-discovers all
plugged-in faders and rescans for hot-plugged ones.

## Result in Home Assistant

After the retained discovery is published, HA auto-creates:

- **Device:** Knight Home Tech Fader
- **Entity:** *Position* — a read-only `%` sensor (0–100)

Usable in dashboards, gauges, history, templates, and automations, e.g.:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.knight_home_tech_fader_position
    above: 75
```
