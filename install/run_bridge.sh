#!/usr/bin/env bash
# Activate the project venv and run the fader bridge. Used for manual runs; the
# systemd service calls the venv python directly. Extra args pass through.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec "$REPO/.venv/bin/python" "$REPO/host/fader_mqtt_bridge.py" "$@"
