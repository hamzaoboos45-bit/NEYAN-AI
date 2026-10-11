
import uuid
import time
from flask import Blueprint, current_app, request, jsonify, session, render_template
import config
from backend.chat_request_lock import session_request_lock
from backend.chatbot import ChatbotEngine
from backend.memory.conversation_memory import ConversationMemory, ConversationOwnershipError
from backend.security import chat_rate_limit
from routes.auth_helpers import customer_required

chat_bp = Blueprint("chat", __name__)
HISTORY_LIMIT = 40


def _resolve_user_conversation(user_id: int) -> str:
    """Resolve only the authenticated user's current/latest conversation.

    A browser never supplies a conversation ID to this endpoint.  If its
    signed session has no usable identifier (including after a normal
    login/restore), the latest conversation belonging to the same user is
    resumed; otherwise a new server-generated identifier is used.
    """
    candidate = session.get("session_id")
    if candidate:
        try:
            ConversationMemory(candidate, user_id=user_id).ensure_row()
            return candidate
        except ConversationOwnershipError:
            session.pop("session_id", None)

    candidate = ConversationMemory.latest_session_id_for_user(user_id) or str(uuid.uuid4())
    ConversationMemory(candidate, user_id=user_id).ensure_row()
    session["session_id"] = candidate
    return candidate


@chat_bp.route("/chat")
@customer_required
def chat_page():
    return render_template("chat.html", nlp_debug_enabled=config.NLP_DEBUG_MODE)


@chat_bp.route("/api/chat/history")
@customer_required
def chat_history():
    """Return a bounded, visible transcript for the authenticated customer."""
    user_id = session["user_id"]
    try:
        session_id = _resolve_user_conversation(user_id)
        messages = ConversationMemory(session_id, user_id=user_id).recent_history(HISTORY_LIMIT)
    except ConversationOwnershipError:
        current_app.logger.warning("Chat history ownership mismatch for user_id=%s", user_id)
        return jsonify({"error": "Conversation is unavailable", "code": "conversation_unavailable"}), 409
    return jsonify({"session_id": session_id, "messages": messages})


@chat_bp.route("/api/chat", methods=["POST"])
@customer_required
def api_chat():
    """
    POST /api/chat
    Body: { "message": "حجز رحلة" }
    Returns: { "reply": "ممتاز! من أي مدينة..." }

    When config.NLP_DEBUG_MODE is enabled (OFF by default — Part Nine),
    the response also includes a "debug" object with the detected
    intent/confidence/entities from the Hybrid NLP Pipeline, so the
    existing frontend contract is unchanged for anyone not opted into
    debugging.
    """
    request_started = time.perf_counter()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object", "code": "invalid_json"}), 400
    if "message" not in data:
        return jsonify({"error": "Missing message field", "code": "missing_message"}), 400
    if not isinstance(data["message"], str):
        return jsonify({"error": "Message must be a string", "code": "invalid_message"}), 400

    message = data["message"].strip()
    if not message:
        return jsonify({"error": "Message must not be empty", "code": "empty_message"}), 400
    if len(message) > config.CHAT_MAX_MESSAGE_LENGTH:
        return jsonify({
            "error": f"Message exceeds {config.CHAT_MAX_MESSAGE_LENGTH} characters",
            "code": "message_too_long",
        }), 400

    user_id = session["user_id"]
    if not chat_rate_limit.consume_request(user_id, request.remote_addr or ""):
        return jsonify({
            "error": "Too many chat messages. Please wait a moment and try again.",
            "code": "rate_limited",
        }), 429

    session_id = _resolve_user_conversation(user_id)

    with session_request_lock(session_id):
        try:
            engine = ChatbotEngine(session_id, user_id=user_id)
            reply = engine.process(message)
        except ConversationOwnershipError:
            # Do not expose or take over a stale session row. Start the
            # authenticated user with a clean server-generated conversation.
            session["session_id"] = str(uuid.uuid4())
            engine = ChatbotEngine(session["session_id"], user_id=user_id)
            reply = engine.process(message)
        except Exception:
            current_app.logger.exception("Chat request failed")
            return jsonify({"error": "Chat processing failed. Please try again.", "code": "chat_failed"}), 500

    response = {"reply": reply, "session_id": session["session_id"]}
    if config.NLP_DEBUG_MODE and engine.last_nlp_result is not None:
        response["debug"] = engine.last_nlp_result.to_api_dict()

    current_app.logger.info(
        "Chat timing total=%.2fms user_id=%s session_id=%s",
        (time.perf_counter() - request_started) * 1000,
        user_id,
        session["session_id"],
    )

    return jsonify(response)


@chat_bp.route("/api/chat/reset", methods=["POST"])
@customer_required
def reset_chat():
    session_id = session.get("session_id")
    if session_id:
        with session_request_lock(session_id):
            try:
                ChatbotEngine(session_id, user_id=session["user_id"]).memory.reset()
            except Exception:
                current_app.logger.exception("Chat reset failed")
                return jsonify({"error": "Unable to reset chat. Please try again.", "code": "reset_failed"}), 500
    # A reset is a true new conversation: old messages remain auditable but
    # cannot be restored into the fresh visible transcript.
    new_session_id = str(uuid.uuid4())
    ConversationMemory(new_session_id, user_id=session["user_id"]).ensure_row()
    session["session_id"] = new_session_id
    return jsonify({"status": "reset", "session_id": new_session_id})
