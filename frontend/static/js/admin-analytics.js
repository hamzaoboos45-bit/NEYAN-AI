/* Role-scoped Phase 8 Step 3 dashboard analytics. Uses one API request per
 * refresh and native SVG, avoiding an additional charting dependency. */
(function () {
    "use strict";

    const isSuper = window.CURRENT_ROLE === "super_admin";
    const text = (key) => {
        const lang = document.documentElement.lang === "en" ? "en" : "ar";
        return (window.NEYAN_I18N?.[lang]?.[key]) || key;
    };
    const number = (value) => new Intl.NumberFormat(document.documentElement.lang === "en" ? "en" : "ar").format(value || 0);
    const money = (value) => `${number(value)} JOD`;
    const dateText = (value) => value ? String(value).slice(0, 16).replace("T", " ") : "—";
    const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };
    const add = (parent, tag, value, className) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (value !== undefined) node.textContent = value;
        parent.appendChild(node);
        return node;
    };

    const KPI_LABELS = {
        total_companies: ["إجمالي الشركات", "Total companies"], active_companies: ["الشركات النشطة", "Active companies"],
        total_users: ["إجمالي المستخدمين", "Total users"], total_trips: ["إجمالي الرحلات", "Total trips"],
        upcoming_active_trips: ["الرحلات النشطة القادمة", "Upcoming active trips"], total_bookings: ["إجمالي الحجوزات", "Total bookings"],
        confirmed_bookings: ["الحجوزات المؤكدة", "Confirmed bookings"], pending_bookings: ["الحجوزات المعلقة", "Pending bookings"],
        cancelled_bookings: ["الحجوزات الملغاة", "Cancelled bookings"], total_maintenance_requests: ["طلبات الصيانة", "Maintenance requests"],
        paid_revenue_jod: ["إيراد الحجوزات المدفوع", "Paid booking revenue"], real_review_count: ["التقييمات الحقيقية", "Real customer reviews"],
        reviewed_companies: ["الشركات التي لديها تقييمات", "Companies with reviews"], average_customer_rating: ["متوسط تقييم العملاء", "Average customer rating"],
    };

    function label(key) { return KPI_LABELS[key]?.[document.documentElement.lang === "en" ? 1 : 0] || key; }
    function chartCard(title, rows) {
        const card = document.createElement("section");
        card.className = "admin-chart-card";
        add(card, "h3", title);
        if (!rows.length) { add(card, "p", text("noData"), "empty-state"); return card; }
        const max = Math.max(...rows.map((row) => Number(row.count) || 0), 1);
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", `0 0 360 ${Math.max(116, rows.length * 30 + 20)}`);
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", title);
        svg.classList.add("admin-bar-chart");
        rows.slice(0, 12).forEach((row, index) => {
            const y = 10 + index * 30;
            const rowLabel = String(row.label || row.date || "—");
            const count = Number(row.count) || 0;
            const labelNode = document.createElementNS(svg.namespaceURI, "text");
            labelNode.setAttribute("x", "4"); labelNode.setAttribute("y", String(y + 14)); labelNode.setAttribute("class", "admin-chart-label");
            labelNode.textContent = rowLabel.length > 22 ? `${rowLabel.slice(0, 21)}…` : rowLabel;
            svg.appendChild(labelNode);
            const bar = document.createElementNS(svg.namespaceURI, "rect");
            bar.setAttribute("x", "148"); bar.setAttribute("y", String(y)); bar.setAttribute("width", String(Math.max(2, (count / max) * 162))); bar.setAttribute("height", "18"); bar.setAttribute("rx", "4"); bar.setAttribute("class", "admin-chart-bar");
            const titleNode = document.createElementNS(svg.namespaceURI, "title"); titleNode.textContent = `${rowLabel}: ${count}`; bar.appendChild(titleNode); svg.appendChild(bar);
            const valueNode = document.createElementNS(svg.namespaceURI, "text"); valueNode.setAttribute("x", "318"); valueNode.setAttribute("y", String(y + 14)); valueNode.setAttribute("class", "admin-chart-value"); valueNode.textContent = number(count); svg.appendChild(valueNode);
        });
        card.appendChild(svg);
        return card;
    }

    function renderKpis(kpis) {
        const grid = document.getElementById("adminKpiGrid"); clear(grid); grid.setAttribute("aria-busy", "false");
        Object.entries(kpis).forEach(([key, value]) => {
            const card = add(grid, "article", undefined, "admin-kpi-card");
            add(card, "span", label(key), "admin-kpi-label");
            const display = key === "paid_revenue_jod" ? money(value) : (key === "average_customer_rating" && value === null ? text("noRatingsYet") : number(value));
            add(card, "strong", display, "admin-kpi-value");
        });
    }

    function previewValue(row, kind) {
        if (kind === "bookings") return `${row.from_city || "—"} → ${row.to_city || "—"} · ${money(row.total_price)} · ${row.status || "—"}`;
        if (kind === "trips") return `${row.from_city || "—"} → ${row.to_city || "—"} · ${dateText(row.departure_time)} · ${number(row.available_seats)} seats`;
        return `${row.service_type || "—"} · ${row.status || "—"} · ${dateText(row.created_at)}`;
    }
    function renderPreviews(previews) {
        const grid = document.getElementById("adminPreviewGrid"); clear(grid);
        const titles = { bookings: text("recentBookings"), trips: text("recentTrips"), maintenance: text("recentMaintenance") };
        Object.entries(previews).forEach(([kind, rows]) => {
            const card = add(grid, "section", undefined, "admin-preview-card"); add(card, "h3", titles[kind]);
            if (!rows.length) { add(card, "p", text("noData"), "empty-state"); return; }
            const list = add(card, "ul", undefined, "admin-preview-list");
            rows.forEach((row) => { const item = add(list, "li"); add(item, "span", previewValue(row, kind)); if (row.company_name) add(item, "small", row.company_name); });
        });
    }
    function render(data) {
        renderKpis(data.kpis);
        const grid = document.getElementById("adminChartGrid"); clear(grid);
        grid.append(
            chartCard(text("bookingsTrend"), data.trends.bookings),
            chartCard(text("tripsTrend"), data.trends.trips),
            chartCard(text("bookingStatus"), data.charts.booking_status),
            chartCard(isSuper ? text("bookingsByCompany") : text("popularRoutes"), isSuper ? data.charts.bookings_by_company : data.charts.popular_routes),
        );
        renderPreviews(data.previews);
    }
    function updateInputs() {
        const custom = document.getElementById("adminDatePreset").value === "custom";
        document.getElementById("adminDateFrom").disabled = !custom;
        document.getElementById("adminDateTo").disabled = !custom;
    }
    function setPresetRange() {
        const value = document.getElementById("adminDatePreset").value;
        if (value === "custom") return;
        const now = new Date(); const to = now.toISOString().slice(0, 10);
        const fromDate = new Date(now); fromDate.setUTCDate(fromDate.getUTCDate() - Number(value) + 1);
        document.getElementById("adminDateFrom").value = fromDate.toISOString().slice(0, 10);
        document.getElementById("adminDateTo").value = to;
    }
    async function load() {
        const grid = document.getElementById("adminKpiGrid"); const error = document.getElementById("adminAnalyticsError");
        grid.setAttribute("aria-busy", "true"); error.hidden = true;
        const params = new URLSearchParams({ timezone: "UTC" });
        const from = document.getElementById("adminDateFrom").value; const to = document.getElementById("adminDateTo").value;
        if (from) params.set("from", from); if (to) params.set("to", to);
        try {
            const response = await fetch(`/api/dashboard/admin?${params.toString()}`);
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error?.message || "Unable to load dashboard.");
            render(payload.data);
            document.getElementById("adminAnalyticsMeta").textContent = from || to ? `${from || "…"} — ${to || "…"} · UTC` : "UTC";
        } catch (err) {
            grid.setAttribute("aria-busy", "false"); error.textContent = err.message; error.hidden = false;
        }
    }
    document.addEventListener("DOMContentLoaded", () => {
        const form = document.getElementById("adminDateFilter"); if (!form) return;
        document.getElementById("adminDatePreset").addEventListener("change", () => { updateInputs(); setPresetRange(); });
        form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
        document.getElementById("adminDateClear").addEventListener("click", () => { document.getElementById("adminDateFrom").value = ""; document.getElementById("adminDateTo").value = ""; document.getElementById("adminDatePreset").value = "custom"; updateInputs(); load(); });
        setPresetRange(); updateInputs(); load();
        document.addEventListener("neyan:languagechange", () => load());
    });
}());
