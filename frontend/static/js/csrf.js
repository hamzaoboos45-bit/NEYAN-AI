/**
 * csrf.js — Phase One CSRF protection (frontend half).
 *
 * The backend (backend/security/csrf.py) issues one token per session and
 * validates it on every POST/PUT/PATCH/DELETE. Rather than editing every
 * fetch() call across chat.js, voice.js, admin.js, etc., this wraps
 * window.fetch ONCE and attaches the token as an 'X-CSRFToken' header to
 * every non-GET, same-origin request automatically.
 */
(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var token = meta ? meta.getAttribute("content") : null;
    if (!token) return;

    var originalFetch = window.fetch;

    window.fetch = function (input, init) {
        init = init || {};
        var method = (init.method || "GET").toUpperCase();

        if (method !== "GET" && method !== "HEAD") {
            var headers = new Headers(init.headers || {});
            if (!headers.has("X-CSRFToken")) {
                headers.set("X-CSRFToken", token);
            }
            init = Object.assign({}, init, { headers: headers });
        }

        return originalFetch(input, init);
    };
})();
