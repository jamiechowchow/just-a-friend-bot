import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from bot.config import DB_PATH


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                timezone TEXT,
                morning_time TEXT,
                evening_time TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                prompt_type TEXT NOT NULL,
                answer_text TEXT,
                answer_score INTEGER,
                FOREIGN KEY (chat_id) REFERENCES users (chat_id)
            )
            """
        )


def create_user_if_missing(chat_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (chat_id, created_at) VALUES (?, ?)",
            (chat_id, datetime.now(timezone.utc).isoformat()),
        )


def update_user_settings(
    chat_id: int,
    timezone_name: str | None = None,
    morning_time: str | None = None,
    evening_time: str | None = None,
) -> None:
    create_user_if_missing(chat_id)
    with get_connection() as conn:
        if timezone_name is not None:
            conn.execute(
                "UPDATE users SET timezone = ? WHERE chat_id = ?", (timezone_name, chat_id)
            )
        if morning_time is not None:
            conn.execute(
                "UPDATE users SET morning_time = ? WHERE chat_id = ?", (morning_time, chat_id)
            )
        if evening_time is not None:
            conn.execute(
                "UPDATE users SET evening_time = ? WHERE chat_id = ?", (evening_time, chat_id)
            )


def get_user(chat_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()


def get_fully_onboarded_users() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM users
            WHERE timezone IS NOT NULL AND morning_time IS NOT NULL AND evening_time IS NOT NULL
            """
        ).fetchall()


def save_response(
    chat_id: int,
    prompt_type: str,
    answer_text: str | None = None,
    answer_score: int | None = None,
) -> None:
    create_user_if_missing(chat_id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO responses (chat_id, timestamp, prompt_type, answer_text, answer_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                datetime.now(timezone.utc).isoformat(),
                prompt_type,
                answer_text,
                answer_score,
            ),
        )


def get_responses(chat_id: int, since_iso: str | None = None) -> list[sqlite3.Row]:
    with get_connection() as conn:
        if since_iso is None:
            return conn.execute(
                "SELECT * FROM responses WHERE chat_id = ? ORDER BY timestamp",
                (chat_id,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM responses WHERE chat_id = ? AND timestamp >= ? ORDER BY timestamp",
            (chat_id, since_iso),
        ).fetchall()
