"""
backend/nlp — Arabic Natural Language Intelligence (Phase Two).

Modular hybrid NLP pipeline layered on top of (never replacing) the
existing rule-based system in backend/intents.py:

    preprocessing.py       Arabic text cleaning/normalization
    normalizer.py          entity value canonicalization (cities, numbers,
                            trip class, service type, phone/email, dates)
    model_loader.py         AraBERT/MARBERT lazy singleton loading
    intent_classifier.py    AraBERT-based intent classification + confidence
    entity_extractor.py     MARBERT + gazetteer/regex NER
    confidence.py           fallback threshold decision
    hybrid_pipeline.py       orchestrates all of the above; the only module
                            backend/chatbot.py and routes/nlp_routes.py
                            need to import from

See backend/ai/arabert_placeholder.py for the original Phase One stub this
package supersedes for intent/entity work (transcribe_audio/analyze_sentiment
in that file are untouched — voice transcription stays Whisper's job, and
sentiment analysis is explicitly out of scope for this phase).
"""
