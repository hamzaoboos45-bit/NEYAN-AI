/** Chat UI: ordered, accessible requests to /api/chat. */
(function () {
    "use strict";

    var sending = false;
    var restoring = true;
    var restoreStarted = false;
    var chatReady = false;
    var lastFailedMessage = null;
    var input = document.getElementById("chatInput");
    var sendButton = document.getElementById("chatSendBtn");
    var resetButton = document.getElementById("chatResetBtn");
    var status = document.getElementById("chatStatus");
    var TEXT = {
        ar: { thinking: "جارِ معالجة رسالتك…", restoring: "جارِ استعادة المحادثة…", connectionError: "تعذر إرسال الرسالة. يرجى المحاولة مرة أخرى.", restoreError: "تعذر استعادة المحادثة. ابدأ رسالة جديدة أو حدّث الصفحة.", retry: "إعادة المحاولة", reset: "تمت بدء محادثة جديدة. كيف يمكنني مساعدتك؟" },
        en: { thinking: "Processing your message…", restoring: "Restoring conversation…", connectionError: "Your message could not be sent. Please try again.", restoreError: "We could not restore this conversation. Start a new message or refresh the page.", retry: "Retry", reset: "A new conversation has started. How can I help you?" }
    };

    function language() { return document.documentElement.getAttribute("lang") === "en" ? "en" : "ar"; }
    function strings() { return TEXT[language()]; }

    function setStatus(message, kind, retry) {
        status.textContent = "";
        status.className = "chat-status" + (message ? " has-message" : "") + (kind ? " " + kind : "");
        if (!message) return;
        var text = document.createElement("span");
        text.textContent = message;
        status.appendChild(text);
        if (retry) {
            var retryButton = document.createElement("button");
            retryButton.type = "button";
            retryButton.className = "chat-retry";
            retryButton.textContent = strings().retry;
            retryButton.addEventListener("click", function () {
                if (lastFailedMessage) sendMessage(lastFailedMessage);
            });
            status.appendChild(retryButton);
        }
    }

    function setSending(value) {
        sending = value;
        input.disabled = value;
        sendButton.disabled = value;
        sendButton.classList.toggle("is-loading", value);
        sendButton.setAttribute("aria-busy", value ? "true" : "false");
        if (value) setStatus(strings().thinking, "chat-thinking");
        else if (!lastFailedMessage) setStatus("");
    }

    async function sendMessage(retryMessage) {
        if (sending || restoring) return;
        var msg = retryMessage || input.value.trim();
        if (!msg) return;
        if (!retryMessage) {
            appendMessage("user", msg);
            input.value = "";
        }
        lastFailedMessage = null;
        setSending(true);
        try {
            var res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg }) });
            var data = await res.json().catch(function () { return {}; });
            if (!res.ok || typeof data.reply !== "string") throw new Error(data.error || "chat_request_failed");
            appendMessage("bot", data.reply, data.debug);
            setStatus("");
        } catch (err) {
            lastFailedMessage = msg;
            setStatus(strings().connectionError, "chat-error", true);
        } finally {
            setSending(false);
            input.disabled = false;
            input.focus();
        }
    }

    async function resetChat() {
        if (sending || restoring) return;
        setSending(true);
        try {
            var res = await fetch("/api/chat/reset", { method: "POST" });
            if (!res.ok) throw new Error("reset_failed");
            var box = document.getElementById("chatMessages");
            box.textContent = "";
            appendMessage("bot", strings().reset);
            lastFailedMessage = null;
            setStatus("");
        } catch (err) {
            setStatus(strings().connectionError, "chat-error", false);
        } finally {
            setSending(false);
            input.disabled = false;
            input.focus();
        }
    }

    function appendMessage(sender, text, debugInfo) {
        var box = document.getElementById("chatMessages");
        var div = document.createElement("div");
        div.className = "message " + sender;
        div.textContent = text;
        box.appendChild(div);
        if (sender === "bot" && window.NLP_DEBUG_ENABLED && debugInfo) {
            var debugDiv = document.createElement("div");
            debugDiv.className = "nlp-debug-line";
            var entitiesStr = Object.keys(debugInfo.entities || {}).length ? JSON.stringify(debugInfo.entities) : "{}";
            debugDiv.textContent = "intent=" + debugInfo.intent + " · confidence=" + debugInfo.confidence + " · source=" + debugInfo.source + " · entities=" + entitiesStr;
            box.appendChild(debugDiv);
        }
        box.scrollTop = box.scrollHeight;
        if (sender === "bot" && typeof window.onBotMessage === "function") window.onBotMessage(div, text);
    }

    function applyChatLanguage() {
        var starter = document.getElementById("chatStarter");
        if (starter && starter.getAttribute("data-chat-default") === "true") starter.textContent = window.NEYAN_PAGE_I18N[language()].chatStarter;
        if (restoring) setStatus(strings().restoring, "chat-thinking");
        if (sending) setStatus(strings().thinking, "chat-thinking");
    }

    function renderStarter() {
        var box = document.getElementById("chatMessages");
        box.textContent = "";
        var starter = document.createElement("div");
        starter.id = "chatStarter";
        starter.className = "message bot";
        starter.setAttribute("data-chat-default", "true");
        starter.textContent = window.NEYAN_PAGE_I18N[language()].chatStarter;
        box.appendChild(starter);
        box.scrollTop = box.scrollHeight;
    }

    async function restoreHistory() {
        if (restoreStarted) return;
        restoreStarted = true;
        restoring = true;
        input.disabled = true;
        sendButton.disabled = true;
        setStatus(strings().restoring, "chat-thinking");
        try {
            var response = await fetch("/api/chat/history", { headers: { "Accept": "application/json" } });
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok || !Array.isArray(data.messages)) throw new Error(data.error || "history_failed");
            var box = document.getElementById("chatMessages");
            box.textContent = "";
            if (data.messages.length) {
                data.messages.forEach(function (message) {
                    if (message && (message.sender === "user" || message.sender === "bot") && typeof message.message_text === "string") {
                        appendMessage(message.sender, message.message_text);
                    }
                });
            }
            if (!box.children.length) renderStarter();
            setStatus("");
        } catch (err) {
            renderStarter();
            setStatus(strings().restoreError, "chat-error", false);
        } finally {
            restoring = false;
            chatReady = true;
            input.disabled = false;
            sendButton.disabled = false;
            input.focus();
            document.dispatchEvent(new CustomEvent("neyan:chatready"));
        }
    }

    sendButton.addEventListener("click", function () { sendMessage(); });
    resetButton.addEventListener("click", resetChat);
    input.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.isComposing) {
            event.preventDefault();
            sendMessage();
        }
    });
    document.addEventListener("neyan:languagechange", applyChatLanguage);
    applyChatLanguage();
    restoreHistory();

    window.sendMessage = sendMessage;
    window.resetChat = resetChat;
    window.appendMessage = appendMessage;
    window.NeyanChatInput = {
        isReady: function () { return chatReady && !restoring; }
    };
})();
