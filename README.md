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
