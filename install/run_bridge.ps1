# Activate the project venv and run the fader bridge. Used by the Scheduled Task
# and for manual runs. Extra args pass through.
$repo = Split-Path -Parent $PSScriptRoot
& "$repo\.venv\Scripts\python.exe" "$repo\host\fader_mqtt_bridge.py" @args
