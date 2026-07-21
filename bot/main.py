import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot import db
from bot.config import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db.create_user_if_missing(update.effective_chat.id)
    await update.message.reply_text(
        "Hey! I'm Just A Friend \U0001F44B I'm still being built, but I can hear you loud and clear."
    )


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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logger.info("Bot is starting... (Ctrl+C to stop)")
    app.run_polling()


if __name__ == "__main__":
    main()
