import logging

import anthropic

from bot.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = (
    'You are "Just A Friend", a warm, casual companion chatting with someone you '
    "know well. Reply like a close friend texting back — 2 to 4 short sentences, "
    "casual tone, never clinical or coach-like, no bullet points or advice-lecturing. "
    "Reference what they actually said or picked."
)

# Plain-language version of each scheduled prompt, so Claude has context for
# what it's replying to (the user only sees their own answer, not this).
QUESTIONS = {
    "morning_lookforward": "What's one thing you're looking forward to today?",
    "evening_highlight": "What was the highlight of your day?",
    "evening_gratitude": "3 things you're grateful for today?",
    "evening_hard": "What's one thing that felt hard today?",
}


async def _generate(user_turn: str) -> str:
    try:
        response = await _get_client().messages.create(
            model="claude-opus-4-8",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_turn}],
        )
        return next(block.text for block in response.content if block.type == "text").strip()
    except anthropic.APIError:
        logger.exception("Claude API call failed; falling back to a generic reply")
        return "Thanks for sharing that with me \U0001F49B"


async def generate_reply(prompt_type: str, answer: str) -> str:
    question = QUESTIONS.get(prompt_type)
    if question is None:
        return await generate_freeform_reply(answer)

    user_turn = f'The daily check-in question was: "{question}"\nThey answered: "{answer}"'
    return await _generate(user_turn)


async def generate_freeform_reply(user_message: str) -> str:
    return await _generate(user_message)
