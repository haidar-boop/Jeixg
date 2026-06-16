#!/usr/bin/env bash
#
# QuantTrade one-step setup.
# A non-coder can run this once and it installs everything.
#
# How to use it (in a PythonAnywhere Bash console, or any Mac/Linux terminal):
#     bash setup.sh
#
# It creates an isolated environment, installs the platform, and runs a quick
# self-test so you can SEE that it works.

set -uo pipefail

# Always work from the folder this script lives in (the project root).
cd "$(dirname "$0")"

echo ""
echo "=================================================="
echo "  QuantTrade setup - sit back, this takes a minute"
echo "=================================================="
echo ""

# 1. Make sure we're on the right version of the code (harmless if already there).
git checkout claude/algo-trading-platform-yxbvk0 >/dev/null 2>&1 || true

# 2. Pick a Python (prefer 3.11, fall back to whatever python3 is available).
PY=python3.11
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi
echo "[1/4] Using $($PY --version)"

# 3. Create a private environment for the project (a sandbox just for this app).
echo "[2/4] Creating the environment (.venv)..."
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null 2>&1 || true

# 4. Install the platform. Core first (must work); web/data add-ons next (nice to have).
echo "[3/4] Installing QuantTrade (this is the slow part)..."
if ! pip install -e . ; then
  echo ""
  echo "!! Install failed. Copy everything above and send it to your helper."
  exit 1
fi
pip install -e ".[web,wsgi,data,security]" >/dev/null 2>&1 \
  || echo "    (some optional add-ons were skipped - the bot still works)"

# 5. Prove it works with a quick backtest.
echo "[4/4] Running a quick self-test..."
echo ""
if python -m quanttrade.cli backtest --strategy ma_crossover --symbols AAPL,MSFT ; then
  echo ""
  echo "=================================================="
  echo "  SUCCESS! QuantTrade is installed and working."
  echo ""
  echo "  To START THE BOT (paper trading, no real money):"
  echo "      bash start_bot.sh"
  echo ""
  echo "  To run the dashboard website setup, see:"
  echo "      docs/pythonanywhere.md  (Part G)"
  echo "=================================================="
else
  echo ""
  echo "!! The self-test failed. Send the messages above to your helper."
  exit 1
fi
