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
SYMBOLS="AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ"  # stocks to watch
BROKER="alpaca"                     # "alpaca" = your Alpaca paper account | "paper" = offline simulator
PROVIDER="yfinance"                 # "yfinance" = real market data | "synthetic" = offline test data
INTERVAL="60"                       # seconds between each check
# -------------------------------------------------------------------------

echo "Starting the bot ($BROKER, $PROVIDER data). Press Ctrl-C to stop."
python run_bot.py --loop \
  --strategy "$STRATEGY" \
  --symbols "$SYMBOLS" \
  --broker "$BROKER" \
  --provider "$PROVIDER" \
  --interval "$INTERVAL"
