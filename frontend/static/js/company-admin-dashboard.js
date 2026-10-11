/* Company Admin operational overview.
 * The server owns company scope: this file makes one bounded request to the
 * existing /api/dashboard/admin contract and never sends role or company_id.
 */
(function () {
  "use strict";

  if (window.__NEYAN_COMPANY_ADMIN_DASHBOARD_STARTED) return;
  window.__NEYAN_COMPANY_ADMIN_DASHBOARD_STARTED = true;

  var COPY = {
    en: {
      title: "Company Dashboard", subtitle: "Operational overview for your company", metrics: "Company metrics",
      totalTrips: "Total trips", upcomingTrips: "Upcoming trips", totalBookings: "Total bookings",
      confirmedBookings: "Confirmed bookings", maintenanceRequests: "Maintenance requests", revenue: "Paid confirmed revenue",
      upcomingPanel: "Upcoming trips", bookingsPanel: "Recent bookings", maintenancePanel: "Maintenance requests",
      demandTitle: "Customer Demand / Forming Trips", demandDescription: "Review only demand assigned to your company. Acceptance does not create a trip or booking.",
      loading: "Loading your company overview…", retry: "Retry", unavailable: "Company dashboard data is unavailable.",
      noTrips: "No upcoming trips are currently available.", noBookings: "No recent bookings are available.",
      noMaintenance: "No maintenance requests are currently assigned to your company.",
      noDemand: "No forming-trip requests currently require action.", noDemandDetail: "New customer demand assigned to your company will appear here.",
      route: "Route", departure: "Departure", seats: "Available seats", booking: "Booking", booked: "Booked", service: "Service", created: "Created", status: "Status",
      active: "Active", pending: "Pending", confirmed: "Confirmed", cancelled: "Cancelled", completed: "Completed", assigned: "Assigned", inProgress: "In progress",
      unknown: "Not available", jod: "JOD"
    },
    ar: {
      title: "لوحة الشركة", subtitle: "نظرة تشغيلية عامة لشركتك", metrics: "مؤشرات الشركة",
      totalTrips: "إجمالي الرحلات", upcomingTrips: "الرحلات القادمة", totalBookings: "إجمالي الحجوزات",
      confirmedBookings: "الحجوزات المؤكدة", maintenanceRequests: "طلبات الصيانة", revenue: "إيراد الحجوزات المؤكدة والمدفوعة",
      upcomingPanel: "الرحلات القادمة", bookingsPanel: "أحدث الحجوزات", maintenancePanel: "طلبات الصيانة",
      demandTitle: "طلبات العملاء / الرحلات قيد الاكتمال", demandDescription: "قيّم فقط الطلبات المعينة لشركتك. القبول لا ينشئ رحلة أو حجزاً.",
      loading: "جارٍ تحميل نظرة شركتك…", retry: "إعادة المحاولة", unavailable: "تعذر تحميل بيانات لوحة الشركة.",
      noTrips: "لا توجد رحلات قادمة حالياً.", noBookings: "لا توجد حجوزات حديثة.",
      noMaintenance: "لا توجد طلبات صيانة معيّنة لشركتك حالياً.",
      noDemand: "لا توجد طلبات رحلات قيد الاكتمال تتطلب إجراءً حالياً.", noDemandDetail: "سيظهر هنا طلب العملاء الجديد المعيّن لشركتك.",
      route: "المسار", departure: "المغادرة", seats: "المقاعد المتاحة", booking: "الحجز", booked: "تاريخ الحجز", service: "الخدمة", created: "تاريخ الإنشاء", status: "الحالة",
      active: "نشطة", pending: "قيد الانتظار", confirmed: "مؤكد", cancelled: "ملغى", completed: "مكتمل", assigned: "معيّن", inProgress: "قيد التنفيذ",
      unknown: "غير متاح", jod: "د.أ"
    }
  };

  var state = { data: null, loading: false };
  function lang() { return document.documentElement.lang === "en" ? "en" : "ar"; }
  function t(key) { return COPY[lang()][key] || key; }
  function byId(id) { return document.getElementById(id); }
  function node(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function textValue(value) { return value === null || value === undefined || value === "" ? t("unknown") : String(value); }
  function formatDate(value) {
    if (!value) return t("unknown");
    var parsed = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(parsed.getTime())) return String(value);
    return new Intl.DateTimeFormat(lang() === "ar" ? "ar-JO" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
  }
  function formatRevenue(value) {
    var amount = Number(value);
    if (!Number.isFinite(amount)) return t("unknown");
    return new Intl.NumberFormat(lang() === "ar" ? "ar-JO" : "en-JO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount) + " " + t("jod");
  }
  function statusLabel(status) {
    var value = String(status || "").toLowerCase();
    var map = { active: "active", pending: "pending", confirmed: "confirmed", cancelled: "cancelled", completed: "completed", assigned: "assigned", in_progress: "inProgress" };
    return map[value] ? t(map[value]) : textValue(status);
  }
  function setStaticCopy() {
    document.querySelectorAll("[data-company-i18n]").forEach(function (element) { element.textContent = t(element.dataset.companyI18n); });
    document.querySelectorAll("[data-company-i18n-label]").forEach(function (element) { element.setAttribute("aria-label", t(element.dataset.companyI18nLabel)); });
  }
  function setLoading(isLoading) {
    state.loading = isLoading;
    var loading = byId("companyDashboardLoading");
    if (loading) { loading.hidden = !isLoading; loading.textContent = t("loading"); }
  }
  function showError(message) {
    var error = byId("companyDashboardError");
    if (!error) return;
    error.hidden = !message;
    error.replaceChildren();
    if (!message) return;
    error.append(node("span", "", message));
    var retry = node("button", "btn btn-secondary btn-small", t("retry"));
    retry.type = "button";
    retry.addEventListener("click", load);
    error.append(retry);
  }
  function renderKpis(kpis) {
    var host = byId("companyDashboardKpis");
    if (!host) return;
    var items = [
      ["totalTrips", kpis.total_trips], ["upcomingTrips", kpis.upcoming_active_trips],
      ["totalBookings", kpis.total_bookings], ["confirmedBookings", kpis.confirmed_bookings],
      ["maintenanceRequests", kpis.total_maintenance_requests], ["revenue", formatRevenue(kpis.paid_revenue_jod)]
    ];
    host.replaceChildren();
    items.forEach(function (item) {
      var card = node("article", "company-kpi");
      card.append(node("span", "company-kpi-label", t(item[0])), node("strong", "company-kpi-value", typeof item[1] === "number" ? String(item[1]) : textValue(item[1])));
      host.append(card);
    });
  }
  function emptyState(message) {
    return node("p", "company-dashboard-empty", message);
  }
  function meta(label, value) {
    var row = node("div", "company-preview-meta");
    row.append(node("span", "", label), node("strong", "", textValue(value)));
    return row;
  }
  function renderTrips(rows) {
    var host = byId("companyUpcomingTrips");
    if (!host) return;
    host.replaceChildren();
    if (!rows.length) { host.append(emptyState(t("noTrips"))); return; }
    rows.forEach(function (trip) {
      var item = node("article", "company-preview-item");
      item.append(node("h3", "", textValue(trip.from_city) + " → " + textValue(trip.to_city)), meta(t("departure"), formatDate(trip.departure_time)), meta(t("seats"), trip.available_seats), node("span", "company-status status-" + String(trip.status || "unknown"), statusLabel(trip.status)));
      host.append(item);
    });
  }
  function renderBookings(rows) {
    var host = byId("companyRecentBookings");
    if (!host) return;
    host.replaceChildren();
    if (!rows.length) { host.append(emptyState(t("noBookings"))); return; }
    rows.forEach(function (booking) {
      var item = node("article", "company-preview-item");
      item.append(node("h3", "", "#" + textValue(booking.booking_id) + " · " + textValue(booking.from_city) + " → " + textValue(booking.to_city)), meta(t("booked"), formatDate(booking.booked_at)), node("span", "company-status status-" + String(booking.status || "unknown"), statusLabel(booking.status)));
      host.append(item);
    });
  }
  function renderMaintenance(rows) {
    var host = byId("companyMaintenanceRequests");
    if (!host) return;
    host.replaceChildren();
    if (!rows.length) { host.append(emptyState(t("noMaintenance"))); return; }
    rows.forEach(function (request) {
      var item = node("article", "company-preview-item");
      item.append(node("h3", "", "#" + textValue(request.request_id) + " · " + textValue(request.service_type)), meta(t("created"), formatDate(request.created_at)), node("span", "company-status status-" + String(request.status || "unknown"), statusLabel(request.status)));
      host.append(item);
    });
  }
  function render() {
    setStaticCopy();
    if (!state.data) return;
    var data = state.data;
    renderKpis(data.kpis || {});
    renderTrips((data.previews && data.previews.trips) || []);
    renderBookings((data.previews && data.previews.bookings) || []);
    renderMaintenance((data.previews && data.previews.maintenance) || []);
  }
  async function load() {
    if (state.loading) return;
    setLoading(true); showError("");
    try {
      var response = await fetch("/api/dashboard/admin", { headers: { Accept: "application/json" } });
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok || !payload.data) throw new Error(payload.error && payload.error.message ? payload.error.message : t("unavailable"));
      state.data = payload.data;
      render();
    } catch (error) {
      state.data = null;
      showError(error && error.message ? error.message : t("unavailable"));
    } finally { setLoading(false); }
  }
  function init() {
    setStaticCopy();
    document.addEventListener("neyan:languagechange", render);
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true }); else init();
}());
