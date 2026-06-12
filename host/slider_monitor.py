#!/usr/bin/env python3
# slider_monitor.py - simple MQTT subscriber that DISPLAYS the slider value.
#
# Subscribes to the slider's topic and draws a live-updating terminal bar:
#
#   [############------------------]  42%  value=0.420 raw=430
#
# This is the consumer end of the chain:
#   slider -> USB serial -> slider_mqtt_bridge.py -> MQTT -> (this) monitor
#
# Run the bridge in one terminal and this in another. Defaults target the same
# lab broker/topic as the bridge.
#
# Requires: paho-mqtt>=2  (pip install -r requirements.txt)

import argparse
import json
import os
import sys
import time

import paho.mqtt.client as mqtt

DEFAULT_BROKER = os.getenv("MQTT_BROKER", "192.168.4.148")
DEFAULT_MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEFAULT_TOPIC = os.getenv("SLIDER_TOPIC", "console10/slider/value")

BAR_W = 30


def _parse(payload):
    """Return (value, pct, raw) from a payload, or None if unparseable.

    Accepts both the JSON object {"value","pct","raw"} and a bare scalar number
    (what the bridge sends with --scalar)."""
    try:
        obj = json.loads(payload.decode("utf-8", "replace").strip())
    except ValueError:
        return None
    if isinstance(obj, dict):
        value = float(obj.get("value", 0.0))
        pct = int(obj.get("pct", round(value * 100)))
        raw = obj.get("raw", "-")
        return value, pct, raw
    # bare number
    try:
        value = float(obj)
    except (TypeError, ValueError):
        return None
    return value, int(round(value * 100)), "-"


def _bar(value):
    filled = max(0, min(BAR_W, int(round(value * BAR_W))))
    return "█" * filled + "░" * (BAR_W - filled)


def main():
    ap = argparse.ArgumentParser(description="Subscribe to the Console10 Slider topic and display it.")
    ap.add_argument("--broker", default=DEFAULT_BROKER)
    ap.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    ap.add_argument("--topic", default=DEFAULT_TOPIC)
    ap.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    ap.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    ap.add_argument("--seconds", type=float, default=0, help="run for N seconds then exit (0 = forever)")
    ap.add_argument("--log", action="store_true", help="print one line per update instead of a live bar")
    args = ap.parse_args()

    # Windows consoles default to cp1252, which can't encode the bar's block
    # glyphs. Force UTF-8 so they print (degrading to '?' on odd consoles rather
    # than throwing inside the MQTT callback thread).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    def on_connect(c, userdata, flags, rc, properties=None):
        if rc == 0:
            c.subscribe(args.topic)
            print("[mqtt] connected; subscribed to {}".format(args.topic))
        else:
            print("[mqtt] connect failed rc={}".format(rc))

    def on_message(c, userdata, msg):
        parsed = _parse(msg.payload)
        if parsed is None:
            return
        value, pct, raw = parsed
        if args.log:
            print("{}  {:3d}%  value={:.3f} raw={}".format(_bar(value), pct, value, raw))
        else:
            sys.stdout.write("\r[{}] {:3d}%  value={:.3f} raw={}   ".format(_bar(value), pct, value, raw))
            sys.stdout.flush()

    client = mqtt.Client(
        client_id="console10-slider-monitor-{}".format(os.getpid()),
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    if args.username:
        client.username_pw_set(args.username, args.password or None)
    client.on_connect = on_connect
    client.on_message = on_message

    print("[monitor] {}:{}  topic={}".format(args.broker, args.mqtt_port, args.topic))
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
