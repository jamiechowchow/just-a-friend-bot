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

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
    )
