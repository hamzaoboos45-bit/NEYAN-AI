"""
backend/chatbot.py — Conversation engine (state machine runner).

Version 2 improvements:
- Handles 13 intents (was 4)
- Booking flow extended: supports company selection + trip class
- Maintenance flow: cleaner step progression
- is_confirmation() / is_cancellation() from intents.py (no duplication)
- _reply() helper keeps all state transitions in one clean pattern
- Friendly Arabic error/fallback messages
- Multi-company support in booking flow
- Better context management

Architecture: stateless engine — all session state lives in SQLite.
"""

import re
from datetime import date as calendar_date, timedelta

import config
from backend import intents, states, responses
from backend.memory.memory_manager import ConversationMemoryManager
from backend.nlp import entity_extractor, hybrid_pipeline, normalizer, preprocessing
from backend.transportation.trip_request_service import TripRequestError, TripRequestService
from backend.transportation.booking_service import BookingError, BookingService
from backend.maintenance.service import MaintenanceRequestError, MaintenanceRequestService
from database.db import get_db_connection

# NOTE (Arabic NLP Intelligence phase): intent resolution at STATE_IDLE
# now goes through backend/nlp/hybrid_pipeline.py instead of the old
# `intents.classify(msg) or ai_classify(msg)` line. That old line was
# dead code — intents.classify() always returns the string "unknown"
# rather than None/"" for a non-match, so `or ai_classify(msg)` could
# never actually run. The hybrid pipeline now does what that call was
# always meant to: try AraBERT first, and only fall back to
# backend/intents.py (still completely unchanged) below a confidence
# threshold. See backend/nlp/hybrid_pipeline.py for the full flow.


