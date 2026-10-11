"""
backend/nlp/entity_extractor.py — Named Entity Recognition (Part Two).

Two layers, merged:

1. Domain gazetteer/regex extraction (ALWAYS available, no model needed).
   This is deliberately the primary layer, not a fallback — a generic NER
   model tagged with generic labels (PER/LOC/ORG/DATE) has no way to know
   that this app needs the *domain* distinction between "departure city"
   and "destination city", or that "تغيير زيت" maps to the service_type
   key 'oil_change' in config.MAINTENANCE_SERVICES. That mapping only
   exists in backend/nlp/normalizer.py's gazetteers, built directly from
   this project's own config/DB vocabulary.

2. MARBERT generic NER (optional — used to additionally surface PERSON
   names and free-form LOCATION mentions that the fixed gazetteer can't
   anticipate, e.g. a maintenance request's street address, or a
   passenger's name). If MARBERT can't be loaded, this layer is silently
   skipped — extract() still returns everything layer 1 found.

Output is a flat dict using the SAME key names backend/chatbot.py's
SessionContext already uses (from_city, to_city, date, seats, trip_class,
service_type, location, passenger_name, ...) so hybrid_pipeline.py can
merge it straight into ctx with no translation step, per Part Three.
"""

import config
from backend.nlp import model_loader, normalizer


def _extract_route(normalized_text: str) -> dict:
    """
    Departure/destination city detection with cue-word awareness.
    Falls back to positional order (first mention = departure, second =
    destination) when no explicit "من / إلى" cue is present — this is a
    common enough pattern in casual Arabic ("عمان ع اربد") to be worth
    supporting, but only when exactly two distinct cities are mentioned so
    we never guess when it's genuinely ambiguous.
    """
    result = {"from_city": None, "to_city": None}

    from_cue_pos = None
    for cue in ("من ", "من"):
        idx = normalized_text.find(cue)
        if idx != -1:
            from_cue_pos = idx
            break

    to_cue_pos = None
    to_cue_len = 0
    for cue in ("الى ", "إلى ", "الي ", "لـ", " ل "):
        idx = normalized_text.find(cue)
        if idx != -1:
            to_cue_pos = idx
            to_cue_len = len(cue)
            break

    if from_cue_pos is not None and to_cue_pos is not None and to_cue_pos > from_cue_pos:
        from_segment = normalized_text[from_cue_pos:to_cue_pos]
        to_segment = normalized_text[to_cue_pos + to_cue_len:]
        from_cities = normalizer.find_cities_in_text(from_segment)
        to_cities = normalizer.find_cities_in_text(to_segment)
        if from_cities:
            result["from_city"] = from_cities[0]
        if to_cities:
            result["to_city"] = to_cities[0]
        if result["from_city"] or result["to_city"]:
            return result

    # No usable cue words — fall back to positional order, but only when
    # unambiguous (exactly two distinct cities mentioned anywhere).
    all_cities = normalizer.find_cities_in_text(normalized_text)
    if len(all_cities) == 2:
        result["from_city"], result["to_city"] = all_cities[0], all_cities[1]
    elif len(all_cities) == 1:
        # Colloquial intent such as "بدي اروح العقبة" expresses a
        # destination even without the formal "إلى" cue. Keep this narrow
        # so a lone city in an otherwise ambiguous message is not guessed.
        if any(cue in normalized_text for cue in ("اريد اروح", "بدي اروح", "راح اروح", "رايح", "مسافر")):
            result["to_city"] = all_cities[0]

    return result


_SEAT_CUE_WORDS = ["مقعد", "مقاعد", "راكب", "ركاب", "شخص", "اشخاص", "seat", "passenger"]


# Arabic grammar encodes "two X" via the dual suffix (ـين/ـان) on the noun
# itself, with no separate digit anywhere in the sentence — "لشخصين" IS "for
# two people". These are recognized directly rather than relying on a
# nearby digit that may not exist.
_DUAL_FORM_COUNT_WORDS = {
    "شخصين": 2, "شخصان": 2, "راكبين": 2, "راكبان": 2,
    "مقعدين": 2, "مقعدان": 2, "تذكرتين": 2,
}


