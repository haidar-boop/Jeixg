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
STRATEGY="buy_and_hold"             # buy the basket and hold (best PnL in the shootout)
BROKER="alpaca"                     # "alpaca" = your Alpaca paper account | "paper" = offline simulator
PROVIDER="yfinance"                 # "yfinance" = real market data | "synthetic" = offline test data
INTERVAL="120"                      # seconds between each scan
ASK_PERMISSION="no"                 # "no" = auto-trade ALL stocks (no permission texts) | "yes" = auto-trade CORE, text for permission on the rest
MAX_CAPITAL="1000"                  # most money the bot may deploy (e.g. 1000). Use "0" for no cap.
STOP_LOSS_PCT="0"                   # OFF for true buy-and-hold (ride out dips). Set 0.08 to add an 8% safety stop.

# The full list of stocks the bot trades.
ALL_STOCKS="AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ,AVGO,COST,HD,BAC,DIS,PYPL,INTC,CRM,PFE,KO,PEP,CSCO,ORCL,ADBE,QCOM,UBER,SHOP,COIN,PLTR,SOFI,BA,GE,F,T,MU"
# When ASK_PERMISSION="yes", these are auto-traded and the REST need your YES/NO.
CORE_STOCKS="AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ"
# -------------------------------------------------------------------------

# Always uses the approval engine (keeps protective stops + SELL ALL kill-switch).
ARGS=(--loop --strategy "$STRATEGY" --broker "$BROKER" --provider "$PROVIDER" --interval "$INTERVAL" --require-approval)
[ "$MAX_CAPITAL" != "0" ] && ARGS+=(--max-capital "$MAX_CAPITAL")
ARGS+=(--stop-loss-pct "$STOP_LOSS_PCT" --universe "$ALL_STOCKS")
if [ "$ASK_PERMISSION" = "yes" ]; then
  ARGS+=(--auto-symbols "$CORE_STOCKS")   # core auto-trades; the rest text you
else
  ARGS+=(--auto-symbols "$ALL_STOCKS")    # everything auto-trades; no permission texts
fi

echo "Starting the bot ($BROKER, $PROVIDER, ask_permission=$ASK_PERMISSION). Press Ctrl-C to stop."
python run_bot.py "${ARGS[@]}"
