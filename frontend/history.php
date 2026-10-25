<?php
require_once __DIR__ . '/api.php';
api_require_auth();
$user = api_current_user();

function history_datetime(?string $iso, string $format): string {
    if (!$iso) return '';
    $date = new DateTime($iso, new DateTimeZone('UTC'));
    $date->setTimezone(new DateTimeZone('Asia/Manila'));
    return $date->format($format);
}

// Read through the existing authenticated APIs; never create or repair records here.
$transactions = [];
$historyError = false;
for ($skip = 0; ; $skip += 100) {
    $response = api_request('GET', "/api/transactions?skip={$skip}&limit=100");
    if ($response['status'] !== 200 || !is_array($response['data']) || !array_is_list($response['data'])) {
        $historyError = true;
        break;
    }
    $batch = api_response_list($response);
    foreach ($batch as $saved) {
        if (($saved['status'] ?? '') !== 'completed') continue;
        $detail = api_request('GET', '/api/inspection/' . (int)$saved['inspection_id']);
        if ($detail['status'] !== 200 || !is_array($detail['data'])) {
            $historyError = true;
            break 2;
        }
        $inspection = $detail['data'];
        $breakdown = $inspection['defect_results'] ?? [];
        $hasBreakdown = count($breakdown) > 0;
        $transactions[] = [
            'id' => $inspection['txn_number'] ?: '#' . $saved['id'],
            'date' => history_datetime($saved['created_at'], 'Y-m-d'),
            'time' => history_datetime($saved['created_at'], 'h:i A'),
            'coffee' => 'Not recorded', // Existing schema has no coffee-type field.
            'weight' => $inspection['sample_weight_g'],
            'beans' => $inspection['total_beans_detected'],
            'defects' => $hasBreakdown ? array_sum(array_column($breakdown, 'bean_count')) : null,
            'defectPercentage' => $hasBreakdown ? array_sum(array_column($breakdown, 'defect_percentage')) : null,
            'grade' => ['extra_class' => 'Extra Class', 'class_i' => 'Class I', 'class_ii' => 'Class II'][$inspection['grade']] ?? $inspection['grade'],
            'confidence' => null, // Classification confidence is not persisted.
            'referencePrice' => $saved['price_per_kg'],
            'suggestedPrice' => $saved['total_price'],
            'defectList' => array_map(fn($d) => [
                'name' => ucwords(str_replace('_', ' ', $d['defect_type'])),
                'count' => $d['bean_count'], 'percentage' => $d['defect_percentage'],
            ], $breakdown),
        ];
    }
    if (count($batch) < 100) break;
}
// Avoid presenting partial totals as a complete history when a request fails.
if ($historyError) { $transactions = []; http_response_code(503); }

$totalTransactions = count($transactions);
$extraClass = count(array_filter($transactions, fn($t) => $t["grade"] === "Extra Class"));
$classI = count(array_filter($transactions, fn($t) => $t["grade"] === "Class I"));
$classII = count(array_filter($transactions, fn($t) => $t["grade"] === "Class II"));

function gradeClass($grade)
{
    return match ($grade) {
        "Extra Class" => "grade-extra",
        "Class I" => "grade-one",
        "Class II" => "grade-two",
        default => ""
    };
}
?>
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>Transaction History | CGI</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Work+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="assets/css/history.css?v=4">
    <link rel="stylesheet" href="assets/css/navbar.css?v=3">
</head>

