"""
routes/nlp_routes.py — Part Eight: reusable AI service endpoint.

    POST /api/nlp/analyze
    Body:   { "text": "اريد حجز رحلة من عمان الى اربد" }
    Returns: {
        "intent": "book_trip",
        "confidence": 0.97,
        "normalized_text": "اريد حجز رحله من عمان الي اربد",
        "entities": { "from_city": "عمان", "to_city": "إربد", ... },
        "source": "ai" | "rule_based"
    }

This calls the exact same backend/nlp/hybrid_pipeline.py used internally
by backend/chatbot.py — it's a read-only analysis endpoint, it does not
advance any conversation state or touch the database, so it's safe to
call as many times as a developer/frontend wants for debugging or for
building other features on top of the same NLP stack.
"""

from flask import Blueprint, request, jsonify

from backend.nlp import hybrid_pipeline
from routes.auth_helpers import customer_required

nlp_bp = Blueprint("nlp", __name__)

# Part Seven (Security): reject absurdly long input before it ever reaches
# preprocessing/model inference.
_MAX_TEXT_LENGTH = 2000


@nlp_bp.route("/api/nlp/analyze", methods=["POST"])
@customer_required
def analyze_text():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    if not isinstance(text, str):
        return jsonify({"error": "'text' must be a string"}), 400
    if not text.strip():
        return jsonify({"error": "'text' must not be empty"}), 400
    if len(text) > _MAX_TEXT_LENGTH:
        return jsonify({"error": f"'text' exceeds {_MAX_TEXT_LENGTH} characters"}), 400

    # hybrid_pipeline.analyze() never raises (every stage degrades
    # independently — see its docstring), but this endpoint is public-ish
    # (any logged-in customer) so we keep a defensive net regardless of
    # what future changes might introduce.
    try:
        result = hybrid_pipeline.analyze(text)
    except Exception:
        return jsonify({"error": "Analysis failed unexpectedly"}), 500

    return jsonify(result.to_api_dict())
