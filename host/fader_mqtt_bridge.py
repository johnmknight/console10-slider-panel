#!/usr/bin/env python3
# fader_mqtt_bridge.py - bridge one OR MORE Knight Home Tech mechanical faders to
# Home Assistant over MQTT. The QT Py RP2040 has no radio, so this host process
# is what actually talks to the broker and to HA's MQTT Discovery.
#
# What it does, per connected fader (auto-discovered by USB):
#   * derives a stable identity from the board's device id (see ha_fader.py)
#   * publishes a RETAINED HA Discovery config  -> HA auto-creates a read-only
#     "%" sensor (NOT a number entity - the fader is the source of truth)
#   * manages availability: an LWT marks the device "offline" if the bridge dies,
#     and it publishes "online" on connect
#   * publishes the integer position (0-100) to the state topic on change
#
# Topics (per device id "a1b2c3"; full spec in ../docs/HA_INTEGRATION.md):
#   knighthometech/fader_a1b2c3/position                         <- state, int 0..100
#   knighthometech/fader_a1b2c3/status                           <- online|offline
#   homeassistant/sensor/knighthometech_fader_a1b2c3_position/config  <- retained discovery
#
# Multiple faders: each gets its OWN MQTT connection so each has its own LWT.
# New faders plugged in while running are picked up on the next rescan.
#
# Requires: pyserial, paho-mqtt>=2  (pip install -r requirements.txt)

import argparse
import json
import os
import sys
import threading
import time

import serial                       # for SerialException
import paho.mqtt.client as mqtt

from console10_slider import Console10Slider, discover_faders
from ha_fader import (
    FaderIdentity,
    discovery_payload,
    ONLINE,
    OFFLINE,
    NAMESPACE,
    DISCOVERY_PREFIX,
    DEVICE_NAME,
)


def log(msg):
    print(msg, flush=True)


# --- tiny .env loader (no dependency) ---------------------------------------
def _load_env_file():
    """Load KEY=VALUE lines from host/.env into os.environ (without overriding
    already-set vars). Lets the installed service pick up broker config from the
    .env the setup script wrote, with no python-dotenv dependency."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())
    except OSError:
        pass


def _env_bool(name, default):
    """Parse a truthy/falsey env var (1/0, true/false, yes/no)."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _clamp_pct(pct):
    """Coerce a reading's pct to an int clamped to 0..100, or None if unusable."""
    try:
        p = int(round(float(pct)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, p))


def _connect_failed(reason_code):
    """True if a paho-2.x on_connect reason_code indicates failure."""
    if hasattr(reason_code, "is_failure"):
        return reason_code.is_failure
    return reason_code != 0


class BridgeConfig:
    """Resolved bridge settings shared by every FaderDevice."""

    def __init__(self, args):
        self.broker = args.broker
        self.mqtt_port = args.mqtt_port
        self.username = args.username
        self.password = args.password
        self.prefix = args.prefix
        self.discovery_prefix = args.discovery_prefix
        self.default_name = args.name
        self.fw_version = args.fw_version
        self.position_retain = (not args.no_position_retain) and _env_bool("POSITION_RETAIN", True)
        self.baud = args.baud
        self.verbose = args.verbose
        self.rescan = args.rescan
        self._names = _load_names(args.names_file)

    def name_for(self, uid):
        return self._names.get(uid, self.default_name)


def _load_names(path):
    """Optional uid -> friendly-name overrides from a JSON file (so two faders
    can read e.g. 'Studio Fader' / 'Desk Fader'). Missing file -> no overrides."""
    if not path:
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError) as e:
        log("[names] ignoring {}: {}".format(path, e))
        return {}


