<?php
require_once __DIR__ . '/../api.php';
api_require_auth(['admin', 'officer']);
$txn_id = (int)($_POST['txn_id'] ?? 0);
if ($txn_id) {
    api_request('POST', "/api/reports/transaction/{$txn_id}/print");
}
header('Location: ' . APP_BASE . '/history.php');
exit;
