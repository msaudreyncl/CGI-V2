/**
 * CGI V2 - User Management
 *
 * Preserves existing FastAPI operations:
 * GET    /api/users/stats
 * PUT    /api/users/{id}
 * DELETE /api/users/{id}
 *
 * Account creation remains a PHP form submission.
 * No localStorage account management.
 */

/* ============================================================
   API HELPERS
   ============================================================ */

const apiToken = () => sessionStorage.getItem("cgi_jwt") || "";

async function apiCall(method, path, body = null) {
    const options = {
        method,
        headers: {
            Authorization: "Bearer " + apiToken(),
            "Content-Type": "application/json"
        }
    };

    if (body !== null) {
        options.body = JSON.stringify(body);
    }

    let response;

    try {
        response = await fetch(
            (window.CGI_API_BASE || "") + path,
            options
        );
    } catch (error) {
        return {
            status: 0,
            data: {
                detail: "Network error: " + error.message
            }
        };
    }

    let data = null;

    try {
        data = await response.json();
    } catch (_) {
        // 204 No Content responses do not contain JSON.
    }

    if (response.status === 401) {
        sessionStorage.removeItem("cgi_jwt");

        window.location.href =
            (window.CGI_BASE || "") + "/login.php";
    }

    return {
        status: response.status,
        data
    };
}

/* ============================================================
   TOAST NOTIFICATIONS
   ============================================================ */

let alertTimer = null;
let alertRemovalTimer = null;

const toastTypes = {
    success: { icon: "\u2713", label: "Success" },
    danger: { icon: "!", label: "Error" },
    warning: { icon: "!", label: "Warning" },
    info: { icon: "i", label: "Information" }
};

function dismissAlert(element) {
    if (!element) return;

    element.classList.add("alert-hiding");

    alertRemovalTimer = setTimeout(() => {
        element.classList.add("d-none");
        element.classList.remove("alert-hiding", "is-visible");
    }, 350);
}

function scheduleAlertDismiss(element) {
    clearTimeout(alertTimer);
    clearTimeout(alertRemovalTimer);

    alertTimer = setTimeout(() => {
        dismissAlert(element);
    }, 5000);
}

function showAlert(message, type = "success") {
    const element = document.getElementById("jsAlert");
    const text = document.getElementById("jsAlertMsg");
    const icon = document.getElementById("jsAlertIcon");

    if (!element || !text) return;

    clearTimeout(alertTimer);
    clearTimeout(alertRemovalTimer);

    const toastType = toastTypes[type] ? type : "info";
    const presentation = toastTypes[toastType];

    element.className = `cgi-users-toast cgi-users-toast-${toastType}`;
    element.setAttribute("aria-label", presentation.label);

    // Use textContent for API/user-derived messages.
    text.textContent = message;
    if (icon) icon.textContent = presentation.icon;

    requestAnimationFrame(() => element.classList.add("is-visible"));

    scheduleAlertDismiss(element);
}

function showInlineAlert(element, message) {
    // Keep the parameter for compatibility with existing validation calls.
    showAlert(message, "danger");
}

const initialServerAlert =
    document.getElementById("serverAlert");

if (initialServerAlert) {
    showAlert(
        initialServerAlert.textContent.trim(),
        initialServerAlert.dataset.toastType || "success"
    );
    initialServerAlert.remove();
}

document.getElementById("jsAlertClose")
    ?.addEventListener("click", () => {
        clearTimeout(alertTimer);
        dismissAlert(document.getElementById("jsAlert"));
    });

/* ============================================================
   ACTION CONFIRMATION POPUP
   ============================================================ */

const confirmModalElement =
    document.getElementById("userActionConfirmModal");
const confirmModal = confirmModalElement
    ? new bootstrap.Modal(confirmModalElement, {
        backdrop: "static",
        keyboard: false
    })
    : null;
let resolveConfirmation = null;

function requestConfirmation({ action, name, message, destructive = false }) {
    if (!confirmModal) return Promise.resolve(false);

    document.getElementById("userActionConfirmTitle").textContent =
        `${action} account?`;
    document.getElementById("userActionConfirmUser").textContent = name;
    document.getElementById("userActionConfirmMessage").textContent = message;

    const confirmButton = document.getElementById("userActionConfirmBtn");
    confirmButton.textContent = action;
    confirmButton.classList.toggle("cgi-users-confirm-danger", destructive);

    const icon = document.getElementById("userActionConfirmIcon");
    icon.classList.toggle("is-danger", destructive);
    icon.textContent = destructive ? "!" : "\u2713";

    confirmModal.show();

    return new Promise(resolve => {
        resolveConfirmation = resolve;
    });
}