class FaderDevice:
    """One physical fader: its own serial reader + its own MQTT connection."""

    def __init__(self, port, uid, serial_number, cfg):
        self.port = port
        self.uid = uid
        self.serial_number = serial_number
        self.cfg = cfg
        self.identity = FaderIdentity(uid, prefix=cfg.prefix, discovery_prefix=cfg.discovery_prefix)
        self.name = cfg.name_for(uid)
        self.client = None
        self._thread = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._last_pct = None

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="fader-" + self.uid, daemon=True)
        self._thread.start()

    def alive(self):
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        c = self.client
        if c is not None:
            self.client = None
            try:
                c.publish(self.identity.status_topic, OFFLINE, qos=1, retain=True)
                c.loop_stop()
                c.disconnect()
            except Exception:
                pass

    # -- MQTT ----------------------------------------------------------------
    def _make_client(self):
        c = mqtt.Client(
            client_id="kht-fader-{}-{}".format(self.uid, os.getpid()),
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if self.cfg.username:
            c.username_pw_set(self.cfg.username, self.cfg.password or None)
        # Last Will: if THIS connection drops unexpectedly, the broker publishes
        # offline on the device's status topic so HA marks it unavailable.
        c.will_set(self.identity.status_topic, OFFLINE, qos=1, retain=True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        return c

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if _connect_failed(reason_code):
            log("[{}] MQTT connect failed: {}".format(self.uid, reason_code))
            return
        # Spec boot order: availability online, then retained discovery, then the
        # current position - all retained so HA recovers fully after a restart.
        client.publish(self.identity.status_topic, ONLINE, qos=1, retain=True)
        payload = json.dumps(discovery_payload(self.identity, self.name, self.cfg.fw_version))
        client.publish(self.identity.config_topic, payload, qos=1, retain=True)
        if self._last_pct is not None:
            client.publish(self.identity.state_topic, str(self._last_pct),
                           qos=0, retain=self.cfg.position_retain)
        self._connected.set()
        log("[{}] online: HA sensor {} ({})".format(
            self.uid, self.identity.entity_unique_id, self.name))

    def _on_disconnect(self, client, userdata, *a):
        self._connected.clear()

    # -- serial loop ---------------------------------------------------------
    def _run(self):
        self.client = self._make_client()
        try:
            self.client.connect(self.cfg.broker, self.cfg.mqtt_port, keepalive=60)
        except Exception as e:
            log("[{}] MQTT connect error: {}".format(self.uid, e))
            self.client = None
            return
        self.client.loop_start()  # background network thread; auto-reconnects
        log("[{}] {} -> {}:{}".format(self.uid, self.port, self.cfg.broker, self.cfg.mqtt_port))
        try:
            with Console10Slider(self.port, baudrate=self.cfg.baud) as slider:
                for reading in slider.readings():
                    if self._stop.is_set():
                        break
                    pct = _clamp_pct(reading.get("pct"))
                    if pct is None or pct == self._last_pct:
                        continue
                    self._last_pct = pct
                    c = self.client
                    if c is not None and self._connected.is_set():
                        c.publish(self.identity.state_topic, str(pct),
                                  qos=0, retain=self.cfg.position_retain)
                        if self.cfg.verbose:
                            log("[{}] {} -> {}%".format(self.uid, self.identity.state_topic, pct))
        except (serial.SerialException, OSError) as e:
            log("[{}] serial lost: {}".format(self.uid, e))
        except Exception as e:
            log("[{}] error: {}".format(self.uid, e))
        finally:
            self.stop()


def _remove_entities(cfg, uid=None):
    """Delete discovered (or one --uid) HA entities by clearing their retained
    discovery config. Handy in development to clear stale test devices."""
    uids = [uid] if uid else [u for _p, u, _sn in discover_faders()]
    if not uids:
        log("Nothing to remove (no faders found; pass --uid <id> to clear a disconnected one).")
        return 0
    c = mqtt.Client(client_id="kht-fader-remove-{}".format(os.getpid()),
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if cfg.username:
        c.username_pw_set(cfg.username, cfg.password or None)
    c.connect(cfg.broker, cfg.mqtt_port, keepalive=30)
    c.loop_start()
    time.sleep(0.5)
    for u in uids:
        ident = FaderIdentity(u, prefix=cfg.prefix, discovery_prefix=cfg.discovery_prefix)
        c.publish(ident.config_topic, "", qos=1, retain=True)   # empty retained -> HA deletes entity
        c.publish(ident.status_topic, "", qos=1, retain=True)   # clear retained availability
        log("[remove] cleared {}".format(ident.entity_unique_id))
    time.sleep(0.5)
    c.loop_stop()
    c.disconnect()
    return 0


def main():
    _load_env_file()
    ap = argparse.ArgumentParser(description="Bridge Knight Home Tech faders to Home Assistant over MQTT.")
    ap.add_argument("--broker", default=os.getenv("MQTT_BROKER", "192.168.4.51"),
                    help="MQTT broker host (must be the one HA's MQTT integration uses)")
    ap.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    ap.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    ap.add_argument("--prefix", default=os.getenv("MQTT_PREFIX", NAMESPACE),
                    help="MQTT root namespace (default: %(default)s)")
    ap.add_argument("--discovery-prefix", default=os.getenv("HA_DISCOVERY_PREFIX", DISCOVERY_PREFIX),
                    help="HA MQTT Discovery prefix (default: %(default)s)")
    ap.add_argument("--name", default=os.getenv("FADER_NAME", DEVICE_NAME),
                    help="friendly device name (default: %(default)s)")
    ap.add_argument("--names-file", default=os.getenv("FADER_NAMES_FILE"),
                    help="optional JSON file of uid -> friendly name overrides")
    ap.add_argument("--fw-version", default="1.0", help="sw_version reported to HA")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--no-position-retain", action="store_true",
                    help="don't retain position (default: retain last value)")
    ap.add_argument("--rescan", type=float, default=10.0,
                    help="seconds between hot-plug rescans (default: %(default)s)")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every position publish")
    ap.add_argument("--list", action="store_true", help="list connected faders and exit")
    ap.add_argument("--remove", action="store_true",
                    help="delete HA entities for connected faders (or --uid) and exit")
    ap.add_argument("--uid", help="target a specific device id (with --remove)")
    args = ap.parse_args()

    cfg = BridgeConfig(args)

    if args.list:
        faders = discover_faders()
        if not faders:
            print("No faders found.")
        else:
            print("Connected faders:")
            for port, uid, sn in faders:
                ident = FaderIdentity(uid, prefix=cfg.prefix, discovery_prefix=cfg.discovery_prefix)
                print("  {}  id={}  serial={}  -> {}".format(port, uid, sn, ident.state_topic))
        return 0

    if args.remove:
        return _remove_entities(cfg, args.uid)

    log("[bridge] broker {}:{}  prefix={}  discovery={}".format(
        cfg.broker, cfg.mqtt_port, cfg.prefix, cfg.discovery_prefix))

    devices = {}  # uid -> FaderDevice

    def sync():
        for port, uid, sn in discover_faders():
            if uid not in devices:
                log("[discover] fader {} on {}".format(uid, port))
                d = FaderDevice(port, uid, sn, cfg)
                devices[uid] = d
                d.start()

    sync()
    if not devices:
        log("[bridge] no faders yet - waiting (plug one in; rescan every {:.0f}s)".format(cfg.rescan))

    try:
        while True:
            time.sleep(cfg.rescan)
            sync()
            for uid in list(devices):                # prune unplugged faders
                if not devices[uid].alive():
                    log("[discover] fader {} gone".format(uid))
                    devices[uid].stop()
                    del devices[uid]
    except KeyboardInterrupt:
        pass
    finally:
        for d in list(devices.values()):
            d.stop()
        time.sleep(0.3)                              # let the offline publishes flush
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
