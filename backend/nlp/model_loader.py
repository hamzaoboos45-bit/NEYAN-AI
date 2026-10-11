"""
backend/nlp/model_loader.py — AraBERT / MARBERT loading (Part Six: Performance).

Mirrors backend/speech/whisper_engine.py on purpose: this project already
has one correct pattern for "load a heavy ML model exactly once, reuse it
for every request, and never let a missing/unavailable model crash the
app" — Whisper. This module applies the same pattern to AraBERT and
MARBERT instead of inventing a second one.

    - Models are module-level singletons, loaded behind a thread lock.
    - preload() is called once at app startup (see app.py) so the first
      chat request doesn't pay the load cost. It NEVER raises.
    - Every other function raises a typed *NotAvailableError with a clear
      message if the model can't be loaded (missing `transformers`/`torch`,
      or — relevant in some deployments — no network access to download
      model weights on first run). Callers (intent_classifier.py,
      entity_extractor.py) always catch this and fall back to the
      rule-based system; they never let it bubble up to the chatbot.

Deployment note: on first run, loading AraBERT/MARBERT downloads model
weights from the Hugging Face Hub and caches them locally (standard
`transformers` behavior — respects the HF_HOME / TRANSFORMERS_CACHE env
vars). That requires outbound network access to huggingface.co at least
once. If that access isn't available in a given environment, every
function below degrades to raising *NotAvailableError, and the hybrid
pipeline transparently falls back to the existing rule-based NLP —
exactly the "never allow AI failure to stop the chatbot" requirement.
"""

import threading

import config

_arabert_lock = threading.Lock()
_arabert_tokenizer = None
_arabert_model = None
_arabert_load_error = None

_marbert_lock = threading.Lock()
_marbert_ner_pipeline = None
_marbert_load_error = None


class AraBERTNotAvailableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class MARBERTNotAvailableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ─────────────────────────────────────────────────────────────────────────
# AraBERT (intent classification backbone — used as a sentence encoder)
# ─────────────────────────────────────────────────────────────────────────

def _do_load_arabert():
    global _arabert_tokenizer, _arabert_model, _arabert_load_error
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        _arabert_load_error = (
            "transformers/torch are not installed. Run "
            "`pip install transformers torch` to enable AraBERT."
        )
        raise AraBERTNotAvailableError(_arabert_load_error) from exc

    try:
        _arabert_tokenizer = AutoTokenizer.from_pretrained(config.ARABERT_MODEL_NAME)
        _arabert_model = AutoModel.from_pretrained(config.ARABERT_MODEL_NAME)
        _arabert_model.eval()
    except Exception as exc:
        _arabert_load_error = (
            f"Failed to load AraBERT model '{config.ARABERT_MODEL_NAME}': {exc}. "
            "This usually means no network access to download model weights, "
            "or the model isn't cached locally yet."
        )
        raise AraBERTNotAvailableError(_arabert_load_error) from exc


def get_arabert():
    """Thread-safe lazy singleton accessor. Returns (tokenizer, model)."""
    global _arabert_tokenizer, _arabert_model
    if _arabert_model is not None:
        return _arabert_tokenizer, _arabert_model
    if _arabert_load_error is not None:
        raise AraBERTNotAvailableError(_arabert_load_error)
    with _arabert_lock:
        if _arabert_model is None:
            if _arabert_load_error is not None:
                raise AraBERTNotAvailableError(_arabert_load_error)
            _do_load_arabert()
    return _arabert_tokenizer, _arabert_model


