#!/usr/bin/env bash
#
# Update QuantTrade to the latest version (downloads new changes + reinstalls).
#
# How to use it:
#     bash update.sh
#
# Safe to run any time. It will NOT touch your .env (your secrets / settings).

set -uo pipefail
cd "$(dirname "$0")"

echo "Updating QuantTrade..."
git pull origin claude/algo-trading-platform-yxbvk0

if [ ! -d ".venv" ]; then
  echo "No environment found - running first-time setup instead."
  exec bash setup.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -e . >/dev/null 2>&1 || pip install -e .
pip install -e ".[web,wsgi,data,security]" >/dev/null 2>&1 || true

echo ""
echo "=================================================="
echo "  Updated! Restart the bot for changes to apply:"
echo "    - if running in a console: press Ctrl-C, then  bash start_bot.sh"
echo "    - if running 24/7: go to Tasks and click the"
echo "      restart/reload arrow on your Always-on task."
echo "=================================================="
