(function () {
    "use strict";
    var destination = window.NEYAN_INTRO_DESTINATION || "/login";
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var lang = document.documentElement.lang === "ar" ? "ar" : "en";
    var copy = { en: { introSkip: "Skip intro", introTagline: "Connected transport. Intelligent support." }, ar: { introSkip: "تخطي المقدمة", introTagline: "نقل مترابط. دعم ذكي." } }[lang];
    document.querySelectorAll("[data-i18n]").forEach(function (node) { node.textContent = copy[node.dataset.i18n]; });
    function leave() { document.querySelector(".intro").classList.add("is-leaving"); window.setTimeout(function () { window.location.replace(destination); }, reduced ? 80 : 400); }
    document.getElementById("introSkip").addEventListener("click", leave);
    try {
        if (sessionStorage.getItem("neyanIntroSeenV1")) { leave(); return; }
        sessionStorage.setItem("neyanIntroSeenV1", "1");
    } catch (e) { /* a full intro is still safe if storage is unavailable */ }
    window.setTimeout(leave, reduced ? 550 : 6000);
}());