def _extract_passenger_count(normalized_text: str):
    """
    Only extract a passenger count when a seat/passenger cue is actually
    present, and only trust a number that is directly adjacent to that
    cue (the immediately preceding or following whitespace-separated
    token) — NOT just "somewhere within N characters", which can still
    reach into an unrelated nearby date/phone number when the two
    happen to sit close together in the sentence (e.g. "...يوم
    2025-08-01 لشخصين" would otherwise misread the date as the seat
    count). Tokenizing and checking only true neighbors avoids that.
    """
    tokens = normalized_text.split()
    for i, token in enumerate(tokens):
        dual_match = next((w for w in _DUAL_FORM_COUNT_WORDS if w in token), None)
        if dual_match:
            return _DUAL_FORM_COUNT_WORDS[dual_match]
        if any(cue in token for cue in _SEAT_CUE_WORDS):
            for neighbor_idx in (i - 1, i + 1):
                if 0 <= neighbor_idx < len(tokens):
                    count = normalizer.parse_number(tokens[neighbor_idx])
                    if count is not None:
                        return count
    return None


def _rule_based_entities(normalized_text: str, raw_text: str) -> dict:
    entities = {}

    route = _extract_route(normalized_text)
    entities["from_city"] = route["from_city"]
    entities["to_city"] = route["to_city"]
    all_cities = normalizer.find_cities_in_text(normalized_text)
    entities["cities"] = all_cities

    entities["date"] = normalizer.extract_date(raw_text)
    entities["time"] = normalizer.extract_time(raw_text)
    entities["seats"] = _extract_passenger_count(normalized_text)
    entities["trip_class"] = normalizer.parse_trip_class(normalized_text)
    entities["service_type"] = normalizer.parse_service_type(normalized_text)
    entities["vehicle_type"] = normalizer.parse_vehicle_type(normalized_text)

    # Phone/email are looked up against the raw (unnormalized) text —
    # normalization lowercases and strips punctuation, which would corrupt
    # an email address like "Name@Example.com".
    entities["phone"] = normalizer.extract_phone(raw_text)
    entities["email"] = normalizer.extract_email(raw_text)

    entities["location"] = None       # only ever filled by MARBERT (layer 2)
    entities["passenger_name"] = None  # only ever filled by MARBERT (layer 2)
    entities["names"] = []

    return entities


def _marbert_entities(raw_text: str) -> dict:
    """Optional layer 2. Returns {} (not None) on any failure so callers
    can safely do rule_entities.update(marbert_entities) unconditionally."""
    if not config.ENABLE_AI_NLP:
        return {}
    try:
        ner = model_loader.get_marbert_ner()
        tags = ner(raw_text)
    except model_loader.MARBERTNotAvailableError:
        return {}
    except Exception:
        # Part Seven (Security): malformed input must never crash the
        # pipeline — degrade silently to "no extra entities".
        return {}

    names = [t["word"] for t in tags if t.get("entity_group") in ("PER", "PERSON")]
    locations = [t["word"] for t in tags if t.get("entity_group") in ("LOC", "GPE")]
    orgs = [t["word"] for t in tags if t.get("entity_group") in ("ORG",)]

    out = {}
    if names:
        out["names"] = names
        out["passenger_name"] = names[0]
    if locations:
        # Only surface as a generic "location" (e.g. a maintenance address)
        # if it isn't already one of our known cities — cities are handled
        # more precisely by the gazetteer layer above.
        unknown_locations = [loc for loc in locations if not normalizer.normalize_city(loc)]
        if unknown_locations:
            out["location"] = unknown_locations[0]
    if orgs:
        out["company_name"] = orgs[0]
    return out


def extract(normalized_text: str, raw_text: str | None = None, *, include_ner: bool = True) -> dict:
    """
    Public entry point. `normalized_text` should come from
    preprocessing.preprocess()['normalized']; `raw_text` (original,
    unnormalized) is used for phone/email/MARBERT so casing/punctuation
    that matters for those isn't destroyed. If raw_text isn't given,
    normalized_text is reused for both (still works, just slightly less
    precise for emails).
    """
    raw_text = raw_text if raw_text is not None else normalized_text
    entities = _rule_based_entities(normalized_text, raw_text)
    if include_ner:
        entities.update({k: v for k, v in _marbert_entities(raw_text).items() if v})
    # Drop empty/None values so merging into conversation context never
    # overwrites an already-known entity with a blank one (Part Three).
    return {k: v for k, v in entities.items() if v not in (None, [], "")}
