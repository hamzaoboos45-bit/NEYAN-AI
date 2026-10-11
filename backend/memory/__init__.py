"""
backend/memory — AI Assistant Conversation Memory Manager (Phase One).

    Conversation → Intent → Entities → Context Memory → Chatbot

This package formalizes the memory layer that backend/chatbot.py already
relied on (the conversation_sessions table + a per-session context dict),
without changing any of its conversation logic. It only extracts and
names the pieces:

    session_context.py    — typed read/write access to the entities the
                             bot has collected so far (cities, date,
                             seats, trip class, company, service type…)
    conversation_memory.py — low-level persistence (DB row <-> objects)
    memory_manager.py      — the public API ChatbotEngine talks to:
                             get / update / reset / expire-if-stale
"""
