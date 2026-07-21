import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from bot import db
from bot.config import TELEGRAM_BOT_TOKEN
from bot.onboarding import onboarding_conversation, settings_conversation

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"You said: {update.message.text}")


def main() -> None:
    db.init_db()

    # Python 3.14 removed the automatic background event loop that older
    # versions created on demand. python-telegram-bot 21.x still expects
    # one to exist, so we create and register it ourselves before the
    # library looks for it.
    asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # These two handle the multi-step /start and /settings conversations.
    # They only "claim" a message if that chat is mid-conversation with
    # them, so plain messages fall through to the echo handler below.
    app.add_handler(onboarding_conversation)
    app.add_handler(settings_conversation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logger.info("Bot is starting... (Ctrl+C to stop)")
    app.run_polling()


if __name__ == "__main__":
    main()
