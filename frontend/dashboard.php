<?php
require_once __DIR__ . '/api.php';
api_require_auth();
$user = api_current_user();
$role = $user['role'];

// Load farmers list only for admin/officer (farmers cannot run inspections)
$farmers = [];
if ($role !== 'farmer') {
    $farmers_resp = api_request('GET', '/api/users/farmers');
    $farmers = api_response_list($farmers_resp);
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400;500;600;700&family=Work+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>Dashboard — CGI</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="assets/css/main.css">
<link rel="stylesheet" href="<?= APP_BASE ?>/assets/css/navbar.css?v=3">
<style>
/* ── Transaction modal overrides ─────────────────────────────────────────── */
#txn-modal .modal-dialog { max-width: 720px; }
#txn-modal .modal-body   { min-height: 480px; }

/* Stage panels */
.txn-stage { animation: fadeIn 0.2s ease-in-out; }

/* Live weight display */
#live-weight-value {
    font-size: 4rem;
    font-weight: 700;
    letter-spacing: -2px;
    line-height: 1;
}

/* Raw ADC labels must fit the existing weight panel. */
#live-weight-value.raw-sensor-reading {
    font-size: 1.5rem;
    letter-spacing: normal;
    line-height: 1.3;
    overflow-wrap: anywhere;
}

/* Capture preview images */
.capture-preview {
    max-height: 200px;
    border-radius: 0.5rem;
    border: 2px solid #dee2e6;
    object-fit: contain;
    width: 100%;
}

/* Receipt preview box */
#receipt-preview-box {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.85rem;
    background: #fff;
    border: 1px solid #dee2e6;
    border-radius: 0.5rem;
    padding: 1rem 1.25rem;
    white-space: pre;
    line-height: 1.5;
}

/* Step progress badges */
.step-badge {
    width: 36px; height: 36px;
    border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.85rem; font-weight: 600;
    background: #dee2e6; color: #6c757d;
    flex-shrink: 0;
}
.step-badge.active  { background: #0d6efd; color: #fff; }
.step-badge.done    { background: #198754; color: #fff; }

/* Hardware status cards */
.hw-card { min-height: 80px; }
.hw-status-icon { font-size: 1.5rem; }

/* Results image grid */
.result-img-thumb {
    width: 100%;
    max-height: 150px;
    object-fit: contain;
    border-radius: 0.4rem;
    border: 1px solid #dee2e6;
    cursor: pointer;
}
/* ── Development mode indicator ─────────────────────────────────────────── */
#dev-mode-banner {
    background: repeating-linear-gradient(
        -45deg,
        #fff3cd,
        #fff3cd 10px,
        #ffc107 10px,
        #ffc107 20px
    );
    color: #212529;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 4px 12px;
    text-align: center;
    border-bottom: 2px solid #fd7e14;
}

#btn-devmode-toggle {
    font-size: 0.78rem;
    padding: 4px 10px;
    border-radius: 20px;
    border: 2px solid #fd7e14;
}
#btn-devmode-toggle.dev-on {
    background: #fd7e14;
    color: #fff;
    border-color: #fd7e14;
}
</style>
<link rel="stylesheet" href="<?= APP_BASE ?>/assets/css/dashboard.css?v=1">
</head>
<body class="cgi-dashboard-body">

<?php include __DIR__ . '/components/navbar.php'; ?>

<main class="cgi-dashboard-page">

<?php if ($role === 'farmer'): ?>
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- FARMER VIEW: read-only list of own inspections (unchanged)             -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<?php
    $insp_resp = api_request('GET', '/api/inspection?limit=20');
    $farmer_inspections = api_response_list($insp_resp);
?>
<h2 class="fw-bold mb-3">My Inspections</h2>
<div class="card border-0 shadow-sm">
    <div class="card-body">
        <?php if (empty($farmer_inspections)): ?>
            <p class="text-muted">No inspections on record yet.</p>
        <?php else: ?>
        <div class="table-responsive">
            <table class="table table-hover align-middle">
                <thead class="table-dark"><tr>
                    <th>Txn No</th><th>Date</th><th>Weight</th><th>Grade</th><th>Over Thresh</th>
                </tr></thead>
                <tbody>
                <?php foreach ($farmer_inspections as $insp): ?>
                <tr>
                    <td><?= htmlspecialchars($insp['txn_number'] ?? '—') ?></td>
                    <td><?= substr($insp['created_at'], 0, 16) ?></td>
                    <td><?= number_format($insp['sample_weight_g'], 1) ?> g</td>
                    <td><?php
                        $g = $insp['grade'];
                        $badge = $g === 'extra_class' ? 'success' : ($g === 'class_i' ? 'warning' : 'danger');
                        echo "<span class='badge bg-{$badge}'>" . ucwords(str_replace('_',' ',$g)) . "</span>";
                    ?></td>
                    <td><?= $insp['over_threshold_flag'] ? '<span class="badge bg-danger">⚠ Yes</span>' : '<span class="text-muted">—</span>' ?></td>
                </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <?php endif; ?>
    </div>
