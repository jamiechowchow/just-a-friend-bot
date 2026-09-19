import logging
import random
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


# Each user gets their own randomized order that cycles through every
# prompt exactly once before any repeat (see _prompt_for_day) — this list's
# own ordering doesn't matter for that, only its contents.
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
    # Self-care
    ButtonsPrompt(
        "morning_selfcare_action",
        "What's one small way you'll take care of yourself today?",
        _options(
            ("Rest", "rest"),
            ("Hydrate", "hydrate"),
            ("Move my body", "move"),
            ("Eat well", "eat_well"),
            ("Others", "other"),
        ),
    ),
    ButtonsPrompt(
        "morning_boundary",
        "Is there a boundary you need to hold today?",
        _options(
            ("Say no", "say_no"),
            ("Protect my time", "protect_time"),
            ("Ask for space", "ask_space"),
            ("Not today", "not_today"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt("morning_rest_quality", "How rested do you feel, beyond just sleep hours? (1 = depleted, 5 = recharged)"),
    # Self-love
    ButtonsPrompt(
        "morning_selflove_action",
        "What's one kind thing you could do for yourself today?",
        _options(
            ("Compliment myself", "compliment"),
            ("Rest, no guilt", "rest_no_guilt"),
            ("Treat myself", "treat"),
            ("Forgive myself", "forgive"),
            ("Others", "other"),
        ),
    ),
    TextPrompt("morning_proud_of", "What's something about yourself you're proud of right now?"),
    ButtonsPrompt(
        "morning_gratitude",
        "What's one thing about your life you're grateful for?",
        _options(
            ("Kinship", "kinship"),
            ("Work", "work"),
            ("Friendship", "friendship"),
            ("Your Pet", "pet"),
            ("Others", "other"),
        ),
    ),
    # Motivational
    ButtonsPrompt(
        "morning_motivation_source",
        "What's motivating you today?",
        _options(
            ("A goal", "goal"),
            ("Someone I love", "someone_i_love"),
            ("Prove myself", "prove_myself"),
            ("Just today", "just_today"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt("morning_confidence", "How confident are you feeling about today? (1 = shaky, 5 = unstoppable)"),
    TextPrompt("morning_push_through", "What's one thing you're going to push through today?"),
    # Inspiration
    TextPrompt("morning_inspired_by", "Who or what is inspiring you lately?"),
    ButtonsPrompt(
        "morning_curiosity_spark",
        "What's sparking your curiosity today?",
        _options(
            ("A new idea", "new_idea"),
            ("A person", "person"),
            ("A place", "place"),
            ("Not yet", "not_yet"),
            ("Others", "other"),
        ),
    ),
    TextPrompt("morning_dream_big", "If nothing could go wrong today, what would you attempt?"),
    # Uplifting
    TextPrompt("morning_guaranteed_smile", "What's something guaranteed to make you smile today?"),
    ButtonsPrompt(
        "morning_mood_lifter",
        "What usually lifts your mood fastest?",
        _options(
            ("Music", "music"),
            ("A good laugh", "laugh"),
            ("Sunshine", "sunshine"),
            ("A chat", "chat"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt("morning_optimism", "How optimistic are you feeling about today? (1 = not very, 5 = very)"),
    # Wellness
    ScalePrompt("morning_body_checkin", "How does your body feel this morning? (1 = achy/tired, 5 = strong/loose)"),
    ButtonsPrompt(
        "morning_hydration_plan",
        "What's the plan for staying hydrated today?",
        _options(
            ("Water ready", "water_ready"),
            ("Coffee/tea", "coffee_tea"),
            ("I'll try", "ill_try"),
            ("Already on it", "already_on_it"),
            ("Others", "other"),
        ),
    ),
    ButtonsPrompt(
        "morning_movement_plan",
        "Any movement planned today?",
        _options(
            ("Workout", "workout"),
            ("Walk", "walk"),
            ("Stretch", "stretch"),
            ("Rest day", "rest_day"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt("morning_stress_level", "How's your stress level feeling right now? (1 = very stressed, 5 = very calm)"),
    ButtonsPrompt(
        "morning_breakfast_plan",
        "What's on the menu for breakfast?",
        _options(
            ("Something hearty", "hearty"),
            ("Something light", "light"),
            ("Skipping it", "skipping"),
            ("Deciding", "deciding"),
            ("Others", "other"),
        ),
    ),
    # Reflection / affirmation
    TextPrompt("morning_pep_talk", "Write yourself a one-line pep talk for today."),
    ButtonsPrompt(
        "morning_need_to_hear",
        "What do you need to hear this morning?",
        _options(
            ("You're enough", "youre_enough"),
            ("Okay to rest", "okay_to_rest"),
            ("You've got this", "youve_got_this"),
            ("Progress > perfect", "progress"),
            ("Others", "other"),
        ),
    ),
    TextPrompt("morning_small_joy", "What's one small thing you're looking forward to enjoying today?"),
    ScalePrompt("morning_growth_check", "How much are you growing/learning lately, would you say? (1 = stuck, 5 = thriving)"),
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
    # Stoic self-review
    TextPrompt("evening_resisted_habit", "What's one bad habit or urge you resisted today?"),
    ButtonsPrompt(
        "evening_virtue",
        "What virtue did you lean on most today?",
        _options(
            ("Patience", "patience"),
            ("Courage", "courage"),
            ("Kindness", "kindness"),
            ("Discipline", "discipline"),
            ("Others", "other"),
        ),
    ),
    TextPrompt("evening_fell_short", "Where do you feel you fell short today, without judging yourself for it?"),
    # Letting go
    ButtonsPrompt(
        "evening_leave_behind",
        "What's one thing you're ready to leave behind before you sleep?",
        _options(
            ("A worry", "worry"),
            ("A conversation", "conversation"),
            ("A mistake", "mistake"),
            ("Nothing tonight", "nothing"),
            ("Others", "other"),
        ),
    ),
    ScalePrompt("evening_tension_level", "How much tension are you still carrying right now? (1 = a lot, 5 = none)"),
    ButtonsPrompt(
        "evening_let_go_method",
        "What would help you let go of today?",
        _options(
            ("Deep breath", "deep_breath"),
            ("Writing it out", "writing"),
            ("Talking to someone", "talking"),
            ("Just sleep", "sleep"),
            ("Others", "other"),
        ),
    ),
    # Lessons & growth
    TextPrompt("evening_lesson", "What's one lesson today tried to teach you?"),
    TextPrompt("evening_friend_advice", "What would you tell a friend who had the exact day you did?"),
    ScalePrompt("evening_growth_scale", "How much did you grow or learn today, even in a small way? (1 = not much, 5 = a lot)"),
    # Self-compassion
    ButtonsPrompt(
        "evening_self_treatment",
        "How did you treat yourself today?",
        _options(
            ("Gently", "gently"),
            ("A bit harsh", "harsh"),
            ("In between", "in_between"),
            ("Didn't notice", "didnt_notice"),
            ("Others", "other"),
        ),
    ),
    TextPrompt("evening_gentler_about", "What's one thing you'd like to be gentler with yourself about?"),
    ScalePrompt("evening_self_compassion_scale", "How much self-compassion did you show yourself today? (1 = not much, 5 = a lot)"),
    # Connection
    ButtonsPrompt(
        "evening_who_helped",
        "Who made today a little better?",
        _options(
            ("A friend", "friend"),
            ("Family", "family"),
            ("A stranger", "stranger"),
            ("No one really", "no_one"),
            ("Others", "other"),
        ),
    ),
    ButtonsPrompt(
        "evening_kindness_given_received",
        "Did you give or receive any kindness today?",
        _options(
            ("Gave it", "gave"),
            ("Received it", "received"),
            ("Both", "both"),
            ("Neither today", "neither"),
            ("Others", "other"),
        ),
    ),
    TextPrompt("evening_reach_out_tomorrow", "Is there anyone you're thinking of reaching out to tomorrow?"),
    # Presence & mindfulness
    TextPrompt("evening_present_moment", "What's a moment today you felt fully present in?"),
    TextPrompt("evening_small_notice", "What's something small you noticed today that you'd normally miss?"),
    TextPrompt("evening_kindness_statement", "Describe a moment today when you were kind to a stranger or to yourself."),
    # Closure & winding down
    TextPrompt("evening_one_word", "If today had one word, what would it be?"),
    ButtonsPrompt(
        "evening_ready_tomorrow",
        "How ready do you feel for tomorrow?",
        _options(
            ("Bring it on", "bring_it_on"),
            ("A bit anxious", "anxious"),
            ("Neutral", "neutral"),
            ("Need more rest", "need_rest"),
            ("Others", "other"),
        ),
    ),
    ButtonsPrompt(
        "evening_winddown_thoughts",
        "What's on your mind as you wind down?",
        _options(
            ("Tomorrow's plans", "tomorrows_plans"),
            ("Loose ends", "loose_ends"),
            ("Replaying today", "replaying"),
            ("Nothing much", "nothing_much"),
            ("Others", "other"),
        ),
    ),
    # Values & meaning
    ScalePrompt("evening_alignment_scale", "How aligned did today feel with what actually matters to you? (1 = not at all, 5 = very)"),
    TextPrompt("evening_felt_right", "What's one thing you did today just because it felt right, not because you had to?"),
    TextPrompt("evening_curious_before_sleep", "What are you curious about as you fall asleep tonight?"),
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


def _prompt_for_day(chat_id: int, day_index: int, prompts: list):
    # Each user gets their own randomized order that runs through every
    # prompt exactly once before repeating, rather than everyone seeing the
    # same prompt on the same day. The order is deterministic (seeded from
    # chat_id + which cycle we're in) rather than stored anywhere, so it's
    # stable across restarts without needing extra database state.
    n = len(prompts)
    cycle_number = day_index // n
    position = day_index % n
    order = list(range(n))
    random.Random(hash((chat_id, cycle_number))).shuffle(order)
    return prompts[order[position]]


async def _send_scheduled_checkin(context: ContextTypes.DEFAULT_TYPE, prompts: list) -> None:
    chat_id = context.job.chat_id
    user = db.get_user(chat_id)
    if user is None:
        return

    tzinfo = _tzinfo_from_stored(user["timezone"])
    prompt = _prompt_for_day(chat_id, _day_index(tzinfo), prompts)
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