function finishConfirmation(confirmed) {
    if (!resolveConfirmation) return;
    const resolve = resolveConfirmation;
    resolveConfirmation = null;
    confirmModal.hide();
    resolve(confirmed);
}

document.getElementById("userActionCancelBtn")
    ?.addEventListener("click", () => finishConfirmation(false));
document.getElementById("userActionConfirmBtn")
    ?.addEventListener("click", () => finishConfirmation(true));

/* ============================================================
   USER STATISTICS
   ============================================================ */

async function refreshUserStats() {
    const response = await apiCall(
        "GET",
        "/api/users/stats"
    );

    if (response.status !== 200 || !response.data) {
        return;
    }

    for (const [key, value] of Object.entries(response.data)) {
        const element = document.getElementById(
            `stat-${key}`
        );

        if (element) {
            element.textContent = value;
        }
    }
}

/* ============================================================
   SEARCH AND FILTERS
   ============================================================ */

const userSearch = document.getElementById("userSearch");
const roleFilter = document.getElementById("roleFilter");
const statusFilter = document.getElementById("statusFilter");
const resetUserFilters =
    document.getElementById("resetUserFilters");

function filterUsers() {
    const query = userSearch.value.trim().toLowerCase();
    const selectedRole = roleFilter.value;
    const selectedStatus = statusFilter.value;

    const rows = document.querySelectorAll(
        "#userTable tbody .user-row"
    );

    let visible = 0;

    rows.forEach(row => {
        const searchValue = row.dataset.search || "";
        const roleValue = row.dataset.role || "";
        const statusValue = row.dataset.status || "";

        const matchesSearch =
            !query || searchValue.includes(query);

        const matchesRole =
            !selectedRole || roleValue === selectedRole;

        const matchesStatus =
            !selectedStatus || statusValue === selectedStatus;

        const show =
            matchesSearch &&
            matchesRole &&
            matchesStatus;

        row.classList.toggle("d-none", !show);

        if (show) visible++;
    });

    document.getElementById("noUsersMatch")
        ?.classList.toggle("d-none", visible !== 0);

    const total = rows.length;

    const showingLabel =
        document.getElementById("showingUsersLabel");

    if (showingLabel) {
        showingLabel.textContent =
            visible === total
                ? `Showing ${total} ${total === 1 ? "user" : "users"}`
                : `Showing ${visible} of ${total} users`;
    }

}

userSearch?.addEventListener("input", filterUsers);
roleFilter?.addEventListener("change", filterUsers);
statusFilter?.addEventListener("change", filterUsers);

resetUserFilters?.addEventListener("click", () => {
    userSearch.value = "";
    roleFilter.value = "";
    statusFilter.value = "";

    filterUsers();
});

filterUsers();

/* ============================================================
   EDIT USER
   ============================================================ */

const editModalElement =
    document.getElementById("editUserModal");

const editModal = new bootstrap.Modal(editModalElement);

document.querySelectorAll(".btn-edit").forEach(button => {
    button.addEventListener("click", () => {
        document.getElementById("editUserId").value =
            button.dataset.id;

        document.getElementById("editName").value =
            button.dataset.name;

        document.getElementById("editEmail").value =
            button.dataset.email;

        document.getElementById("editRole").value =
            button.dataset.role;

        document.getElementById("editPassword").value = "";

        document.getElementById("editError")
            .classList.add("d-none");

        editModal.show();
    });
});