<body>

    <?php
    $currentPage = 'history';
    include __DIR__ . '/components/navbar.php';
    ?>

    <main class="history-main">
        <?php if ($historyError): ?><p role="alert">Transaction history could not be loaded. Please refresh to try again.</p><?php endif; ?>
        <section class="page-heading">
            <div>
                <span class="eyebrow">TRANSACTION RECORDS</span>
                <h1>Transaction History</h1>
                <p>Review completed coffee quality assessments, inspect results, and reprint previous receipts.</p>
            </div>
            <button type="button" class="export-btn" id="export-btn">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M11 3h2v10.17l3.59-3.58L18 11l-6 6-6-6 1.41-1.41L11 13.17V3ZM5 19h14v2H5v-2Z" />
                </svg>
                Export records
            </button>
        </section>

        <section class="summary-grid" aria-label="Transaction summary">
            <article class="summary-card summary-total">
                <div class="summary-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M6 2h9l5 5v15H6V2Zm8 2v4h4.17L14 4ZM8 12h10v-2H8v2Zm0 4h10v-2H8v2Zm0 4h7v-2H8v2Z" />
                    </svg>
                </div>
                <div>
                    <strong><?= $totalTransactions ?></strong>
                    <span>Total transactions</span>
                </div>
            </article>

            <article class="summary-card summary-extra">
                <div class="summary-dot"></div>
                <div>
                    <strong><?= $extraClass ?></strong>
                    <span>Extra Class</span>
                </div>
            </article>

            <article class="summary-card summary-one">
                <div class="summary-dot"></div>
                <div>
                    <strong><?= $classI ?></strong>
                    <span>Class I</span>
                </div>
            </article>

            <article class="summary-card summary-two">
                <div class="summary-dot"></div>
                <div>
                    <strong><?= $classII ?></strong>
                    <span>Class II</span>
                </div>
            </article>
        </section>

        <section class="history-panel">
            <div class="history-toolbar">
                <div class="search-box">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="m21 19-4.35-4.35A7.5 7.5 0 1 0 15.24 16L19.59 20.35 21 19ZM5 10.5a5.5 5.5 0 1 1 11 0 5.5 5.5 0 0 1-11 0Z" />
                    </svg>
                    <input type="search" id="history-search" placeholder="Search transaction ID..." autocomplete="off">
                </div>

                <div class="filter-group">
                    <select id="grade-filter" aria-label="Filter by grade">
                        <option value="all">All grades</option>
                        <option value="Extra Class">Extra Class</option>
                        <option value="Class I">Class I</option>
                        <option value="Class II">Class II</option>
                    </select>

                    <select id="date-filter" aria-label="Filter by date">
                        <option value="all">All dates</option>
                        <option value="today">Today</option>
                        <option value="7">Last 7 days</option>
                        <option value="30">Last 30 days</option>
                    </select>

                    <button type="button" class="reset-btn" id="reset-filters">Reset</button>
                </div>
            </div>

            <div class="table-wrap">
                <table class="history-table">
                    <thead>
                        <tr>
                            <th>Transaction</th>
                            <th>Date & Time</th>
                            <th>Weight</th>
                            <th>Defects</th>
                            <th>Grade</th>
                            <th>Suggested Price</th>
                            <th class="print-heading">Receipt</th>
                            <th class="view-heading"></th>
                        </tr>
                    </thead>
                    <tbody id="history-body">
                        <?php foreach ($transactions as $transaction): ?>
                            <tr
                                class="transaction-row"
                                tabindex="0"
                                data-transaction='<?= htmlspecialchars(json_encode($transaction), ENT_QUOTES, "UTF-8") ?>'
                                data-id="<?= htmlspecialchars(strtolower($transaction["id"])) ?>"
                                data-grade="<?= htmlspecialchars($transaction["grade"]) ?>"
                                data-date="<?= htmlspecialchars($transaction["date"]) ?>">

                                <td>
                                    <div class="transaction-id">
                                        <span class="transaction-mark"></span>
                                        <div>
                                            <strong><?= htmlspecialchars($transaction["id"]) ?></strong>
                                            <span><?= htmlspecialchars($transaction["coffee"]) ?></span>
                                        </div>
                                    </div>
                                </td>

                                <td>
                                    <strong class="table-date"><?= date("M d, Y", strtotime($transaction["date"])) ?></strong>
                                    <span class="table-sub"><?= htmlspecialchars($transaction["time"]) ?></span>
                                </td>

                                <td>
                                    <strong><?= number_format($transaction["weight"], 2) ?> g</strong>
                                    <span class="table-sub"><?= number_format($transaction["beans"]) ?> beans</span>
                                </td>

                                <td>
                                    <strong><?= $transaction["defects"] === null ? "Not recorded" : number_format($transaction["defects"]) ?></strong>
                                    <span class="table-sub"><?= $transaction["defectPercentage"] === null ? "Not recorded" : number_format($transaction["defectPercentage"], 3) . "% defects" ?></span>
                                </td>

                                <td>
                                    <span class="grade-badge <?= gradeClass($transaction["grade"]) ?>">
                                        <?= htmlspecialchars($transaction["grade"]) ?>
                                    </span>
                                </td>

                                <td>
                                    <strong class="price-value">₱<?= number_format($transaction["suggestedPrice"], 2) ?></strong>
                                    <span class="table-sub">₱<?= number_format($transaction["referencePrice"], 2) ?>/kg ref.</span>
                                </td>

                                <td class="print-cell">
                                    <button type="button" class="print-btn" aria-label="Print receipt for <?= htmlspecialchars($transaction["id"]) ?>">
                                        <svg viewBox="0 0 24 24" aria-hidden="true">
                                            <path d="M6 9V3h12v6h1a3 3 0 0 1 3 3v5h-4v4H6v-4H2v-5a3 3 0 0 1 3-3h1Zm2-4v4h8V5H8Zm8 14v-5H8v5h8Zm3-4h1v-3a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v3h2v-3h12v3h1Z" />
                                        </svg>
                                        Print
                                    </button>
                                </td>

                                <td class="view-cell">
                                    <button type="button" class="view-btn" aria-label="View <?= htmlspecialchars($transaction["id"]) ?>">
                                        <svg viewBox="0 0 24 24" aria-hidden="true">
                                            <path d="m9.29 6.71 1.42-1.42L17.41 12l-6.7 6.71-1.42-1.42L14.59 12 9.29 6.71Z" />
                                        </svg>
                                    </button>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>

            <div class="empty-state" id="empty-state" hidden>
                <div class="empty-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M9.5 3a6.5 6.5 0 1 0 3.98 11.64L19.84 21 21 19.84l-6.36-6.36A6.5 6.5 0 0 0 9.5 3Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z" />
                    </svg>
                </div>
                <h3><?= $historyError ? "History unavailable" : "No matching transactions" ?></h3>
                <p>Try changing your search or transaction filters.</p>
                <button type="button" id="empty-reset">Clear filters</button>
            </div>

            <div class="table-footer">
                <p id="result-count">Showing <?= $totalTransactions ?> transactions</p>
            </div>
        </section>
    </main>

    <div class="details-overlay" id="details-overlay" hidden>
        <aside class="details-panel" role="dialog" aria-modal="true" aria-labelledby="details-title">
            <div class="details-header">
                <div>
                    <span class="eyebrow">TRANSACTION DETAILS</span>
                    <h2 id="details-title">Transaction</h2>
                    <p id="details-datetime">—</p>
                </div>
            </div>

            <div class="details-body">
                <section class="details-grade">
                    <span class="grade-badge" id="details-grade">—</span>
                    <div>
                        <span>Classification confidence</span>
                        <strong id="details-confidence">—</strong>
                    </div>
                </section>

                <section class="details-section">
                    <span class="details-label">SAMPLE INFORMATION</span>
                    <div class="details-list">
                        <div><span>Coffee type</span><strong id="details-coffee">—</strong></div>
                        <div><span>Sample weight</span><strong id="details-weight">—</strong></div>
                        <div><span>Detected beans</span><strong id="details-beans">—</strong></div>
                        <div><span>Detected defects</span><strong id="details-defects">—</strong></div>
                    </div>
                </section>

                <section class="details-section">
                    <div class="section-title-row">
                        <span class="details-label">DEFECT ANALYSIS</span>
                        <span id="details-points">—</span>
                    </div>
                    <div class="defect-list" id="details-defect-list"></div>
                </section>

                <section class="details-section pricing-section">
                    <span class="details-label">SUGGESTED TRANSACTIONAL PRICING</span>
                    <div class="details-list">
                        <div><span>Reference price</span><strong id="details-reference">—</strong></div>
                        <div><span>Recorded weight</span><strong id="details-recorded-weight">—</strong></div>
                    </div>
                    <div class="details-total">
                        <span>Suggested price</span>
                        <strong id="details-price">—</strong>
                    </div>
                    <p>This suggested price is generated from the recorded assessment and does not represent a finalized sale.</p>
                </section>
            </div>

            <div class="details-footer">
                <button type="button" class="secondary-btn" id="details-close-footer">Close</button>
                <button type="button" class="primary-btn" id="details-print">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M6 9V3h12v6h1a3 3 0 0 1 3 3v5h-4v4H6v-4H2v-5a3 3 0 0 1 3-3h1Zm2-4v4h8V5H8Zm8 14v-5H8v5h8Zm3-4h1v-3a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v3h2v-3h12v3h1Z" />
                    </svg>
                    Print receipt
                </button>
            </div>
        </aside>
    </div>

    <div id="receipt-print-area" aria-hidden="true"></div>

    <script src="assets/js/navbar.js?v=2"></script>
    <script src="assets/js/history.js?v=4"></script>
</body>

</html>