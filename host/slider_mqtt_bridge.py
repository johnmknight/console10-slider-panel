#!/usr/bin/env python3
# slider_mqtt_bridge.py - DEPRECATED.
#
# The original single-device bridge (one board -> the single retained topic
# console10/slider/value) has been replaced by fader_mqtt_bridge.py, which
# supports MULTIPLE faders and full Home Assistant MQTT Discovery. This shim just
# forwards so any old command or script keeps working.

import sys

from fader_mqtt_bridge import main

if __name__ == "__main__":
    print(
        "[deprecated] slider_mqtt_bridge.py is now fader_mqtt_bridge.py "
        "(multi-device + Home Assistant). Forwarding...",
        file=sys.stderr,
    )
    raise SystemExit(main())
