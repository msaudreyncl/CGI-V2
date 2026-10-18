<?php
require_once __DIR__ . '/api.php';
api_require_auth();

$user = api_current_user();
$page = max(1, (int)($_GET['page'] ?? 1));
$limit = 20;
$skip = ($page - 1) * $limit;
$resp = api_request('GET', "/api/transactions?skip={$skip}&limit={$limit}");
$transactions = api_response_list($resp);

function history_escape($value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function history_datetime(?string $iso, string $format): string {
    if (!$iso) return '-';
    try {
        $date = new DateTime($iso, new DateTimeZone('UTC'));
        $date->setTimezone(new DateTimeZone('Asia/Manila'));
        return $date->format($format);
    } catch (Exception $e) {
        return $iso;
    }
}

$page_total = array_sum(array_map(
    fn($transaction) => (float)($transaction['total_price'] ?? 0),
    $transactions
));
$api_priced = count(array_filter(
    $transactions,
    fn($transaction) => ($transaction['price_source'] ?? '') === 'api'
));
$printed = count(array_filter(
    $transactions,
    fn($transaction) => ($transaction['print_status'] ?? '') === 'printed'
));
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>History — CGI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400;500;600;700&family=Work+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="assets/css/main.css">
<link rel="stylesheet" href="<?= history_escape(APP_BASE) ?>/assets/css/navbar.css?v=3">
<link rel="stylesheet" href="<?= history_escape(APP_BASE) ?>/assets/css/history.css?v=3">
</head>
<body class="cgi-history-body">

<?php include __DIR__ . '/components/navbar.php'; ?>

<main class="cgi-history-main">
    <section class="cgi-history-heading">
        <div>
            <span class="cgi-history-eyebrow">TRANSACTION RECORDS</span>
            <h1>History</h1>
            <p>Review completed coffee assessments, transaction pricing, and previous receipts.</p>
        </div>

        <?php if ($user['role'] !== 'farmer'): ?>
        <a href="<?= history_escape(APP_BASE) ?>/api/reports/transactions/csv"
           class="cgi-history-export" target="_blank" rel="noopener">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 3h2v10.17l3.59-3.58L18 11l-6 6-6-6 1.41-1.41L11 13.17V3ZM5 19h14v2H5v-2Z"/></svg>
            Export records
        </a>
        <?php endif; ?>
    </section>

    <section class="cgi-history-summary" aria-label="Current page transaction summary">
        <article class="cgi-history-summary-card summary-total">
            <span class="cgi-history-summary-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M6 2h9l5 5v15H6V2Zm8 2v4h4.17L14 4ZM8 12h10v-2H8v2Zm0 4h10v-2H8v2Zm0 4h7v-2H8v2Z"/></svg>
            </span>
            <div><strong><?= count($transactions) ?></strong><span>Transactions on page</span></div>
        </article>
        <article class="cgi-history-summary-card">
            <span class="cgi-history-summary-dot dot-gold"></span>
            <div><strong>₱<?= number_format($page_total, 2) ?></strong><span>Page transaction value</span></div>
        </article>
        <article class="cgi-history-summary-card">
            <span class="cgi-history-summary-dot dot-sage"></span>
            <div><strong><?= $api_priced ?></strong><span>API-priced records</span></div>
        </article>
        <article class="cgi-history-summary-card">
            <span class="cgi-history-summary-dot dot-bean"></span>
            <div><strong><?= $printed ?></strong><span>Printed receipts</span></div>
        </article>
    </section>

    <section class="cgi-history-panel">
        <div class="cgi-history-toolbar">
            <label class="cgi-history-search" for="history-search">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 19-4.35-4.35A7.5 7.5 0 1 0 15.24 16L19.59 20.35 21 19ZM5 10.5a5.5 5.5 0 1 1 11 0 5.5 5.5 0 0 1-11 0Z"/></svg>
                <input type="search" id="history-search"
                       placeholder="Search transaction or inspection ID..." autocomplete="off">
            </label>

            <div class="cgi-history-filters">
                <label><span>Source</span>
                    <select id="source-filter">
                        <option value="all">All sources</option>
                        <option value="api">API</option>
                        <option value="manual">Manual</option>
                    </select>
                </label>
                <label><span>Status</span>
                    <select id="status-filter">
                        <option value="all">All statuses</option>
                        <option value="completed">Completed</option>
                        <option value="analyzed">Analyzed</option>
                        <option value="in_progress">In progress</option>
                    </select>
                </label>
                <button type="button" id="reset-history-filters">Reset</button>
            </div>
        </div>

        <div class="cgi-history-table-wrap" id="history-table-wrap" <?= empty($transactions) ? 'hidden' : '' ?>>
            <table class="cgi-history-table">
                <thead><tr>
                    <th>Transaction</th>
                    <th>Date &amp; Time</th>
                    <th>Weight</th>
                    <th>Price / kg</th>
                    <th>Total</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr></thead>
                <tbody id="history-body">
                <?php foreach ($transactions as $transaction):
                    $source = strtolower((string)($transaction['price_source'] ?? ''));
                    $status = strtolower((string)($transaction['status'] ?? ''));
                    $print_status = strtolower((string)($transaction['print_status'] ?? ''));
                    $search = strtolower(
                        (string)($transaction['id'] ?? '') . ' ' .
                        (string)($transaction['inspection_id'] ?? '')
                    );
                    $details = [
                        'id' => $transaction['id'] ?? '',
                        'inspection_id' => $transaction['inspection_id'] ?? '',
                        'weight_kg' => (float)($transaction['weight_kg'] ?? 0),
                        'price_per_kg' => (float)($transaction['price_per_kg'] ?? 0),
                        'total_price' => (float)($transaction['total_price'] ?? 0),
                        'currency' => $transaction['currency'] ?? 'PHP',
                        'price_source' => $transaction['price_source'] ?? '',
                        'status' => $transaction['status'] ?? '',
                        'print_status' => $transaction['print_status'] ?? '',
                        'notes' => $transaction['notes'] ?? '',
                        'created_at' => history_datetime($transaction['created_at'] ?? null, 'M d, Y · g:i A'),
                    ];
                ?>
                <tr class="cgi-history-row" tabindex="0"
                    data-search="<?= history_escape($search) ?>"
                    data-source="<?= history_escape($source) ?>"
                    data-status="<?= history_escape($status) ?>"
                    data-transaction="<?= history_escape(json_encode($details)) ?>">
                    <td>
                        <div class="cgi-history-transaction">
                            <span></span>
                            <div><strong>#<?= (int)$transaction['id'] ?></strong><small>Inspection #<?= (int)$transaction['inspection_id'] ?></small></div>
                        </div>
                    </td>
                    <td><strong><?= history_escape(history_datetime($transaction['created_at'] ?? null, 'M d, Y')) ?></strong><small><?= history_escape(history_datetime($transaction['created_at'] ?? null, 'g:i A')) ?></small></td>
                    <td><strong><?= number_format((float)$transaction['weight_kg'], 3) ?> kg</strong></td>
                    <td><strong>₱<?= number_format((float)$transaction['price_per_kg'], 2) ?></strong></td>
                    <td><strong class="cgi-history-price">₱<?= number_format((float)$transaction['total_price'], 2) ?></strong></td>
                    <td><span class="cgi-history-badge source-<?= history_escape($source) ?>"><?= history_escape(strtoupper($source ?: '-')) ?></span></td>
                    <td><span class="cgi-history-badge status-<?= history_escape($status) ?>"><?= history_escape(ucwords(str_replace('_', ' ', $status ?: '-'))) ?></span></td>
                    <td>
                        <div class="cgi-history-actions">
                            <a href="<?= history_escape(APP_BASE) ?>/api/reports/inspection/<?= (int)$transaction['inspection_id'] ?>/pdf"
                               target="_blank" rel="noopener" class="cgi-history-action">PDF</a>
                            <?php if ($user['role'] !== 'farmer'): ?>
                            <form method="POST" action="<?= history_escape(APP_BASE) ?>/actions/print_receipt.php">
                                <input type="hidden" name="txn_id" value="<?= (int)$transaction['id'] ?>">
                                <button type="submit" class="cgi-history-action">Print</button>
                            </form>
                            <?php endif; ?>
                            <button type="button" class="cgi-history-view" aria-label="View transaction details">
                                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9.29 6.71 1.42-1.42L17.41 12l-6.7 6.71-1.42-1.42L14.59 12 9.29 6.71Z"/></svg>
                            </button>
                        </div>
                    </td>
                </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>

        <div class="cgi-history-empty" id="history-empty" <?= empty($transactions) ? '' : 'hidden' ?>>
            <span aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9.5 3a6.5 6.5 0 1 0 3.98 11.64L19.84 21 21 19.84l-6.36-6.36A6.5 6.5 0 0 0 9.5 3Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z"/></svg></span>
            <h2><?= empty($transactions) ? 'No transaction history found' : 'No matching transactions' ?></h2>
            <p><?= empty($transactions) ? 'Completed transactions will appear here.' : 'Try changing your search or filters.' ?></p>
            <?php if (!empty($transactions)): ?><button type="button" id="history-empty-reset">Clear filters</button><?php endif; ?>
        </div>

        <footer class="cgi-history-footer">
            <p id="history-result-count">Showing <?= count($transactions) ?> transaction<?= count($transactions) === 1 ? '' : 's' ?> on page <?= $page ?></p>
            <nav class="cgi-history-pagination" aria-label="History pages">
                <?php if ($page > 1): ?><a href="?page=<?= $page - 1 ?>">← Previous</a><?php endif; ?>
                <span>Page <?= $page ?></span>
                <?php if (count($transactions) === $limit): ?><a href="?page=<?= $page + 1 ?>">Next →</a><?php endif; ?>
            </nav>
        </footer>
    </section>
</main>

<div class="cgi-history-details" id="history-details" hidden>
    <aside role="dialog" aria-modal="true" aria-labelledby="history-details-title">
        <header>
            <div><span class="cgi-history-eyebrow">TRANSACTION DETAILS</span><h2 id="history-details-title">Transaction</h2><p id="detail-created"></p></div>
            <button type="button" id="history-details-close" aria-label="Close details">&times;</button>
        </header>
        <div class="cgi-history-details-body">
            <div class="cgi-history-details-total"><span>Total transaction value</span><strong id="detail-total">₱0.00</strong></div>
            <dl>
                <div><dt>Inspection</dt><dd id="detail-inspection"></dd></div>
                <div><dt>Weight</dt><dd id="detail-weight"></dd></div>
                <div><dt>Price per kilogram</dt><dd id="detail-price"></dd></div>
                <div><dt>Price source</dt><dd id="detail-source"></dd></div>
                <div><dt>Status</dt><dd id="detail-status"></dd></div>
                <div><dt>Print status</dt><dd id="detail-print-status"></dd></div>
                <div><dt>Notes</dt><dd id="detail-notes"></dd></div>
            </dl>
        </div>
        <footer><button type="button" id="history-details-close-footer">Close</button></footer>
    </aside>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="<?= APP_BASE ?>/assets/js/navbar.js?v=2"></script>
<script src="<?= history_escape(APP_BASE) ?>/assets/js/history.js?v=2"></script>
</body>
</html>