</div>

<?php else: ?>
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- ADMIN / OFFICER VIEW: six-stage transaction workflow                   -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->

<!-- Dashboard overview; transaction IDs and behavior remain unchanged. -->
<section class="cgi-dashboard-panel">
<header class="cgi-dashboard-panel-head">
    <div class="cgi-dashboard-title">
        <span class="cgi-dashboard-title-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M18.7 3.5c-4.9-.7-9.3 1-11.8 4.4-2.7 3.7-2.1 8.2.2 11.3 3.8-1 7-3.1 9.2-6.3-1.7 1.5-3.6 2.7-5.8 3.5 2.4-2 4.4-4.5 5.9-7.4-2.8 3.1-5.7 5.4-8.8 7 .1-2.7 1.1-5.2 3.1-7.1 2.1-2.1 5-3.1 8-3.3V3.5Z"/></svg>
        </span>
        <div>
            <h1>Coffee Grade Identification</h1>
            <p>Automated quality assessment and transactional pricing</p>
        </div>
    </div>
    <div class="cgi-dashboard-head-actions">
        <button id="btn-devmode-toggle" class="btn btn-sm" title="Toggle Development Mode — bypasses hardware and external APIs">
            🛠 Dev Mode: OFF
        </button>
    </div>
</header>

<div class="cgi-dashboard-panel-body">
    <div class="cgi-dashboard-status-row">
        <span>System status</span>
        <div class="cgi-dashboard-clock">
            <strong id="live-clock">--:--:--</strong>
            <span id="live-date">Loading date...</span>
        </div>
    </div>

    <div class="cgi-device-grid" aria-label="Transaction hardware">
        <article class="cgi-device-card" id="overview-hw-card-camera">
            <span class="cgi-device-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 4 7.2 6H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3.2L15 4H9Zm3 13a4 4 0 1 1 0-8 4 4 0 0 1 0 8Z"/></svg></span>
            <div><small>Camera</small><strong id="overview-hw-camera"><i></i>Checked on start</strong><span>Image acquisition</span></div>
        </article>
        <article class="cgi-device-card" id="overview-hw-card-scale">
            <span class="cgi-device-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 3h14a2 2 0 0 1 2 2v16H3V5a2 2 0 0 1 2-2Zm7 3a5 5 0 0 0-5 5h10a5 5 0 0 0-5-5Zm0 2 2 2h-4l2-2Z"/></svg></span>
            <div><small>Weighing scale</small><strong id="overview-hw-scale"><i></i>Checked on start</strong><span>Sample weight acquisition</span></div>
        </article>
        <article class="cgi-device-card" id="overview-hw-card-printer">
            <span class="cgi-device-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 2h12v5H6V2Zm-2 6h16a2 2 0 0 1 2 2v7h-4v5H6v-5H2v-7a2 2 0 0 1 2-2Zm4 8v4h8v-4H8Zm10-5a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z"/></svg></span>
            <div><small>Printer</small><strong id="overview-hw-printer"><i></i>Checked on start</strong><span>Receipt output</span></div>
        </article>
    </div>

    <div class="cgi-dashboard-cta">
        <div>
            <span class="cgi-dashboard-eyebrow">COFFEE QUALITY ASSESSMENT</span>
            <h2>Ready for a new assessment?</h2>
            <p>Prepare the required green Robusta coffee bean sample to begin.</p>
            <button id="btn-start-txn" class="btn btn-success btn-lg px-4">
                <span>Start Transaction</span>
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 11h10.2l-3.6-3.6L13 6l6 6-6 6-1.4-1.4 3.6-3.6H5v-2Z"/>
                </svg>
            </button>
        </div>
    </div>

    <p class="cgi-hardware-note">Hardware readiness is verified before every transaction.</p>
</div>
</section>

