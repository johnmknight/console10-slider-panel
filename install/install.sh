#!/usr/bin/env bash
# Super-easy host setup for the Knight Home Tech fader bridge on Linux / Raspberry Pi.
# Creates a venv, installs deps, seeds host/.env, ensures serial access, and
# (unless --no-service) installs a systemd service that auto-starts the bridge on
# boot and auto-detects every plugged-in fader.
#
#   ./install/install.sh                 # full install incl. systemd service
#   ./install/install.sh --no-service    # just venv + deps + .env
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WITH_SERVICE=1
[ "${1:-}" = "--no-service" ] && WITH_SERVICE=0

echo "==> Repo: $REPO"

# 1) venv + dependencies
PY="$(command -v python3 || command -v python)"
echo "==> Creating venv (.venv) with $PY"
"$PY" -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install --upgrade pip >/dev/null
echo "==> Installing host requirements"
"$REPO/.venv/bin/pip" install -r "$REPO/host/requirements.txt"

# 2) .env (broker config)
if [ ! -f "$REPO/host/.env" ]; then
  cp "$REPO/host/.env.example" "$REPO/host/.env"
  echo "==> Seeded host/.env from the example - edit it to set your broker."
else
  echo "==> host/.env already exists - leaving it as-is."
fi

# 3) serial access: the bridge must be able to open the USB CDC ports
if getent group dialout >/dev/null 2>&1; then
  if ! id -nG "$USER" | grep -qw dialout; then
    echo "==> Adding $USER to 'dialout' (serial access; takes effect after re-login)"
    sudo usermod -aG dialout "$USER" || echo "   (couldn't add to dialout - do it manually if serial fails)"
  fi
fi

# 4) systemd service
if [ "$WITH_SERVICE" = "1" ]; then
  echo "==> Installing systemd service"
  UNIT=/etc/systemd/system/console10-fader-bridge.service
  sed -e "s|__REPO__|$REPO|g" -e "s|__USER__|$USER|g" \
      "$REPO/install/console10-fader-bridge.service" | sudo tee "$UNIT" >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now console10-fader-bridge.service
  echo "==> Service enabled. Logs:  journalctl -u console10-fader-bridge.service -f"
else
  echo "==> Skipped service. Run manually:  ./install/run_bridge.sh"
fi

echo
echo "Done."
echo "  Flash a board:  python tools/flash_firmware.py"
echo "  List faders:    ./install/run_bridge.sh --list"