# ═══════════════════════════════════════════════════════════════════════════════
# CHATBOT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class ChatbotEngine:
    """
    Main conversation controller using a State Machine pattern.

    Flow:
        process(msg)
            └── _load_session()
            └── _handle(state, msg, ctx)
                    ├── idle       → _handle_idle()
                    ├── booking_*  → booking step handlers
                    ├── maint_*    → maintenance step handlers
                    └── fallback   → unknown response
            └── _save_session()
            └── return reply
    """

    def __init__(self, session_id: str, user_id: int = None):
        self.session_id = session_id
        # The route supplies this from Flask's signed server-side session.
        # It is never accepted from a chat request body.
        self.user_id = user_id
        # Conversation Memory Manager: loads/saves conversation state +
        # remembered entities, and auto-expires stale conversations.
        # See backend/memory/ — Conversation → Intent → Entities → Context Memory.
        self.memory = ConversationMemoryManager(session_id, user_id=user_id)
        # Populated during process() — the last hybrid_pipeline.NLPResult,
        # exposed for the optional debug panel (Part Nine) and for
        # best-effort analytics logging. None until the first message.
        self.last_nlp_result = None

    # ─── Public API ───────────────────────────────────────────────────────────

    def process(self, user_message: str) -> str:
        """
        Main entry point.
        Receives raw user text → returns bot reply string.
        """
        current_state = self.memory.get_state()
        context       = self.memory.get_context_dict()

        if current_state == states.STATE_IDLE and _is_why_question(user_message):
            explanation = context.get("last_safe_explanation")
            reply = ("بالطبع. " + explanation) if explanation else "لا توجد نتيجة سابقة يمكنني شرحها. أخبرني بما تحتاجه وسأساعدك."
            self.memory.update(states.STATE_IDLE, {**context, "last_action": "explanation", "last_result": "explained", "last_safe_explanation": explanation or reply})
            self.memory.append_history("user", user_message, detected_intent="why", bot_state=current_state)
            self.memory.append_history("bot", reply, bot_state=states.STATE_IDLE)
            return reply

        # A short "why?" during a booking is a request for the reason for
        # the current slot, not a malformed slot value.  Preserve the exact
        # persisted state and every already-collected booking entity.
        if current_state in states.BOOKING_FLOW and _is_why_question(user_message):
            reply = _booking_step_explanation(current_state)
            self.memory.update(current_state, context)
            self.memory.append_history("user", user_message, detected_intent="why", bot_state=current_state)
            self.memory.append_history("bot", reply, bot_state=current_state)
            return reply

        # A clearly unrelated domain request starts a clean flow. This
        # prevents a maintenance request from inheriting transportation
        # entities (and vice versa) after restoration.
        switch_intent = intents.classify(user_message)
        if current_state in (states.BOOKING_FLOW + [states.STATE_FORMING_JOIN_CONFIRM, states.STATE_FORMING_MODE, states.STATE_FORMING_CREATE_CONFIRM]) and switch_intent == "maintenance":
            reply, next_state, updated_context = self._start_maintenance({})
            self.memory.update(next_state, updated_context)
            self.memory.append_history("user", user_message, detected_intent="maintenance", bot_state=current_state)
            self.memory.append_history("bot", reply, bot_state=next_state)
            return reply

        # Corrections are interpreted against the active booking context
        # before the ordinary slot handler consumes the message. This lets a
        # customer amend one known value without discarding the rest of a
        # persisted flow or accidentally selecting/confirming a trip.
        if current_state in states.BOOKING_FLOW:
            correction = self._apply_booking_correction(user_message, current_state, context)
            if correction:
                reply, next_state, updated_context = correction
                self.memory.update(next_state, updated_context)
                self.memory.append_history("user", user_message, detected_intent="booking", bot_state=current_state)
                self.memory.append_history("bot", reply, bot_state=next_state)
                return reply
        if current_state in states.MAINTENANCE_FLOW and switch_intent == "booking":
            reply, next_state, updated_context = self._start_booking({})
            self.memory.update(next_state, updated_context)
            self.memory.append_history("user", user_message, detected_intent="booking", bot_state=current_state)
            self.memory.append_history("bot", reply, bot_state=next_state)
            return reply

        # Active flows still need lightweight entity recognition. Re-running
        # the full model pipeline for every answer would be unnecessarily
        # expensive, so this uses only the deterministic Arabic rule layer.
        # It lets a user provide slots out of order (for example, "لشخصين"
        # before the date) while preserving bounded SessionContext storage.
        if current_state != states.STATE_IDLE:
            pre = preprocessing.preprocess(user_message)
            turn_entities = entity_extractor.extract(
                pre["normalized"], raw_text=pre["cleaned"], include_ner=False
            )
            # A free-form maintenance description can mention another service
            # (for example, "المحرك") without changing the service selected
            # in the preceding step. Only the service-choice state may alter
            # that slot; booking class has the same state-specific rule.
            if current_state != states.STATE_MAINT_TYPE:
                turn_entities.pop("service_type", None)
            if current_state not in (states.STATE_BOOKING_CLASS, states.STATE_BOOKING_COMPANY, states.STATE_BOOKING_CONFIRM,
                                     states.STATE_FORMING_JOIN_CONFIRM, states.STATE_FORMING_MODE, states.STATE_FORMING_CREATE_CONFIRM):
                turn_entities.pop("trip_class", None)
            context = hybrid_pipeline.merge_entities(context, turn_entities, overwrite=True)

        reply, next_state, updated_context = self._handle(
            current_state, user_message.strip(), context
        )

        if next_state == states.STATE_IDLE:
            source = updated_context if updated_context else context
            updated_context = {
                "last_action": current_state if current_state != states.STATE_IDLE else "conversation",
                "last_result": "completed",
                "last_safe_explanation": str(reply)[:400],
                **{key: value for key, value in source.items() if key in {"last_failure_reason"}},
            }

        self.memory.update(next_state, updated_context)
        # Keep the visible transcript separate from bounded active NLP
        # context.  Both writes remain scoped to the ownership-checked
        # conversation row held by ConversationMemoryManager.
        detected_intent = self.last_nlp_result.legacy_intent if self.last_nlp_result else None
        self.memory.append_history("user", user_message, detected_intent=detected_intent, bot_state=current_state)
        self.memory.append_history("bot", reply, bot_state=next_state)
        return reply

    # ─── Master Dispatcher ────────────────────────────────────────────────────

    def _handle(self, state: str, msg: str, ctx: dict):
        """
        Route the message to the correct handler based on current state.
        Returns (reply, next_state, updated_context).

        ── Mid-flow escape hatch ──
        If the user types a global command (help, cancel, goodbye)
        while inside a flow, we handle it immediately without
        advancing the current state.
        """

        # ── Global escapes — work from ANY state ──────────────────────────────
        if state != states.STATE_IDLE:
            escape = self._check_global_escape(msg, state, ctx)
            if escape:
                return escape

        # ── IDLE: classify intent (Hybrid NLP Pipeline) and start a flow ──────
        if state == states.STATE_IDLE:
            nlp_result = hybrid_pipeline.analyze(msg)
            self.last_nlp_result = nlp_result
            self._log_nlp_result(nlp_result)
            ctx = hybrid_pipeline.merge_entities(ctx, nlp_result.entities)
            return self._handle_idle(nlp_result.legacy_intent, ctx)

        # ── BOOKING FLOW ──────────────────────────────────────────────────────
        if state == states.STATE_BOOKING_FROM:
            return self._booking_got_from(msg, ctx)

        if state == states.STATE_BOOKING_TO:
            return self._booking_got_to(msg, ctx)

        if state == states.STATE_BOOKING_DATE:
            return self._booking_got_date(msg, ctx)

        if state == states.STATE_BOOKING_SEATS:
            return self._booking_got_seats(msg, ctx)

        if state == states.STATE_BOOKING_CLASS:
            return self._booking_got_class(msg, ctx)

        if state == states.STATE_BOOKING_COMPANY:
            return self._booking_got_company(msg, ctx)

        if state == states.STATE_BOOKING_CONFIRM:
            return self._finalize_booking(msg, ctx)

        if state == states.STATE_FORMING_JOIN_CONFIRM:
            return self._confirm_forming_join(msg, ctx)

        if state == states.STATE_FORMING_MODE:
            return self._choose_forming_mode(msg, ctx)

        if state == states.STATE_FORMING_CREATE_CONFIRM:
            return self._confirm_forming_create(msg, ctx)

        # ── MAINTENANCE FLOW ──────────────────────────────────────────────────
        if state == states.STATE_MAINT_TYPE:
            return self._maint_got_type(msg, ctx)

        if state == states.STATE_MAINT_DETAILS:
            return self._maint_got_details(msg, ctx)

        if state == states.STATE_MAINT_LOCATION:
            return self._maint_got_location(msg, ctx)

        if state == states.STATE_MAINT_DATE:
            return self._maint_got_date(msg, ctx)

        if state == states.STATE_MAINT_CONFIRM:
            return self._finalize_maintenance(msg, ctx)

        # ── Fallback ──────────────────────────────────────────────────────────
        return _reply(responses.get("unknown"), states.STATE_IDLE, {})

    # ─── Global Escape Handler ────────────────────────────────────────────────

    def _check_global_escape(self, msg: str, state: str, ctx: dict):
        """
        Handle commands that interrupt any active flow:
          - help  → show help menu, stay in same state
          - cancel / goodbye → abort flow, go idle
          - ask_price / ask_seats / ask_companies → answer and continue

        Returns a reply tuple or None (if no escape triggered).
        """
        intent = intents.classify(msg)

        # Confirmation states own a standalone "no" so they can give a
        # precise, customer-safe result and retain it for a later "why?".
        if state in (states.STATE_BOOKING_CONFIRM, states.STATE_MAINT_CONFIRM,
                     states.STATE_FORMING_JOIN_CONFIRM, states.STATE_FORMING_MODE,
                     states.STATE_FORMING_CREATE_CONFIRM) and intent == "cancel":
            return None

        if intent == "help":
            # Answer help but DON'T reset the flow
            return _reply(responses.get("help_mid_flow"), state, ctx)

        if intent in ("greeting", "thanks"):
            key = "greeting_short" if intent == "greeting" else "thanks"
            return _reply(responses.get(key), state, ctx)

        if intent in ("cancel", "goodbye"):
            return _reply(responses.get("flow_cancelled"), states.STATE_IDLE, {})

        if intent == "ask_price":
            price_info = self._get_price_info(ctx)
            return _reply(price_info, state, ctx)

        if intent == "ask_companies":
            companies = self._get_companies_list()
            return _reply(companies, state, ctx)

        if intent == "ask_available_seats":
            seats_info = self._get_seats_info(ctx)
            return _reply(seats_info, state, ctx)

        return None  # No escape — continue normal flow

    # ─── Idle Handler ─────────────────────────────────────────────────────────

    def _handle_idle(self, intent: str, ctx: dict):
        """Map detected intent → start appropriate flow or reply directly.

        `ctx` may already contain entities the Hybrid NLP Pipeline
        extracted from this very message (e.g. "احجز من عمان الى اربد"
        already knows from_city/to_city) — booking/maintenance below
        start the flow at the first still-unanswered slot instead of
        always asking from scratch (Part Three: don't re-ask what's
        already known).
        """

        handlers = {
            "greeting":            lambda: _reply(responses.get("greeting"),        states.STATE_IDLE, {}),
            "thanks":              lambda: _reply(responses.get("thanks"),          states.STATE_IDLE, ctx),
            "goodbye":             lambda: _reply(responses.get("goodbye"),         states.STATE_IDLE, {}),
            "help":                lambda: _reply(responses.get("help"),            states.STATE_IDLE, {}),
            "booking":             lambda: self._start_booking(ctx),
            "maintenance":         lambda: self._start_maintenance(ctx),
            "search_trip":         lambda: _reply(self._get_all_trips(),            states.STATE_IDLE, {}),
            "ask_price":           lambda: _reply(responses.get("ask_price_first"), states.STATE_IDLE, {}),
            "ask_available_seats": lambda: _reply(responses.get("ask_seats_first"), states.STATE_IDLE, {}),
            "ask_companies":       lambda: _reply(self._get_companies_list(),       states.STATE_IDLE, {}),
            "cancel_booking":      lambda: _reply(responses.get("cancel_booking"),  states.STATE_IDLE, {}),
            "confirm":             lambda: _reply(responses.get("confirm_nothing"), states.STATE_IDLE, {}),
            "cancel":              lambda: _reply(responses.get("cancel_nothing"),  states.STATE_IDLE, {}),
            # New, purely additive intents from the AraBERT canonical
            # taxonomy (backend/nlp/intent_classifier.py) — backend/intents.py
            # also grew matching keyword lists so the rule-based fallback
            # recognizes them too. Nothing above this line changed.
            "complaint":           lambda: _reply(responses.get("complaint_ack"),   states.STATE_IDLE, {}),
            "general_conversation": lambda: _reply(responses.get("general_chat"),   states.STATE_IDLE, {}),
        }

        handler = handlers.get(intent)
        if handler:
            return handler()

        # Unknown intent
        return _reply(responses.get("unknown"), states.STATE_IDLE, ctx)

    def _apply_booking_correction(self, msg: str, state: str, ctx: dict):
        """Safely revise an already-known booking slot when explicitly asked.

        This does not finalize, create, or join anything. It merely updates
        the bounded active context then returns the next missing question (or
        refreshes the matching-trip offer). Ordinary one-word slot answers
        still follow their existing state handlers.
        """
        normalized = preprocessing.preprocess(msg)["normalized"]
        if not _looks_like_correction(normalized):
            return None

        changed = False
        cities = normalizer.find_cities_in_text(normalized)
        if cities:
            if _has_from_cue(normalized):
                ctx["from_city"] = cities[0]
                changed = True
            elif _has_to_cue(normalized) or "قصدي" in normalized:
                ctx["to_city"] = cities[-1]
                changed = True

        changed_values = {
            "date": normalizer.extract_date(msg),
            "time": normalizer.extract_time(msg),
            "trip_class": normalizer.parse_trip_class(msg),
            "vehicle_type": normalizer.parse_vehicle_type(msg),
        }
        seats = _parse_number(msg) if any(word in normalized for word in ("شخص", "راكب", "مقعد", "seats", "passenger")) else None
        if seats is not None and seats > 0:
            changed_values["seats"] = seats
        for key, value in changed_values.items():
            if value is not None:
                if key == "date":
                    classified = normalizer.classify_future_travel_date(value)
                    if classified.status != "valid":
                        self._clear_booking_date_dependents(ctx)
                        return _reply(_travel_date_message(classified.status, msg), states.STATE_BOOKING_DATE, ctx)
                    value = classified.value
                ctx[key] = value
                changed = True
        if not changed:
            return None

        for stale_key in ("available_companies", "company_id", "company_name", "price", "selected_trip_id", "booking_quote", "forming_request_id", "forming_payload", "forming_quote"):
            ctx.pop(stale_key, None)
        if not ctx.get("from_city"):
            return _reply(responses.get("booking_start"), states.STATE_BOOKING_FROM, ctx)
        if not ctx.get("to_city"):
            return _reply(responses.get("booking_to"), states.STATE_BOOKING_TO, ctx)
        if not ctx.get("date"):
            return _reply(responses.get("booking_date"), states.STATE_BOOKING_DATE, ctx)
        if ctx.get("seats") is None:
            return _reply(responses.get("booking_seats"), states.STATE_BOOKING_SEATS, ctx)
        if ctx.get("trip_class") is None:
            return _reply(responses.get("booking_class"), states.STATE_BOOKING_CLASS, ctx)
        return self._present_matching_trips(ctx)

    # ─── Smart slot pre-fill (Part Three) ─────────────────────────────────────

    def _start_booking(self, ctx: dict):
        """Enter the booking flow at the first slot NOT already known from
        entities extracted out of the triggering message, instead of
        always starting at from_city. If every slot up through company is
        already known (rare, but possible from a very explicit message),
        this still stops at STATE_BOOKING_COMPANY rather than guessing a
        company — a booking is only ever finalized after the user
        explicitly confirms a specific company + summary."""
        # Normalize any city entities the pipeline already found so they
        # match config.SUPPORTED_CITIES / the trips table exactly.
        if ctx.get("from_city"):
            ctx["from_city"] = normalizer.normalize_city(ctx["from_city"]) or ctx["from_city"]
        if ctx.get("to_city"):
            ctx["to_city"] = normalizer.normalize_city(ctx["to_city"]) or ctx["to_city"]

        if ctx.get("date"):
            classified = normalizer.classify_future_travel_date(ctx["date"])
            if classified.status != "valid":
                self._clear_booking_date_dependents(ctx)
                return _reply(_travel_date_message(classified.status, ctx.get("date")), states.STATE_BOOKING_DATE, ctx)
            ctx["date"] = classified.value

        for state, key in states.BOOKING_SLOTS:
            if ctx.get(key) is not None:
                continue
            if state == states.STATE_BOOKING_FROM:
                return _reply(responses.get("booking_start"), state, ctx)
            if state == states.STATE_BOOKING_TO:
                return _reply(responses.get("booking_to"), state, ctx)
            if state == states.STATE_BOOKING_DATE:
                return _reply(responses.get("booking_date"), state, ctx)
            if state == states.STATE_BOOKING_SEATS:
                return _reply(responses.get("booking_seats"), state, ctx)
            if state == states.STATE_BOOKING_CLASS:
                return _reply(responses.get("booking_class"), state, ctx)
            if state == states.STATE_BOOKING_COMPANY:
                return self._present_matching_trips(ctx)
        # Every slot already known — extremely unlikely via free text, but
        # handled safely: re-run the company step so the user still
        # explicitly picks/confirms rather than the bot silently deciding.
        return self._present_matching_trips(ctx)

    def _start_maintenance(self, ctx: dict):
        """Same idea as _start_booking, scoped to the maintenance flow.
        'details' is always asked in the user's own words (see
        states.MAINT_SLOTS) — it's a free-form description, not a
        fixed-vocabulary slot NER can reliably pre-fill."""
        if ctx.get("service_type") is None:
            return _reply(responses.get("maint_start"), states.STATE_MAINT_TYPE, ctx)
        try:
            quote = MaintenanceRequestService.catalog_quote_for_service(ctx["service_type"])
        except MaintenanceRequestError:
            quote = None
        if quote:
            ctx["catalog_service_id"] = quote["catalog_service_id"]
            ctx["maintenance_quote"] = quote
        if ctx.get("details") is None:
            return _reply(_maintenance_quote_intro(quote) + "\n" + responses.get("maint_details"), states.STATE_MAINT_DETAILS, ctx)
        if ctx.get("location") is None:
            return _reply(responses.get("maint_location"), states.STATE_MAINT_LOCATION, ctx)
        if ctx.get("date") is None:
            return _reply(responses.get("maint_date"), states.STATE_MAINT_DATE, ctx)
        try:
            ctx["date"] = MaintenanceRequestService.normalize_preferred_date(ctx["date"])
        except MaintenanceRequestError:
            ctx.pop("date", None)
            return _reply("يرجى كتابة تاريخ مناسب مثل بكرا أو 2030-07-01.", states.STATE_MAINT_DATE, ctx)
        return _reply(_maintenance_confirmation(ctx), states.STATE_MAINT_CONFIRM, ctx)

    def _log_nlp_result(self, nlp_result) -> None:
        """Best-effort analytics logging (Final Audit: intent/entity
        accuracy needs data to evaluate against). Never allowed to affect
        the chatbot's response — any DB error here is swallowed."""
        try:
            import json as _json
            conn = get_db_connection()
            try:
                conn.execute(
                    """INSERT INTO nlp_analysis_log
                       (session_id, detected_intent, confidence, source, entities_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        self.session_id,
                        nlp_result.intent,
                        nlp_result.confidence,
                        nlp_result.source,
                        _json.dumps(nlp_result.entities, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # BOOKING FLOW — one method per step
    # ═══════════════════════════════════════════════════════════════════════════

    def _booking_got_from(self, msg: str, ctx: dict):
        """Step 1 — user provided departure city.
        Normalized to the canonical Arabic spelling (Part Two: entity
        normalization) so "عمّان"/"Amman"/"عمان" all match the `trips`
        table the same way. Falls back to the raw text for a city not in
        config.SUPPORTED_CITIES rather than rejecting it outright — trip
        lookup will just correctly find no matching route later."""
        city = normalizer.normalize_city(msg) or _single_known_city(msg)
        if not city:
            return _reply("لم أتمكن من التعرف على مدينة الانطلاق. اكتب اسم المدينة مرة أخرى.", states.STATE_BOOKING_FROM, ctx)
        ctx["from_city"] = city
        if not ctx.get("to_city"):
            return _reply(responses.get("booking_to"), states.STATE_BOOKING_TO, ctx)
        return self._continue_booking_after_route(ctx)

    def _booking_got_to(self, msg: str, ctx: dict):
        """Step 2 — user provided destination city."""
        city = normalizer.normalize_city(msg) or _single_known_city(msg)
        if not city:
            return _reply("لم أتمكن من التعرف على مدينة الوصول. اكتب اسم المدينة مرة أخرى.", states.STATE_BOOKING_TO, ctx)
        ctx["to_city"] = city
        return self._continue_booking_after_route(ctx)

    def _continue_booking_after_route(self, ctx: dict):
        """Ask only the next missing booking slot after late entity capture."""
        if not ctx.get("date"):
            return _reply(responses.get("booking_date"), states.STATE_BOOKING_DATE, ctx)
        if ctx.get("seats") is None:
            return _reply(responses.get("booking_seats"), states.STATE_BOOKING_SEATS, ctx)
        if ctx.get("trip_class") is None:
            return _reply(responses.get("booking_class"), states.STATE_BOOKING_CLASS, ctx)
        return self._present_matching_trips(ctx)

    def _booking_got_date(self, msg: str, ctx: dict):
        """Step 3 — user provided travel date."""
        classified = normalizer.classify_future_travel_date(msg)
        if classified.status != "valid":
            self._clear_booking_date_dependents(ctx)
            return _reply(_travel_date_message(classified.status, msg), states.STATE_BOOKING_DATE, ctx)
        ctx["date"] = classified.value
        self._clear_booking_date_dependents(ctx, keep_date=True)
        if ctx.get("seats") is None:
            return _reply(responses.get("booking_seats"), states.STATE_BOOKING_SEATS, ctx)
        if ctx.get("trip_class") is None:
            return _reply(responses.get("booking_class"), states.STATE_BOOKING_CLASS, ctx)
        return self._present_matching_trips(ctx)

    def _booking_got_seats(self, msg: str, ctx: dict):
        """Step 4 — user provided seat count. Validate it's a number."""
        seats = ctx.get("seats") or _parse_number(msg)
        if not isinstance(seats, int) or seats <= 0:
            return _reply(responses.get("invalid_seats"), states.STATE_BOOKING_SEATS, ctx)
        ctx["seats"] = seats
        return _reply(responses.get("booking_class"), states.STATE_BOOKING_CLASS, ctx)

    def _booking_got_class(self, msg: str, ctx: dict):
        """Step 5 — user chose trip class (economy / business / vip)."""
        trip_class = _parse_trip_class(msg)
        if not trip_class:
            return _reply(responses.get("invalid_class"), states.STATE_BOOKING_CLASS, ctx)
        ctx["trip_class"] = trip_class

        return self._present_matching_trips(ctx)

    def _present_matching_trips(self, ctx: dict):
        """Store and display concrete trip choices after all required slots exist."""
        classified = normalizer.classify_future_travel_date(ctx.get("date"))
        if classified.status != "valid":
            self._clear_booking_date_dependents(ctx)
            return _reply(_travel_date_message(classified.status, ctx.get("date")), states.STATE_BOOKING_DATE, ctx)
        ctx["date"] = classified.value
        companies = self._fetch_matching_companies(ctx)
        if not companies:
            return self._offer_forming_trip_fallback(ctx)
        ctx["available_companies"] = companies
        return _reply(
            responses.get("booking_company", companies=_format_companies(companies)),
            states.STATE_BOOKING_COMPANY,
            ctx,
        )

    @staticmethod
    def _clear_booking_date_dependents(ctx: dict, *, keep_date: bool = False):
        if not keep_date:
            ctx.pop("date", None)
        for key in ("available_companies", "company_id", "company_name", "selected_trip_id", "booking_quote", "forming_request_id", "forming_payload", "forming_quote"):
            ctx.pop(key, None)

    def _forming_payload(self, ctx: dict) -> dict:
        """Translate already-collected booking entities to the public service contract.

        The Chat engine deliberately does not calculate thresholds, expiry,
        capacity, compatibility, or lifecycle state: TripRequestService is
        authoritative for each of those decisions.
        """
        requested_date = _resolve_trip_date(ctx.get("date"))
        return {
            "from_city": ctx.get("from_city"),
            "to_city": ctx.get("to_city"),
            "requested_date": requested_date,
            "requested_time_start": ctx.get("time") or "",
            "requested_time_end": ctx.get("time") or "",
            # Chat's booking flow already applies the bus capacity policy
            # when no vehicle preference was supplied. Preserve that same
            # explicit default for compatible-demand and pricing lookups so
            # a valid bus policy is discoverable before confirmation.
            "desired_vehicle_type": ctx.get("vehicle_type") or "bus",
            "desired_trip_class": ctx.get("trip_class") or "economy",
            "passenger_quantity": ctx.get("seats"),
        }

    def _offer_forming_trip_fallback(self, ctx: dict):
        """Offer, but never mutate, compatible forming-trip demand."""
        if self.user_id is None:
            return _reply(responses.get("no_trips_found"), states.STATE_IDLE, {})
        payload = self._forming_payload(ctx)
        try:
            compatible = TripRequestService.compatible(self.user_id, payload)
            quote = TripRequestService.preview_shared_pricing(payload)
        except TripRequestError as error:
            # The service validates the same domain contract as the
            # Transportation UI.  A safe validation failure must not be
            # hidden behind a generic chat error or trigger a mutation.
            return _reply(_forming_domain_error(error), states.STATE_IDLE, {})

        joinable = [card for card in compatible if not card.get("is_member") and card.get("remaining_capacity", 0) >= (ctx.get("seats") or 0)]
        if joinable:
            card = joinable[0]
            ctx["forming_request_id"] = card["request_id"]
            ctx["forming_payload"] = payload
            ctx["forming_quote"] = quote
            return _reply(
                _forming_join_offer(card, int(ctx.get("seats") or 1)),
                states.STATE_FORMING_JOIN_CONFIRM,
                ctx,
            )

        ctx["forming_payload"] = payload
        ctx["forming_quote"] = quote
        return _reply(
            _forming_mode_offer(payload, quote),
            states.STATE_FORMING_MODE,
            ctx,
        )

    def _choose_forming_mode(self, msg: str, ctx: dict):
        if intents.is_cancellation(msg):
            return _reply("لم يتم إنشاء طلب رحلة. يمكنك طلب رحلة أخرى في أي وقت.", states.STATE_IDLE, {})
        mode = _parse_sharing_mode(msg)
        if not mode:
            return _reply("هل تفضّل طلباً مشتركاً يمكن للآخرين الانضمام إليه، أم طلباً خاصاً لك فقط؟", states.STATE_FORMING_MODE, ctx)
        payload = ctx.get("forming_payload")
        if not isinstance(payload, dict):
            return _reply("تعذر تحضير طلب الرحلة بأمان. لم يُجرَ أي تغيير.", states.STATE_IDLE, {})
        payload = dict(payload)
        payload["sharing_mode"] = mode
        ctx["forming_payload"] = payload
        return _reply(_forming_create_offer(payload, ctx.get("forming_quote")), states.STATE_FORMING_CREATE_CONFIRM, ctx)

    def _confirm_forming_join(self, msg: str, ctx: dict):
        if _is_booking_preference_correction(msg):
            return self._offer_forming_trip_fallback(ctx)
        if intents.is_cancellation(msg):
            payload = ctx.get("forming_payload")
            if isinstance(payload, dict):
                ctx.pop("forming_request_id", None)
                return _reply(
                    "لن أنضم بك إلى الطلب المشترك. لم يُنشأ أي حجز.\n" +
                    _forming_mode_offer(payload, ctx.get("forming_quote")),
                    states.STATE_FORMING_MODE,
                    ctx,
                )
            return _reply("لم يتم الانضمام إلى طلب الرحلة. لم يُنشأ أي حجز.", states.STATE_IDLE, {})
        if not intents.is_confirmation(msg):
            return _reply("يرجى تأكيد الانضمام صراحةً (نعم) أو رفضه (لا).", states.STATE_FORMING_JOIN_CONFIRM, ctx)
        request_id = ctx.get("forming_request_id")
        quantity = ctx.get("seats")
        if self.user_id is None or not isinstance(request_id, int) or not isinstance(quantity, int) or quantity <= 0:
            return _reply("تعذر تأكيد طلب الرحلة بأمان. لم يُجرَ أي تغيير.", states.STATE_IDLE, {})
        try:
            card = TripRequestService.join(self.user_id, request_id, {"passenger_quantity": quantity})
        except TripRequestError as error:
            if error.code == "not_joinable" and isinstance(ctx.get("forming_payload"), dict):
                # The offered request may have expired between presentation
                # and confirmation.  It is not a generic chat failure: tell
                # the customer what changed and offer the normal next state.
                offer, next_state, updated_context = self._offer_forming_trip_fallback(ctx)
                return _reply(_forming_domain_error(error) + "\n" + offer, next_state, updated_context)
            return _reply(_forming_domain_error(error), states.STATE_IDLE, {})
        return _reply(_forming_joined_message(card), states.STATE_IDLE, {})

    def _confirm_forming_create(self, msg: str, ctx: dict):
        if _is_booking_preference_correction(msg):
            return self._offer_forming_trip_fallback(ctx)
        if intents.is_cancellation(msg):
            return _reply("لم يتم إنشاء طلب رحلة. لم يُنشأ أي حجز.", states.STATE_IDLE, {})
        if not intents.is_confirmation(msg):
            return _reply("يرجى تأكيد إنشاء طلب الرحلة صراحةً (نعم) أو رفضه (لا).", states.STATE_FORMING_CREATE_CONFIRM, ctx)
        payload = ctx.get("forming_payload")
        if self.user_id is None or not isinstance(payload, dict):
            return _reply("تعذر إنشاء طلب الرحلة بأمان. لم يُجرَ أي تغيير.", states.STATE_IDLE, {})
        try:
            card = TripRequestService.create(self.user_id, payload)
        except TripRequestError as error:
            return _reply(_forming_domain_error(error), states.STATE_IDLE, {})
        return _reply(_forming_created_message(card), states.STATE_IDLE, {})

    def _booking_got_company(self, msg: str, ctx: dict):
        """Step 6 — user selected a company. Show summary."""
        # A date/time correction while the choice list is open must refresh
        # concrete trip rows rather than leave a stale selectable list.
        if _is_booking_preference_correction(msg):
            ctx.pop("available_companies", None)
            ctx.pop("company_id", None)
            ctx.pop("company_name", None)
            ctx.pop("selected_trip_id", None)
            return self._present_matching_trips(ctx)

        companies = ctx.get("available_companies", [])
        chosen = _match_company(msg, companies)

        if not chosen:
            company_list_text = _format_companies(companies)
            return _reply(
                responses.get("invalid_company", companies=company_list_text),
                states.STATE_BOOKING_COMPANY,
                ctx
            )

        ctx["company_name"] = chosen["name_ar"]
        ctx["company_id"]   = chosen["company_id"]
        # A company can operate multiple matching departures. Preserve the
        # concrete row the customer selected so confirmation cannot silently
        # book a different trip from the same company.
        ctx["selected_trip_id"] = chosen["trip_id"]
        try:
            quote = BookingService.preview(trip_id=chosen["trip_id"], seats=ctx["seats"])
        except BookingError as error:
            return _reply(_booking_domain_error(error), states.STATE_IDLE, {})
        ctx["booking_quote"] = quote

        summary = responses.get(
            "booking_confirm",
            from_city   = ctx.get("from_city"),
            to_city     = ctx.get("to_city"),
            date        = ctx.get("date"),
            seats       = ctx.get("seats"),
            trip_class  = _class_label(ctx.get("trip_class", "")),
            company     = ctx.get("company_name"),
            unit_price  = quote["unit_price_jod"],
            total_price = quote["total_price_jod"],
        )
        return _reply(summary, states.STATE_BOOKING_CONFIRM, ctx)

    # ═══════════════════════════════════════════════════════════════════════════
    # MAINTENANCE FLOW — one method per step
    # ═══════════════════════════════════════════════════════════════════════════

    def _maint_got_type(self, msg: str, ctx: dict):
        """Step 1 — user chose service type."""
        service_type = normalizer.parse_service_type(msg) or ctx.get("service_type")
        if service_type not in config.MAINTENANCE_SERVICES:
            return _reply(responses.get("invalid_service_type"), states.STATE_MAINT_TYPE, ctx)
        ctx["service_type"] = service_type
        try:
            quote = MaintenanceRequestService.catalog_quote_for_service(service_type)
        except MaintenanceRequestError:
            quote = None
        if quote:
            ctx["catalog_service_id"] = quote["catalog_service_id"]
            ctx["maintenance_quote"] = quote
        else:
            ctx.pop("catalog_service_id", None)
            ctx.pop("maintenance_quote", None)
        return _reply(_maintenance_quote_intro(quote) + "\n" + responses.get("maint_details"), states.STATE_MAINT_DETAILS, ctx)

    def _maint_got_details(self, msg: str, ctx: dict):
        """Step 2 — user described the problem."""
        ctx["details"] = msg
        return _reply(responses.get("maint_location"), states.STATE_MAINT_LOCATION, ctx)

    def _maint_got_location(self, msg: str, ctx: dict):
        """Step 3 — user provided location."""
        ctx["location"] = msg
        return _reply(responses.get("maint_date"), states.STATE_MAINT_DATE, ctx)

    def _maint_got_date(self, msg: str, ctx: dict):
        """Step 4 — user provided preferred date. Show summary."""
        preferred_date = normalizer.extract_date(msg)
        if not preferred_date:
            return _reply("يرجى كتابة تاريخ مناسب مثل بكرا أو 2030-07-01.", states.STATE_MAINT_DATE, ctx)
        try:
            ctx["date"] = MaintenanceRequestService.normalize_preferred_date(preferred_date)
        except MaintenanceRequestError:
            return _reply("يرجى كتابة تاريخ صالح مثل بكرا أو 2030-07-01.", states.STATE_MAINT_DATE, ctx)
        return _reply(_maintenance_confirmation(ctx), states.STATE_MAINT_CONFIRM, ctx)

    # ═══════════════════════════════════════════════════════════════════════════
    # FINALIZERS — write to DB on confirmation
    # ═══════════════════════════════════════════════════════════════════════════

    def _finalize_booking(self, msg: str, ctx: dict):
        """Commit booking to DB if user confirmed, else cancel."""
        if intents.is_cancellation(msg):
            return _reply(responses.get("booking_cancelled"), states.STATE_IDLE, {})
        if not intents.is_confirmation(msg):
            return _reply(responses.get("booking_confirm_repeat"), states.STATE_BOOKING_CONFIRM, ctx)

        if self.user_id is None:
            # Defense in depth: /api/chat is customer-protected, but a
            # direct engine caller must never create an unowned booking.
            return _reply(responses.get("booking_owner_required"), states.STATE_IDLE, {})

        trip_id = ctx.get("selected_trip_id")
        seats = ctx.get("seats")
        if not trip_id or not isinstance(seats, int) or seats <= 0:
            return _reply(responses.get("no_trips_found"), states.STATE_IDLE, {})

        try:
            booking = BookingService.create(
                user_id=self.user_id,
                trip_id=trip_id,
                seats=seats,
                passenger_name=ctx.get("passenger_name", "ضيف"),
            )
        except BookingError as error:
            return _reply(_booking_domain_error(error), states.STATE_IDLE, {})
        return _reply(
            responses.get("booking_done", booking_id=booking["booking_id"], total_price=booking["committed_total_price_jod"]),
            states.STATE_IDLE,
            {},
        )

    def _finalize_maintenance(self, msg: str, ctx: dict):
        """Commit maintenance request to DB if user confirmed."""
        if intents.is_cancellation(msg):
            return _reply(responses.get("maint_cancelled"), states.STATE_IDLE, {})
        if not intents.is_confirmation(msg):
            return _reply(responses.get("maint_confirm_repeat"), states.STATE_MAINT_CONFIRM, ctx)

        if self.user_id is None:
            return _reply(responses.get("maintenance_owner_required"), states.STATE_IDLE, {})

        try:
            created = MaintenanceRequestService.create(self.user_id, {
                "service_type": ctx.get("service_type"), "service_details": ctx.get("details", ""),
                "location": ctx.get("location"), "preferred_date": ctx.get("date"),
                "catalog_service_id": ctx.get("catalog_service_id"), "quantity": 1,
            })
        except MaintenanceRequestError as error:
            return _reply(_maintenance_domain_error(error), states.STATE_IDLE, {})
        return _reply(responses.get("maint_done", request_id=created["request_id"]), states.STATE_IDLE, {})

    # ═══════════════════════════════════════════════════════════════════════════
    # INLINE QUERY HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_all_trips(self) -> str:
        """Return a formatted list of all active trips."""
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """SELECT t.from_city, t.to_city, t.departure_time,
                          t.trip_class, t.price_jod, c.name_ar
                   FROM trips t
                   JOIN companies c ON t.company_id=c.company_id
                   WHERE t.status='active'
                   ORDER BY t.departure_time
                   LIMIT 8"""
            ).fetchall()

            if not rows:
                return responses.get("no_trips_found")

            lines = ["🗺️ الرحلات المتاحة:\n"]
            for r in rows:
                lines.append(
                    f"• {r['from_city']} ← {r['to_city']} | "
                    f"{r['departure_time'][11:16]} | "
                    f"{_class_label(r['trip_class'])} | "
                    f"{r['price_jod']} د.أ | {r['name_ar']}"
                )
            lines.append("\nاكتب 'حجز رحلة' لبدء الحجز.")
            return "\n".join(lines)
        finally:
            conn.close()

    def _get_companies_list(self) -> str:
        """Return formatted list of transport companies."""
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """SELECT name_ar, city, phone
                   FROM companies
                   WHERE company_type='transport' AND status='active'"""
            ).fetchall()

            if not rows:
                return "عذراً، لا توجد شركات نقل مسجّلة حالياً."

            lines = ["🏢 شركات النقل المتاحة:\n"]
            for r in rows:
                lines.append(f"• {r['name_ar']} — {r['city']} — {r['phone']}")
            return "\n".join(lines)
        finally:
            conn.close()

    def _get_price_info(self, ctx: dict) -> str:
        """Return price for the route in context, if available."""
        from_city = ctx.get("from_city")
        to_city   = ctx.get("to_city")
        if not from_city or not to_city:
            return responses.get("ask_price_first")

        conn = get_db_connection()
        try:
            rows = conn.execute(
                """SELECT trip_class, price_jod
                   FROM trips
                   WHERE from_city=? AND to_city=? AND status='active'
                   ORDER BY price_jod""",
                (from_city, to_city)
            ).fetchall()

            if not rows:
                return responses.get("no_trips_found")

            lines = [f"💰 أسعار رحلة {from_city} ← {to_city}:\n"]
            for r in rows:
                lines.append(f"• {_class_label(r['trip_class'])}: {r['price_jod']} د.أ")
            return "\n".join(lines)
        finally:
            conn.close()

    def _get_seats_info(self, ctx: dict) -> str:
        """Return available seats for the route in context."""
        from_city = ctx.get("from_city")
        to_city   = ctx.get("to_city")
        if not from_city or not to_city:
            return responses.get("ask_seats_first")

        conn = get_db_connection()
        try:
            rows = conn.execute(
                """SELECT available_seats, trip_class, departure_time
                   FROM trips
                   WHERE from_city=? AND to_city=? AND status='active'""",
                (from_city, to_city)
            ).fetchall()

            if not rows:
                return responses.get("no_trips_found")

            lines = [f"💺 المقاعد المتاحة {from_city} ← {to_city}:\n"]
            for r in rows:
                lines.append(
                    f"• {_class_label(r['trip_class'])} "
                    f"({r['departure_time'][11:16]}): "
                    f"{r['available_seats']} مقعد"
                )
            return "\n".join(lines)
        finally:
            conn.close()

    def _fetch_matching_companies(self, ctx: dict) -> list:
        """
        Return list of companies that have trips matching
        from_city, to_city, trip_class with available seats.

        (Bug fix — Arabic NLP Intelligence phase audit: this query
        referenced `t.is_active=1`, but the `trips` table has no such
        column — it uses `status TEXT CHECK(status IN ('active',
        'cancelled', 'completed'))` instead (see database/init_db.py).
        That meant every booking crashed with sqlite3.OperationalError
        the moment a user reached this step, regardless of the NLP work
        in this phase. Also now filters on the company's own `status`,
        since offering a suspended/inactive company's trips wouldn't
        make sense either — same bug, same fix.)
        """
        requested_date = _resolve_trip_date(ctx.get("date"))
        if not requested_date:
            return []
        return BookingService.search_compatible(
            from_city=ctx.get("from_city"),
            to_city=ctx.get("to_city"),
            requested_date=requested_date,
            trip_class=ctx.get("trip_class", "economy"),
            seats=int(ctx.get("seats", 1)),
            departure_time=ctx.get("time"),
        )

# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL HELPERS (pure functions — no DB, no state)
# ═══════════════════════════════════════════════════════════════════════════════

def _reply(text: str, next_state: str, ctx: dict) -> tuple:
    """
    Convenience wrapper so every handler returns the same 3-tuple.
    Makes the code uniform and easy to read.
    """
    return (text, next_state, ctx)


def _parse_number(text: str):
    """
    Extract an integer from user input.
    Handles Arabic-Indic digits and written numbers.

    Returns int or None if not parseable.

    (Arabic NLP Intelligence phase: delegates to the single canonical
    implementation in backend/nlp/normalizer.py — "never duplicate
    existing code". Behavior is unchanged; normalizer.parse_number()
    covers the same digit/word set this function used to hardcode.)
    """
    return normalizer.parse_number(text)


def _single_known_city(text: str) -> str | None:
    """Accept one canonical city embedded in a natural slot answer.

    ``normalize_city`` intentionally requires an exact alias.  Slot answers
    such as ``من عمّان`` and ``إلى إربد`` are normal Arabic conversation, so
    use the existing bounded city extractor before treating the input as
    unsupported.  Multiple mentions remain ambiguous and are not guessed.
    """
    cities = normalizer.find_cities_in_text(text)
    return cities[0] if len(cities) == 1 else None