<!-- ── Transaction Modal ──────────────────────────────────────────────────── -->
<div class="modal fade" id="txn-modal" tabindex="-1" aria-labelledby="txn-modal-label"
     data-bs-backdrop="static" data-bs-keyboard="false">
  <div class="modal-dialog modal-dialog-scrollable modal-lg">
    <div class="modal-content">

      <!-- Header -->
      <div class="modal-header bg-success text-white py-2">
        <div class="d-flex align-items-center gap-3 flex-grow-1 flex-wrap">
          <h5 class="modal-title fw-semibold mb-0" id="txn-modal-label">New Transaction</h5>
          <span id="txn-number-badge" class="badge bg-light text-dark fs-6 d-none"></span>
        </div>
        <button type="button" id="btn-close-modal" class="btn-close btn-close-white"
                aria-label="Close"></button>
      </div>

      <!-- Development mode banner (shown only when dev mode is active) -->
      <div id="dev-mode-banner" class="d-none">
        🛠 DEVELOPMENT MODE — Simulated data only. No hardware required. Records are NOT saved to the database.
      </div>

      <!-- Stage progress bar -->
      <div class="bg-light border-bottom px-3 py-2">
        <div class="d-flex align-items-center gap-2 flex-wrap" id="stage-progress">
          <?php
          $stages = ['Prepare','Weight','Capture','Analyze','Results','Receipt'];
          foreach ($stages as $i => $s):
            $n = $i + 1;
          ?>
          <div class="d-flex align-items-center gap-1">
            <span class="step-badge <?= $n === 1 ? 'active' : '' ?>"
                  id="step-badge-<?= $n ?>"><?= $n ?></span>
            <span class="small fw-semibold text-muted stage-label" id="stage-label-<?= $n ?>"><?= $s ?></span>
          </div>
          <?php if ($n < 6): ?>
          <div class="flex-grow-1" style="height:2px;background:#dee2e6;min-width:8px;max-width:40px;"></div>
          <?php endif; ?>
          <?php endforeach; ?>
        </div>
      </div>

      <!-- Modal body: stage panels -->
      <div class="modal-body p-4">

        <!-- ── STAGE 1: PREPARE ─────────────────────────────────────────── -->
        <div id="stage-1" class="txn-stage">
          <h6 class="fw-bold text-success mb-3">Stage 1 — Prepare</h6>

          <!-- Farmer selection -->
          <div class="mb-3">
            <label class="form-label fw-semibold">Farmer <span class="text-danger">*</span></label>
            <select id="farmer-select" class="form-select form-select-lg">
              <option value="">— Select farmer —</option>
              <?php foreach ($farmers as $f): ?>
              <option value="<?= $f['id'] ?>"><?= htmlspecialchars($f['name']) ?></option>
              <?php endforeach; ?>
            </select>
          </div>

          <!-- Hardware status -->
          <p class="fw-semibold mb-2">Hardware Readiness</p>
          <div class="row g-2 mb-3" id="hw-status-row">
            <div class="col-4">
              <div class="card hw-card border text-center p-2">
                <div class="hw-status-icon" id="hw-icon-camera">⏳</div>
                <div class="small fw-semibold">Camera</div>
                <div class="small" id="hw-label-camera">Checking…</div>
              </div>
            </div>
            <div class="col-4">
              <div class="card hw-card border text-center p-2">
                <div class="hw-status-icon" id="hw-icon-scale">⏳</div>
                <div class="small fw-semibold">Scale</div>
                <div class="small" id="hw-label-scale">Checking…</div>
              </div>
            </div>
            <div class="col-4">
              <div class="card hw-card border text-center p-2">
                <div class="hw-status-icon" id="hw-icon-printer">⏳</div>
                <div class="small fw-semibold">Printer</div>
                <div class="small" id="hw-label-printer">Checking…</div>
              </div>
            </div>
          </div>
          <button class="btn btn-outline-secondary btn-sm mb-3" id="btn-recheck-hw">↻ Re-check Hardware</button>

          <!-- Preparation checklist -->
          <p class="fw-semibold mb-2">Preparation Checklist</p>
          <div class="list-group mb-3" id="prep-checklist">
            <label class="list-group-item d-flex gap-2">
              <input class="form-check-input prep-check flex-shrink-0" type="checkbox" id="chk-sample">
              <span>Coffee bean sample is ready for inspection</span>
            </label>
            <label class="list-group-item d-flex gap-2">
              <input class="form-check-input prep-check flex-shrink-0" type="checkbox" id="chk-tray">
              <span>Inspection tray is clean</span>
            </label>
            <label class="list-group-item d-flex gap-2">
              <input class="form-check-input prep-check flex-shrink-0" type="checkbox" id="chk-layer">
              <span>Beans are distributed in a single layer without overlapping</span>
            </label>
            <label class="list-group-item d-flex gap-2">
              <input class="form-check-input prep-check flex-shrink-0" type="checkbox" id="chk-camera">
              <span>Camera and inspection area are properly positioned</span>
            </label>
          </div>

          <div id="stage1-error" class="d-none" aria-hidden="true"></div>
          <button id="btn-to-weight" class="btn btn-success btn-lg w-100" disabled>
            Continue to Weight →
          </button>
        </div><!-- /stage-1 -->

        <!-- ── STAGE 2: WEIGHT ──────────────────────────────────────────── -->
        <div id="stage-2" class="txn-stage d-none">
          <h6 class="fw-bold text-success mb-3">Stage 2 — Weight</h6>
          <p class="text-muted">Place the 350 g coffee sample on the weighing platform.
             Accepted range: <strong>340–360 g</strong>.</p>

          <div class="text-center my-4">
            <div id="live-weight-value" class="text-secondary">— g</div>
            <div id="weight-raw-value" class="small text-muted mt-2"></div>
            <div id="weight-status-badge" class="mt-2"></div>
            <div id="weight-range-bypass" class="small text-warning mt-2"></div>
            <button type="button" id="btn-tare-scale" class="btn btn-outline-secondary btn-lg mt-3">Tare / Zero</button>
            <button type="button" id="btn-calibrate-scale" class="btn btn-outline-secondary btn-lg mt-3">Calibrate scale</button>
            <div class="small text-muted mt-2">Remove the beans and leave the empty tray before taring.</div>
          </div>

          <div id="stage2-error" class="d-none" aria-hidden="true"></div>

          <div class="d-flex gap-2 mt-3">
            <button class="btn btn-outline-secondary" id="btn-back-to-prepare">← Back</button>
            <button class="btn btn-success btn-lg flex-fill" id="btn-to-capture" disabled>
              Continue to Capture →
            </button>
          </div>
        </div><!-- /stage-2 -->

        <!-- ── STAGE 3: CAPTURE ─────────────────────────────────────────── -->
        <div id="stage-3" class="txn-stage d-none">
          <h6 class="fw-bold text-success mb-3">Stage 3 — Capture</h6>

          <div class="card border mb-3 p-3">
            <div id="camera-live-status" class="small text-muted mb-2" role="status" aria-live="polite">Connecting to camera…</div>
            <img id="camera-live-preview" class="capture-preview d-none" style="max-height:180px;object-fit:contain" alt="Live camera preview">
          </div>

          <!-- View A -->
          <div class="card border mb-3 p-3" id="view-a-section">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <span class="fw-semibold">View A</span>
              <span id="view-a-badge" class="badge bg-secondary">Pending</span>
            </div>
            <div id="view-a-countdown" class="text-center d-none">
              <div class="display-1 fw-bold text-primary" id="view-a-count"></div>
              <p class="text-muted">Get ready…</p>
            </div>
            <img id="view-a-preview" class="capture-preview d-none" alt="View A preview">
            <div class="d-flex gap-2 mt-2">
              <button id="btn-capture-a" class="btn btn-primary flex-fill">📷 Capture View A</button>
              <button id="btn-retake-a" class="btn btn-outline-secondary d-none">↺ Retake</button>
              <button id="btn-accept-a" class="btn btn-success d-none">✓ Accept View A</button>
            </div>
          </div>

          <!-- Reorientation instruction (shown after View A accepted) -->
          <div id="reorient-instruction" class="cgi-dashboard-instruction d-none mb-3">
            <strong>Flip the beans!</strong> Manually reorient the coffee beans to expose
            their opposite sides, then capture View B.
          </div>

          <!-- View B -->
          <div class="card border mb-3 p-3" id="view-b-section">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <span class="fw-semibold">View B</span>
              <span id="view-b-badge" class="badge bg-secondary">Pending</span>
            </div>
            <div id="view-b-countdown" class="text-center d-none">
              <div class="display-1 fw-bold text-primary" id="view-b-count"></div>
              <p class="text-muted">Get ready…</p>
            </div>
            <img id="view-b-preview" class="capture-preview d-none" alt="View B preview">
            <div class="d-flex gap-2 mt-2">
              <button id="btn-capture-b" class="btn btn-primary flex-fill" disabled>📷 Capture View B</button>
              <button id="btn-retake-b" class="btn btn-outline-secondary d-none">↺ Retake</button>
              <button id="btn-accept-b" class="btn btn-success d-none">✓ Accept View B</button>
            </div>
          </div>

          <div id="stage3-error" class="d-none" aria-hidden="true"></div>

          <div class="d-flex gap-2">
            <button class="btn btn-outline-secondary" id="btn-back-to-weight">← Back</button>
            <button class="btn btn-success btn-lg flex-fill" id="btn-to-analyze" disabled>
              Continue to Analyze →
            </button>
          </div>
        </div><!-- /stage-3 -->

        <!-- ── STAGE 4: ANALYZE ─────────────────────────────────────────── -->
        <div id="stage-4" class="txn-stage d-none">
          <h6 class="fw-bold text-success mb-3">Stage 4 — Analyze</h6>
          <p class="text-muted mb-3">Review the captured images below, then start the YOLOv8 analysis.</p>

          <!-- Image review row -->
          <div class="row g-2 mb-3">
            <div class="col-6">
              <p class="small fw-semibold mb-1">View A</p>
              <img id="analyze-view-a" class="capture-preview" alt="View A">
            </div>
            <div class="col-6">
              <p class="small fw-semibold mb-1">View B</p>
              <img id="analyze-view-b" class="capture-preview" alt="View B">
            </div>
          </div>

          <!-- Analysis progress -->
          <div id="analysis-progress" class="text-center d-none my-3">
            <div class="spinner-border text-success" role="status">
              <span class="visually-hidden">Analyzing…</span>
            </div>
            <p class="text-muted mt-2" id="analysis-progress-label">Running YOLOv8 analysis — please wait…</p>
          </div>

          <div id="stage4-error" class="d-none" aria-hidden="true"></div>

          <div class="d-flex gap-2">
            <button class="btn btn-outline-secondary" id="btn-back-to-capture">← Back</button>
            <button class="btn btn-success btn-lg flex-fill" id="btn-start-analysis">
              🔬 Start Analysis
            </button>
          </div>
        </div><!-- /stage-4 -->

        <!-- ── STAGE 5: RESULTS ─────────────────────────────────────────── -->
        <div id="stage-5" class="txn-stage d-none">
          <h6 class="fw-bold text-success mb-3">Stage 5 — Results</h6>

          <!-- Transaction info -->
          <div class="card border-0 bg-light mb-3 p-3">
            <div class="row g-1 small">
              <div class="col-6"><strong>Txn No:</strong> <span id="res-txn-number"></span></div>
              <div class="col-6"><strong>Date:</strong> <span id="res-date"></span></div>
              <div class="col-6"><strong>Farmer:</strong> <span id="res-farmer"></span></div>
              <div class="col-6"><strong>Weight:</strong> <span id="res-weight"></span></div>
            </div>
          </div>

          <!-- Grade + threshold -->
          <div class="d-flex align-items-center gap-2 mb-3">
            <span class="badge fs-5 px-3 py-2" id="res-grade-badge">—</span>
            <span id="res-threshold-badge" class="badge bg-danger d-none">⚠ Over Threshold</span>
          </div>

          <!-- Defect table -->
          <div class="table-responsive mb-3">
            <table class="table table-sm table-bordered">
              <thead class="table-dark">
                <tr><th>Defect</th><th>Count</th><th>%</th><th>Class</th><th>Over?</th></tr>
              </thead>
              <tbody id="res-defect-tbody"></tbody>
            </table>
          </div>

          <!-- Images: original + annotated for A and B -->
          <p class="fw-semibold mb-2">Captured Images</p>
          <div class="row g-2 mb-3">
            <div class="col-6 col-md-3">
              <p class="small text-muted mb-1">View A (original)</p>
              <a id="res-img-a-link" href="#" target="_blank">
                <img id="res-img-a" class="result-img-thumb" alt="View A original">
              </a>
            </div>
            <div class="col-6 col-md-3">
              <p class="small text-muted mb-1">View A (annotated)</p>
              <a id="res-img-a-ann-link" href="#" target="_blank">
                <img id="res-img-a-ann" class="result-img-thumb" alt="View A annotated">
              </a>
            </div>
            <div class="col-6 col-md-3">
              <p class="small text-muted mb-1">View B (original)</p>
              <a id="res-img-b-link" href="#" target="_blank">
                <img id="res-img-b" class="result-img-thumb" alt="View B original">
              </a>
            </div>
            <div class="col-6 col-md-3">
              <p class="small text-muted mb-1">View B (annotated)</p>
              <a id="res-img-b-ann-link" href="#" target="_blank">
                <img id="res-img-b-ann" class="result-img-thumb" alt="View B annotated">
              </a>
            </div>
          </div>

          <!-- Pricing -->
          <div class="card border-0 bg-light p-3 mb-3">
            <p class="fw-semibold mb-2">Suggested Pricing</p>
            <div class="row g-1 small">
              <div class="col-6"><strong>Commodity Price:</strong> <span id="res-market-rate"></span></div>
              <div class="col-6"><strong>Grade Multiplier:</strong> <span id="res-multiplier"></span></div>
              <div class="col-6"><strong>Suggested Price/kg:</strong> <span id="res-price-per-kg"></span></div>
              <div class="col-6"><strong>Suggested Sample Value:</strong> <span id="res-total-price"></span></div>
              <div class="col-12 text-muted" id="res-price-source"></div>
            </div>
          </div>

          <button class="btn btn-success btn-lg w-100" id="btn-to-receipt">
            Continue to Receipt →
          </button>
        </div><!-- /stage-5 -->

        <!-- ── STAGE 6: RECEIPT ─────────────────────────────────────────── -->
        <div id="stage-6" class="txn-stage d-none">
          <h6 class="fw-bold text-success mb-3">Stage 6 — Receipt</h6>
          <p class="text-muted mb-3">Review the receipt and print, then complete the transaction.</p>

          <!-- Receipt preview -->
          <div id="receipt-preview-box" class="mb-3"></div>

          <!-- Print controls -->
          <div class="d-flex align-items-center gap-2 mb-3 flex-wrap">
            <button class="btn btn-primary" id="btn-print-receipt">🖨 Print Receipt</button>
            <span id="print-status-badge"></span>
          </div>

          <div id="stage6-error" class="d-none" aria-hidden="true"></div>

          <!-- Complete transaction — always enabled once Stage 6 is reached -->
          <button class="btn btn-success btn-lg w-100" id="btn-complete-txn">
            ✔ Complete Transaction
          </button>
        </div><!-- /stage-6 -->

      </div><!-- /modal-body -->
    </div><!-- /modal-content -->
  </div><!-- /modal-dialog -->
