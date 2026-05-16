#!/bin/bash
set -euo pipefail

if ! ls /Library/Input\ Methods/Squirrel.app &>/dev/null; then
    brew install --cask squirrel
    echo "Squirrel installed. Please log out and log in, then add Squirrel in System Settings > Keyboard > Input Sources."
else
    echo "Squirrel already installed."
fi

RIME_DIR="$HOME/Library/Rime"
mkdir -p "$RIME_DIR/lua" "$RIME_DIR/scripts"

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ln -sf "$SCRIPT_DIR/rime/default.custom.yaml" "$RIME_DIR/default.custom.yaml"
ln -sf "$SCRIPT_DIR/rime/luna_pinyin.custom.yaml" "$RIME_DIR/luna_pinyin.custom.yaml"
ln -sf "$SCRIPT_DIR/rime/lua/rerank_filter.lua" "$RIME_DIR/lua/rerank_filter.lua"
ln -sf "$SCRIPT_DIR/rime/lua/select_notifier.lua" "$RIME_DIR/lua/select_notifier.lua"
ln -sf "$SCRIPT_DIR/rime/lua/json_helper.lua" "$RIME_DIR/lua/json_helper.lua"
ln -sf "$SCRIPT_DIR/scripts/ranker_client.py" "$RIME_DIR/scripts/ranker_client.py"

echo "RIME config linked. Run 'Deploy' from Squirrel menu to apply."
