"""Conversational Arabic NLU regressions for the shared Chat/Voice pipeline."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from backend import intents, states


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    original_path = config.DATABASE_PATH
    config.DATABASE_PATH = path
    try:
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            yield test_client
    finally:
        config.DATABASE_PATH = original_path
        if os.path.exists(path):
            os.remove(path)


def login(client, session_id="nlu-session"):
    from backend.security.csrf import SESSION_KEY

    token = "nlu-test-token"
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["role"] = "customer"
        session["session_id"] = session_id
        session[SESSION_KEY] = token
    return token


def chat(client, token, message):
    response = client.post("/api/chat", json={"message": message, "csrf_token": token})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["reply"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("هلااا", "greeting"),
        ("صباح الخير", "greeting"),
        ("يسلمو", "thanks"),
        ("اشوفك", "goodbye"),
        ("شو بتقدر تعمل؟", "help"),
        ("احجوز", "booking"),
        ("نفسي اسافر", "booking"),
        ("بدي مواصلات", "booking"),
        ("عندي عطل بالمحرك", "maintenance"),
        ("I need a trip", "booking"),
        ("Maintenance", "maintenance"),
    ],
)
def test_natural_short_intents_and_paraphrases(message, expected):
    # Several variants are intentionally not the primary vocabulary entries.
    assert intents.classify(message) == expected


def test_actionable_request_outranks_conversational_wrapper():
    assert intents.classify("مرحبا بدي احجز رحلة") == "booking"
    assert intents.classify("تمام شكرا بدي صيانة") == "maintenance"
    assert intents.classify("السلام عليكم بدي اروح العقبة") == "booking"


def test_ambiguous_words_do_not_randomly_start_a_side_effecting_flow(client):
    token = login(client)
    assert intents.classify("مشكلة") == "unknown"
    reply = chat(client, token, "مشكلة")
    assert "توض" in reply or "الرحلات" in reply
    assert intents.classify("تمام") == "confirm"
    assert "لا يوجد طلب معل" in chat(client, token, "تمام")


def test_thanks_preserves_active_context_and_short_city_answer_is_consumed(client):
    token = login(client)
    assert "مدينة" in chat(client, token, "حجز")
    assert "الرحب" in chat(client, token, "شكرا")
    assert "وإلى" in chat(client, token, "عمان")


def test_booking_context_accepts_short_date_people_and_time_without_reset(client):
    token = login(client, "contextual-booking")
    chat(client, token, "حجز")
    chat(client, token, "عمان")
    chat(client, token, "العقبة")
    assert "مقاعد" in chat(client, token, "بكرا")
    assert "درجة" in chat(client, token, "شخصين")
    # The existing flow asks for trip class at this point, but its shared
    # entity pass must still retain an out-of-order contextual time answer.
    chat(client, token, "الساعة 6")
    from backend.chatbot import ChatbotEngine

    context = ChatbotEngine("contextual-booking", user_id=1).memory.get_context_dict()
    assert context["time"] == "06:00"
    assert context["seats"] == 2


def test_explicit_corrections_keep_other_booking_slots(client):
    token = login(client, "correction-nlu")
    from backend.chatbot import ChatbotEngine

    engine = ChatbotEngine("correction-nlu", user_id=1)
    engine.memory.update(states.STATE_BOOKING_COMPANY, {
        "from_city": "عمان", "to_city": "إربد", "date": "2030-07-01",
        "time": "06:00", "seats": 2, "trip_class": "economy", "available_companies": [],
    })
    chat(client, token, "لا قصدي العقبة")
    context = ChatbotEngine("correction-nlu", user_id=1).memory.get_context_dict()
    assert context["from_city"] == "عمان"
    assert context["to_city"] == "العقبة"
    assert context["seats"] == 2
    chat(client, token, "خليها الساعة 8")
    context = ChatbotEngine("correction-nlu", user_id=1).memory.get_context_dict()
    assert context["time"] == "08:00"


def test_non_answer_does_not_cancel_pending_confirmation(client):
    token = login(client, "pending-confirmation")
    from backend.chatbot import ChatbotEngine

    engine = ChatbotEngine("pending-confirmation", user_id=1)
    engine.memory.update(states.STATE_FORMING_CREATE_CONFIRM, {"forming_payload": {}})
    reply = chat(client, token, "ممكن توضح؟")
    assert "تأكيد" in reply
    assert ChatbotEngine("pending-confirmation", user_id=1).memory.get_state() == states.STATE_FORMING_CREATE_CONFIRM


def test_voice_transcript_contract_remains_the_normal_chat_sender():
    source = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "static", "js", "voice.js"), encoding="utf-8").read()
    assert "window.sendMessage()" in source
    assert 'fetch("/api/voice/transcribe"' in source
    assert 'fetch("/api/chat"' not in source
