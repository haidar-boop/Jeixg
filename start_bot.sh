#!/usr/bin/env bash
#
# Start the QuantTrade bot in PAPER mode (simulated money - zero risk).
#
# How to use it:
#     bash start_bot.sh
#
# Press Ctrl-C to stop it.
#
# When you are ready for a real broker's paper account (Alpaca) or live trading,
# see docs/pythonanywhere.md - you only change the two settings marked below.

set -uo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "It looks like setup hasn't been run yet. Run this first:"
  echo "    bash setup.sh"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ----- Settings you can change later -------------------------------------
STRATEGY="ma_crossover"             # which strategy to trade
SYMBOLS="AAPL,MSFT,GOOG"            # which stocks to watch
BROKER="paper"                      # "paper" = built-in simulator (change to "alpaca" later)
PROVIDER="synthetic"                # "synthetic" = offline data (change to "yfinance" for real data)
INTERVAL="60"                       # seconds between each check
# -------------------------------------------------------------------------

echo "Starting the bot in PAPER mode. Press Ctrl-C to stop."
python run_bot.py --loop \
  --strategy "$STRATEGY" \
  --symbols "$SYMBOLS" \
  --broker "$BROKER" \
  --provider "$PROVIDER" \
  --interval "$INTERVAL"
