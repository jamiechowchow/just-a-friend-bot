# Just A Friend

A warm, casual Telegram companion bot that checks in daily and chats like a friend.

This is being built step by step. Right now the bot can only do one thing:
reply to `/start` and echo back whatever text you send it. That's on purpose —
it's the smallest possible version, just to prove the connection to Telegram
works end to end. Scheduling, buttons, the AI replies, and the database come next.

## How it's organized

```
just-a-friend-bot/
  bot/
    __init__.py
    config.py   # loads secrets (API keys) from a .env file
    main.py     # the actual bot: commands + message handling
  requirements.txt   # list of Python packages this project needs
  .env.example        # template for your secrets file
  .gitignore           # tells git which files NOT to save (secrets, caches)
```

## Setup (do this once)

1. **Create a virtual environment** (an isolated space for this project's
   Python packages, so they don't clash with anything else on your machine):

   ```bash
   cd just-a-friend-bot
   python3 -m venv .venv
   source .venv/bin/activate   # on Windows: .venv\Scripts\activate
   ```

2. **Install the dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Add your bot token**:

   ```bash
   cp .env.example .env
   ```

   Then open `.env` in a text editor and paste in the token you got from
   [@BotFather](https://t.me/BotFather) after `TELEGRAM_BOT_TOKEN=`.
   The `.env` file is listed in `.gitignore`, so it will never get committed
   to git or uploaded anywhere — that's where secrets belong.

## Running it

```bash
python -m bot.main
```

You should see a log line saying "Bot is starting...". Now open Telegram,
find your bot, and send it `/start`, then send it any text message. It
should reply instantly. Press `Ctrl+C` in the terminal to stop it.

## What's next

Once this basic version is confirmed working, we'll add (in order):
1. SQLite database to store users and their check-in answers
2. `/start` onboarding (timezone + preferred check-in time) and `/settings`
3. Scheduled morning/evening check-ins with inline buttons
4. Claude-powered warm replies to whatever the user says

## Deploying to Railway

The bot runs with polling (`app.run_polling()`), so it doesn't need a public
URL or an open port — it's a background worker, not a web service. Railway
hosts this fine.

1. **Push this repo to GitHub** (already done if you're reading this on a
   branch that's pushed).
2. **In Railway**, create a new project → "Deploy from GitHub repo" → pick
   this repo and branch.
3. Railway will detect the `Procfile` (`worker: python -m bot.main`) and
   `.python-version` and build automatically — no extra config needed.
4. **Set environment variables** in the Railway service's Variables tab:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `DB_PATH=/data/just_a_friend.db`
5. **Attach a Volume** (Railway dashboard → service → "Volumes") mounted at
   `/data`. Without this, the SQLite file lives on the container's disk and
   gets wiped every time you redeploy — the volume makes user data survive
   deploys and restarts.
6. Deploy. Check the service logs for `Bot is starting...` to confirm it's
   running, then message the bot on Telegram to test it end to end.

## Where this is headed

The near-term goal isn't just "keep this bot running for me" — it's to get
this to a state where it could be sold to the public as a real product
(many independent people signing up on their own, not just one or two
friends). That changes what "done" looks like, so a few things are
deliberately *not* built yet and are worth remembering as milestones,
roughly in the order they'll matter:

1. **A real multi-user database.** SQLite (a single file) is fine for
   validating the idea with a handful of people, but it isn't built for many
   concurrent strangers. Before opening this up publicly, this needs to
   move to a proper hosted database (e.g. Postgres — Railway can add this
   as a one-click service on the same platform, no re-hosting required).
2. **Onboarding, privacy policy, and terms of service.** Right now access
   is just "whoever has the Telegram link." Selling to the public means a
   real signup flow plus a privacy policy — this bot stores personal
   journaling/check-in data, which is sensitive and comes with real privacy
   expectations and (depending on where users are) legal obligations.
3. **A way to actually charge money.** No billing exists yet. Options when
   the time comes: Telegram's built-in Payments API, or Stripe with account
   linking.

None of this needs to happen now — it's here so the roadmap stays visible
as development continues, not just in one conversation's memory.
