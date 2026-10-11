"""
backend/states.py — State definitions for the conversation machine.

Each state is a plain string constant. The chatbot engine
reads the session's current_state and decides what to do next.

State naming convention:  <flow>_<action>
  e.g.  booking_ask_from_city
        maintenance_ask_service_type
        idle  (waiting for any user input)
"""

# ─── Neutral ───────────────────────────────────────────
STATE_IDLE = "idle"

# ─── Booking flow ──────────────────────────────────────
STATE_BOOKING_FROM      = "booking_ask_from_city"
STATE_BOOKING_TO        = "booking_ask_to_city"
STATE_BOOKING_DATE      = "booking_ask_date"
STATE_BOOKING_SEATS     = "booking_ask_seats"
STATE_BOOKING_CLASS     = "booking_ask_class"
STATE_BOOKING_COMPANY   = "booking_ask_company"
STATE_BOOKING_CONFIRM   = "booking_confirm"

# Forming-trip is a safe fallback after the existing scheduled-trip lookup
# returns no bookable result.  It never bypasses TripRequestService.
STATE_FORMING_JOIN_CONFIRM = "forming_join_confirm"
STATE_FORMING_MODE = "forming_choose_visibility"
STATE_FORMING_CREATE_CONFIRM = "forming_create_confirm"

# NOTE (bug fix): STATE_BOOKING_CLASS / STATE_BOOKING_COMPANY were referenced
# by backend/chatbot.py (_booking_got_seats, _booking_got_class, etc.) but
# were never defined here, which meant the booking flow raised an
# AttributeError as soon as a user picked seats. Added here — no existing
# state was renamed or removed, so nothing that worked before is affected.
BOOKING_FLOW = [
    STATE_BOOKING_FROM,
    STATE_BOOKING_TO,
    STATE_BOOKING_DATE,
    STATE_BOOKING_SEATS,
    STATE_BOOKING_CLASS,
    STATE_BOOKING_COMPANY,
    STATE_BOOKING_CONFIRM,
]

# Ordered (state, context_key) pairs used by the new NLP slot pre-fill logic
# (backend/nlp/hybrid_pipeline.py + chatbot.py) to figure out which booking
# question still needs an answer after entities have been auto-extracted
# from the user's message. Purely additive — existing step-by-step handlers
# in chatbot.py are unchanged and still work turn-by-turn as before.
BOOKING_SLOTS = [
    (STATE_BOOKING_FROM,    "from_city"),
    (STATE_BOOKING_TO,      "to_city"),
    (STATE_BOOKING_DATE,    "date"),
    (STATE_BOOKING_SEATS,   "seats"),
    (STATE_BOOKING_CLASS,   "trip_class"),
    (STATE_BOOKING_COMPANY, "company_id"),
]

# ─── Maintenance flow ───────────────────────────────────
STATE_MAINT_TYPE        = "maintenance_ask_service_type"
STATE_MAINT_DETAILS     = "maintenance_ask_service_details"
STATE_MAINT_LOCATION    = "maintenance_ask_location"
STATE_MAINT_DATE        = "maintenance_ask_date"
STATE_MAINT_CONFIRM     = "maintenance_confirm"

MAINTENANCE_FLOW = [
    STATE_MAINT_TYPE,
    STATE_MAINT_DETAILS,
    STATE_MAINT_LOCATION,
    STATE_MAINT_DATE,
    STATE_MAINT_CONFIRM,
]

# "details" is deliberately excluded — it's a free-form problem description,
# not a fixed-vocabulary slot, so it should always be asked in the user's
# own words rather than auto-filled/skipped by NER.
MAINT_SLOTS = [
    (STATE_MAINT_TYPE,     "service_type"),
    (STATE_MAINT_LOCATION, "location"),
    (STATE_MAINT_DATE,     "date"),
]
