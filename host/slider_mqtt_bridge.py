#!/usr/bin/env python3
# slider_mqtt_bridge.py - read the Console10 Slider over USB serial and publish
# its value to MQTT. This is the "host MQTT bridge" - the RP2040 has no WiFi, so
# this process is what actually talks to the broker.
#
# Topic convention (see ../docs/PROTOCOL.md and the jmk-mqtt skill):
#   console10/slider/value   <- JSON {"value":0.42,"pct":42,"raw":430}, retained
# Retained because it's current state: a late subscriber (dashboard, HA) gets the
# last position immediately instead of waiting for the next slide.
#
# Defaults target the homelab lab broker on appserv1 (192.168.4.148:1883,
# anonymous on the LAN). Override via env (MQTT_BROKER / MQTT_PORT / SLIDER_TOPIC)
# or the flags below.
#
# Requires: pyserial, paho-mqtt>=2  (pip install -r requirements.txt)

import argparse
import json
import os
import sys

import paho.mqtt.client as mqtt

from console10_slider import Console10Slider, find_ports, pick_data_port

DEFAULT_BROKER = os.getenv("MQTT_BROKER", "192.168.4.148")   # appserv1 lab broker
DEFAULT_MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEFAULT_TOPIC = os.getenv("SLIDER_TOPIC", "console10/slider/value")


def main():
    ap = argparse.ArgumentParser(description="Bridge a Console10 Slider to MQTT.")
    ap.add_argument("--port", help="serial port (default: auto-detect data channel)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host")
    ap.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    ap.add_argument("--topic", default=DEFAULT_TOPIC)
    ap.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    ap.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    ap.add_argument("--qos", type=int, default=0, choices=[0, 1, 2])
    ap.add_argument("--no-retain", action="store_true", help="don't retain (default: retain)")
    ap.add_argument("--scalar", action="store_true",
                    help="publish just the 0..1 value instead of the JSON object")
    ap.add_argument("--verbose", "-v", action="store_true", help="print each publish")
    ap.add_argument("--list", action="store_true", help="list candidate serial ports and exit")
    args = ap.parse_args()

    if args.list:
        ports = find_ports()
        if not ports:
            print("No Adafruit serial ports found.")
        else:
            print("Candidate ports (data channel is usually the higher-numbered one):")
            for dev, desc in ports:
                print("  {}\t{}".format(dev, desc))
        return 0

    port = args.port or pick_data_port()
    if not port:
        ap.error("no serial port given and none auto-detected (use --list)")
    retain = not args.no_retain

    # paho-mqtt 2.x requires the callback_api_version. Unique client id per PID so
    # two instances don't boot each other off the broker.
    client = mqtt.Client(
        client_id="console10-slider-{}".format(os.getpid()),
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    if args.username:
        client.username_pw_set(args.username, args.password or None)

    def on_connect(c, userdata, flags, rc, properties=None):
        print("[mqtt] connected" if rc == 0 else "[mqtt] connect failed rc={}".format(rc))

    def on_disconnect(c, userdata, *a):
        print("[mqtt] disconnected")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    print("[bridge] {} -> {}:{}  topic={}  retain={}".format(
        port, args.broker, args.mqtt_port, args.topic, retain))
    client.connect(args.broker, args.mqtt_port, keepalive=60)
    client.loop_start()  # background network thread; reconnects automatically

    try:
        with Console10Slider(port, baudrate=args.baud) as slider:
            for reading in slider.readings():
                payload = str(reading["value"]) if args.scalar else json.dumps(reading)
                client.publish(args.topic, payload, qos=args.qos, retain=retain)
                if args.verbose:
                    print("-> {} {}".format(args.topic, payload))
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
