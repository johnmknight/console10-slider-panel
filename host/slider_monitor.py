#!/usr/bin/env python3
# slider_monitor.py - simple MQTT subscriber that DISPLAYS fader values.
#
# Subscribes to every fader's state + status topics and prints a live bar per
# update - the consumer end of the chain, handy for eyeballing the bridge
# without Home Assistant:
#
#   [fader_a1b2c3] [############------------------]  42%
#   [fader_a1b2c3] online
#
# Topics (see ../docs/HA_INTEGRATION.md):
#   knighthometech/+/position   <- bare integer 0..100
#   knighthometech/+/status     <- online|offline
#
# Requires: paho-mqtt>=2  (pip install -r requirements.txt)

import argparse
import os
import sys
import time

import paho.mqtt.client as mqtt

DEFAULT_BROKER = os.getenv("MQTT_BROKER", "192.168.4.51")
DEFAULT_MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEFAULT_PREFIX = os.getenv("MQTT_PREFIX", "knighthometech")

BAR_W = 30


def _fader(topic):
    """Device slug from a topic, e.g. 'knighthometech/fader_a1b2c3/position' -> 'fader_a1b2c3'."""
    parts = topic.split("/")
    return parts[1] if len(parts) > 1 else topic


def _bar(frac):
    filled = max(0, min(BAR_W, int(round(frac * BAR_W))))
    return "█" * filled + "░" * (BAR_W - filled)


def main():
    ap = argparse.ArgumentParser(description="Subscribe to Knight Home Tech fader topics and display them.")
    ap.add_argument("--broker", default=DEFAULT_BROKER)
    ap.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX, help="MQTT root namespace (default: %(default)s)")
    ap.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    ap.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    ap.add_argument("--seconds", type=float, default=0, help="run for N seconds then exit (0 = forever)")
    args = ap.parse_args()

    pos_topic = args.prefix + "/+/position"
    status_topic = args.prefix + "/+/status"

    # Windows consoles default to cp1252, which can't encode the bar's block
    # glyphs. Force UTF-8 so they print (degrading to '?' rather than throwing
    # inside the MQTT callback thread).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    def on_connect(c, userdata, flags, rc, properties=None):
        if not getattr(rc, "is_failure", rc != 0):
            c.subscribe([(pos_topic, 0), (status_topic, 0)])
            print("[mqtt] connected; subscribed to {} and {}".format(pos_topic, status_topic))
        else:
            print("[mqtt] connect failed rc={}".format(rc))

    def on_message(c, userdata, msg):
        payload = msg.payload.decode("utf-8", "replace").strip()
        if msg.topic.endswith("/position"):
            try:
                pct = int(round(float(payload)))
            except (TypeError, ValueError):
                return
            pct = max(0, min(100, pct))
            print("[{}] [{}] {:3d}%".format(_fader(msg.topic), _bar(pct / 100.0), pct))
        elif msg.topic.endswith("/status"):
            print("[{}] {}".format(_fader(msg.topic), payload or "(cleared)"))

    client = mqtt.Client(
        client_id="kht-fader-monitor-{}".format(os.getpid()),
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    if args.username:
        client.username_pw_set(args.username, args.password or None)
    client.on_connect = on_connect
    client.on_message = on_message

    print("[monitor] {}:{}  prefix={}".format(args.broker, args.mqtt_port, args.prefix))
    client.connect(args.broker, args.mqtt_port, keepalive=60)
    client.loop_start()
    try:
        if args.seconds > 0:
            time.sleep(args.seconds)
        else:
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
