document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("history-search");
    const gradeFilter = document.getElementById("grade-filter");
    const dateFilter = document.getElementById("date-filter");
    const resetBtn = document.getElementById("reset-filters");
    const emptyReset = document.getElementById("empty-reset");
    const emptyState = document.getElementById("empty-state");
    const tableWrap = document.querySelector(".table-wrap");
    const tableFooter = document.querySelector(".table-footer");
    const resultCount = document.getElementById("result-count");
    const rows = [...document.querySelectorAll(".transaction-row")];
    const detailsOverlay = document.getElementById("details-overlay");
    const detailsCloseFooter = document.getElementById("details-close-footer");
    const detailsPrint = document.getElementById("details-print");
    const exportBtn = document.getElementById("export-btn");
    let activeTransaction = null;
    let lastTrigger = null;

    function getTodayString() {
        const parts = new Intl.DateTimeFormat("en-US", {
            timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit"
        }).formatToParts(new Date());
        const part = type => parts.find(value => value.type === type).value;
        return `${part("year")}-${part("month")}-${part("day")}`;
    }

    function daysBetween(dateString) {
        const dayNumber = value => {
            const [year, month, day] = value.split("-").map(Number);
            return Date.UTC(year, month - 1, day) / 86400000;
        };
        return dayNumber(getTodayString()) - dayNumber(dateString);
    }

    function applyFilters() {
        const query = searchInput.value.trim().toLowerCase();
        const selectedGrade = gradeFilter.value;
        const selectedDate = dateFilter.value;
        let visible = 0;

        rows.forEach((row) => {
            const idMatches = row.dataset.id.includes(query);
            const gradeMatches = selectedGrade === "all" || row.dataset.grade === selectedGrade;
            let dateMatches = true;

            if (selectedDate === "today") {
                dateMatches = row.dataset.date === getTodayString();
            } else if (selectedDate !== "all") {
                const difference = daysBetween(row.dataset.date);
                dateMatches = difference >= 0 && difference < Number(selectedDate);
            }

            const show = idMatches && gradeMatches && dateMatches;
            row.hidden = !show;
            if (show) visible++;
        });

        const noResults = visible === 0;
        emptyState.hidden = !noResults;
        tableWrap.hidden = noResults;
        tableFooter.hidden = noResults;
        exportBtn.disabled = noResults;
        resultCount.textContent = `Showing ${visible} ${visible === 1 ? "transaction" : "transactions"}`;
    }

    function resetFilters() {
        searchInput.value = "";
        gradeFilter.value = "all";
        dateFilter.value = "all";
        applyFilters();
        searchInput.focus();
    }

    searchInput.addEventListener("input", applyFilters);
    gradeFilter.addEventListener("change", applyFilters);
    dateFilter.addEventListener("change", applyFilters);
    resetBtn.addEventListener("click", resetFilters);
    emptyReset.addEventListener("click", resetFilters);

    function formatDate(dateString) {
        return new Intl.DateTimeFormat("en-PH", {
            month: "long",
            day: "numeric",
            year: "numeric"
        }).format(new Date(`${dateString}T00:00:00`));
    }

    function formatNumber(value, decimals = 0, suffix = "") {
        return value == null ? "Not recorded" : Number(value).toLocaleString("en-PH", {
            minimumFractionDigits: decimals, maximumFractionDigits: decimals
        }) + suffix;
    }

    function sensorReading(transaction) {
        const reading = transaction.sensorReading;
        if (reading?.value == null) return "Not recorded";
        return `${reading.value} ${reading.unit || "Unit not recorded"} (${reading.calibrated ? "calibrated" : "uncalibrated"})`;
    }

    function formatMoney(value, currency) {
        if (value == null) return "Not recorded";
        return new Intl.NumberFormat("en-PH", {
            style: "currency", currency,
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(Number(value));
    }

    function gradeClass(grade) {
        if (grade === "Extra Class") return "grade-extra";
        if (grade === "Class I") return "grade-one";
        if (grade === "Class II") return "grade-two";
        return "";
    }

    function openDetails(transaction) {
        lastTrigger = document.activeElement;
        activeTransaction = transaction;

        document.getElementById("details-title").textContent = transaction.id;
        document.getElementById("details-record-label").textContent = transaction.recordLabel;
        document.getElementById("details-sensor-reading").textContent = sensorReading(transaction);
        document.getElementById("details-sensor-time").textContent = transaction.sensorReading?.measured_at ?? "Not recorded";
        document.getElementById("details-raw-counts").textContent = transaction.sensorReading?.raw_counts == null
            ? "Not recorded" : String(transaction.sensorReading.raw_counts);
        document.getElementById("details-datetime").textContent = `${formatDate(transaction.date)} · ${transaction.time}`;

        const grade = document.getElementById("details-grade");
        grade.textContent = transaction.grade;
        grade.className = `grade-badge ${gradeClass(transaction.grade)}`;

        document.getElementById("details-confidence").textContent = transaction.confidence == null ? "Not recorded" : `${Number(transaction.confidence).toFixed(1)}%`;
        document.getElementById("details-coffee").textContent = transaction.coffee;
        document.getElementById("details-weight").textContent = formatNumber(transaction.weight, 2, " g");
        document.getElementById("details-beans").textContent = formatNumber(transaction.beans);
        document.getElementById("details-defects").textContent = transaction.defects == null ? "Not recorded" : transaction.defects.toLocaleString();
        document.getElementById("details-percentage").textContent = transaction.defectPercentage == null ? "Not recorded" : `${Number(transaction.defectPercentage).toFixed(3)}% defects`;
        document.getElementById("details-reference").textContent = transaction.referencePrice == null ? "Not recorded" : `${formatMoney(transaction.referencePrice, transaction.currency)}/kg`;
        document.getElementById("details-recorded-weight").textContent = formatNumber(transaction.pricingWeightKg, 4, " kg");
        document.getElementById("details-threshold").hidden = !transaction.overThreshold;
        document.getElementById("details-price").textContent = formatMoney(transaction.suggestedPrice, transaction.currency);

        const defectList = document.getElementById("details-defect-list");
        defectList.innerHTML = "";

        if (!transaction.defectList.length) {
            defectList.innerHTML = `<div class="defect-item"><span>Defect breakdown not recorded</span><strong>—</strong></div>`;
        } else {
            transaction.defectList.forEach((defect) => {
                const item = document.createElement("div");
                item.className = "defect-item";
                item.innerHTML = `<span>${escapeHTML(defect.name)}</span><strong>${Number(defect.count)} · ${Number(defect.percentage).toFixed(3)}%</strong>`;
                defectList.appendChild(item);
            });
        }

        detailsOverlay.hidden = false;
        document.body.classList.add("details-open");
        detailsCloseFooter?.focus();
    }

    function closeDetails() {
        detailsOverlay.hidden = true;
        document.body.classList.remove("details-open");
        activeTransaction = null;
        lastTrigger?.focus();
    }

    function escapeHTML(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    rows.forEach((row) => {
        const transaction = JSON.parse(row.dataset.transaction);

        row.addEventListener("click", (event) => {
            if (event.target.closest(".print-btn") || event.target.closest(".view-btn")) return;
            openDetails(transaction);
        });

        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && event.target === row) openDetails(transaction);
        });

        row.querySelector(".view-btn").addEventListener("click", () => {
            openDetails(transaction);
        });

        row.querySelector(".print-btn").addEventListener("click", () => {
            printReceipt(transaction);
        });
    });

    detailsCloseFooter?.addEventListener("click", closeDetails);

    detailsOverlay.addEventListener("click", (event) => {
        if (event.target === detailsOverlay) closeDetails();
    });

    document.addEventListener("keydown", (event) => {
        if (detailsOverlay.hidden) return;
        if (event.key === "Escape") closeDetails();
        if (event.key === "Tab") {
            const buttons = [...detailsOverlay.querySelectorAll("button")];
            const first = buttons[0];
            const last = buttons[buttons.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    });

    detailsPrint.addEventListener("click", () => {
        if (activeTransaction) printReceipt(activeTransaction);
    });

    function buildReceipt(transaction) {
        return `
        <div class="receipt-paper">
            <div class="receipt-brand">
                <h3>COFFEE GRADE<br>IDENTIFICATION</h3>
                <p>Quality Assessment Receipt</p>
                <p>${escapeHTML(transaction.recordLabel)}</p>
            </div>

            <div class="receipt-rule"></div>

            <div class="receipt-row">
                <span>Transaction ID</span>
                <strong>${escapeHTML(transaction.id)}</strong>
            </div>
            <div class="receipt-row">
                <span>Date</span>
                <strong>${escapeHTML(formatDate(transaction.date))}</strong>
            </div>
            <div class="receipt-row">
                <span>Time</span>
                <strong>${escapeHTML(transaction.time)}</strong>
            </div>

            <div class="receipt-rule"></div>

            <div class="receipt-row">
                <span>Coffee type</span>
                <strong>${escapeHTML(transaction.coffee)}</strong>
            </div>
            <div class="receipt-row">
                <span>Quality grade</span>
                <strong>${escapeHTML(transaction.grade)}</strong>
            </div>
            <div class="receipt-row">
                <span>Weight</span>
                <strong>${formatNumber(transaction.weight, 2, " g")}</strong>
            </div>
            <div class="receipt-row"><span>Saved HX711 reading</span><strong>${escapeHTML(sensorReading(transaction))}</strong></div>
            <div class="receipt-row"><span>Raw HX711 ADC counts</span><strong>${escapeHTML(transaction.sensorReading?.raw_counts ?? "Not recorded")}</strong></div>
            <div class="receipt-row"><span>Detected beans</span><strong>${formatNumber(transaction.beans)}</strong></div>
            <div class="receipt-row"><span>Detected defects</span><strong>${transaction.defects == null ? 'Not recorded' : Number(transaction.defects)}</strong></div>
            <div class="receipt-row"><span>Defects (%)</span><strong>${transaction.defectPercentage == null ? 'Not recorded' : Number(transaction.defectPercentage).toFixed(3) + '%'}</strong></div>
            <div class="receipt-row">
                <span>Transaction weight</span><strong>${formatNumber(transaction.pricingWeightKg, 4, " kg")}</strong>
            </div>
            <div class="receipt-row">
                <span>Reference price</span>
                <strong>${escapeHTML(formatMoney(transaction.referencePrice, transaction.currency))}${transaction.referencePrice == null ? "" : " / kg"}</strong>
            </div>

            <div class="receipt-rule"></div>

            <div class="receipt-total">
                <span>SUGGESTED PRICE</span>
                <strong>${escapeHTML(formatMoney(transaction.suggestedPrice, transaction.currency))}</strong>
            </div>

            <div class="receipt-rule"></div>

            <p class="receipt-note">
                This receipt contains a suggested transaction price and does not represent a finalized sale.
            </p>

            <p class="receipt-thank-you">
                Thank you for using CGI.
            </p>
        </div>
    `;
    }

    function printReceipt(transaction) {
        const printArea = document.getElementById("receipt-print-area");

        if (!printArea) return;

        printArea.innerHTML = buildReceipt(transaction);
        document.body.classList.add("printing-history-receipt");

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                window.print();
            });
        });
    }

    window.addEventListener("afterprint", () => {
        document.body.classList.remove("printing-history-receipt");
    });

    exportBtn.addEventListener("click", () => {
        const visibleTransactions = rows
            .filter((row) => !row.hidden)
            .map((row) => JSON.parse(row.dataset.transaction));

        if (!visibleTransactions.length) return;

        const headers = [
            "Transaction ID",
            "Record Type",
            "HX711 Value",
            "HX711 Unit",
            "HX711 Calibrated",
            "HX711 Raw ADC Counts",
            "HX711 Measured At",
            "Date",
            "Time",
            "Coffee Type",
            "Weight (g)",
            "Detected Beans",
            "Detected Defects",
            "Defects (%)",
            "Grade",
            "Confidence (%)",
            "Transaction Weight (kg)",
            "Currency",
            "Reference Price (per kg)",
            "Suggested Price",
            "Over Class II Threshold"
        ];

        const csvRows = visibleTransactions.map((transaction) => [
            transaction.id,
            transaction.recordLabel,
            transaction.sensorReading?.value,
            transaction.sensorReading?.unit,
            transaction.sensorReading?.calibrated,
            transaction.sensorReading?.raw_counts,
            transaction.sensorReading?.measured_at,
            transaction.date,
            transaction.time,
            transaction.coffee,
            transaction.weight,
            transaction.beans,
            transaction.defects,
            transaction.defectPercentage,
            transaction.grade,
            transaction.confidence,
            transaction.pricingWeightKg,
            transaction.currency,
            transaction.referencePrice,
            transaction.suggestedPrice,
            transaction.overThreshold
        ]);

        const csv = [headers, ...csvRows]
            .map((row) => row.map(csvValue).join(","))
            .join("\n");

        const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `CGI-Transaction-History-${getTodayString()}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    });

    function csvValue(value) {
        const raw = String(value ?? "");
        const string = typeof value === "string" && /^[=+@\-\t\r]/.test(raw) ? "\'" + raw : raw;
        return `"${string.replaceAll('"', '""')}"`;
    }

    // Back/forward cache must not restore an old list after completing a transaction.
    window.addEventListener("pageshow", event => {
        if (event.persisted) window.location.reload();
    });

    applyFilters();
});