def _parse_trip_class(text: str) -> str:
    """
    Map user input to a valid trip class key.

    Returns 'economy', 'business', 'vip', or None.

    (Delegates to backend/nlp/normalizer.py — same reasoning as
    _parse_number() above.)
    """
    return normalizer.parse_trip_class(text)


def _class_label(trip_class: str) -> str:
    """Translate trip class key to Arabic display label."""
    return {
        "economy":  "اقتصادي",
        "business": "أعمال",
        "vip":      "VIP",
    }.get(trip_class, trip_class)


def _format_companies(companies: list) -> str:
    """Format a list of company dicts into a numbered Arabic string."""
    if not companies:
        return "لا توجد شركات متاحة."
    lines = []
    for i, c in enumerate(companies, 1):
        dep_time = c.get("departure_time", "")
        time_str = dep_time[11:16] if len(dep_time) > 10 else ""
        lines.append(
            f"{i}. {c['name_ar']} — {_jod_text(c.get('price_jod'))} د.أ"
            + (f" — {time_str}" if time_str else "")
            + (f" — {c.get('vehicle_type')}" if c.get("vehicle_type") else "")
            + (f" — {c.get('available_seats')} مقعد متاح" if c.get("available_seats") is not None else "")
        )
    return "\n".join(lines)


