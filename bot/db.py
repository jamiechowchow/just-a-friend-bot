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


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                timezone TEXT,
                morning_time TEXT,
                evening_time TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Databases created before name/email existed won't get them from the
        # CREATE TABLE above (SQLite only applies that to a brand-new table).
        _ensure_column(conn, "users", "name", "TEXT")
        _ensure_column(conn, "users", "email", "TEXT")
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
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
    name: str | None = None,
    email: str | None = None,
    timezone_name: str | None = None,
    morning_time: str | None = None,
    evening_time: str | None = None,
) -> None:
    create_user_if_missing(chat_id)
    with get_connection() as conn:
        if name is not None:
            conn.execute("UPDATE users SET name = ? WHERE chat_id = ?", (name, chat_id))
        if email is not None:
            conn.execute("UPDATE users SET email = ? WHERE chat_id = ?", (email, chat_id))
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


def list_users() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()


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


def get_conversation_history(chat_id: int, limit: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversation_turns WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def append_conversation_turns(chat_id: int, turns: list[tuple[str, str]], keep_last: int) -> None:
    create_user_if_missing(chat_id)
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO conversation_turns (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [(chat_id, role, content, now) for role, content in turns],
        )
        conn.execute(
            """
            DELETE FROM conversation_turns
            WHERE chat_id = ? AND id NOT IN (
                SELECT id FROM conversation_turns WHERE chat_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (chat_id, chat_id, keep_last),
        )


def count_users() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_onboarded_users() -> int:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT COUNT(*) FROM users
            WHERE timezone IS NOT NULL AND morning_time IS NOT NULL AND evening_time IS NOT NULL
            """
        ).fetchone()[0]


def count_active_users_since(since_iso: str) -> int:
    # "Active" means any interaction at all — a check-in answer (responses)
    # or a plain chat message (conversation_turns) — not just structured
    # check-in answers.
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT chat_id FROM responses WHERE timestamp >= ?
                UNION
                SELECT chat_id FROM conversation_turns WHERE created_at >= ? AND role = 'user'
            )
            """,
            (since_iso, since_iso),
        ).fetchone()[0]


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
