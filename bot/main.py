import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import ai_reply, db, scheduling
from bot.config import ADMIN_CHAT_IDS, TELEGRAM_BOT_TOKEN
from bot.onboarding import onboarding_conversation, rename_conversation, settings_conversation

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text
    pending_prompt = context.chat_data.pop("pending_prompt", None)

    if pending_prompt is not None:
        db.save_response(chat_id, pending_prompt, answer_text=text)
        reply = await ai_reply.generate_reply(pending_prompt, text, chat_id)
    else:
        # No scheduled prompt was waiting on this — just an anytime message.
        reply = await ai_reply.generate_freeform_reply(text, chat_id)

    scheduling.maybe_schedule_crisis_followup(chat_id, text, reply)
    await update.message.reply_text(reply)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ADMIN_CHAT_IDS:
        return  # Silent no-op for anyone who isn't an admin — no hint this command exists.

    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    total = db.count_users()
    onboarded = db.count_onboarded_users()
    active = db.count_active_users_since(since)
    await update.message.reply_text(
        f"Total users: {total}\n"
        f"Finished onboarding: {onboarded}\n"
        f"Active in last 7 days: {active}"
    )


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id not in ADMIN_CHAT_IDS:
        return

    users = db.list_users()
    if not users:
        await update.message.reply_text("No users yet.")
        return

    lines = []
    for user in users:
        name = user["name"] or "(no name)"
        email = user["email"] or "(no email)"
        joined = user["created_at"][:10]
        lines.append(f"{name} — {email} — joined {joined} — chat_id {user['chat_id']}")
    await update.message.reply_text("\n".join(lines))


async def _post_init(application: Application) -> None:
    scheduling.schedule_all_users(application.job_queue)
    # Source of truth for "is a crisis follow-up due" lives in the database
    # (see db.schedule_crisis_followup), not in this job's own timer — so a
    # redeploy between now and when one comes due can't lose it. This just
    # sweeps for anything that's become due since the last check.
    application.job_queue.run_repeating(
        scheduling.check_crisis_followups, interval=timedelta(minutes=30), first=10
    )


def main() -> None:
    db.init_db()

    # Python 3.14 removed the automatic background event loop that older
    # versions created on demand. python-telegram-bot 21.x still expects
    # one to exist, so we create and register it ourselves before the
    # library looks for it.
    asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    # These handle the multi-step /start, /settings, and /rename
    # conversations. They only "claim" a message if that chat is
    # mid-conversation with them, so plain messages fall through to
    # handle_free_text below.
    app.add_handler(onboarding_conversation)
    app.add_handler(settings_conversation)
    app.add_handler(rename_conversation)
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CallbackQueryHandler(scheduling.handle_button_tap))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))

    logger.info("Bot is starting... (Ctrl+C to stop)")
    app.run_polling()


if __name__ == "__main__":
    main()
