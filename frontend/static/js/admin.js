/**
 * admin.js — Admin dashboard data loading.
 * Phase One: role-scoped. super_admin sees the full platform view;
 * company_admin sees only their own company's trips/bookings/maintenance
 * (window.CURRENT_ROLE is set inline by admin.html).
 */

const IS_SUPER_ADMIN = window.CURRENT_ROLE === "super_admin";

function realCompanyRatingLabel(company) {
    if (company.average_rating === null || company.average_rating === undefined) {
        return document.documentElement.lang === "en" ? "No ratings yet" : "لا توجد تقييمات بعد";
    }
    return `${company.average_rating.toFixed(1)} ⭐ (${company.review_count})`;
}

async function loadDashboard() {
    try {
        if (IS_SUPER_ADMIN) {
            await loadCompanies();
            await loadPendingAdmins();
            await loadUsers();
            await loadActivityLog();
        } else {
            await loadMyTrips();
            await loadMyBookings();
            await loadMyMaintenance();
        }
    } catch (err) {
        console.error("Dashboard load error:", err);
    }
}

// ─────────────────────────────────────────────────────────────────────────
// company_admin — scoped to their own company (RBAC requirement 2)
// ─────────────────────────────────────────────────────────────────────────

async function loadMyTrips() {
    try {
        const data = await fetch("/api/analytics/my-trips").then(r => r.json());
        const tbody = document.getElementById("myTripsTable");
        if (!tbody) return;

        const statusLabel = { active: "نشطة", cancelled: "ملغاة", completed: "منتهية" };

        tbody.innerHTML = data.length
            ? data.map(t => `
                <tr>
                    <td>${escapeHtml(t.from_city)}</td>
                    <td>${escapeHtml(t.to_city)}</td>
                    <td>${escapeHtml((t.departure_time || "").slice(0, 16).replace("T", " "))}</td>
                    <td>${t.available_seats}</td>
                    <td>${t.price_jod} د.أ</td>
                    <td><span class="badge ${t.status === 'active' ? 'badge-confirmed' : 'badge-pending'}">${statusLabel[t.status] || t.status}</span></td>
                </tr>`).join("")
            : '<tr><td colspan="6" class="empty-state">لا توجد رحلات</td></tr>';
    } catch (err) {
        console.error("My trips load error:", err);
    }
}

async function loadMyBookings() {
    try {
        const data = await fetch("/api/bookings").then(r => r.json());
        const tbody = document.getElementById("myBookingsTable");
        if (!tbody) return;

        const statusLabel = { pending: "معلق", confirmed: "مؤكد", cancelled: "ملغي" };
        const payLabel = { unpaid: "غير مدفوع", paid: "مدفوع", refunded: "مسترد" };

        tbody.innerHTML = data.length
            ? data.map(b => `
                <tr>
                    <td>${escapeHtml(b.passenger_name) || "—"}</td>
                    <td>${escapeHtml(b.from_city)} → ${escapeHtml(b.to_city)}</td>
                    <td>${b.seats_booked}</td>
                    <td>${b.total_price} د.أ</td>
                    <td>
                        <select onchange="updateBookingStatus(${b.booking_id}, 'status', this.value)">
                            ${Object.entries(statusLabel).map(([v, l]) => `<option value="${v}" ${b.status === v ? "selected" : ""}>${l}</option>`).join("")}
                        </select>
                    </td>
                    <td>
                        <select onchange="updateBookingStatus(${b.booking_id}, 'payment_status', this.value)">
                            ${Object.entries(payLabel).map(([v, l]) => `<option value="${v}" ${b.payment_status === v ? "selected" : ""}>${l}</option>`).join("")}
                        </select>
                    </td>
                    <td>—</td>
                </tr>`).join("")
            : '<tr><td colspan="7" class="empty-state">لا توجد حجوزات</td></tr>';
    } catch (err) {
        console.error("My bookings load error:", err);
    }
}

