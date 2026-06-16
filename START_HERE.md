# START HERE 👋

This is the simplest way to get your trading bot running. You do **not** need to
know how to code. You will type just a few commands. Each one is on its own line
— copy it, paste it into the black "console" window, and press **Enter**.

> Wherever you see `<USER>`, replace it with your PythonAnywhere username.

---

## Step 1 — Open the console
1. Log in to **pythonanywhere.com**
2. Click **Consoles** at the top
3. Click **Bash** — a black window opens. This is where you paste commands.

## Step 2 — Download the program
Paste this and press Enter:

```
cd ~ && git clone https://github.com/haidar-boop/jeixg.git Jeixg
```

## Step 3 — Install it (one command does everything)
Paste this and press Enter, then wait until it finishes (a minute or two):

```
bash ~/Jeixg/setup.sh
```

When it's done you'll see **"SUCCESS!"** and a little results report with
numbers like `sharpe` and `win_rate`. That means everything works. 🎉

## Step 4 — Start the bot (paper trading — fake money, zero risk)
Paste this and press Enter:

```
bash ~/Jeixg/start_bot.sh
```

The bot is now running. You'll see a new line every minute showing your account.
Press **Ctrl-C** to stop it.

---

## Want it to run 24/7 (even when your computer is off)?
1. On PythonAnywhere, click **Tasks** at the top
2. Under **Always-on tasks**, paste this command and click **Create**
   (replace `<USER>`):

   ```
   bash /home/<USER>/Jeixg/start_bot.sh
   ```

That's it — the bot now runs around the clock.

---

## Want the dashboard website too?
Follow **Part G** in `docs/pythonanywhere.md`. It's a few clicks to turn on a
web page that shows your portfolio, trades, and charts.

---

## When you're ready for a real broker (later, no rush)
Right now the bot uses pretend money inside the program. When you've watched it
for a while and trust it, you can connect a real broker's **paper account**
(still fake money, but realistic) and then go **live**. Those steps are in
`docs/pythonanywhere.md`, Section 6 — or just ask your helper and they'll walk
you through it.

## If anything goes wrong
If a command shows **red text** or an error, **stop** and copy everything the
window shows. Send it to your helper. Don't worry — nothing here can lose money;
it's all simulated until you deliberately connect a real broker.
