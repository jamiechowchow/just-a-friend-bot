import logging
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, JobQueue

from bot import ai_reply, db

logger = logging.getLogger(__name__)

LOOKFORWARD_OPTIONS = [
    ("Coffee", "coffee"),
    ("Morning sun (Vitamin D)", "sun"),
    ("Birds", "birds"),
    ("Nature", "nature"),
    ("Others", "other"),
]

EVENING_PROMPTS = [
    ("evening_highlight", "What was the highlight of your day?"),
    ("evening_gratitude", "3 things you're grateful for today?"),
    ("evening_hard", "What's one thing that felt hard today?"),
]


def _tzinfo_from_stored(timezone_str: str):
    """Stored value is either an IANA name ("America/New_York") or our
    own "UTC+HH:MM" / "UTC-HH:MM" format from time_parsing.parse_timezone()."""
    if timezone_str.startswith("UTC+") or timezone_str.startswith("UTC-"):
        sign = 1 if timezone_str[3] == "+" else -1
        hours, minutes = timezone_str[4:].split(":")
        return dt_timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
    return ZoneInfo(timezone_str)


def _day_index(tzinfo) -> int:
    return datetime.now(tzinfo).toordinal()


async def send_morning_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    user = db.get_user(chat_id)
    if user is None:
        return

    tzinfo = _tzinfo_from_stored(user["timezone"])
    if _day_index(tzinfo) % 2 == 0:
        await _send_lookforward_prompt(context, chat_id)
    else:
        await _send_sleep_prompt(context, chat_id)


async def _send_lookforward_prompt(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    keyboard = [
        [InlineKeyboardButton("Coffee", callback_data="lookforward:coffee"),
         InlineKeyboardButton("Morning sun (Vitamin D)", callback_data="lookforward:sun")],
        [InlineKeyboardButton("Birds", callback_data="lookforward:birds"),
         InlineKeyboardButton("Nature", callback_data="lookforward:nature")],
        [InlineKeyboardButton("Others", callback_data="lookforward:other")],
    ]
    context.chat_data["pending_prompt"] = "morning_lookforward"
    await context.bot.send_message(
        chat_id=chat_id,
        text="What's one thing you're looking forward to today?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _send_sleep_prompt(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    keyboard = [[InlineKeyboardButton(str(n), callback_data=f"sleep:{n}") for n in range(1, 6)]]
    context.chat_data["pending_prompt"] = "morning_sleep"
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "How'd you sleep last night? Science says good sleep resets your brain and "
            "mood — how alert/rested are you feeling today? (1 = rough, 5 = great)"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def send_evening_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    user = db.get_user(chat_id)
    if user is None:
        return

    tzinfo = _tzinfo_from_stored(user["timezone"])
    prompt_type, prompt_text = EVENING_PROMPTS[_day_index(tzinfo) % len(EVENING_PROMPTS)]

    context.chat_data["pending_prompt"] = prompt_type
    await context.bot.send_message(chat_id=chat_id, text=prompt_text)


def _sleep_score_reply(score: int) -> str:
    if score >= 4:
        return (
            "Amazing \U0001F31F Good sleep resets your brain overnight — sharper focus, "
            "steadier mood, more energy. Ride that wave today!"
        )
    if score == 3:
        return (
            "Decent \U0001F60C Even so-so sleep still lets your brain recharge a bit. "
            "Take it easy and let the day unfold."
        )
    return (
        "Rough night \U0001F49B Sleep is when your brain clears out the clutter and your "
        "body repairs itself, so if today feels slower, that's why. Be gentle with "
        "yourself — tonight's a fresh shot at it."
    )


async def handle_button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    kind, value = query.data.split(":", 1)

    if kind == "lookforward":
        if value == "other":
            context.chat_data["pending_prompt"] = "morning_lookforward"
            await query.edit_message_text("What are you looking forward to? Type it out \U0001F447")
            return

        label = next(label for label, key in LOOKFORWARD_OPTIONS if key == value)
        db.save_response(chat_id, "morning_lookforward", answer_text=label)
        context.chat_data.pop("pending_prompt", None)
        await query.edit_message_text(
            f"What's one thing you're looking forward to today?\n\nYou picked: {label}"
        )
        history = context.chat_data.setdefault("history", [])
        reply = await ai_reply.generate_reply("morning_lookforward", label, history)
        await context.bot.send_message(chat_id=chat_id, text=reply)

    elif kind == "sleep":
        score = int(value)
        db.save_response(chat_id, "morning_sleep", answer_score=score)
        context.chat_data.pop("pending_prompt", None)
        await query.edit_message_text(f"How'd you sleep last night?\n\nYou rated it: {score}/5")
        await context.bot.send_message(chat_id=chat_id, text=_sleep_score_reply(score))


def _cancel_existing_jobs(job_queue: JobQueue, name: str) -> None:
    for job in job_queue.get_jobs_by_name(name):
        job.schedule_removal()


def schedule_user_jobs(job_queue: JobQueue, chat_id: int) -> None:
    user = db.get_user(chat_id)
    if user is None or not (user["timezone"] and user["morning_time"] and user["evening_time"]):
        return

    tzinfo = _tzinfo_from_stored(user["timezone"])
    morning_hour, morning_minute = (int(part) for part in user["morning_time"].split(":"))
    evening_hour, evening_minute = (int(part) for part in user["evening_time"].split(":"))

    morning_name = f"morning-{chat_id}"
    evening_name = f"evening-{chat_id}"
    _cancel_existing_jobs(job_queue, morning_name)
    _cancel_existing_jobs(job_queue, evening_name)

    # If this process was asleep/suspended (e.g. the computer's screen locked)
    # right as a check-in was due, the scheduler's default behavior is to give
    # up on that occurrence entirely rather than fire it late. A grace window
    # lets it still fire as soon as the process wakes back up.
    catch_up_window = {"misfire_grace_time": 3600}

    job_queue.run_daily(
        send_morning_checkin,
        time=time(morning_hour, morning_minute, tzinfo=tzinfo),
        chat_id=chat_id,
        name=morning_name,
        job_kwargs=catch_up_window,
    )
    job_queue.run_daily(
        send_evening_checkin,
        time=time(evening_hour, evening_minute, tzinfo=tzinfo),
        chat_id=chat_id,
        name=evening_name,
        job_kwargs=catch_up_window,
    )
    logger.info("Scheduled daily check-ins for chat %s", chat_id)


def schedule_all_users(job_queue: JobQueue) -> None:
    for user in db.get_fully_onboarded_users():
        schedule_user_jobs(job_queue, user["chat_id"])
