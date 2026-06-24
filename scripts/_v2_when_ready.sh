#!/usr/bin/env bash
cd "$(dirname "$0")/.."
for i in $(seq 1 25); do
  if python -c "import warnings;warnings.filterwarnings('ignore');import yfinance as yf,sys;d=yf.download('SPY',period='5d',progress=False,auto_adjust=True);sys.exit(0 if len(d)>0 else 1)" 2>/dev/null; then
    echo "Yahoo back (attempt $i) -- running real v2 backtest..."
    QT_TEST_PROVIDER=yfinance python scripts/ensemble_v2_research.py > /tmp/v2real.txt 2>&1
    echo "REAL_RUN_DONE"
    exit 0
  fi
  sleep 120
done
echo "TIMEOUT: Yahoo still throttled after ~50min"