document.getElementById("saveEditBtn")
    ?.addEventListener("click", async () => {

        const id =
            document.getElementById("editUserId").value;

        const name =
            document.getElementById("editName").value.trim();

        const email =
            document.getElementById("editEmail").value.trim();

        const role =
            document.getElementById("editRole").value;

        const password =
            document.getElementById("editPassword").value;

        const errorElement =
            document.getElementById("editError");

        const saveButton =
            document.getElementById("saveEditBtn");

        errorElement.classList.add("d-none");

        if (!name || !email) {
            showInlineAlert(
                errorElement,
                "Name and email are required."
            );
            return;
        }

        if (password && password.length < 8) {
            showInlineAlert(
                errorElement,
                "Password must be at least 8 characters."
            );
            return;
        }

        const payload = {
            name,
            email,
            role
        };

        if (password) {
            payload.password = password;
        }

        saveButton.disabled = true;
        saveButton.textContent = "Saving...";

        try {
            const response = await apiCall(
                "PUT",
                `/api/users/${id}`,
                payload
            );

            if (response.status === 200) {
                editModal.hide();

                showAlert(
                    "User updated successfully. Reloading..."
                );

                setTimeout(() => {
                    window.location.reload();
                }, 5350);
            } else {
                showInlineAlert(
                    errorElement,
                    response.data?.detail ??
                    `Update failed (HTTP ${response.status}).`
                );
            }
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = "Save Changes";
        }
    });

/* ============================================================
   ACTIVATE / DEACTIVATE USER
   ============================================================ */

document.querySelectorAll(".btn-toggle").forEach(button => {
    button.addEventListener("click", async () => {
        const id = button.dataset.id;
        const active = button.dataset.active === "1";
        const name = button.dataset.name;

        const action = active
            ? "deactivate"
            : "activate";

        const confirmed = await requestConfirmation({
            action: active ? "Deactivate" : "Activate",
            name,
            message: `Are you sure you want to ${action} this account?`,
            destructive: active
        });

        if (!confirmed) return;

        const response = await apiCall(
            "PUT",
            `/api/users/${id}`,
            {
                is_active: !active
            }
        );

        if (response.status === 200) {
            const newActive = response.data.is_active;

            const row = document.getElementById(
                `row-${id}`
            );

            if (row) {
                row.dataset.status = newActive
                    ? "active"
                    : "inactive";
            }

            const statusCell = document.getElementById(
                `status-${id}`
            );

            if (statusCell) {
                statusCell.innerHTML = newActive
                    ? '<span class="badge bg-success">Active</span>'
                    : '<span class="badge bg-secondary">Inactive</span>';
            }

            button.textContent = newActive
                ? "Deactivate"
                : "Activate";

            button.dataset.active = newActive ? "1" : "0";

            button.className =
                "btn btn-sm " +
                (newActive
                    ? "btn-outline-warning"
                    : "btn-outline-success") +
                " btn-toggle";

            showAlert(
                `"${name}" has been ${
                    newActive ? "activated" : "deactivated"
                }.`
            );

            await refreshUserStats();
            filterUsers();
        } else {
            showAlert(
                response.data?.detail ??
                "Could not update user.",
                "danger"
            );
        }
    });
});

/* ============================================================
   DELETE USER
   ============================================================ */

document.querySelectorAll(".btn-delete").forEach(button => {
    button.addEventListener("click", async () => {
        const id = button.dataset.id;
        const name = button.dataset.name;

        const confirmed = await requestConfirmation({
            action: "Delete",
            name,
            message: "This cannot be undone. Users with transaction records will be deactivated instead.",
            destructive: true
        });

        if (!confirmed) return;

        const response = await apiCall(
            "DELETE",
            `/api/users/${id}`
        );

        if (response.status === 204) {
            document.getElementById(
                `row-${id}`
            )?.remove();

            showAlert(
                `User "${name}" has been deleted.`
            );

            filterUsers();
            await refreshUserStats();

        } else if (response.status === 409) {
            // V2 preserves linked transaction records
            // by deactivating rather than deleting.

            const row = document.getElementById(
                `row-${id}`
            );

            if (row) {
                row.dataset.status = "inactive";
            }

            const statusCell = document.getElementById(
                `status-${id}`
            );

            if (statusCell) {
                statusCell.innerHTML =
                    '<span class="badge bg-secondary">Inactive</span>';
            }

            const toggleButton = document.querySelector(
                `.btn-toggle[data-id="${id}"]`
            );

            if (toggleButton) {
                toggleButton.textContent = "Activate";
                toggleButton.dataset.active = "0";

                toggleButton.className =
                    "btn btn-sm btn-outline-success btn-toggle";
            }

            showAlert(
                response.data?.detail ??
                "User deactivated (has linked records).",
                "warning"
            );

            filterUsers();
            await refreshUserStats();

        } else {
            showAlert(
                response.data?.detail ??
                "Delete failed.",
                "danger"
            );
        }
    });
});
