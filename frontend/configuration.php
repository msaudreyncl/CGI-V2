<?php
require_once __DIR__ . '/api.php';
api_require_auth(['admin', 'officer']);
$user = api_current_user();
$config_resp = api_request('GET', '/api/pricing/config');
$configs = api_response_list($config_resp);
$msg = '';
$msg_type = 'success';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $updates = [];
    foreach (['extra_class', 'class_i', 'class_ii'] as $grade) {
        if (isset($_POST[$grade])) {
            $updates[] = ['grade' => $grade, 'multiplier' => (float)$_POST[$grade]];
        }
    }
    if ($updates) {
        $r = api_request('PUT', '/api/pricing/config', $updates);
        $msg = $r['status'] === 200 ? 'Pricing config updated.' : ($r['data']['detail'] ?? 'Error saving.');
        $msg_type = $r['status'] === 200 ? 'success' : 'danger';
        $config_resp = api_request('GET', '/api/pricing/config');
        $configs = api_response_list($config_resp);
    }
}
$cfg_map = [];
foreach ($configs as $c) {
    if (isset($c['grade'])) $cfg_map[$c['grade']] = $c;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Configuration — CGI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400;500;600;700&family=Work+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="assets/css/main.css">
<link rel="stylesheet" href="<?= APP_BASE ?>/assets/css/navbar.css?v=3">
<link rel="stylesheet" href="<?= APP_BASE ?>/assets/css/configuration.css?v=1">
</head>
<body class="cgi-configuration-body">

<?php include __DIR__ . '/components/navbar.php'; ?>

<main class="cgi-configuration-main">
    <header class="cgi-configuration-heading">
        <div>
            <span class="cgi-configuration-eyebrow">SYSTEM CONFIGURATION</span>
            <h1>Pricing Configuration</h1>
            <p>Manage the grade multipliers used to calculate suggested coffee prices.</p>
        </div>
        <span class="cgi-configuration-heading-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.07-.94l2.03-1.58-2-3.46-2.39.96a7.19 7.19 0 0 0-1.62-.94L14.8 3.5h-4l-.37 2.54c-.58.24-1.12.56-1.62.94l-2.39-.96-2 3.46 2.03 1.58c-.04.31-.07.64-.07.94s.03.63.07.94l-2.03 1.58 2 3.46 2.39-.96c.5.38 1.04.7 1.62.94l.37 2.54h4l.36-2.54c.58-.24 1.13-.56 1.63-.94l2.38.96 2-3.46-2.03-1.58ZM12.8 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7Z"/></svg>
        </span>
    </header>

    <?php if ($msg): ?>
    <div class="cgi-configuration-alert is-<?= $msg_type ?>" role="alert">
        <span class="cgi-configuration-alert-icon" aria-hidden="true"><?= $msg_type === 'success' ? '&#10003;' : '!' ?></span>
        <span><?= htmlspecialchars($msg) ?></span>
        <button type="button" data-bs-dismiss="alert" aria-label="Dismiss notification">&times;</button>
    </div>
    <?php endif; ?>

    <form method="POST" class="cgi-configuration-panel" id="configuration-form">
        <section class="cgi-configuration-panel-head">
            <div>
                <span class="cgi-configuration-eyebrow">GRADE MULTIPLIERS</span>
                <h2>Suggested price settings</h2>
                <p>Adjust how each quality grade is valued against the current market rate.</p>
            </div>
            <div class="cgi-configuration-formula" aria-label="Suggested price formula">
                <span>PRICE FORMULA</span>
                <strong>Market rate <b>&times;</b> Multiplier <b>&times;</b> Weight</strong>
            </div>
        </section>

        <div class="cgi-configuration-panel-body">
            <div class="cgi-configuration-grid">
                <?php
                $grade_info = [
                    'extra_class' => ['label' => 'Extra Class', 'tone' => 'sage', 'description' => 'Premium-grade coffee with the highest quality classification.'],
                    'class_i' => ['label' => 'Class I', 'tone' => 'gold', 'description' => 'High-quality coffee meeting the primary grade standard.'],
                    'class_ii' => ['label' => 'Class II', 'tone' => 'bean', 'description' => 'Standard-grade coffee suitable for regular market pricing.'],
                ];
                foreach ($grade_info as $key => $info):
                    $current = $cfg_map[$key]['multiplier'] ?? 1.0;
                ?>
                <article class="cgi-configuration-card tone-<?= $info['tone'] ?>">
                    <div class="cgi-configuration-card-top">
                        <span class="cgi-configuration-grade-icon" aria-hidden="true">
                            <svg viewBox="0 0 24 24"><path d="M7.4 20.6c-2.7-1.4-4.3-4-4.3-7.1C3.1 7.8 8 3.2 15.6 3c1.7 5.3.4 10.4-3.5 13.5-1.3 1-2.9 1.7-4.7 2.1v2Zm-.7-4.2c3.7-.5 6.5-2.8 8.2-6.7-2.5 2.5-5.2 4.4-8.2 5.7v1Z"/></svg>
                        </span>
                        <span class="cgi-configuration-grade-label"><?= $info['label'] ?></span>
                    </div>
                    <h3><?= $info['label'] ?> multiplier</h3>
                    <p><?= $info['description'] ?></p>
                    <label for="<?= $key ?>">Multiplier value</label>
                    <div class="cgi-configuration-input-wrap">
                        <input type="number" id="<?= $key ?>" name="<?= $key ?>"
                               value="<?= number_format($current, 4) ?>"
                               step="0.0001" min="0" max="10" required
                               aria-describedby="<?= $key ?>-updated">
                        <span>&times; rate</span>
                    </div>
                    <div class="cgi-configuration-card-meta" id="<?= $key ?>-updated">
                        <span>Current: <strong data-value-for="<?= $key ?>"><?= number_format($current, 4) ?></strong></span>
                        <span>Updated <?= isset($cfg_map[$key]) ? htmlspecialchars(substr($cfg_map[$key]['updated_at'], 0, 16)) : 'N/A' ?></span>
                    </div>
                </article>
                <?php endforeach; ?>
            </div>
        </div>

        <footer class="cgi-configuration-panel-footer">
            <p><span aria-hidden="true">i</span> Changes apply to future transaction price calculations.</p>
            <button type="submit" id="save-configuration">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h12l4 4v14H3V3h2Zm0 2v14h14V8h-3V5H5Zm3 0v5h8V5H8Zm0 9h8v3H8v-3Z"/></svg>
                <span>Save Changes</span>
            </button>
        </footer>
    </form>
</main>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="<?= APP_BASE ?>/assets/js/navbar.js?v=3"></script>
<script src="<?= APP_BASE ?>/assets/js/configuration.js?v=1"></script>
</body>
</html>
