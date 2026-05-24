#!/bin/bash
set -euo pipefail

if ! ls /Library/Input\ Methods/Squirrel.app &>/dev/null; then
    brew install --cask squirrel
    echo "Squirrel installed. Please log out and log in, then add Squirrel in System Settings > Keyboard > Input Sources."
else
    echo "Squirrel already installed."
fi

# Install HanaMin font for CJK Extension B+ character support.
# Without this, rare characters in Rime's luna_pinyin dictionary render as tofu blocks.
if ! ls "$HOME/Library/Fonts/HanaMinB.ttf" &>/dev/null; then
    brew install font-hanamin
    echo "HanaMin font installed for CJK Extension B+ coverage."
else
    echo "HanaMin font already installed."
fi

RIME_DIR="$HOME/Library/Rime"
mkdir -p "$RIME_DIR/lua" "$RIME_DIR/scripts"

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ln -sf "$SCRIPT_DIR/rime/default.custom.yaml" "$RIME_DIR/default.custom.yaml"
ln -sf "$SCRIPT_DIR/rime/luna_pinyin.custom.yaml" "$RIME_DIR/luna_pinyin.custom.yaml"
ln -sf "$SCRIPT_DIR/rime/squirrel.custom.yaml" "$RIME_DIR/squirrel.custom.yaml"
ln -sf "$SCRIPT_DIR/rime/lua/rerank_filter.lua" "$RIME_DIR/lua/rerank_filter.lua"
ln -sf "$SCRIPT_DIR/rime/lua/select_notifier.lua" "$RIME_DIR/lua/select_notifier.lua"
ln -sf "$SCRIPT_DIR/rime/lua/json_helper.lua" "$RIME_DIR/lua/json_helper.lua"
ln -sf "$SCRIPT_DIR/scripts/ranker_client.py" "$RIME_DIR/scripts/ranker_client.py"

# Compile C socket relay for fast Lua→ranker communication (~2ms startup)
if [ -f "$SCRIPT_DIR/scripts/ranker_relay.c" ] && command -v cc &>/dev/null; then
    cc -O2 -o "$SCRIPT_DIR/scripts/ranker_relay" "$SCRIPT_DIR/scripts/ranker_relay.c"
    echo "C relay compiled."
fi

echo "RIME config linked. Run 'Deploy' from Squirrel menu to apply."
