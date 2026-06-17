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
APPROVAL="yes"                      # "yes" = ask before buying NON-core stocks | "no" = buy everything automatically
ASK_FOR_OTHERS="no"                 # "yes" = scan wider list & text you for permission | "no" = trade ONLY your core list (no permission texts)
MAX_CAPITAL="1000"                  # most money the bot may deploy (e.g. 1000). Use "0" for no cap.
STOP_LOSS_PCT="0.08"                # protective stop placed under each position (0.08 = 8%; "0" = off)

# Your trusted core: these are traded AUTOMATICALLY, no text permission needed.
CORE_STOCKS="AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ"
# Wider pool to also hunt across; anything here NOT in CORE_STOCKS will text you
# for YES/NO approval. Leave blank to use the built-in 40-stock pool.
EXTRA_SCAN=""
# -------------------------------------------------------------------------

ARGS=(--loop --strategy "$STRATEGY" --broker "$BROKER" --provider "$PROVIDER" --interval "$INTERVAL")
[ "$MAX_CAPITAL" != "0" ] && ARGS+=(--max-capital "$MAX_CAPITAL")
ARGS+=(--stop-loss-pct "$STOP_LOSS_PCT")
if [ "$APPROVAL" = "yes" ]; then
  ARGS+=(--require-approval --auto-symbols "$CORE_STOCKS")
  if [ "$ASK_FOR_OTHERS" = "yes" ]; then
    [ -n "$EXTRA_SCAN" ] && ARGS+=(--universe "$EXTRA_SCAN")
  else
    ARGS+=(--universe "$CORE_STOCKS")   # no non-core symbols -> no permission texts
  fi
else
  ARGS+=(--symbols "$CORE_STOCKS")
fi

echo "Starting the bot ($BROKER, $PROVIDER, approval=$APPROVAL). Press Ctrl-C to stop."
python run_bot.py "${ARGS[@]}"
