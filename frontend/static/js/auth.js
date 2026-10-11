const adminRoleToggle = document.getElementById("adminRoleToggle");
const adminApprovalNote = document.getElementById("adminApprovalNote");

if (adminRoleToggle && adminApprovalNote) {
    const syncAdminNote = () => {
        adminApprovalNote.classList.toggle("visible", adminRoleToggle.checked);
    };

    adminRoleToggle.addEventListener("change", syncAdminNote);
    syncAdminNote();
}
