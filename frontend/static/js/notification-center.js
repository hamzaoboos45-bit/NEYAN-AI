(function () {
  "use strict";

  var host = document.getElementById("notificationCenterList");
  var more = document.getElementById("notificationLoadMore");
  var all = document.getElementById("notificationCenterMarkAll");
  var offset = 0;
  var locale = document.documentElement.lang === "ar" ? "ar" : "en";
  var labels = {
    en: {forming_minimum_reached:"Your forming trip reached its minimum",forming_ready_for_assignment:"A forming trip is ready for assignment",forming_cancelled:"A forming trip was cancelled",forming_company_assigned:"A transport company was assigned",forming_assigned_for_review:"A forming trip needs your review",forming_company_accepted:"Your forming trip was accepted",forming_company_rejected:"Your forming trip was not accepted",forming_converted:"Your forming trip is now operational",booking_confirmed:"Your booking was confirmed",booking_cancelled:"Your booking was cancelled",maintenance_status_changed:"Your maintenance request was updated"},
    ar: {forming_minimum_reached:"وصلت رحلتك التكوينية إلى الحد الأدنى",forming_ready_for_assignment:"رحلة تكوينية جاهزة للتعيين",forming_cancelled:"تم إلغاء رحلة تكوينية",forming_company_assigned:"تم تعيين شركة نقل",forming_assigned_for_review:"رحلة تكوينية بانتظار المراجعة",forming_company_accepted:"تم قبول رحلتك التكوينية",forming_company_rejected:"لم يتم قبول رحلتك التكوينية",forming_converted:"أصبحت رحلتك التكوينية تشغيلية",booking_confirmed:"تم تأكيد حجزك",booking_cancelled:"تم إلغاء حجزك",maintenance_status_changed:"تم تحديث طلب الصيانة"}
  };

  function text(key) { return labels[locale][key] || key.replaceAll("_", " "); }
  function strings() { return (window.NEYAN_NOTIFICATION_CENTER_I18N || {})[locale] || {}; }
  function localize() { document.querySelectorAll("[data-notification-i18n]").forEach(function (node) { node.textContent = strings()[node.dataset.notificationI18n] || node.textContent; }); }
  function emptyState() { var item = document.createElement("p"); item.className = "notification-empty"; item.textContent = strings().empty || "No notifications yet."; host.append(item); }
  function render(items) {
    if (!items.length && offset === 0) { emptyState(); return; }
    items.forEach(function (n) {
      var item = document.createElement(n.action_target ? "a" : "article");
      item.className = "notification-item" + (n.is_read ? "" : " unread");
      if (n.action_target) item.href = n.action_target;
      var title = document.createElement("strong"), time = document.createElement("time");
      title.textContent = text(n.event_type); time.textContent = (n.created_at || "").slice(0, 16); item.append(title, time); host.append(item);
    });
  }
  function load() {
    fetch("/api/notifications?limit=20&offset=" + offset)
      .then(function (response) { if (!response.ok) throw new Error("notifications request failed"); return response.json(); })
      .then(function (payload) { var items = payload.data || []; render(items); offset += items.length; if (!items.length) more.hidden = true; })
      .catch(function () { if (offset === 0) { host.textContent = ""; emptyState(); } more.hidden = true; });
  }

  more.addEventListener("click", load);
  all.addEventListener("click", function () { fetch("/api/notifications/mark-all-read", {method: "POST"}).then(function () { host.textContent = ""; offset = 0; more.hidden = false; load(); }); });
  localize();
  load();
})();
