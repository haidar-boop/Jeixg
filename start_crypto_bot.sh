#!/usr/bin/env bash
#
# Start the SEPARATE crypto bot.
#
# This is a SECOND, fully isolated bot. It scans crypto, trades on PAPER (fake
# money), runs 24/7, and writes its OWN state files -- so it can NEVER interfere
# with your main stock bot. Run it as its own task / in its own console.
#
# How to use it:
#     bash start_crypto_bot.sh
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

# ----- ISOLATION: the crypto bot's own state files (do NOT change) --------
# These keep the crypto bot 100% separate from the main stock bot. Different
# heartbeat, control, approvals and watchlist files = zero interference.
export QT_HEARTBEAT_PATH="heartbeat_crypto.txt"
export QT_CONTROL_PATH="control_crypto.json"
export QT_APPROVALS_PATH="approvals_crypto.json"
export QT_WATCHLIST_PATH="watchlist_crypto.json"

# ----- Settings you can change ------------------------------------------
STRATEGY="crypto_momentum"          # your editable crypto strategy (quanttrade/strategies/crypto.py)
BROKER="paper"                      # "paper" = fake money simulator (recommended). NOT your stock broker.
PROVIDER="yfinance"                 # "yfinance" = real crypto prices | "synthetic" = offline test data
INTERVAL="300"                      # seconds between each scan (crypto is 24/7)
CASH="10000"                        # starting fake money in the paper account
MAX_CAPITAL="1000"                  # most money the bot may deploy. Use "0" for no cap.
STOP_LOSS_PCT="0.10"                # protective stop (crypto is volatile). 0.10 = 10%.

# The coins the bot scans. yfinance crypto tickers end in -USD.
# Majors (steadier) + cheaper "could run up" names. Edit this list freely.
ALL_COINS="BTC-USD,ETH-USD,SOL-USD,XRP-USD,ADA-USD,DOGE-USD,TRX-USD,LTC-USD,LINK-USD,DOT-USD,AVAX-USD,POL-USD,ATOM-USD,XLM-USD,ALGO-USD,HBAR-USD,VET-USD,FIL-USD,NEAR-USD,INJ-USD"
# -------------------------------------------------------------------------

# Uses the approval engine so protective stops + the SELL ALL kill-switch work,
# but auto-trades EVERY coin (no permission texts).
ARGS=(--loop --strategy "$STRATEGY" --broker "$BROKER" --provider "$PROVIDER" \
      --interval "$INTERVAL" --cash "$CASH" --always-open --require-approval \
      --universe "$ALL_COINS" --auto-symbols "$ALL_COINS" \
      --stop-loss-pct "$STOP_LOSS_PCT")
[ "$MAX_CAPITAL" != "0" ] && ARGS+=(--max-capital "$MAX_CAPITAL")

echo "Starting the CRYPTO bot ($BROKER, $PROVIDER, 24/7). Isolated from the main bot. Press Ctrl-C to stop."
python run_bot.py "${ARGS[@]}"
