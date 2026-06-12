# ha_fader.py - Home Assistant identity + MQTT Discovery for the Knight Home Tech
# Mechanical MQTT Fader.
#
# Pure helpers, no I/O - the bridge (fader_mqtt_bridge.py) does the publishing.
# This module is the single source of truth for how a fader's stable device id
# (6 hex from the RP2040 chip uid, e.g. "a1b2c3") maps to Home Assistant's
# several different names/ids and to the MQTT topic tree. The rules come from
# docs/HA_INTEGRATION.md - read that for the "why".
#
# The device is a READ-ONLY mechanical fader, so it surfaces in HA as an MQTT
# *sensor* (0-100 %), never an MQTT *number*: the slider is the source of truth,
# HA cannot command it.

# --- product identity (these are user-visible, may repeat across devices) -----
MANUFACTURER = "Knight Home Tech"
MODEL = "Mechanical MQTT Fader"
DEVICE_NAME = "Knight Home Tech Fader"   # friendly device name (HA users can rename)
ENTITY_NAME = "Position"                 # friendly entity name (shows as "<device> Position")

# --- stable, unique-per-device namespaces (do NOT change after release) -------
NAMESPACE = "knighthometech"             # MQTT root prefix + device-id stem
DISCOVERY_PREFIX = "homeassistant"       # HA MQTT Discovery prefix

ONLINE = "online"
OFFLINE = "offline"


class FaderIdentity:
    """All the names/ids/topics for ONE physical fader, derived from its uid.

    HA uses several distinct identifiers that are NOT interchangeable:
      - device.identifiers : unique per physical device      (knighthometech_fader_a1b2c3)
      - entity unique_id   : unique per HA entity            (..._position)
      - MQTT topics        : where the device publishes data

    The friendly NAME may repeat across devices; these must not.
    """

    def __init__(self, uid, prefix=NAMESPACE, discovery_prefix=DISCOVERY_PREFIX):
        self.uid = uid                                         # "a1b2c3"
        self.prefix = prefix
        self.discovery_prefix = discovery_prefix

        self.device_slug = "fader_{}".format(uid)              # fader_a1b2c3 (human readable)
        self.device_identifier = "{}_fader_{}".format(prefix, uid)        # knighthometech_fader_a1b2c3
        self.entity_unique_id = "{}_position".format(self.device_identifier)

        # State / availability live under the product namespace; the discovery
        # config lives under HA's discovery prefix (object id == entity unique_id
        # for best compatibility).
        self.state_topic = "{}/{}/position".format(prefix, self.device_slug)
        self.status_topic = "{}/{}/status".format(prefix, self.device_slug)
        self.config_topic = "{}/sensor/{}/config".format(discovery_prefix, self.entity_unique_id)

    def __repr__(self):
        return "FaderIdentity(uid={!r}, state={!r})".format(self.uid, self.state_topic)


def discovery_payload(identity, name=DEVICE_NAME, fw_version="1.0", precision=0):
    """The retained MQTT Discovery config that makes HA create the sensor.

    Published (retained) to identity.config_topic. Re-publishing the same topic
    with a changed payload is treated by HA as a config UPDATE; publishing an
    empty payload deletes the entity (see fader_mqtt_bridge.py --remove).
    """
    return {
        "name": ENTITY_NAME,
        "unique_id": identity.entity_unique_id,
        "state_topic": identity.state_topic,
        "availability_topic": identity.status_topic,
        "payload_available": ONLINE,
        "payload_not_available": OFFLINE,
        "unit_of_measurement": "%",
        "state_class": "measurement",
        "icon": "mdi:tune-variant",
        "suggested_display_precision": precision,
        "device": {
            "identifiers": [identity.device_identifier],
            "name": name,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "sw_version": fw_version,
        },
    }
