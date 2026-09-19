import logging
from datetime import datetime, timedelta, timezone

import anthropic

from bot import db
from bot.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


CRISIS_RESOURCES = (
    "\U0001F4DE Samaritans of Singapore (SOS), 24/7: 1767\n"
    "\U0001F4AC SOS CareText (WhatsApp), 24/7: 9151 1767\n"
    "\U0001F4DE National Mindline, 24/7: 1771\n"
    "\U0001F4DE Mental Health Helpline (IMH): 6389 2222\n\n"
    "If you're in immediate danger, please call 999."
)

# Used only as a deterministic backstop for the most explicit, unambiguous
# phrases — not the primary detector (see the system prompt instruction
# below for the nuanced/implicit cases). This guarantees these specific
# phrases always get the safety response, even if the Claude call below
# fails and would otherwise fall back to a generic, tone-deaf reply.
CRISIS_KEYWORDS = [
    "kill myself",
    "killing myself",
    "end my life",
    "ending my life",
    "want to die",
    "wanna die",
    "suicidal",
    "suicide",
    "don't want to live",
    "not worth living",
    "self harm",
    "self-harm",
    "hurt myself",
    "hurting myself",
]

CRISIS_RESPONSE = (
    "That sounds like a lot to carry, and I'm really glad you told me \U0001F49B I'm not "
    "able to give you the kind of support you deserve here, though — please reach out to "
    "people trained for this:\n\n" + CRISIS_RESOURCES + "\n\nYou don't have to go through this alone."
)


def _mentions_crisis(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in CRISIS_KEYWORDS)


SYSTEM_PROMPT = (
    'You are "Just A Friend", a warm, casual companion chatting with someone you '
    "know well. Reply like a close friend texting back — 1 to 3 short sentences, "
    "casual tone, never clinical or coach-like, no bullet points or advice-lecturing. "
    "Reference what they actually said, specifically, not just the general topic.\n\n"
    "Don't ask a question in every reply — often the best reply is just a genuine "
    "reaction with no question at all. When you do ask something, make it feel like "
    "actual curiosity, not a follow-up form. Vary how you open each reply; don't lean "
    'on the same one or two phrases ("Ooh", "Aw", "Nice, glad...") across a '
    "conversation. Keep it grounded, not overly hyped — a real friend reacts warmly "
    "without gushing.\n\n"
    "If someone's message suggests real distress, hopelessness, or any hint of self-harm "
    "or suicidal thoughts — even if not stated directly, just implied by tone or meaning — "
    "set the usual casual style aside. Respond warmly first, without being overly agreeing "
    "or disagreeing with how they're feeling, then clearly point them to real support. "
    "Don't try to counsel them yourself or talk them out of it — always defer to these "
    "resources instead:\n\n" + CRISIS_RESOURCES
)

# Plain-language version of each scheduled prompt, so Claude has context for
# what it's replying to (the user only sees their own answer, not this).
QUESTIONS = {
    "morning_lookforward": "What's one thing you're looking forward to today?",
    "morning_mood": "How are you feeling as you start the day? They answered on a 1-5 scale.",
    "morning_fuel": "What's getting you going this morning?",
    "morning_energy": (
        "How much energy do you have to start the day? They answered on a 1-5 scale."
    ),
    "morning_first_move": "What's the first thing you did after waking up?",
    "morning_intention": "What kind of day are you hoping for?",
    "evening_highlight": "What was the highlight of your day?",
    "evening_gratitude": "3 things you're grateful for today?",
    "evening_hard": "What's one thing that felt hard today?",
    "evening_mood": (
        "How are you feeling right now, as the day wraps up? They answered on a 1-5 scale."
    ),
    "evening_wind_down": "How are you planning to wind down tonight?",
    "evening_day_rating": (
        "Looking back, how would you rate today overall? They answered on a 1-5 scale."
    ),
    "evening_biggest_win": "What's one win from today, big or small?",
    "evening_tomorrow_focus": "What's one thing you want tomorrow to look like?",
    # Not used for generate_reply (sleep replies are fixed-text, not Claude-written) —
    # only needed to label this prompt type in the recent-history context below.
    "morning_sleep": "How they slept last night (they answered on a 1-5 scale)",
}


# How many recent messages (user + assistant turns combined) to keep per
# chat, so replies stay aware of what was just said instead of restarting
# the conversation from scratch each time. Persisted in the database (not
# just in-memory), so it survives restarts/redeploys too.
MAX_HISTORY_MESSAGES = 12

# How far back to look for past check-in answers worth referencing in a
# reply (a name they mentioned, something that seemed to affect their
# mood, a recurring theme) — not everything gets brought up, just what's
# genuinely worth a callback.
MILESTONE_LOOKBACK_DAYS = 30


def _format_past_answer(row) -> str:
    question = QUESTIONS.get(row["prompt_type"], row["prompt_type"])
    when = row["timestamp"][:10]
    answer = row["answer_text"] if row["answer_text"] is not None else f'{row["answer_score"]}/5'
    return f"- {when}: {question} — {answer}"


def _build_recent_history_context(chat_id: int) -> str | None:
    since = (datetime.now(timezone.utc) - timedelta(days=MILESTONE_LOOKBACK_DAYS)).isoformat()
    rows = db.get_responses(chat_id, since_iso=since)
    if not rows:
        return None

    lines = "\n".join(_format_past_answer(row) for row in rows)
    return (
        "Here's what this person has shared over the past month, oldest first. Only bring "
        "any of it up if something genuinely resonates with what they're saying right now — "
        "a name, a recurring theme, something that seemed to affect their mood. Don't force "
        "a callback just because it's here.\n\n" + lines
    )


async def _generate(chat_id: int, user_turn: str) -> str:
    if _mentions_crisis(user_turn):
        db.append_conversation_turns(
            chat_id,
            [("user", user_turn), ("assistant", CRISIS_RESPONSE)],
            keep_last=MAX_HISTORY_MESSAGES,
        )
        return CRISIS_RESPONSE

    history = db.get_conversation_history(chat_id, MAX_HISTORY_MESSAGES)

    system_parts = [SYSTEM_PROMPT]
    user = db.get_user(chat_id)
    if user and user["name"]:
        system_parts.append(
            f"Their name is {user['name']}. You can address them by name occasionally when it "
            "feels natural, but don't force it into every reply."
        )
    recent_history_context = _build_recent_history_context(chat_id)
    if recent_history_context:
        system_parts.append(recent_history_context)
    system = "\n\n".join(system_parts)

    messages = [*history, {"role": "user", "content": user_turn}]
    try:
        response = await _get_client().messages.create(
            model="claude-opus-4-8",
            max_tokens=300,
            system=system,
            messages=messages,
        )
        reply = next(block.text for block in response.content if block.type == "text").strip()
    except anthropic.APIError:
        logger.exception("Claude API call failed; falling back to a generic reply")
        return "Thanks for sharing that with me \U0001F49B"

    db.append_conversation_turns(
        chat_id, [("user", user_turn), ("assistant", reply)], keep_last=MAX_HISTORY_MESSAGES
    )
    return reply


async def generate_reply(prompt_type: str, answer: str, chat_id: int) -> str:
    question = QUESTIONS.get(prompt_type)
    if question is None:
        return await generate_freeform_reply(answer, chat_id)

    user_turn = f'The daily check-in question was: "{question}"\nThey answered: "{answer}"'
    return await _generate(chat_id, user_turn)


async def generate_freeform_reply(user_message: str, chat_id: int) -> str:
    return await _generate(chat_id, user_message)
