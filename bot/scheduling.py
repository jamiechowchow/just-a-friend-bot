import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, JobQueue

from bot import ai_reply, db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ButtonOption:
    label: str
    value: str


@dataclass(frozen=True)
class ButtonsPrompt:
    prompt_type: str
    question: str
    options: list[ButtonOption]


@dataclass(frozen=True)
class ScalePrompt:
    prompt_type: str
    question: str


@dataclass(frozen=True)
class TextPrompt:
    prompt_type: str
    question: str


def _options(*pairs: tuple[str, str]) -> list[ButtonOption]:
    return [ButtonOption(label, value) for label, value in pairs]


# One prompt is sent per day, cycling through the list in order (wrapping
# back to the start) — it doesn't try to line up with the day of the week.
MORNING_PROMPTS = [
    ButtonsPrompt(
        "morning_lookforward",
        "What's one thing you're looking forward to today?",
        _options(
            ("Coffee", "coffee"),
            ("Morning sun (Vitamin D)", "sun"),
            ("Birds", "birds"),
            ("Nature", "nature"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt(
        "morning_sleep",
        "How'd you sleep last night? Science says good sleep resets your brain and "
        "mood — how alert/rested are you feeling today? (1 = rough, 5 = great)",
    ),
    ScalePrompt("morning_mood", "How are you feeling as you start the day? (1 = rough, 5 = great)"),
    ButtonsPrompt(
        "morning_fuel",
        "What's getting you going this morning?",
        _options(
            ("Coffee/Tea", "coffee_tea"),
            ("Breakfast", "breakfast"),
            ("Music", "music"),
            ("A good night's rest", "rest"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt(
        "morning_energy",
        "How much energy do you have to start the day? "
        "(1 = running on empty, 5 = fully charged)",
    ),
    ButtonsPrompt(
        "morning_first_move",
        "What's the first thing you did after waking up?",
        _options(
            ("Stretched", "stretched"),
            ("Checked my phone", "phone"),
            ("Made coffee/tea", "coffee_tea"),
            ("Just laid there for a bit", "laid_there"),
            ("Others", "other"),
        ),
    ),
    ButtonsPrompt(
        "morning_intention",
        "What kind of day are you hoping for?",
        _options(
            ("Calm", "calm"),
            ("Productive", "productive"),
            ("Adventurous", "adventurous"),
            ("Restful", "restful"),
            ("Others", "other"),
        ),
    ),
]

EVENING_PROMPTS = [
    TextPrompt("evening_highlight", "What was the highlight of your day?"),
    TextPrompt("evening_gratitude", "3 things you're grateful for today?"),
    TextPrompt("evening_hard", "What's one thing that felt hard today?"),
    ScalePrompt(
        "evening_mood", "How are you feeling right now, as the day wraps up? (1 = rough, 5 = great)"
    ),
    ButtonsPrompt(
        "evening_wind_down",
        "How are you planning to wind down tonight?",
        _options(
            ("Reading", "reading"),
            ("TV/Movies", "tv_movies"),
            ("Music", "music"),
            ("Early sleep", "early_sleep"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt(
        "evening_day_rating",
        "Looking back, how would you rate today overall? (1 = rough day, 5 = great day)",
    ),
    ButtonsPrompt(
        "evening_biggest_win",
        "What's one win from today, big or small?",
        _options(
            ("Finished a task", "finished_task"),
            ("Talked to someone", "connected"),
            ("Took care of myself", "self_care"),
            ("Learned something", "learned"),
            ("Others", "other"),
        ),
    ),
    ButtonsPrompt(
        "evening_tomorrow_focus",
        "What's one thing you want tomorrow to look like?",
        _options(
            ("Restful", "restful"),
            ("Productive", "productive"),
            ("Social", "social"),
            ("Adventurous", "adventurous"),
            ("Others", "other"),
        ),
    ),
]

PROMPTS_BY_TYPE: dict[str, ButtonsPrompt | ScalePrompt | TextPrompt] = {
    prompt.prompt_type: prompt for prompt in [*MORNING_PROMPTS, *EVENING_PROMPTS]
}


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


async def _send_prompt(context: ContextTypes.DEFAULT_TYPE, chat_id: int, prompt) -> None:
    # Set even for button/scale prompts, not just free-text ones — this lets
    # someone type their answer instead of tapping a button, and it still
    # gets picked up as the answer to this prompt.
    context.chat_data["pending_prompt"] = prompt.prompt_type

    if isinstance(prompt, ButtonsPrompt):
        buttons = [
            InlineKeyboardButton(opt.label, callback_data=f"prompt:{prompt.prompt_type}:{opt.value}")
            for opt in prompt.options
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        await context.bot.send_message(
            chat_id=chat_id, text=prompt.question, reply_markup=InlineKeyboardMarkup(rows)
        )
    elif isinstance(prompt, ScalePrompt):
        keyboard = [
            [
                InlineKeyboardButton(str(n), callback_data=f"scale:{prompt.prompt_type}:{n}")
                for n in range(1, 6)
            ]
        ]
        await context.bot.send_message(
            chat_id=chat_id, text=prompt.question, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=prompt.question)


async def _send_scheduled_checkin(context: ContextTypes.DEFAULT_TYPE, prompts: list) -> None:
    chat_id = context.job.chat_id
    user = db.get_user(chat_id)
    if user is None:
        return

    tzinfo = _tzinfo_from_stored(user["timezone"])
    prompt = prompts[_day_index(tzinfo) % len(prompts)]
    await _send_prompt(context, chat_id, prompt)


async def send_morning_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_scheduled_checkin(context, MORNING_PROMPTS)


async def send_evening_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_scheduled_checkin(context, EVENING_PROMPTS)


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


def maybe_schedule_crisis_followup(chat_id: int, trigger_text: str, reply: str) -> None:
    if not ai_reply.is_crisis_reply(reply):
        return
    due_at = (
        datetime.now(dt_timezone.utc) + timedelta(days=ai_reply.CRISIS_FOLLOWUP_DELAY_DAYS)
    ).isoformat()
    db.schedule_crisis_followup(chat_id, trigger_text, due_at)


async def check_crisis_followups(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(dt_timezone.utc).isoformat()
    for followup in db.get_due_crisis_followups(now):
        await context.bot.send_message(
            chat_id=followup["chat_id"], text=ai_reply.CRISIS_FOLLOWUP_MESSAGE
        )
        db.mark_crisis_followup_sent(followup["id"])


async def _handle_buttons_tap(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, prompt_type: str, value: str
) -> None:
    query = update.callback_query
    prompt = PROMPTS_BY_TYPE[prompt_type]

    if value == "other":
        context.chat_data["pending_prompt"] = prompt_type
        await query.edit_message_text(f"{prompt.question}\n\nType it out \U0001F447")
        return

    label = next(opt.label for opt in prompt.options if opt.value == value)
    db.save_response(chat_id, prompt_type, answer_text=label)
    context.chat_data.pop("pending_prompt", None)
    await query.edit_message_text(f"{prompt.question}\n\nYou picked: {label}")

    reply = await ai_reply.generate_reply(prompt_type, label, chat_id)
    maybe_schedule_crisis_followup(chat_id, label, reply)
    await context.bot.send_message(chat_id=chat_id, text=reply)


async def _handle_scale_tap(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, prompt_type: str, score: int
) -> None:
    query = update.callback_query
    prompt = PROMPTS_BY_TYPE[prompt_type]
    db.save_response(chat_id, prompt_type, answer_score=score)
    context.chat_data.pop("pending_prompt", None)
    await query.edit_message_text(f"{prompt.question}\n\nYou rated it: {score}/5")

    if prompt_type == "morning_sleep":
        reply = _sleep_score_reply(score)
    else:
        reply = await ai_reply.generate_reply(prompt_type, f"{score}/5", chat_id)
        maybe_schedule_crisis_followup(chat_id, f"{score}/5", reply)
    await context.bot.send_message(chat_id=chat_id, text=reply)


async def handle_button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    kind, prompt_type, value = query.data.split(":", 2)

    if kind == "prompt":
        await _handle_buttons_tap(update, context, chat_id, prompt_type, value)
    elif kind == "scale":
        await _handle_scale_tap(update, context, chat_id, prompt_type, int(value))


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