def _forming_join_offer(card: dict, quantity: int) -> str:
    estimate = ""
    if card.get("pricing_available") and card.get("per_passenger_estimate_jod"):
        estimate = f"\nالسعر التقديري الحالي لكل راكب: {card['per_passenger_estimate_jod']} د.أ (قد يتغير قبل الحجز)."
    return (
        "لم أجد رحلة مجدولة مناسبة، لكن يوجد طلب رحلة قيد الاكتمال:\n"
        f"{card['from_city']} ← {card['to_city']} | {card.get('requested_date')} | {card.get('requested_time_start') or 'غير محدد'}\n"
        f"المركبة: {card.get('desired_vehicle_type') or 'غير محدد'} | الدرجة: {card.get('desired_trip_class') or 'غير محدد'}\n"
        f"العدد الحالي: {card['current_passengers']} من {card['minimum_passengers']} ركاب مطلوبين "
        f"(السعة القصوى {card['maximum_passengers']}).{estimate}\n"
        f"سأنضم بك لـ {quantity} راكب/ركاب فقط بعد تأكيدك. هل تريد الانضمام؟"
    )


def _forming_mode_offer(payload: dict, quote: dict | None = None) -> str:
    estimate = _forming_price_note(quote)
    return (
        "لا توجد رحلة مجدولة أو رحلة مشتركة متوافقة حالياً. "
        "يمكنني تحضير طلب رحلة جديد، وليس حجزاً أو رحلة مؤكدة.\n"
        + estimate + "\n"
        "هل تفضّل طلباً مشتركاً يمكن للآخرين الانضمام إليه وقد يظهر له سعر تقديري، "
        "أم طلباً خاصاً لك فقط؟"
    )


