#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.wildidea.web.plist"
LOG_DIR="$APP_DIR/logs"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.wildidea.web</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APP_DIR/deploy/macmini/start.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$APP_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/wildidea.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/wildidea.err.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
launchctl start com.wildidea.web

echo "Installed launch agent: $PLIST"
echo "Logs: $LOG_DIR/wildidea.out.log and $LOG_DIR/wildidea.err.log"
echo "Health check: curl http://127.0.0.1:8000/"
