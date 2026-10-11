/* Customer-only Phase 8 home dashboard. Dynamic values use textContent. */
(function () {
    "use strict";

    var dashboard = null;
    var dashboardState = "idle";
    var initialized = false;
    var inFlightLoad = null;
    var loading = document.getElementById("homeDashboardLoading");
    var content = document.getElementById("homeDashboardContent");
    var errorBox = document.getElementById("homeDashboardError");

    function setDashboardState(nextState) {
        dashboardState = nextState;
        loading.hidden = nextState !== "loading";
        errorBox.hidden = nextState !== "error";
        content.hidden = nextState !== "success";
    }

    function currentLang() { return document.documentElement.getAttribute("lang") === "en" ? "en" : "ar"; }
    function text(key) {
        var dict = window.NEYAN_I18N && window.NEYAN_I18N[currentLang()];
        return (dict && dict[key]) || key;
    }
    function el(tag, className, value) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (value !== undefined && value !== null) node.textContent = value;
        return node;
    }
    function localCompanyName(item) {
        return currentLang() === "ar" ? (item.company_name_ar || item.name_ar || item.company_name || item.name) : (item.company_name || item.name || item.company_name_ar || item.name_ar);
    }
    function storedDateTime(value) { return value ? String(value).replace("T", " ").slice(0, 16) : text("unavailable"); }
    function money(value) { return value === null || value === undefined ? text("unavailable") : String(value) + (currentLang() === "ar" ? " د.أ" : " JOD"); }
    function statusLabel(value) {
        var labels = { pending: "statusPending", confirmed: "statusConfirmed", cancelled: "statusCancelled", paid: "statusPaid", unpaid: "statusUnpaid", refunded: "statusRefunded" };
        return text(labels[value] || "unavailable");
    }
    function statusClass(value) {
        return { pending: "badge-pending", confirmed: "badge-confirmed", cancelled: "badge-cancelled", paid: "badge-confirmed", unpaid: "badge-pending", refunded: "badge-refunded" }[value] || "badge-info";
    }
    function serviceLabel(value) {
        var labels = { tire_repair: "serviceTireRepair", tire_replace: "serviceTireReplace", engine: "serviceEngine", oil_change: "serviceOilChange", battery: "serviceBattery", other: "serviceOther" };
        return text(labels[value] || "serviceOther");
    }
    function addDetail(parent, label, value) {
        var detail = el("div", "dashboard-detail");
        detail.append(el("span", "dashboard-detail-label", label));
        detail.append(el("strong", "", value));
        parent.append(detail);
    }
    function actionLink(label, href) {
        var link = el("a", "btn btn-secondary btn-small", label);
        link.href = href;
        return link;
    }
    function stars(rating) { return "★".repeat(Number(rating) || 0) + "☆".repeat(5 - (Number(rating) || 0)); }

    function renderNextBooking(item) {
        var host = document.getElementById("homeNextTrip");
        host.replaceChildren();
        if (!item) {
            var empty = el("div", "dashboard-empty", text("nextTripEmpty"));
            empty.append(actionLink(text("searchTrips"), "/trips"));
            host.append(empty);
            return;
        }
        var details = el("div", "dashboard-detail-grid");
        addDetail(details, text("company"), localCompanyName(item) || text("unavailable"));
        addDetail(details, text("bookingStatus"), statusLabel(item.status));
        addDetail(details, text("paymentStatus"), statusLabel(item.payment_status));
        addDetail(details, text("seats"), item.seats_booked);
        addDetail(details, text("price"), money(item.total_price));
        host.append(el("div", "dashboard-route", item.from_city + " → " + item.to_city), el("div", "dashboard-trip-meta", storedDateTime(item.departure_time)), details);
    }

    function renderMaintenance(item) {
        var host = document.getElementById("homeMaintenance");
        host.replaceChildren();
        if (!item) {
            var empty = el("div", "dashboard-empty", text("maintenanceEmpty"));
            empty.append(actionLink(text("viewMaintenance"), "/maintenance"));
            host.append(empty);
            return;
        }
        var details = el("div", "dashboard-detail-grid");
        addDetail(details, text("latestRequest"), "#" + item.request_id);
        addDetail(details, text("bookingStatus"), statusLabel(item.status));
        addDetail(details, text("preferredDate"), item.preferred_date || text("unavailable"));
        host.append(el("div", "dashboard-route", serviceLabel(item.service_type)), details, actionLink(text("viewMaintenance"), "/maintenance"));
    }

    function renderRecent(items) {
        var host = document.getElementById("homeRecentBookings");
        host.replaceChildren();
        if (!items.length) { host.append(el("div", "dashboard-empty", text("recentBookingsEmpty"))); return; }
        items.forEach(function (item) {
            var row = el("article", "dashboard-list-row");
            var main = el("div", "dashboard-list-main");
            main.append(el("strong", "", item.from_city + " → " + item.to_city));
            main.append(el("span", "", (localCompanyName(item) || text("unavailable")) + " · " + storedDateTime(item.departure_time)));
            if (item.review_text) main.append(el("small", "review-owned-text", item.review_text));
            var side = el("div", "dashboard-list-side");
            side.append(el("span", "badge " + statusClass(item.status), statusLabel(item.status)));
            side.append(el("span", "dashboard-price", money(item.total_price)));
            if (item.review_rating !== null && item.review_rating !== undefined) {
                side.append(el("span", "review-owned-rating", text("yourRating") + ": " + stars(item.review_rating) + " " + item.review_rating + "/5"));
            }
            row.append(main, side);
            host.append(row);
        });
    }

    function renderTrips(items) {
        var host = document.getElementById("homeUpcomingTrips");
        host.replaceChildren();
        if (!items.length) { host.append(el("div", "card dashboard-empty", text("tripsEmpty"))); return; }
        items.forEach(function (item) {
            var card = el("article", "card discovery-trip-card");
            card.append(el("strong", "dashboard-route", item.from_city + " → " + item.to_city));
            card.append(el("span", "dashboard-trip-meta", storedDateTime(item.departure_time)));
            card.append(el("span", "", localCompanyName(item) || text("unavailable")));
            card.append(el("span", "", String(item.available_seats) + " · " + money(item.price_jod)));
            host.append(card);
        });
    }

    function renderCompanies(items) {
        var host = document.getElementById("homeCompanies");
        host.replaceChildren();
        if (!items.length) { host.append(el("div", "card dashboard-empty", text("companiesEmpty"))); return; }
        items.forEach(function (item) {
            var card = el("article", "company-discovery-card");
            card.append(el("h3", "", localCompanyName(item) || text("unavailable")));
            card.append(el("p", "company-city", text("city") + ": " + (item.city || text("unavailable"))));
            var coverage = el("div", "company-coverage");
            coverage.append(el("span", "", String(item.available_upcoming_trips) + " " + text("availableTrips")));
            coverage.append(el("span", "", String(item.available_upcoming_routes) + " " + text("availableRoutes")));
            if (item.average_rating === null || item.average_rating === undefined) {
                coverage.append(el("span", "company-rating-empty", text("noRatingsYet")));
            } else {
                coverage.append(el("span", "company-rating", stars(item.average_rating) + " " + item.average_rating + "/5 · " + text("basedOnReviews") + " " + item.review_count + " " + text("reviews")));
            }
            card.append(coverage);
            host.append(card);
        });
    }

    function renderReviewOpportunities(items) {
        var section = document.getElementById("homeReviewSection");
        var host = document.getElementById("homeReviewOpportunities");
        host.replaceChildren();
        section.hidden = !items.length;
        items.forEach(function (item) {
            var card = el("article", "review-opportunity");
            card.append(el("strong", "dashboard-route", item.from_city + " → " + item.to_city));
            card.append(el("span", "dashboard-trip-meta", (localCompanyName(item) || text("unavailable")) + " · " + storedDateTime(item.departure_time)));
            var form = document.createElement("form");
            form.className = "review-form";
            form.dataset.bookingId = item.booking_id;
            var fieldset = document.createElement("fieldset");
            var legend = el("legend", "review-legend", text("ratingLabel"));
            fieldset.append(legend);
            var choices = el("div", "rating-choices");
            for (var rating = 1; rating <= 5; rating += 1) {
                var input = document.createElement("input");
                input.type = "radio"; input.name = "rating"; input.value = String(rating);
                input.id = "review-" + item.booking_id + "-rating-" + rating;
                input.className = "rating-radio";
                input.setAttribute("aria-label", rating + " / 5");
                var labelNode = document.createElement("label");
                labelNode.htmlFor = input.id; labelNode.className = "rating-star"; labelNode.textContent = "★";
                choices.append(input, labelNode);
            }
            fieldset.append(choices); form.append(fieldset);
            var textLabel = el("label", "sr-only", text("reviewOptional"));
            textLabel.htmlFor = "review-" + item.booking_id + "-text";
            var textarea = document.createElement("textarea");
            textarea.id = textLabel.htmlFor; textarea.name = "review_text"; textarea.maxLength = 1000; textarea.rows = 3;
            textarea.placeholder = text("reviewPlaceholder");
            var status = el("div", "review-form-status"); status.setAttribute("role", "alert");
            var button = el("button", "btn btn-small", text("submitReview")); button.type = "submit";
            form.append(textLabel, textarea, status, button); card.append(form); host.append(card);
        });
    }

    function render() {
        if (!dashboard) return;
        var summary = dashboard.summary;
        document.getElementById("homeTotalBookings").textContent = summary.total_bookings;
        document.getElementById("homeUpcomingBookings").textContent = summary.upcoming_bookings;
        document.getElementById("homePendingBookings").textContent = summary.pending_bookings;
        document.getElementById("homeMaintenanceCount").textContent = summary.total_maintenance_requests;
        renderNextBooking(dashboard.next_booking);
        renderMaintenance(dashboard.latest_maintenance);
        renderRecent(dashboard.recent_bookings);
        renderTrips(dashboard.upcoming_trips);
        renderCompanies(dashboard.companies);
        renderReviewOpportunities(dashboard.review_opportunities || []);
    }

    async function load() {
        if (inFlightLoad) return inFlightLoad;
        // Reset prior-error visibility before the single state transition.
        errorBox.hidden = true;
        loading.hidden = false;
        setDashboardState("loading");
        inFlightLoad = (async function () {
          try {
            var response = await fetch("/api/dashboard/home");
            var payload = await response.json().catch(function () { return {}; });
            if (!response.ok || !payload.data) throw new Error("dashboard request failed");
            dashboard = payload.data;
            render();
            setDashboardState("success");
          } catch (err) {
            setDashboardState("error");
          } finally {
            if (dashboardState === "loading") {
              loading.hidden = true;
              setDashboardState("error");
            }
            inFlightLoad = null;
          }
        }());
        return inFlightLoad;
    }

    function init() {
      if (initialized) return;
      initialized = true;
      document.getElementById("homeDashboardRetry").addEventListener("click", load);
      document.getElementById("homeReviewOpportunities").addEventListener("submit", async function (event) {
        event.preventDefault();
        var form = event.target;
        var selected = form.querySelector('input[name="rating"]:checked');
        var status = form.querySelector(".review-form-status");
        var button = form.querySelector('button[type="submit"]');
        if (!selected) { status.textContent = text("ratingLabel"); status.className = "review-form-status is-error"; return; }
        status.textContent = ""; status.className = "review-form-status"; button.disabled = true; button.textContent = text("submittingReview");
        try {
            var response = await fetch("/api/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ booking_id: Number(form.dataset.bookingId), rating: Number(selected.value), review_text: form.elements.review_text.value }) });
            var payload = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(payload.error && payload.error.message ? payload.error.message : text("reviewError"));
            status.textContent = text("reviewSuccess"); status.className = "review-form-status is-success";
            await load();
        } catch (err) {
            status.textContent = err.message || text("reviewError"); status.className = "review-form-status is-error";
            button.disabled = false; button.textContent = text("submitReview");
        }
      });
      document.addEventListener("neyan:languagechange", render);
      load();
    }

    // A cached or dynamically restored document may execute this file after
    // DOMContentLoaded. Choose one startup path and never leave the dashboard
    // waiting for an event that has already happened.
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
      init();
    }
}());
