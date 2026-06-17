# Deploying QuantTrade on PythonAnywhere

This guide targets a **paid PythonAnywhere account** (Hacker tier or above) and
covers all three pieces:

1. **Backtests / scans** — run on demand from a Bash console.
2. **The trading bot** — `run_bot.py` as an **Always-on task**.
3. **The dashboard** — served via the **Flask WSGI shim** (`quanttrade.api.wsgi`)
   as a PythonAnywhere **Web app**.

> **Why a Flask shim?** PythonAnywhere serves **WSGI** apps only. The platform's
> primary API is FastAPI (ASGI) with WebSockets, which PA cannot run. The
> included Flask shim exposes the same REST endpoints and serves the built React
> UI. The dashboard works via REST polling; there's no live WebSocket push on PA
> (the UI degrades gracefully).

> **Paid tier is required** for: full outbound internet (live broker/market-data
> APIs) and Always-on tasks (the continuous bot). The free tier can only run the
> bot once/day via a scheduled task and only with the offline `synthetic`
> provider.

---

## 1. Get the code onto PythonAnywhere

Open a **Bash console** (Dashboard → *Consoles* → *Bash*):

```bash
cd ~
git clone <YOUR_REPO_URL> Jeixg      # or your fork
cd Jeixg
git checkout claude/algo-trading-platform-yxbvk0
```

## 2. Create a virtualenv and install

PythonAnywhere has Python 3.10/3.11 available. Create a venv:

```bash
mkvirtualenv quanttrade --python=python3.11   # or: python3.11 -m venv ~/.venvs/quanttrade
workon quanttrade                              # if you used mkvirtualenv

pip install -e ".[web,wsgi,data,security]"
```

`wsgi` pulls in Flask (the dashboard host). `data` adds yfinance for real market
data; `security` adds credential encryption.

Smoke-test:

```bash
python -m quanttrade.cli backtest --strategy ma_crossover --symbols AAPL,MSFT
pytest -q
```

## 3. Run backtests / scans (console)

These just run in the Bash console — nothing to deploy:

```bash
workon quanttrade
cd ~/Jeixg
python -m quanttrade.cli backtest --provider yfinance --strategy momentum --symbols AAPL,MSFT
python -m quanttrade.cli scan --provider yfinance --symbols AAPL,MSFT,TSLA,NVDA,SPY
python examples/optimize_strategy.py
```

## 4. Run the bot — Always-on task

Dashboard → *Tasks* → **Always-on tasks** → add:

```
/home/<USER>/.virtualenvs/quanttrade/bin/python /home/<USER>/Jeixg/run_bot.py --loop --strategy ma_crossover --symbols AAPL,MSFT,GOOG --broker paper --provider synthetic --interval 60
```

Notes:
- Replace `<USER>` with your PythonAnywhere username.
- `--broker paper` + `--provider synthetic` = safe, no creds, no network.
- For real (delayed) data while still paper trading: `--provider yfinance`.
- The task auto-restarts if it dies. Logs go to the task's log page and to
  `~/Jeixg/logs/quanttrade.log`.

## 5. Serve the dashboard — Web app (Flask WSGI)

### 5a. Build the React frontend

You can build locally and upload, or build in a PA console if Node is available.
Locally is easiest:

```bash
cd dashboard
npm install
npm run build          # outputs dashboard/dist/
```

Upload the `dashboard/dist/` folder to `~/Jeixg/dashboard/dist/` on
PythonAnywhere (the *Files* tab, or commit `dist/` and `git pull`). The Flask
shim auto-detects and serves it.

### 5b. Create the web app

Dashboard → *Web* → **Add a new web app** → **Manual configuration** →
Python 3.11.

Then set:

