#!/usr/bin/env bash
#
# Start the QuantTrade bot.
#
# Currently configured for ALPACA PAPER TRADING (real broker, simulated money,
# zero financial risk) using real market data. To go back to the fully offline
# simulator, set BROKER="paper" and PROVIDER="synthetic" below.
#
# How to use it:
#     bash start_bot.sh
#
# Press Ctrl-C to stop it.

set -uo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "It looks like setup hasn't been run yet. Run this first:"
  echo "    bash setup.sh"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ----- Settings you can change ------------------------------------------
STRATEGY="rsi_reversion"            # which strategy to trade (active dip-buyer)
BROKER="alpaca"                     # "alpaca" = your Alpaca paper account | "paper" = offline simulator
PROVIDER="yfinance"                 # "yfinance" = real market data | "synthetic" = offline test data
INTERVAL="120"                      # seconds between each scan
APPROVAL="yes"                      # "yes" = text you for YES/NO before buying | "no" = buy automatically
# Stocks to hunt across (leave blank to use the built-in 40-stock list).
SYMBOLS=""
# -------------------------------------------------------------------------

ARGS=(--loop --strategy "$STRATEGY" --broker "$BROKER" --provider "$PROVIDER" --interval "$INTERVAL")
if [ "$APPROVAL" = "yes" ]; then
  ARGS+=(--require-approval)
  [ -n "$SYMBOLS" ] && ARGS+=(--universe "$SYMBOLS")
else
  ARGS+=(--symbols "${SYMBOLS:-AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ}")
fi

echo "Starting the bot ($BROKER, $PROVIDER, approval=$APPROVAL). Press Ctrl-C to stop."
python run_bot.py "${ARGS[@]}"
