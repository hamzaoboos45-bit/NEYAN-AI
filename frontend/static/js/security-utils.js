/**
 * security-utils.js
 *
 * Audit finding (AI_AUDIT_REPORT.md / UI transformation report, section
 * "Security-related UI improvements"): several pages build table rows with
 * innerHTML + template literals that interpolate user-controlled values
 * (passenger name, maintenance location, account name/email, …) without
 * escaping. That's an XSS risk if any of those fields ever contain HTML.
 *
 * This file changes NOTHING about how those pages fetch or render data —
 * it only gives them a safe way to escape text before it goes into an
 * innerHTML string. Same technique voice.js already used internally
 * (textContent round-trip through a detached element); centralized here
 * so trips.html / bookings.html / maintenance.html / admin.js can all
 * share it instead of re-implementing it.
 *
 * Usage:  `<td>${escapeHtml(row.location)}</td>`
 */
(function () {
    "use strict";

    var _div = null;

    window.escapeHtml = function escapeHtml(value) {
        if (value === null || value === undefined) return "";
        if (!_div) _div = document.createElement("div");
        _div.textContent = String(value);
        return _div.innerHTML;
    };
})();