def _forming_create_offer(payload: dict, quote: dict | None = None) -> str:
    time_text = payload.get("requested_time_start") or "غير محدد"
    vehicle = payload.get("desired_vehicle_type") or "bus"
    trip_class = payload.get("desired_trip_class") or "economy"
    return (
        "لا توجد رحلة مجدولة أو رحلة قيد الاكتمال مطابقة حالياً.\n"
        "يمكنني إنشاء طلب رحلة فقط، وليس حجزاً أو رحلة مؤكدة:\n"
        f"{payload.get('from_city')} ← {payload.get('to_city')} | {payload.get('requested_date')} | "
        f"{time_text} | {payload.get('passenger_quantity')} راكب/ركاب | {vehicle} | {trip_class} | "
        f"{'مشترك' if payload.get('sharing_mode') == 'shared' else 'خاص'}.\n"
        + _forming_price_note(quote) + "\n"
        "هل تريد إنشاء طلب الرحلة؟"
    )


def _forming_joined_message(card: dict) -> str:
    estimate = ""
    if card.get("pricing_available") and card.get("per_passenger_estimate_jod"):
        estimate = f" السعر التقديري الحالي بعد الانضمام لكل راكب: {card['per_passenger_estimate_jod']} د.أ، وقد يتغير قبل الحجز النهائي."
    return (
        "تم الانضمام إلى طلب الرحلة بنجاح. "
        f"الطلب الآن {card['current_passengers']} من {card['minimum_passengers']} ركاب مطلوبين. "
        "هذا طلب قيد الاكتمال وليس حجزاً أو رحلة مؤكدة." + estimate
    )