async function updateBookingStatus(bookingId, field, value) {
    const body = {};
    body[field] = value;
    const res = await fetch(`/api/bookings/${bookingId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const data = await res.json();
        alert(data.error || "تعذر تحديث الحجز.");
        await loadMyBookings();
    }
}

async function loadMyMaintenance() {
    try {
        const data = await fetch("/api/maintenance/requests").then(r => r.json());
        const tbody = document.getElementById("myMaintenanceTable");
        if (!tbody) return;

        const statusLabel = { pending: "معلق", assigned: "مسند", in_progress: "قيد التنفيذ", completed: "مكتمل", cancelled: "ملغي" };

        tbody.innerHTML = data.length
            ? data.map(r => `
                <tr>
                    <td>${escapeHtml(r.customer_name) || "—"}</td>
                    <td>${escapeHtml(r.service_type)}</td>
                    <td>${escapeHtml(r.location)}</td>
                    <td>${escapeHtml(r.preferred_date)}</td>
                    <td>
                        <select onchange="updateRequestStatus(${r.request_id}, this.value)">
                            ${Object.entries(statusLabel).map(([v, l]) => `<option value="${v}" ${r.status === v ? "selected" : ""}>${l}</option>`).join("")}
                        </select>
                    </td>
                    <td>—</td>
                </tr>`).join("")
            : '<tr><td colspan="6" class="empty-state">لا توجد طلبات صيانة</td></tr>';
    } catch (err) {
        console.error("My maintenance load error:", err);
    }
}

async function updateRequestStatus(requestId, value) {
    const res = await fetch(`/api/maintenance/requests/${requestId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: value }),
    });
    if (!res.ok) {
        const data = await res.json();
        alert(data.error || "تعذر تحديث الطلب.");
        await loadMyMaintenance();
    }
}

// ─────────────────────────────────────────────────────────────────────────
// super_admin — platform-wide (RBAC requirement 2)
// ─────────────────────────────────────────────────────────────────────────

async function loadCompanies() {
    try {
        const data  = await fetch("/api/analytics/companies").then(r => r.json());
        const tbody = document.getElementById("companiesTable");

        const typeLabel   = { transport: "نقل", maintenance: "صيانة" };
        const statusLabel = { active: "نشطة", inactive: "غير نشطة", suspended: "موقوفة" };
        const statusClass = { active: "badge-confirmed", inactive: "badge-pending", suspended: "badge-cancelled" };

        tbody.innerHTML = data.length
            ? data.map(c => `
                <tr>
                    <td>${escapeHtml(c.name_ar)}</td>
                    <td>${escapeHtml(typeLabel[c.company_type] || c.company_type)}</td>
                    <td>${escapeHtml(c.city) || "—"}</td>
                    <td>${realCompanyRatingLabel(c)}</td>
                    <td><span class="badge ${statusClass[c.status] || 'badge-pending'}">${statusLabel[c.status] || c.status}</span></td>
                </tr>`).join("")
            : '<tr><td colspan="5" class="empty-state">لا توجد شركات</td></tr>';
    } catch (err) {
        console.error("Companies load error:", err);
    }
}

async function loadActivityLog() {
    try {
        const data  = await fetch("/api/analytics/activity").then(r => r.json());
        const tbody = document.getElementById("activityTable");

        const actionLabel = {
            login:               "تسجيل دخول",
            logout:              "تسجيل خروج",
            trip_search:         "بحث رحلة",
            trip_view:           "عرض رحلة",
            booking_create:      "حجز جديد",
            booking_cancel:      "إلغاء حجز",
            maintenance_create:  "طلب صيانة",
            maintenance_cancel:  "إلغاء صيانة",
            chat_start:          "بدء محادثة",
            chat_reset:          "إعادة محادثة",
            admin_action:        "إجراء إداري",
        };

        tbody.innerHTML = data.length
            ? data.map(a => `
                <tr>
                    <td>${escapeHtml(actionLabel[a.action_type] || a.action_type)}</td>
                    <td>${escapeHtml(a.details) || "—"}</td>
                    <td>${escapeHtml(a.logged_at?.slice(0, 16).replace("T", " ")) || "—"}</td>
                </tr>`).join("")
            : '<tr><td colspan="3" class="empty-state">لا يوجد نشاط مسجّل</td></tr>';
    } catch (err) {
        console.error("Activity log load error:", err);
    }
}

async function loadPendingAdmins() {
    try {
        const data = await fetch("/api/admin/pending-admins").then(r => r.json());
        const tbody = document.getElementById("pendingAdminsTable");
        if (!tbody) return;

        tbody.innerHTML = data.length
            ? data.map(admin => `
                <tr>
                    <td>${escapeHtml(admin.name || admin.full_name) || "—"}${admin.company_name ? ` (${escapeHtml(admin.company_name)})` : ""}</td>
                    <td>${escapeHtml(admin.email)}</td>
                    <td>${escapeHtml(admin.created_at?.slice(0, 16)) || "—"}</td>
                    <td>
                        <button class="btn btn-small" onclick="reviewAdmin(${admin.user_id}, 'approve')">قبول</button>
                        <button class="btn btn-small btn-danger" onclick="reviewAdmin(${admin.user_id}, 'reject')">رفض</button>
                    </td>
                </tr>`).join("")
            : '<tr><td colspan="4" class="empty-state">لا توجد طلبات مديرين معلقة</td></tr>';
    } catch (err) {
        console.error("Pending admins load error:", err);
    }
}