</div><!-- /txn-modal -->

<?php endif; ?>
</main><!-- /cgi-dashboard-page -->

<div class="cgi-dashboard-toast-region" aria-live="assertive" aria-atomic="true">
    <div class="cgi-dashboard-toast" id="dashboard-toast" role="alert" hidden>
        <span class="cgi-dashboard-toast-icon" id="dashboard-toast-icon" aria-hidden="true"></span>
        <span class="cgi-dashboard-toast-message" id="dashboard-toast-message"></span>
        <button type="button" class="cgi-dashboard-toast-close" id="dashboard-toast-close"
                aria-label="Dismiss notification">&times;</button>
    </div>
</div>

<div class="cgi-dashboard-confirm" id="dashboard-confirm" hidden>
    <section class="cgi-dashboard-confirm-dialog" role="dialog" aria-modal="true"
             aria-labelledby="dashboard-confirm-title"
             aria-describedby="dashboard-confirm-message">
        <span class="cgi-dashboard-confirm-icon" aria-hidden="true">!</span>
        <h2 id="dashboard-confirm-title">Confirm action</h2>
        <p id="dashboard-confirm-message"></p>
        <div class="cgi-dashboard-confirm-actions">
            <button type="button" class="btn cgi-confirm-cancel" id="dashboard-confirm-cancel">
                Keep Transaction
            </button>
            <button type="button" class="btn cgi-confirm-submit" id="dashboard-confirm-submit">
                Confirm
            </button>
        </div>
    </section>
</div>

<?php api_inject_jwt_script(); ?>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="<?= APP_BASE ?>/assets/js/navbar.js?v=3"></script>
<script src="<?= APP_BASE ?>/assets/js/dashboard.js?v=9"
        data-app-base="<?= htmlspecialchars(APP_BASE, ENT_QUOTES, 'UTF-8') ?>"
        data-api-base=""></script>
<script src="<?= htmlspecialchars(APP_BASE, ENT_QUOTES, 'UTF-8') ?>/assets/js/api.js"></script>
</body>
</html>
