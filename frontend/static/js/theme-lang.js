/**
 * theme-lang.js — shared theme (light/dark) + language (EN/AR) control
 * for the authenticated app shell (base.html and everything that extends
 * it). login.html / forgot_password.html / reset_password.html keep
 * their own small, self-contained copy of this logic (see the
 * transformation report for why), but both read and write the exact
 * same localStorage keys — 'neyanTheme' and 'neyanLang' — so a
 * preference set on one screen is respected everywhere else.
 *
 * Shell strings (sidebar nav, topbar, profile menu, common buttons) are
 * translated here. Individual pages may additionally define
 * `window.NEYAN_PAGE_I18N = { en: {...}, ar: {...} }` in an inline
 * <script> inside their content block (i.e. BEFORE this file runs) to
 * translate their own page title / labels using the same [data-i18n]
 * mechanism — see home.html for an example. Deep, page-specific dynamic
 * content (table data returned from the API, chatbot replies, etc.) is
 * intentionally NOT machine-translated; see the transformation report's
 * "RTL/LTR & i18n" section for the documented scope of this feature.
 */
(function () {
    "use strict";

    var SHELL_I18N = {
        en: {
            navHome: "Home",
            navChat: "Assistant",
            navTrips: "Transportation",
            navBookings: "My Transportation",
            navMaintenance: "Maintenance",
            navAdminPlatform: "Platform Dashboard",
            navAdminCompany: "Company Dashboard",
            navPricing: "Pricing",
            brandSub: "Transport Platform",
            languageControl: "Language",
            themeControl: "Theme",
            topbarThemeLight: "Light",
            topbarThemeDark: "Dark",
            profileMenuProfile: "Profile",
            profileMenuLogout: "Log Out",
            roleSuperAdmin: "Super Admin",
            roleCompanyAdmin: "Company Admin",
            roleCustomer: "Customer",
            menuOpen: "Open menu",
            menuClose: "Close menu",
            notificationBell: "Notifications",
            notificationPanel: "Notifications",
            notificationTitle: "Notifications",
            notificationMarkAll: "Mark all read",
            notificationViewAll: "View all notifications",
        },
        ar: {
            navHome: "الرئيسية",
            navChat: "المحادثة الذكية",
            navTrips: "التنقل",
            navBookings: "تنقلاتي",
            navMaintenance: "الصيانة",
            navAdminPlatform: "لوحة الإدارة العامة",
            navAdminCompany: "لوحة الشركة",
            navPricing: "التسعير",
            brandSub: "منصة النقل",
            languageControl: "اللغة",
            themeControl: "المظهر",
            topbarThemeLight: "فاتح",
            topbarThemeDark: "داكن",
            profileMenuProfile: "الملف الشخصي",
            profileMenuLogout: "تسجيل الخروج",
            roleSuperAdmin: "مدير عام",
            roleCompanyAdmin: "مدير شركة",
            roleCustomer: "عميل",
            menuOpen: "فتح القائمة",
            menuClose: "إغلاق القائمة",
            notificationBell: "الإشعارات",
            notificationPanel: "الإشعارات",
            notificationTitle: "الإشعارات",
            notificationMarkAll: "تحديد الكل كمقروء",
            notificationViewAll: "عرض كل الإشعارات",
        },
    };

    // Merge in any page-specific dictionary defined before this script ran.
    var pageDict = window.NEYAN_PAGE_I18N || { en: {}, ar: {} };
    window.NEYAN_I18N = {
        en: Object.assign({}, SHELL_I18N.en, pageDict.en || {}),
        ar: Object.assign({}, SHELL_I18N.ar, pageDict.ar || {}),
    };

    function applyLang(lang) {
        var dict = window.NEYAN_I18N[lang] || window.NEYAN_I18N.en;
        document.querySelectorAll("[data-i18n]").forEach(function (el) {
            var key = el.getAttribute("data-i18n");
            if (dict[key] !== undefined) el.textContent = dict[key];
        });
        document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
            var key = el.getAttribute("data-i18n-html");
            if (dict[key] !== undefined) el.innerHTML = dict[key];
        });
        document.querySelectorAll("[data-i18n-label]").forEach(function (el) {
            var key = el.getAttribute("data-i18n-label");
            if (dict[key] !== undefined) el.setAttribute("aria-label", dict[key]);
        });
        document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
            var key = el.getAttribute("data-i18n-placeholder");
            if (dict[key] !== undefined) el.setAttribute("placeholder", dict[key]);
        });
        document.documentElement.setAttribute("lang", lang);
        document.documentElement.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");
        document.querySelectorAll("[data-lang-btn]").forEach(function (b) {
            var active = b.getAttribute("data-lang-btn") === lang;
            b.classList.toggle("active", active);
            b.setAttribute("aria-pressed", active ? "true" : "false");
        });
        try {
            localStorage.setItem("neyanLang", lang);
        } catch (e) { /* ignore (private browsing / storage disabled) */ }
        document.dispatchEvent(new CustomEvent("neyan:languagechange", { detail: { lang: lang } }));
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        document.querySelectorAll("[data-theme-btn]").forEach(function (b) {
            var active = b.getAttribute("data-theme-btn") === theme;
            b.classList.toggle("active", active);
            b.setAttribute("aria-pressed", active ? "true" : "false");
        });
        try {
            localStorage.setItem("neyanTheme", theme);
        } catch (e) { /* ignore */ }
    }

    function currentLang() {
        try {
            return localStorage.getItem("neyanLang") || document.documentElement.getAttribute("lang") || "ar";
        } catch (e) {
            return "ar";
        }
    }

    function currentTheme() {
        try {
            return localStorage.getItem("neyanTheme") || document.documentElement.getAttribute("data-theme") || "dark";
        } catch (e) {
            return "dark";
        }
    }

    function init() {
        applyLang(currentLang());
        applyTheme(currentTheme());

        document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                applyLang(btn.getAttribute("data-lang-btn"));
            });
        });
        document.querySelectorAll("[data-theme-btn]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                applyTheme(btn.getAttribute("data-theme-btn"));
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.neyanApplyLang = applyLang;
    window.neyanApplyTheme = applyTheme;
})();