async function reviewAdmin(userId, action) {
    const res = await fetch(`/api/admin/pending-admins/${userId}/${action}`, { method: "POST" });
    if (!res.ok) {
        const data = await res.json();
        alert(data.error || "Unable to update admin request.");
        return;
    }
    await loadPendingAdmins();
    await loadUsers();
}

async function loadUsers() {
    try {
        const data = await fetch("/api/admin/users").then(r => r.json());
        const tbody = document.getElementById("usersTable");
        if (!tbody) return;

        const roleLabel = { super_admin: "مدير عام", company_admin: "مدير شركة", customer: "عميل" };
        const statusLabel = {
            active: "نشط",
            approved: "موافق عليه",
            pending: "معلق",
            rejected: "مرفوض",
            disabled: "معطل"
        };
        const statusClass = {
            active: "badge-confirmed",
            approved: "badge-confirmed",
            pending: "badge-pending",
            rejected: "badge-cancelled",
            disabled: "badge-cancelled"
        };

        tbody.innerHTML = data.length
            ? data.map(user => `
                <tr>
                    <td>${escapeHtml(user.name || user.full_name) || "—"}${user.company_name ? ` (${escapeHtml(user.company_name)})` : ""}</td>
                    <td>${escapeHtml(user.email)}</td>
                    <td>${escapeHtml(roleLabel[user.effective_role] || user.effective_role)}</td>
                    <td><span class="badge ${statusClass[user.status] || 'badge-info'}">${escapeHtml(statusLabel[user.status] || user.status)}</span></td>
                    <td>${escapeHtml(user.last_login?.slice(0, 16)) || "—"}</td>
                    <td>
                        <button class="btn btn-small" onclick="toggleUserActive(${user.user_id})">${user.is_active ? "تعطيل" : "تفعيل"}</button>
                    </td>
                </tr>`).join("")
            : '<tr><td colspan="6" class="empty-state">لا يوجد مستخدمون</td></tr>';
    } catch (err) {
        console.error("Users load error:", err);
    }
}

async function toggleUserActive(userId) {
    const res = await fetch(`/api/admin/users/${userId}/toggle-active`, { method: "POST" });
    if (!res.ok) {
        const data = await res.json();
        alert(data.error || "Unable to update user.");
        return;
    }
    await loadUsers();
}

// ─────────────────────────────────────────────────────────────────────────
// Admin-controlled user creation (Phase 3 rebuild).
//
// This used to be a chain of native prompt()/alert() dialogs, including
// one asking the super_admin to type a raw numeric `company_id` — a value
// that was never shown anywhere else in the UI, so there was no reliable
// way to know what to type. A non-numeric guess crashed the backend with
// an unhandled 500 (fixed separately in auth_routes.py). This replaces
// that flow with a real modal: the company is chosen by name from a
// dropdown populated from the same data the companies table already uses,
// so the numeric ID never has to be known or typed by anyone.
// ─────────────────────────────────────────────────────────────────────────

function showUsersCardFeedback(message, type) {
    const host = document.getElementById("usersCardFeedback");
    if (!host) return;
    host.innerHTML = `<div class="flash flash-${type}">${escapeHtml(message)}</div>`;
    window.clearTimeout(showUsersCardFeedback._t);
    showUsersCardFeedback._t = window.setTimeout(() => { host.innerHTML = ""; }, 5000);
}

let companiesForSelect = null; // cached after first fetch, refreshed each time the modal opens

async function populateCompanySelect() {
    const select = document.getElementById("cuCompany");
    if (!select) return;
    try {
        companiesForSelect = await fetch("/api/analytics/companies").then(r => r.json());
    } catch (err) {
        companiesForSelect = [];
    }
    const options = ['<option value="">اختر الشركة...</option>'].concat(
        companiesForSelect.map(c => `<option value="${c.company_id}">${escapeHtml(c.name_ar)}</option>`)
    );
    select.innerHTML = options.join("");
}

function setCreateUserError(message) {
    const box = document.getElementById("createUserError");
    if (!box) return;
    if (message) {
        box.textContent = message;
        box.hidden = false;
    } else {
        box.hidden = true;
        box.textContent = "";
    }
}

