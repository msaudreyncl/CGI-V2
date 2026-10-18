(function initHistory() {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initHistory);
        return;
    }
    const search = document.getElementById("history-search");
    const sourceFilter = document.getElementById("source-filter");
    const statusFilter = document.getElementById("status-filter");
    const reset = document.getElementById("reset-history-filters");
    const emptyReset = document.getElementById("history-empty-reset");
    const empty = document.getElementById("history-empty");
    const tableWrap = document.getElementById("history-table-wrap");
    const resultCount = document.getElementById("history-result-count");
    const rows = [...document.querySelectorAll(".cgi-history-row")];
    const details = document.getElementById("history-details");
    const detailsClose = document.getElementById("history-details-close");
    const detailsCloseFooter = document.getElementById("history-details-close-footer");
    let lastDetailsTrigger = null;

    function applyFilters() {
        if (!search || !sourceFilter || !statusFilter) return;
        const query = search.value.trim().toLowerCase();
        const source = sourceFilter.value;
        const status = statusFilter.value;
        let visible = 0;

        rows.forEach(row => {
            const matches = (!query || row.dataset.search.includes(query)) &&
                (source === "all" || row.dataset.source === source) &&
                (status === "all" || row.dataset.status === status);
            row.hidden = !matches;
            if (matches) visible++;
        });

        const noMatches = rows.length > 0 && visible === 0;
        if (empty) empty.hidden = !noMatches && rows.length > 0;
        if (tableWrap) tableWrap.hidden = rows.length === 0 || noMatches;
        if (resultCount) {
            resultCount.textContent = `Showing ${visible} ${visible === 1 ? "transaction" : "transactions"} on this page`;
        }
    }

    function resetFilters() {
        if (!search || !sourceFilter || !statusFilter) return;
        search.value = "";
        sourceFilter.value = "all";
        statusFilter.value = "all";
        applyFilters();
        search.focus();
    }

    function peso(value) {
        return `₱${Number(value || 0).toLocaleString("en-PH", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        })}`;
    }

    function openDetails(row, trigger) {
        if (!details) return;
        const transaction = JSON.parse(row.dataset.transaction);
        lastDetailsTrigger = trigger || row;
        document.getElementById("history-details-title").textContent = `Transaction #${transaction.id}`;
        document.getElementById("detail-created").textContent = transaction.created_at || "-";
        document.getElementById("detail-total").textContent = peso(transaction.total_price);
        document.getElementById("detail-inspection").textContent = `#${transaction.inspection_id}`;
        document.getElementById("detail-weight").textContent = `${Number(transaction.weight_kg).toFixed(3)} kg`;
        document.getElementById("detail-price").textContent = `${peso(transaction.price_per_kg)} / kg`;
        document.getElementById("detail-source").textContent = String(transaction.price_source || "-").toUpperCase();
        document.getElementById("detail-status").textContent = transaction.status || "-";
        document.getElementById("detail-print-status").textContent = transaction.print_status || "-";
        document.getElementById("detail-notes").textContent = transaction.notes || "No notes recorded";
        details.hidden = false;
        document.body.classList.add("details-open");
        requestAnimationFrame(() => details.classList.add("is-open"));
        detailsClose?.focus();
    }

    function closeDetails() {
        if (!details || details.hidden) return;
        details.classList.remove("is-open");
        window.setTimeout(() => { details.hidden = true; }, 220);
        document.body.classList.remove("details-open");
        lastDetailsTrigger?.focus();
    }

    search?.addEventListener("input", applyFilters);
    sourceFilter?.addEventListener("change", applyFilters);
    statusFilter?.addEventListener("change", applyFilters);
    reset?.addEventListener("click", resetFilters);
    emptyReset?.addEventListener("click", resetFilters);

    rows.forEach(row => {
        row.addEventListener("click", event => {
            if (event.target.closest("a, button, form")) return;
            openDetails(row, row);
        });
        row.addEventListener("keydown", event => {
            if (event.key === "Enter") openDetails(row, row);
        });
        row.querySelector(".cgi-history-view")?.addEventListener("click", event => {
            openDetails(row, event.currentTarget);
        });
    });

    detailsClose?.addEventListener("click", closeDetails);
    detailsCloseFooter?.addEventListener("click", closeDetails);
    details?.addEventListener("click", event => {
        if (event.target === details) closeDetails();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && details && !details.hidden) closeDetails();
    });

    applyFilters();
})();