def embed_text(text: str):
    """
    Mean-pooled AraBERT sentence embedding, used for embedding-similarity
    intent classification (see intent_classifier.py). Raises
    AraBERTNotAvailableError if the model can't be loaded — callers must
    catch this and fall back to the rule-based classifier.
    """
    import torch  # safe: get_arabert() already proved transformers/torch import

    tokenizer, model = get_arabert()
    with torch.no_grad():
        tokens = tokenizer(text, return_tensors="pt", truncation=True, max_length=64, padding=True)
        output = model(**tokens)
        # Mean pooling over the token dimension, masked so padding doesn't
        # skew the sentence vector.
        mask = tokens["attention_mask"].unsqueeze(-1).float()
        summed = (output.last_hidden_state * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        vector = (summed / counts).squeeze(0)
    return vector


# ─────────────────────────────────────────────────────────────────────────
# MARBERT (named entity recognition)
# ─────────────────────────────────────────────────────────────────────────

def _do_load_marbert():
    global _marbert_ner_pipeline, _marbert_load_error
    try:
        from transformers import pipeline
    except ImportError as exc:
        _marbert_load_error = (
            "transformers/torch are not installed. Run "
            "`pip install transformers torch` to enable MARBERT NER."
        )
        raise MARBERTNotAvailableError(_marbert_load_error) from exc

    try:
        _marbert_ner_pipeline = pipeline(
            "ner",
            model=config.MARBERT_NER_MODEL_NAME,
            aggregation_strategy="simple",
        )
    except Exception as exc:
        _marbert_load_error = (
            f"Failed to load MARBERT NER model '{config.MARBERT_NER_MODEL_NAME}': "
            f"{exc}. This usually means no network access to download model "
            "weights, or the model isn't cached locally yet."
        )
        raise MARBERTNotAvailableError(_marbert_load_error) from exc


def get_marbert_ner():
    """Thread-safe lazy singleton accessor for the MARBERT NER pipeline."""
    global _marbert_ner_pipeline
    if _marbert_ner_pipeline is not None:
        return _marbert_ner_pipeline
    if _marbert_load_error is not None:
        raise MARBERTNotAvailableError(_marbert_load_error)
    with _marbert_lock:
        if _marbert_ner_pipeline is None:
            if _marbert_load_error is not None:
                raise MARBERTNotAvailableError(_marbert_load_error)
            _do_load_marbert()
    return _marbert_ner_pipeline


# ─────────────────────────────────────────────────────────────────────────
# Startup preload — called once from app.py, mirrors whisper_engine.preload()
# ─────────────────────────────────────────────────────────────────────────

def preload():
    """
    Call once at app startup. Never raises — logs a warning and defers the
    real error to the first request that actually needs the model, so a
    missing/unavailable AI NLP stack never prevents the Flask app (or any
    of the rule-based chatbot functionality) from booting.
    """
    if not config.ENABLE_AI_NLP:
        print("[NLP] AraBERT/MARBERT disabled via config.ENABLE_AI_NLP — "
              "running on rule-based NLP only.")
        return

    try:
        get_arabert()
        # Build the immutable intent anchors while the app is warming up,
        # not on the first customer message. The classifier owns its lock and
        # catches model failures, so this cannot make startup fatal.
        from backend.nlp import intent_classifier
        intent_classifier.preload_reference_embeddings()
        print(f"[NLP] AraBERT '{config.ARABERT_MODEL_NAME}' loaded and ready.")
    except AraBERTNotAvailableError as exc:
        print(f"[NLP] WARNING — AraBERT not ready yet, will use rule-based "
              f"fallback: {exc.message}")

    try:
        get_marbert_ner()
        print(f"[NLP] MARBERT NER '{config.MARBERT_NER_MODEL_NAME}' loaded and ready.")
    except MARBERTNotAvailableError as exc:
        print(f"[NLP] WARNING — MARBERT NER not ready yet, will use "
              f"gazetteer/regex fallback: {exc.message}")


def is_arabert_available() -> bool:
    if not config.ENABLE_AI_NLP:
        return False
    try:
        get_arabert()
        return True
    except AraBERTNotAvailableError:
        return False


def is_marbert_available() -> bool:
    if not config.ENABLE_AI_NLP:
        return False
    try:
        get_marbert_ner()
        return True
    except MARBERTNotAvailableError:
        return False
