#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_NAME="com.custom-ime.ranker"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

case "${1:-start}" in
    install)
        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl load "$PLIST_DST"
        echo "Ranker service installed and started."
        ;;
    uninstall)
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "Ranker service uninstalled."
        ;;
    start)
        cd "$PROJECT_DIR"
        source .venv/bin/activate
        exec python -m ranker.server
        ;;
    *)
        echo "Usage: $0 {start|install|uninstall}"
        exit 1
        ;;
esac