def _jod_text(value) -> str:
    """Presentation-only formatting for an amount already selected by the server."""
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "غير محدد حالياً"


def _forming_created_message(card: dict) -> str:
    return (
        "تم إنشاء طلب الرحلة بنجاح. "
        f"العدد الحالي {card['current_passengers']} من {card['minimum_passengers']} ركاب مطلوبين "
        f"(السعة القصوى {card['maximum_passengers']}). "
        "لم يتم إنشاء حجز أو رحلة تشغيلية."
    )


def _forming_domain_error(error: TripRequestError) -> str:
    messages = {
        "already_member": "أنت منضم بالفعل إلى طلب الرحلة هذا.",
        "capacity_exceeded": "العدد المطلوب يتجاوز السعة المتبقية لطلب الرحلة.",
        "not_joinable": "طلب الرحلة لم يعد متاحاً للانضمام.",
        "request_frozen": "طلب الرحلة قيد التحضير التشغيلي ولا يمكن تغييره الآن.",
        "expiration_not_feasible": "لا يمكن إنشاء طلب بهذه المدة لأن مهلة تجميع الطلبات غير كافية.",
        "ineligible_date": "اختر تاريخاً مستقبلياً لطلب الرحلة.",
        "compatible_request_exists": "يوجد طلب رحلة متوافق؛ اختر الانضمام إليه صراحةً بدلاً من إنشاء طلب مكرر.",
        "invalid_json": "تعذر قراءة بيانات طلب الرحلة. ابدأ طلباً جديداً من فضلك.",
        "invalid_field": "تأكد من المدن والتاريخ والعدد المطلوب ثم حاول مرة أخرى.",
        "invalid_route": "يجب أن تكون مدينة الانطلاق مختلفة عن مدينة الوصول.",
        "invalid_time_window": "تأكد من أن وقت نهاية الرحلة لا يسبق وقت بدايتها.",
        "forbidden_field": "لا يمكن تعديل التسعير أو حالة الطلب من خلال المحادثة.",
        "private_request": "الطلبات الخاصة لا يمكن الانضمام إليها؛ يمكنك إنشاء طلب جديد.",
        "not_found": "لم يعد طلب الرحلة متاحاً. يمكنني البحث عن خيار آخر.",
        "pricing_unavailable": "لا توجد سياسة تسعير نشطة لهذه الرحلة حالياً؛ لم يُنشأ أي طلب.",
        "not_eligible": "لم يصل طلب الرحلة إلى العدد المطلوب بعد.",
    }
    return messages.get(error.code, "تعذر إكمال طلب الرحلة بأمان. يرجى مراجعة البيانات والمحاولة مرة أخرى.")