- **Virtualenv**: `/home/<USER>/.virtualenvs/quanttrade`
- **WSGI configuration file** (click to edit) — replace contents with the
  following to show your **live Alpaca account** on the dashboard:

  ```python
  import sys
  path = "/home/<USER>/Jeixg"
  if path not in sys.path:
      sys.path.insert(0, path)

  import os
  # Make the dashboard read your live Alpaca paper account + real market data.
  os.environ["QT_BROKER__NAME"] = "alpaca"
  os.environ["QT_DATA__PROVIDER"] = "yfinance"
  os.environ["QT_SYMBOLS"] = "AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ,AVGO,COST,HD,BAC,DIS,PYPL,INTC,CRM,PFE,KO,PEP,CSCO,ORCL,ADBE,QCOM,UBER,SHOP,COIN,PLTR,SOFI,BA,GE,F,T,MU"
  # Alpaca / Twilio keys are read from ~/Jeixg/.env automatically.

  from quanttrade.api.wsgi import application   # noqa: E402
  ```

- (Optional) **Static files** mapping for faster asset serving:
  URL `/assets/` → Directory `/home/<USER>/Jeixg/dashboard/dist/assets/`

Click **Reload**. Your dashboard is now at `https://<USER>.pythonanywhere.com/`
and the API at `https://<USER>.pythonanywhere.com/api/health`.

> The dashboard auto-refreshes every 20s by polling the API (PythonAnywhere
> doesn't support WebSockets, so there's no instant push — the periodic refresh
> and the ↻ button keep it current). If `/api/health` shows `"mode": "live"` and
> `"broker_connected": true`, it's reading your real Alpaca account.

## 6. Going live later (after paper testing)

When you're ready to trade real money through a broker (e.g. Alpaca):

1. Install the broker SDK in the venv (e.g. `pip install alpaca-trade-api` or
   `requests` for the REST adapters).
2. Set credentials as environment variables — **never commit them**. For the
   Always-on task, prefix them in the command or set them in a small wrapper
   script:

   ```bash
   #!/bin/bash
   export QT_SECRET_KEY="..."
   export QT_ALPACA_API_KEY="..."
   export QT_ALPACA_API_SECRET="..."
   /home/<USER>/.virtualenvs/quanttrade/bin/python /home/<USER>/Jeixg/run_bot.py \
       --loop --broker alpaca --provider yfinance --strategy ma_crossover \
       --symbols AAPL,MSFT --interval 60
   ```

   Save as `~/Jeixg/run_live.sh`, `chmod +x`, and point the Always-on task at it.
3. For the web app, set the same env vars in the WSGI file's `os.environ` block.
4. Start with tiny size and conservative `risk.*` limits in `config/config.yaml`.
   Confirm the daily-loss / drawdown halts work before scaling up.

> **Risk warning.** Live mode places real orders. Validate thoroughly in paper
> mode first; markets are unpredictable and you can lose money. Trade at your own
> risk.

## 7. Two-way SMS trade approval

The bot can scan a universe of stocks and **text you for permission** before
buying ("I found NVDA @ $120 (RSI 27, oversold). Reply YES to buy or NO to
skip."). You reply YES/NO and it acts. Exits are handled automatically.

Enable it:

1. In `start_bot.sh`, keep `APPROVAL="yes"` (the default). Restart the bot task.
2. Tell Twilio where to deliver your replies: in the Twilio Console open your
   phone number's settings → **Messaging** → *"A MESSAGE COMES IN"* → set it to
   **Webhook**, **HTTP POST**, URL:

   ```
   https://<USER>.pythonanywhere.com/sms
   ```

   Save. (This requires the dashboard web app from section 5 to be running, since
   it receives the replies.)

Now when the bot finds an opportunity it texts you; your YES/NO reply is sent by
Twilio to `/sms`, recorded, and the bot buys on its next scan if you approved.
Only your verified number (`QT_TWILIO_TO`) is accepted.

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| `ModuleNotFoundError: quanttrade` | Web app virtualenv not set, or `sys.path` missing the repo path in the WSGI file. |
| Dashboard shows "Build the dashboard…" text | `dashboard/dist/` not present on the server — build & upload it. |
| Bot can't reach broker/Yahoo | Confirm you're on a **paid** tier (free tier blocks non-whitelisted internet). |
| Always-on task keeps restarting | Check its log; run the same command in a console to see the traceback. |
| `cryptography` import warning | Optional; install it (`pip install cryptography`) or ignore — secrets just won't be encrypted at rest. |
