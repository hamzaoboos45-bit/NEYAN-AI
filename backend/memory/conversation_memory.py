"""
backend/memory/conversation_memory.py — persistence for one conversation.

Reads/writes the SAME conversation_sessions table backend/chatbot.py has
always used (current_state, context_json, last_active). No schema change.
This module only centralizes the SQL that used to live inline inside
ChatbotEngine, so it can be reused by the memory manager and unit-tested
on its own.
"""

import json

from database.db import get_db_connection


class ConversationOwnershipError(Exception):
    """Raised before a conversation owned by another identity is accessed."""


class ConversationMemory:
    def __init__(self, session_id: str, user_id: int | None = None):
        self.session_id = session_id
        self.user_id = user_id

    def ensure_row(self) -> None:
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO conversation_sessions (session_id, user_id)
                VALUES (?, ?)
                """,
                (self.session_id, self.user_id),
            )
            row = conn.execute(
                "SELECT user_id FROM conversation_sessions WHERE session_id = ?",
                (self.session_id,),
            ).fetchone()
            owner_id = row["user_id"] if row else None
            # Chat is currently authenticated-only. An old anonymous row must
            # not be silently claimed by a logged-in user, and a row belonging
            # to a different user must never be read or changed.
            if owner_id != self.user_id:
                raise ConversationOwnershipError("Conversation belongs to another identity")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ownership_params(self) -> tuple:
        if self.user_id is None:
            return self.session_id,
        return self.session_id, self.user_id

    def _ownership_sql(self) -> str:
        if self.user_id is None:
            return "session_id = ? AND user_id IS NULL"
        return "session_id = ? AND user_id = ?"

    def load(self) -> dict:
        """Returns {'current_state', 'context_json', 'last_active'} raw row dict."""
        conn = get_db_connection()
        try:
            row = conn.execute(
                """
                SELECT current_state, context_json, last_active
                FROM conversation_sessions
                WHERE """ + self._ownership_sql(),
                self._ownership_params(),
            ).fetchone()
            if not row:
                raise ConversationOwnershipError("Conversation is unavailable")
            return dict(row)
        finally:
            conn.close()

    def save(self, state: str, context: dict) -> None:
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE conversation_sessions
                SET current_state = ?,
                    context_json = ?,
                    last_active = datetime('now')
                WHERE """ + self._ownership_sql(),
                (state, json.dumps(context, ensure_ascii=False), *self._ownership_params()),
            )
            if cursor.rowcount != 1:
                raise ConversationOwnershipError("Conversation is unavailable")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def minutes_since_last_active(self) -> float | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                """
                SELECT (julianday('now') - julianday(last_active)) * 1440.0 AS minutes
                FROM conversation_sessions
                WHERE """ + self._ownership_sql(),
                self._ownership_params(),
            ).fetchone()
            if not row:
                raise ConversationOwnershipError("Conversation is unavailable")
            return row["minutes"] if row["minutes"] is not None else None
        finally:
            conn.close()

    def append_history(self, sender: str, message_text: str, *, detected_intent: str | None = None,
                       bot_state: str | None = None) -> None:
        """Append one safe, user-owned visible chat message.

        The existing ``chat_history`` table is deliberately the single source
        of truth for conversation restoration.  The ownership predicate is
        checked again at write time, so a stale browser session identifier
        cannot be used to append to somebody else's transcript.
        """
        if sender not in {"user", "bot"}:
            raise ValueError("sender must be user or bot")
        conn = get_db_connection()
        try:
            owned = conn.execute(
                "SELECT 1 FROM conversation_sessions WHERE " + self._ownership_sql(),
                self._ownership_params(),
            ).fetchone()
            if not owned:
                raise ConversationOwnershipError("Conversation is unavailable")
            conn.execute(
                """INSERT INTO chat_history
                   (session_id, user_id, sender, message_text, detected_intent, bot_state)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (self.session_id, self.user_id, sender, message_text, detected_intent, bot_state),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def recent_history(self, limit: int) -> list[dict]:
        """Return a bounded, chronological, user-owned visible transcript."""
        limit = max(1, min(int(limit), 100))
        conn = get_db_connection()
        try:
            ownership = "c.user_id = ?" if self.user_id is not None else "c.user_id IS NULL"
            sql = (
                "SELECT h.sender, h.message_text, h.sent_at "
                "FROM chat_history h JOIN conversation_sessions c ON c.session_id = h.session_id "
                "WHERE h.session_id = ? AND " + ownership +
                " ORDER BY h.message_id DESC LIMIT ?"
            )
            rows = conn.execute(
                sql,
                (self.session_id, *((self.user_id,) if self.user_id is not None else ()), limit),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]
        finally:
            conn.close()

    @staticmethod
    def latest_session_id_for_user(user_id: int) -> str | None:
        """Find only this user's most recently active conversation."""
        conn = get_db_connection()
        try:
            row = conn.execute(
                """SELECT session_id FROM conversation_sessions
                   WHERE user_id = ?
                   ORDER BY last_active DESC, created_at DESC, session_id DESC
                   LIMIT 1""",
                (user_id,),
            ).fetchone()
            return row["session_id"] if row else None
        finally:
            conn.close()
