import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot import db
from bot.time_parsing import parse_time_of_day, parse_timezone

logger = logging.getLogger(__name__)

ASK_TIMEZONE, ASK_MORNING_TIME, ASK_EVENING_TIME = range(3)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db.create_user_if_missing(update.effective_chat.id)
    await update.message.reply_text(
        "Hey! I'm Just A Friend \U0001F44B I'll check in with you every morning and evening, "
        "like a friend would. Let's get you set up — takes about 30 seconds.\n\n"
        "First: what time zone are you in? Type a city-based name like "
        '"America/New_York" or "Asia/Singapore", or a UTC offset like "UTC-5".'
    )
    return ASK_TIMEZONE


async def receive_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tz_name = parse_timezone(update.message.text)
    if tz_name is None:
        await update.message.reply_text(
            "I couldn't quite place that time zone. Try something like "
            '"America/New_York", "Europe/London", or "UTC+8".'
        )
        return ASK_TIMEZONE

    context.user_data["timezone"] = tz_name
    await update.message.reply_text(
        f'Got it, {tz_name}. What time should I say good morning? (e.g. "8:00 AM")'
    )
    return ASK_MORNING_TIME


async def receive_morning_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_str = parse_time_of_day(update.message.text)
    if time_str is None:
        await update.message.reply_text(
            'Didn\'t quite catch that — try a format like "8:00 AM" or "20:00".'
        )
        return ASK_MORNING_TIME

    context.user_data["morning_time"] = time_str
    await update.message.reply_text(
        'And what time should I check in during the evening? (e.g. "9:00 PM")'
    )
    return ASK_EVENING_TIME


async def receive_evening_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_str = parse_time_of_day(update.message.text)
    if time_str is None:
        await update.message.reply_text(
            'Didn\'t quite catch that — try a format like "9:00 PM" or "21:00".'
        )
        return ASK_EVENING_TIME

    chat_id = update.effective_chat.id
    db.update_user_settings(
        chat_id,
        timezone_name=context.user_data.get("timezone"),
        morning_time=context.user_data.get("morning_time"),
        evening_time=time_str,
    )
    context.user_data.clear()

    user = db.get_user(chat_id)
    await update.message.reply_text(
        f"All set! I'll check in around {user['morning_time']} and {user['evening_time']} "
        f"your time ({user['timezone']}). You can change this anytime with /settings.\n\n"
        "Talk soon \U0001F49B"
    )
    return ConversationHandler.END


async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = db.get_user(update.effective_chat.id)
    if user is None or user["timezone"] is None:
        await update.message.reply_text(
            "Looks like we haven't set you up yet — send /start first to get going!"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"Your check-ins are currently set for {user['morning_time']} and {user['evening_time']} "
        f"({user['timezone']}).\n\n"
        'What time should your morning check-in be? (e.g. "8:00 AM")'
    )
    return ASK_MORNING_TIME


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("No worries, we can pick this up later.")
    return ConversationHandler.END


onboarding_conversation = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_timezone)],
        ASK_MORNING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_morning_time)],
        ASK_EVENING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_evening_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

settings_conversation = ConversationHandler(
    entry_points=[CommandHandler("settings", settings_start)],
    states={
        ASK_MORNING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_morning_time)],
        ASK_EVENING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_evening_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
