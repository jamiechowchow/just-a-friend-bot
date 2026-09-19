import os

from dotenv import load_dotenv

# Reads the ".env" file (if present) and copies its values into the
# environment, so os.environ.get() below can find them.
load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Where the SQLite database file lives. SQLite is just a single file on
# disk — no separate database server to install or run.
DB_PATH = os.environ.get("DB_PATH", "just_a_friend.db")

# Telegram chat IDs allowed to use admin-only commands like /stats.
# Comma-separated, e.g. "111111,222222". Optional — /stats just won't
# respond to anyone if this isn't set.
ADMIN_CHAT_IDS = {
    int(chat_id) for chat_id in os.environ.get("ADMIN_CHAT_IDS", "").split(",") if chat_id.strip()
}

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
    )

if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY is not set. Add it to your .env file — the bot's replies "
        "are powered by Claude, so this is required."
    )