function setCreateUserLoading(loading) {
    const btn = document.getElementById("createUserSubmitBtn");
    const cancelBtn = document.getElementById("createUserCancelBtn");
    if (!btn) return;
    btn.classList.toggle("is-loading", loading);
    btn.disabled = loading;          // prevents a double-submit while the request is in flight
    if (cancelBtn) cancelBtn.disabled = loading;
}

function openCreateUserModal() {
    const modal = document.getElementById("createUserModal");
    if (!modal) return;
    document.getElementById("createUserForm").reset();
    setCreateUserError(null);
    setCreateUserLoading(false);
    document.getElementById("cuCompanyField").hidden = true;
    populateCompanySelect();
    modal.hidden = false;
    document.getElementById("cuName").focus();
}

function closeCreateUserModal() {
    const modal = document.getElementById("createUserModal");
    if (modal) modal.hidden = true;
}

// Same complexity rule the backend enforces (routes/auth_routes.py
// PASSWORD_RE) — checked here too so obviously-invalid input never even
// reaches the network, but the server remains the authority either way.
const CU_PASSWORD_RE = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/;
const CU_EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function setupAddUserButton() {
    const openBtn = document.getElementById("addUserBtn");
    const closeBtn = document.getElementById("createUserCloseBtn");
    const cancelBtn = document.getElementById("createUserCancelBtn");
    const modal = document.getElementById("createUserModal");
    const form = document.getElementById("createUserForm");
    const roleSelect = document.getElementById("cuRole");
    const companyField = document.getElementById("cuCompanyField");
    const pwdInput = document.getElementById("cuPassword");
    const pwdToggle = document.getElementById("cuPasswordToggle");
    if (!openBtn || !modal || !form) return;

    openBtn.addEventListener("click", openCreateUserModal);
    closeBtn.addEventListener("click", closeCreateUserModal);
    cancelBtn.addEventListener("click", closeCreateUserModal);
    modal.addEventListener("click", (e) => { if (e.target === modal) closeCreateUserModal(); });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !modal.hidden) closeCreateUserModal();
    });

    roleSelect.addEventListener("change", () => {
        companyField.hidden = roleSelect.value !== "company_admin";
        document.getElementById("cuCompany").required = roleSelect.value === "company_admin";
    });

    pwdToggle.addEventListener("click", () => {
        const showing = pwdInput.type === "text";
        pwdInput.type = showing ? "password" : "text";
        pwdToggle.setAttribute("aria-pressed", showing ? "false" : "true");
        pwdToggle.setAttribute("aria-label", showing ? "إظهار كلمة المرور" : "إخفاء كلمة المرور");
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        setCreateUserError(null);

        const name = document.getElementById("cuName").value.trim();
        const email = document.getElementById("cuEmail").value.trim().toLowerCase();
        const password = pwdInput.value;
        const role = roleSelect.value;
        const companyId = document.getElementById("cuCompany").value;

        if (name.length < 2) { setCreateUserError("الرجاء إدخال الاسم الكامل."); return; }
        if (!CU_EMAIL_RE.test(email)) { setCreateUserError("الرجاء إدخال بريد إلكتروني صحيح."); return; }
        if (!CU_PASSWORD_RE.test(password)) { setCreateUserError("كلمة المرور يجب أن تكون 8 أحرف على الأقل وتتضمن حرفاً ورقماً."); return; }
        if (role === "company_admin" && !companyId) { setCreateUserError("الرجاء اختيار الشركة."); return; }

        setCreateUserLoading(true);
        let res, data;
        try {
            res = await fetch("/api/admin/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name, email, password, role,
                    company_id: role === "company_admin" ? companyId : null,
                }),
            });
            data = await res.json().catch(() => ({}));
        } catch (err) {
            setCreateUserLoading(false);
            setCreateUserError("تعذر الوصول إلى الخادم. تحقق من اتصالك وحاول مرة أخرى.");
            return;
        }
        setCreateUserLoading(false);

        // Only ever treat this as success once the server has actually
        // confirmed it (2xx + the expected body) — never before.
        if (!res.ok || data.status !== "created") {
            setCreateUserError(data.error || "تعذر إنشاء المستخدم.");
            return;
        }

        closeCreateUserModal();
        showUsersCardFeedback("تم إنشاء المستخدم بنجاح.", "success");
        await loadUsers();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    loadDashboard();
    setupAddUserButton();
});
