"""
backend/memory/session_context.py — Entities the bot has remembered
for one conversation (the "Context Memory" layer).

This is a thin, typed wrapper around the same plain dict that
backend/chatbot.py has always stored as context_json — no storage
format changes, so existing rows in conversation_sessions keep working
unmodified. It just gives the entities names instead of passing a
raw dict everywhere.
"""

from dataclasses import dataclass, field, fields
from typing import Any, Optional


@dataclass
class SessionContext:
    """
    One slot per entity the chatbot can extract from the user across
    turns of a booking or maintenance conversation. Every field is
    optional — it starts empty and fills in as the user answers each
    question ("From which city?" → from_city, "Tomorrow" → date, ...).
    """

    from_city: Optional[str] = None
    to_city: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    seats: Optional[int] = None
    trip_class: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    price: Optional[float] = None
    selected_trip_id: Optional[int] = None
    available_companies: Optional[list] = None

    service_type: Optional[str] = None
    details: Optional[str] = None
    location: Optional[str] = None

    passenger_name: Optional[str] = None

    # Anything not modeled above (forward-compatible with new intents)
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionContext":
        data = dict(data or {})
        known = {f.name for f in fields(cls) if f.name != "extra"}
        kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(extra=extra, **kwargs)

    def to_dict(self) -> dict:
        """Flatten back to the plain dict shape chatbot.py's handlers expect
        (ctx["from_city"], ctx.get("seats"), etc.) — round-trips losslessly."""
        out = {}
        for f in fields(self):
            if f.name == "extra":
                continue
            value = getattr(self, f.name)
            if value is not None:
                out[f.name] = value
        out.update(self.extra)
        return out

    def has_entity(self, name: str) -> bool:
        return self.to_dict().get(name) is not None

    def get(self, name: str, default: Any = None) -> Any:
        return self.to_dict().get(name, default)
