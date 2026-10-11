"""
backend/memory/memory_manager.py — public Conversation Memory Manager API.

    ChatbotEngine talks ONLY to this class for anything memory-related.
    It composes conversation_memory.py (storage) + session_context.py
    (typed entities) and adds the one behavior that was missing before
    Phase One: automatic expiry of inactive conversations.

    Memory Architecture:
        Conversation → Intent → Entities → Context Memory → Chatbot
                                    ^              ^
                              session_context  conversation_memory
                                    \\            /
                                   memory_manager (this file)
"""

import json

from backend import states
from backend.memory.conversation_memory import ConversationMemory
from backend.memory.session_context import SessionContext

try:
    import config
    SESSION_TIMEOUT_MINUTES = getattr(config, "SESSION_TIMEOUT_MINUTES", 30)
except Exception:  # pragma: no cover - config always present in this project
    SESSION_TIMEOUT_MINUTES = 30


class ConversationMemoryManager:
    """One instance per chat request, scoped to a single session_id."""

    def __init__(self, session_id: str, user_id: int | None = None):
        self.session_id = session_id
        self._store = ConversationMemory(session_id, user_id=user_id)
        self._store.ensure_row()
        self._auto_expire_if_stale()

    # ─── Public API ───────────────────────────────────────────────────

    def get_state(self) -> str:
        return self._store.load()["current_state"]

    def get_context(self) -> SessionContext:
        raw = self._store.load()["context_json"]
        return SessionContext.from_dict(json.loads(raw))

    def get_context_dict(self) -> dict:
        """Convenience for chatbot.py, which passes ctx around as a plain dict."""
        return self.get_context().to_dict()

    def update(self, state: str, context: dict) -> None:
        """Persist bounded active-flow context and enforce the turn limit."""
        if state == states.STATE_IDLE:
            # Idle conversations retain only a small, customer-safe outcome
            # summary. This lets a follow-up such as "why?" refer to the
            # immediately preceding result without retaining an unbounded
            # active booking/maintenance payload or internal diagnostics.
            safe_keys = ("last_action", "last_result", "last_failure_reason", "last_safe_explanation")
            safe = {key: str((context or {}).get(key, ""))[:400] for key in safe_keys if (context or {}).get(key)}
            self._store.save(state, safe)
            return

        next_context = dict(context or {})
        try:
            turns = int(next_context.get("_turn_count", 0)) + 1
        except (TypeError, ValueError):
            turns = 1
        if turns >= getattr(config, "MAX_CONVERSATION_TURNS", 20):
            self._store.save(states.STATE_IDLE, {})
            return
        next_context["_turn_count"] = turns
        self._store.save(state, next_context)

    def reset(self) -> None:
        """Wipe this conversation back to idle with no remembered entities.
        Used by /api/chat/reset and automatically after a timeout."""
        self._store.save(states.STATE_IDLE, {})

    def append_history(self, sender: str, message_text: str, *, detected_intent: str | None = None,
                       bot_state: str | None = None) -> None:
        self._store.append_history(sender, message_text, detected_intent=detected_intent, bot_state=bot_state)

    def recent_history(self, limit: int) -> list[dict]:
        return self._store.recent_history(limit)

    def is_expired(self) -> bool:
        minutes = self._store.minutes_since_last_active()
        if minutes is None:
            return False
        return minutes > SESSION_TIMEOUT_MINUTES

    # ─── Internal ─────────────────────────────────────────────────────

    def _auto_expire_if_stale(self) -> None:
        """
        If the user has gone quiet for longer than SESSION_TIMEOUT_MINUTES
        while mid-flow (e.g. abandoned a booking), silently reset them to
        idle so their next message starts a clean conversation instead of
        being misinterpreted as an answer to a question from 40 minutes
        ago. A brand-new session (last_active is NULL) is never expired.
        """
        if self.is_expired():
            self.reset()