def _booking_domain_error(error: BookingError) -> str:
    """Map booking outcomes without exposing internal database/service text."""
    messages = {
        "owner_required": responses.get("booking_owner_required"),
        "invalid_seats": "عدد المقاعد غير صالح. ابدأ طلب حجز جديداً وحدد عدداً صحيحاً.",
        "not_found": "الرحلة المختارة لم تعد متاحة. ابحث عن رحلة جديدة من فضلك.",
        "not_bookable": "الرحلة المختارة لم تعد متاحة للحجز. ابحث عن رحلة جديدة من فضلك.",
        "capacity_exceeded": "لم تعد المقاعد المطلوبة متاحة في هذه الرحلة. ابحث عن رحلة جديدة من فضلك.",
        "pricing_unavailable": "تعذر تأكيد سعر هذه الرحلة حالياً. لم يُنشأ أي حجز.",
    }
    return messages.get(error.code, "تعذر تأكيد الحجز الآن. لم يُنشأ أي حجز؛ حاول مرة أخرى لاحقاً.")


def _forming_price_note(quote: dict | None) -> str:
    if not isinstance(quote, dict) or not quote.get("pricing_available"):
        return "لا توجد سياسة تسعير نشطة لهذه الرحلة حالياً؛ لا يمكن عرض تقدير قبل اعتمادها."
    return (
        f"السعر الأساسي التقديري للطلب المشترك: {quote['base_trip_price_jod']} د.أ؛ "
        f"والتقدير الحالي لكل راكب: {quote['per_passenger_estimate_jod']} د.أ. "
        "هذا تقدير وليس حجزاً أو سعراً نهائياً."
    )


def _maintenance_domain_error(error: MaintenanceRequestError) -> str:
    messages = {
        "invalid_json": "تعذر قراءة بيانات طلب الصيانة. ابدأ طلباً جديداً من فضلك.",
        "invalid_service": "اختر خدمة صيانة مدعومة ثم حاول مرة أخرى.",
        "invalid_location": "أدخل موقعاً واضحاً لخدمة الصيانة.",
        "invalid_date": "أدخل تاريخ الخدمة بالصيغة YYYY-MM-DD.",
        "invalid_quantity": "كمية خدمة الصيانة غير صالحة.",
        "service_unavailable": "خدمة الصيانة المختارة غير متاحة حالياً.",
        "service_mismatch": "الخدمة المختارة لا تطابق بند التسعير المتاح.",
        "forbidden_field": "لا يمكن تعديل السعر أو حالة طلب الصيانة من خلال المحادثة.",
    }
    return messages.get(error.code, "تعذر حفظ طلب الصيانة الآن. لم يُنشأ أي طلب؛ حاول مرة أخرى لاحقاً.")


def _maintenance_quote_intro(quote: dict | None) -> str:
    if not quote or not quote.get("pricing_available"):
        return "يتطلب سعر هذه الخدمة فحصاً قبل تقديم تقدير."
    if quote["pricing_type"] == "fixed":
        return f"السعر الثابت لهذه الخدمة هو {quote['minimum_jod']} د.أ."
    return f"السعر المتوقع لهذه الخدمة بين {quote['minimum_jod']} و{quote['maximum_jod']} د.أ، وليس سعراً نهائياً."


def _maintenance_confirmation(ctx: dict) -> str:
    """Build the final maintenance proposal from the server-derived quote."""
    summary = responses.get(
        "maint_confirm",
        service_type=ctx.get("service_type"),
        details=ctx.get("details"),
        location=ctx.get("location"),
        date=ctx.get("date"),
    )
    return _maintenance_quote_intro(ctx.get("maintenance_quote")) + "\n" + summary


def _parse_sharing_mode(text: str) -> str | None:
    normalized = preprocessing.preprocess(text or "")["normalized"]
    if any(token in normalized for token in ("مشترك", "مشاركة", "shared", "group")):
        return "shared"
    if any(token in normalized for token in ("خاص", "private", "لوحدي", "لنفسى", "نفسي")):
        return "private"
    return None


def _is_why_question(text: str) -> bool:
    normalized = preprocessing.preprocess(text or "")["normalized"]
    return normalized in {"لماذا", "ليش", "ليه", "why", "how come"}


def _is_booking_preference_correction(msg: str) -> bool:
    """Recognize explicit time/class changes without treating menu 1/2/3 as a class change."""
    if normalizer.extract_date(msg) or normalizer.extract_time(msg):
        return True
    trip_class = normalizer.parse_trip_class(msg)
    return trip_class is not None and _parse_number(msg) not in (1, 2, 3)


def _looks_like_correction(normalized_msg: str) -> bool:
    """Return whether the user explicitly signals an amendment, not a slot answer."""
    return any(marker in normalized_msg for marker in ("قصدي", "بدل", "خليها", "غير", "مش ", "لا "))


def _has_from_cue(normalized_msg: str) -> bool:
    return "من " in normalized_msg or normalized_msg.startswith("من")


def _has_to_cue(normalized_msg: str) -> bool:
    return any(cue in normalized_msg for cue in ("الى ", "الي ", "للعقبة", "لاربد", "للزرقاء"))


def _match_company(user_input: str, companies: list):
    """
    Match user input (number or name) to a company in the list.

    Returns the matched company dict or None.
    """
    text = user_input.strip()

    # Match by number (e.g. "1", "٢")
    num = _parse_number(text)
    if num and 1 <= num <= len(companies):
        return companies[num - 1]

    # A company name is only sufficient when it identifies one displayed
    # departure. Otherwise require the numbered choice shown to the user.
    text_lower = text.lower()
    name_matches = [c for c in companies if text_lower in c["name_ar"].lower()]
    if len(name_matches) == 1:
        return name_matches[0]

    return None


def _resolve_trip_date(value: str | None) -> str | None:
    """Turn supported relative date entities into the date format stored in trips."""
    classified = normalizer.classify_future_travel_date(value)
    return classified.value if classified.status == "valid" else None


def _travel_date_message(status: str, raw_message: str | None) -> str:
    english = bool(re.search(r"[A-Za-z]", raw_message or ""))
    if status == "past":
        return responses.get("past_travel_date_en" if english else "past_travel_date")
    return responses.get("invalid_travel_date_en" if english else "invalid_travel_date")


def _booking_step_explanation(state: str) -> str:
    """Explain the active booking question without changing the conversation."""
    explanations = {
        states.STATE_BOOKING_FROM: "أحتاج مدينة الانطلاق حتى أبحث عن الرحلات من المكان الصحيح.",
        states.STATE_BOOKING_TO: "أحتاج مدينة الوصول لتحديد المسار المناسب.",
        states.STATE_BOOKING_DATE: "أحتاج تاريخ سفر صحيحاً ومستقبلياً للتحقق من الرحلات أو الطلبات المتاحة لذلك اليوم.",
        states.STATE_BOOKING_SEATS: "أحتاج عدد المقاعد للتحقق من السعة وحساب السعر الصحيح.",
        states.STATE_BOOKING_CLASS: "أحتاج درجة الرحلة لمطابقة الخيارات والسعر المتاحين.",
        states.STATE_BOOKING_COMPANY: "أحتاج اختيارك من القائمة حتى أعد عرض الحجز الدقيق قبل التأكيد.",
        states.STATE_BOOKING_CONFIRM: "أحتاج تأكيدك لأن الحجز لا يُنشأ ولا يتغير قبل موافقتك الصريحة.",
    }
    return explanations.get(state, "أحتاج هذه المعلومة لإكمال الحجز بدقة. يمكنك الإجابة على السؤال الأخير أو كتابة إلغاء.")
