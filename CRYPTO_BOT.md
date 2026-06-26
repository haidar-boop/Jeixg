# The Crypto Bot (separate, isolated)

This is a **second bot** that scans crypto, trades on **paper (fake money)**, and
runs **24/7**. It is completely separate from your main stock bot — different files,
different account — so it **cannot interfere** with the bot you already have running.

## How to run it

It's just like your main bot, but you run a different file:

```bash
bash start_crypto_bot.sh
```

On PythonAnywhere, set it up as **its own Always-on task** (separate from the main
bot's task), with the command:

```
bash /home/Moehaidar/Jeixg/start_crypto_bot.sh
```

That's it. You'll now have **two tasks** running side by side:
- Task 1: `start_bot.sh`        → your main stock bot (unchanged)
- Task 2: `start_crypto_bot.sh` → the new crypto bot

## Why it can't touch your main bot

The crypto bot writes its own separate state files:

| | Main bot | Crypto bot |
|---|---|---|
| Heartbeat | `heartbeat.txt` | `heartbeat_crypto.txt` |
| Controls | `control.json` | `control_crypto.json` |
| Approvals | `approvals.json` | `approvals_crypto.json` |
| Watchlist | `watchlist.json` | `watchlist_crypto.json` |
| Money | your Alpaca paper account | its own fake-money simulator |

They share nothing that matters, so one can't trip up the other.

## Settings you can change

Open `start_crypto_bot.sh` and edit the top section:
- `ALL_COINS` — the list of coins it scans (yfinance crypto tickers end in `-USD`)
- `MAX_CAPITAL` — most fake money it will deploy (default `1000`)
- `STOP_LOSS_PCT` — protective stop (default `0.10` = 10%, since crypto swings hard)
- `INTERVAL` — seconds between scans (default `300`)

## The strategy

The starter strategy lives in **`quanttrade/strategies/crypto.py`** (`crypto_momentum`).
It's heavily commented and built to "buy cheap coins that are starting to run up,
ride them, cut losers fast." **Edit it freely** — every knob is at the top in
`on_init`. This is *your* strategy to shape.

## Honest reminders

- It's on **paper money**. Paper trading hides the real cost of spreads/slippage,
  so good paper results are NOT proof it makes money. Backtest before trusting it.
- Crypto is **far more volatile** than stocks — bigger gains *and* bigger losses.
- This is education/engineering, **not financial advice**.

## Going live later (when/if you're ready)

Paper uses the offline simulator. To trade real crypto you'd switch `BROKER` to a
real crypto exchange adapter (e.g. Coinbase/Kraken) — that's a separate build we can
do once you've proven the strategy on paper. **Don't skip the paper stage.**
