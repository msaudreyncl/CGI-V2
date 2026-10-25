/**
 * CGI dashboard interactions and six-stage transaction workflow.
 * API, database, and hardware behavior is unchanged from dashboard.php.
 */
(() => {
    const dashboardScript = document.currentScript;
    window.CGI_BASE = dashboardScript?.dataset.appBase || "";
    window.CGI_API_BASE = dashboardScript?.dataset.apiBase || "";

    let dashboardToastTimer = null;
    let dashboardConfirmResolve = null;

    const toastPresentations = {
        success: { icon: "✓", label: "Success" },
        danger: { icon: "!", label: "Error" },
        warning: { icon: "!", label: "Warning" },
        info: { icon: "i", label: "Information" }
    };

    function dismissDashboardToast() {
        const toast = document.getElementById("dashboard-toast");
        if (!toast || toast.hidden) return;
        window.clearTimeout(dashboardToastTimer);
        toast.classList.add("is-hiding");
        window.setTimeout(() => {
            toast.hidden = true;
            toast.classList.remove("is-visible", "is-hiding");
        }, 300);
    }

    function showDashboardToast(message, type = "info", source = "") {
        const toast = document.getElementById("dashboard-toast");
        const text = document.getElementById("dashboard-toast-message");
        const icon = document.getElementById("dashboard-toast-icon");
        if (!toast || !text || !icon) return;

        const toastType = toastPresentations[type] ? type : "info";
        const presentation = toastPresentations[toastType];
        window.clearTimeout(dashboardToastTimer);

        toast.className = `cgi-dashboard-toast cgi-dashboard-toast-${toastType}`;
        toast.dataset.source = source;
        toast.setAttribute("aria-label", presentation.label);
        text.textContent = message;
        icon.textContent = presentation.icon;
        toast.hidden = false;
        window.requestAnimationFrame(() => toast.classList.add("is-visible"));

        dashboardToastTimer = window.setTimeout(dismissDashboardToast, 5000);
    }

    function requestDashboardConfirmation({ title, message, confirmLabel = "Confirm" }) {
        const overlay = document.getElementById("dashboard-confirm");
        if (!overlay) return Promise.resolve(false);

        document.getElementById("dashboard-confirm-title").textContent = title;
        document.getElementById("dashboard-confirm-message").textContent = message;
        document.getElementById("dashboard-confirm-submit").textContent = confirmLabel;
        overlay.hidden = false;
        window.requestAnimationFrame(() => overlay.classList.add("is-visible"));
        document.getElementById("dashboard-confirm-cancel").focus();

        return new Promise(resolve => {
            dashboardConfirmResolve = resolve;
        });
    }

    function finishDashboardConfirmation(confirmed) {
        if (!dashboardConfirmResolve) return;
        const resolve = dashboardConfirmResolve;
        const overlay = document.getElementById("dashboard-confirm");
        dashboardConfirmResolve = null;
        overlay.classList.remove("is-visible");
        window.setTimeout(() => { overlay.hidden = true; }, 200);
        resolve(confirmed);
    }

    function initializePopupUi() {
        document.getElementById("dashboard-toast-close")
            ?.addEventListener("click", dismissDashboardToast);
        document.getElementById("dashboard-confirm-cancel")
            ?.addEventListener("click", () => finishDashboardConfirmation(false));
        document.getElementById("dashboard-confirm-submit")
            ?.addEventListener("click", () => finishDashboardConfirmation(true));
        document.addEventListener("keydown", event => {
            if (event.key === "Escape" && dashboardConfirmResolve) {
                finishDashboardConfirmation(false);
            }
        });
    }

    function initializeClock() {
        const clock = document.getElementById("live-clock");
        const date = document.getElementById("live-date");
        if (!clock || !date) return;

        const updateDateTime = () => {
            const now = new Date();
            clock.textContent = now.toLocaleTimeString("en-PH", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: true
            });
            date.textContent = now.toLocaleDateString("en-PH", {
                weekday: "long",
                month: "long",
                day: "numeric",
                year: "numeric"
            });
        };

        updateDateTime();
        window.setInterval(updateDateTime, 1000);
    }

    function initializeTransactionWorkflow() {
        if (!document.getElementById("btn-start-txn")) return;

        // ─────────────────────────────────────────────────────────────────────────────
        // CGI Six-Stage Transaction Workflow
        // ─────────────────────────────────────────────────────────────────────────────
        const API = window.CGI_API;
        
        // ── Workflow state ────────────────────────────────────────────────────────────
        let pendingId        = null;   // pending_transactions.id  (null in dev mode)
        let txnNumber        = null;   // CGI-YYYYMMDD-XXXXXX
        let txnId            = null;   // finalized transactions.id (null in dev mode)
        let currentWeight    = null;   // validated weight in grams
        let imageAb64        = null;   // accepted View A base64
        let imageBb64        = null;   // accepted View B base64
        let currentAnalysis  = null;   // DualInspectionOut (real) or DEV mock object
        let farmerName       = null;   // selected farmer display name
        
        let weightPollGeneration = 0;
        let weightRequestBusy = false;
        let weightSaving = false;
        let sensorTestMode = false;
        let tareBusy = false;
        let weightReadAt = 0;
        let weightMeasuredAt = null;
        let acceptedA = false, acceptedB = false;
        let captureStage = false;
        let captureBusy = false;
        let stageGeneration = 0;
        let previewGeneration = 0;
        let cameraPreviewTimer = null;
        let cameraPreviewRequest = null;
        let weightPollTimer  = null;   // setInterval handle for weight polling
        let analysisRunning  = false;  // guard against duplicate YOLOv8 requests
        
        // Hardware status cache
        let hwCamera  = 'checking';
        let hwScale   = 'checking';
        let hwPrinter = 'checking';
        
        // ── Development mode ─────────────────────────────────────────────────────────
        // Persisted across page reloads in localStorage. Never changes during an active
        // transaction (guarded by the toggle handler below).
        let devMode = localStorage.getItem('cgi_dev_mode') === '1';
        let txnActive = false;  // true while the modal is open with a started transaction
        
        function _applyDevModeUI() {
            const btn    = document.getElementById('btn-devmode-toggle');
            const banner = document.getElementById('dev-mode-banner');
            if (devMode) {
                btn.textContent = '🛠 Dev Mode: ON';
                btn.classList.add('dev-on');
                banner.classList.remove('d-none');
            } else {
                btn.textContent = '🛠 Dev Mode: OFF';
                btn.classList.remove('dev-on');
                banner.classList.add('d-none');
            }
        }
        
        document.getElementById('btn-devmode-toggle').addEventListener('click', () => {
            if (txnActive) {
                showDashboardToast(
                    'Cannot switch Development Mode during an active transaction.',
                    'warning'
                );
                return;
            }
            devMode = !devMode;
            localStorage.setItem('cgi_dev_mode', devMode ? '1' : '0');
            _applyDevModeUI();
        });
        
        // Apply on page load
        _applyDevModeUI();
        
        // ── DEV: Simulation helpers ───────────────────────────────────────────────────
        // All simulation logic is contained in this namespace.
        // Real workflow functions check `devMode` and call the appropriate branch.
        
        const DEV = {
            // Placeholder 1×1 orange SVG encoded as base64 JPEG-like data URI base.
            // A simple coloured canvas PNG rendered as base64 so the <img> tag loads.
            _makePlaceholderImg(label) {
                // Inline SVG → base64 (no external request, no canvas API needed)
                const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480">
                    <rect width="640" height="480" fill="#fff3cd"/>
                    <rect x="10" y="10" width="620" height="460" fill="none" stroke="#fd7e14" stroke-width="4" stroke-dasharray="12,6"/>
                    <text x="320" y="200" font-family="monospace" font-size="48" fill="#fd7e14" text-anchor="middle">📷</text>
                    <text x="320" y="270" font-family="monospace" font-size="28" fill="#6c757d" text-anchor="middle">[DEV] ${label}</text>
                    <text x="320" y="310" font-family="monospace" font-size="18" fill="#adb5bd" text-anchor="middle">Simulated Image — Not Real Capture</text>
                </svg>`;
                return 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)));
            },
        

        
            // Generate a DEV transaction number (no DB call)
            makeTxnNumber() {
                const now = new Date();
                const date = now.toISOString().slice(0,10).replace(/-/g,'');
                const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
                let suffix = '';
                for (let i = 0; i < 6; i++) suffix += chars[Math.floor(Math.random() * chars.length)];
                return 'DEV-' + date + '-' + suffix;
            },
        
            // Fixed mock detection/grading/pricing result (clearly labelled)
            makeMockAnalysis(txnNum, weight, farmer) {
                const now = new Date().toISOString();
                return {
                    // Inspection fields
                    id:                   0,
                    txn_number:           txnNum,
                    farmer_id:            0,
                    officer_id:           0,
                    sample_weight_g:      weight,
                    total_beans_detected: 280,
                    image_path:           null,
                    image_path_b:         null,
                    image_path_annotated_a: null,
                    image_path_annotated_b: null,
                    grade:                'class_i',
                    over_threshold_flag:  false,
                    notes:                null,
                    created_at:           now,
                    defect_results: [
                        { defect_type:'black_bean',     bean_count:12, defect_percentage:4.29, assigned_class:'class_i',   over_threshold:false },
                        { defect_type:'moldy_infested', bean_count:9,  defect_percentage:3.21, assigned_class:'extra_class', over_threshold:false },
                        { defect_type:'immature',       bean_count:5,  defect_percentage:1.79, assigned_class:'extra_class', over_threshold:false },
                        { defect_type:'broken',         bean_count:8,  defect_percentage:2.86, assigned_class:'extra_class', over_threshold:false },
                        { defect_type:'dried_cherry',   bean_count:2,  defect_percentage:0.71, assigned_class:'class_i',   over_threshold:false },
                        { defect_type:'foreign_matter', bean_count:1,  defect_percentage:0.36, assigned_class:'extra_class', over_threshold:false },
                    ],
                    // Pricing fields
                    txn_id:            0,
                    price_per_kg:      255.00,
                    market_rate_per_kg: 300.00,
                    multiplier:        0.8500,
                    total_price:       (255.00 * weight / 1000),
                    currency:          'PHP',
                    price_source:      'dev-mock',
                };
            },
        };
        
        // ── Bootstrap modal ───────────────────────────────────────────────────────────
        const txnModalEl = document.getElementById('txn-modal');
        const txnModal   = new bootstrap.Modal(txnModalEl);
        
        // Clear all timers and state when modal is dismissed
        txnModalEl.addEventListener('hidden.bs.modal', () => {
            captureStage = false;
            stageGeneration++;
            _stopCameraPreview();
            _stopWeightPoll();
            txnActive       = false;
            pendingId       = null;
            txnNumber       = null;
            txnId           = null;
            currentWeight   = null;
            imageAb64       = null;
            imageBb64       = null;
            currentAnalysis = null;
            analysisRunning = false;
            // Restore modal banner visibility to match current devMode state
            _applyDevModeUI();
        });
        
        document.getElementById('btn-start-txn').addEventListener('click', () => {
            _resetModal();
            txnModal.show();
            _checkHardware();
        });
        
        document.getElementById('btn-close-modal').addEventListener('click', async () => {
            const confirmed = await requestDashboardConfirmation({
                title: 'Cancel transaction?',
                message: 'Your current transaction progress will be discarded.',
                confirmLabel: 'Cancel Transaction'
            });
            if (confirmed) txnModal.hide();
        });
        
        // ── Helpers ───────────────────────────────────────────────────────────────────
        function _setStage(n) {
            stageGeneration++;
            captureStage = n === 3;
            _stopCameraPreview();
            document.querySelectorAll('.txn-stage').forEach(el => el.classList.add('d-none'));
            document.getElementById('stage-' + n).classList.remove('d-none');
            for (let i = 1; i <= 6; i++) {
                const badge = document.getElementById('step-badge-' + i);
                if (i < n)        badge.className = 'step-badge done';
                else if (i === n) badge.className = 'step-badge active';
                else              badge.className = 'step-badge';
            }
            if (captureStage) _startCameraPreview();
        }
        
        function _showError(elId, msg) {
            const el = document.getElementById(elId);
            if (el) el.textContent = msg;
            showDashboardToast(msg, 'danger', elId);
        }
        
        function _hideError(elId) {
            const el = document.getElementById(elId);
            if (el) el.textContent = '';
            const toast = document.getElementById('dashboard-toast');
            if (toast?.dataset.source === elId) dismissDashboardToast();
        }
        
        function _gradeClass(g) {
            return g === 'extra_class' ? 'success' : g === 'class_i' ? 'warning' : 'danger';
        }
        
        function _gradeLabel(g) {
            return (g || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        }
        
        function _phpFormat(n) {
            return 'PHP ' + parseFloat(n).toLocaleString('en-PH', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        
        function _staticUrl(relPath) {
            if (/^(https?:|data:|blob:)/i.test(relPath)) return relPath;
            return (window.CGI_API_BASE || '').replace(/\/$/, '') +
                '/static/' + relPath.replace(/^\/?static\//, '');
        }
        
        function _resetModal() {
            _setStage(1);
            document.getElementById('txn-number-badge').classList.add('d-none');
            document.getElementById('btn-to-weight').disabled = true;
            document.getElementById('btn-to-capture').disabled = true;
            document.getElementById('btn-to-analyze').disabled = true;
            document.getElementById('btn-start-analysis').disabled = false;
            document.getElementById('analysis-progress').classList.add('d-none');
            document.querySelectorAll('.prep-check').forEach(c => c.checked = false);
            ['a','b'].forEach(v => {
                document.getElementById('view-' + v + '-preview').classList.add('d-none');
                document.getElementById('view-' + v + '-badge').className = 'badge bg-secondary';
                document.getElementById('view-' + v + '-badge').textContent = 'Pending';
                document.getElementById('btn-retake-' + v).classList.add('d-none');
                document.getElementById('btn-accept-' + v).classList.add('d-none');
                document.getElementById('view-' + v + '-countdown').classList.add('d-none');
            });
            acceptedA = acceptedB = false;
            document.getElementById('btn-capture-a').disabled = false;
            document.getElementById('btn-capture-b').disabled = true;
            document.getElementById('reorient-instruction').classList.add('d-none');
            ['camera','scale','printer'].forEach(k => {
                document.getElementById('hw-icon-' + k).textContent  = '⏳';
                document.getElementById('hw-label-' + k).textContent = 'Checking…';
            });
            ['stage1-error','stage2-error','stage3-error','stage4-error','stage6-error'].forEach(_hideError);
            document.getElementById('print-status-badge').innerHTML = '';
            hwCamera = hwScale = hwPrinter = 'checking';
            pendingId = txnNumber = txnId = null;
            currentWeight = imageAb64 = imageBb64 = currentAnalysis = null;
            analysisRunning = false;
            _stopWeightPoll();
            // Keep banner in sync
            _applyDevModeUI();
        }
        
        // ── Stage 1 — Prepare ─────────────────────────────────────────────────────────
        
        async function _checkHardware() {
            hwCamera = hwScale = 'checking';
            _validateStage1();
            ['camera','scale','printer'].forEach(k => {
                document.getElementById('hw-icon-' + k).textContent  = '⏳';
                document.getElementById('hw-label-' + k).textContent = 'Checking…';
            });
        
            if (devMode) {
                // Simulate all hardware as ready immediately
                hwCamera = hwScale = hwPrinter = 'ready';
                _updateHwCard('camera',  'ready');
                _updateHwCard('scale',   'ready');
                _updateHwCard('printer', 'ready');
                _validateStage1();
                return;
            }
        
            try {
                const resp = await API.get('/api/hardware/status');
                if (!resp.ok) throw new Error('Hardware check failed');
                const data = await resp.json();
                sensorTestMode = data.sensor_test_mode === true;
                hwCamera  = data.camera;
                hwScale   = data.scale;
                hwPrinter = data.printer;
                _updateHwCard('camera',  data.camera, data.details?.camera);
                _updateHwCard('scale',   data.scale, data.details?.scale);
                _updateHwCard('printer', data.printer);
            } catch (e) {
                hwCamera = hwScale = 'error';
                hwPrinter = 'warning';
                _updateHwCard('camera',  'error', e.message);
                _updateHwCard('scale',   'error', e.message);
                _updateHwCard('printer', 'warning');
            }
            _validateStage1();
        }
        
        function _updateHwCard(key, st, detail = '') {
            const icons  = { ready: '✅', error: '❌', warning: '⚠️', checking: '⏳' };
            const labels = {
                ready:   devMode && key !== 'printer' ? 'Ready (Simulated)' : 'Ready',
                error:   'Error',
                warning: 'Unavailable (non-blocking)',
                checking:'Checking…',
            };
            document.getElementById('hw-icon-' + key).textContent  = icons[st]  || '❓';
            const label = document.getElementById('hw-label-' + key);
            label.textContent = st === 'error' && detail ? 'Error: ' + detail : (labels[st] || st);
            label.title = detail || '';
        
            const overviewLabel = document.getElementById('overview-hw-' + key);
            const overviewCard = document.getElementById('overview-hw-card-' + key);
            if (overviewLabel && overviewCard) {
                overviewLabel.lastChild.textContent = labels[st] || st;
                overviewCard.dataset.status = st;
            }
        }
        
        function _validateStage1() {
            const farmerId   = document.getElementById('farmer-select').value;
            const allChecked = document.querySelectorAll('.prep-check:not(:checked)').length === 0;
            const hwOk       = (hwCamera === 'ready') && (hwScale === 'ready');
            document.getElementById('btn-to-weight').disabled = !(farmerId && allChecked && hwOk);
        }
        
        document.getElementById('farmer-select').addEventListener('change', _validateStage1);
        document.querySelectorAll('.prep-check').forEach(cb => cb.addEventListener('change', _validateStage1));
        document.getElementById('btn-recheck-hw').addEventListener('click', _checkHardware);
        
        async function _resolveFarmerProfile(userId) {
            const path = '/api/users/' + userId + '/farmer';
            let resp = await API.get(path);
            if (resp.status === 404) {
                // Registration creates a user account; create its optional profile
                // through the existing endpoint when starting its first transaction.
                resp = await API.post(path, { user_id: userId });
                if (resp.status === 409) resp = await API.get(path);
            }
            const profile = await resp.json();
            if (!resp.ok) throw new Error(profile.detail || 'Could not load the farmer profile.');
            if (!Number.isInteger(profile.id) || profile.id <= 0 || profile.user_id !== userId)
                throw new Error('Invalid farmer profile returned. Refresh the page and try again.');
            return profile.id;
        }

        document.getElementById('btn-to-weight').addEventListener('click', async () => {
            const farmerUserId = Number(document.getElementById('farmer-select').value);
            const farmerOpt = document.querySelector('#farmer-select option:checked');
            farmerName = farmerOpt ? farmerOpt.textContent.trim() : '';
        
            _hideError('stage1-error');
            document.getElementById('btn-to-weight').disabled = true;
        
            if (devMode) {
                // Generate a DEV transaction number without a DB call
                txnNumber = DEV.makeTxnNumber();
                pendingId = null;  // no DB row in dev mode
                txnActive = true;
                document.getElementById('txn-number-badge').textContent = txnNumber;
                document.getElementById('txn-number-badge').classList.remove('d-none');
                document.getElementById('txn-modal-label').textContent = '[DEV] ' + txnNumber;
                _setStage(2);
                _startWeightPoll();
                return;
            }
        
            // Production: call the real init endpoint
            try {
                const farmerId = await _resolveFarmerProfile(farmerUserId);
                const resp = await API.post('/api/transaction/init', { farmer_id: farmerId });
                if (!resp.ok) {
                    const err = await resp.json();
                    _showError('stage1-error', err.detail || 'Failed to initialize transaction.');
                    document.getElementById('btn-to-weight').disabled = false;
                    return;
                }
                const data = await resp.json();
                pendingId = data.pending_id;
                txnNumber = data.txn_number;
                txnActive = true;
                document.getElementById('txn-number-badge').textContent = txnNumber;
                document.getElementById('txn-number-badge').classList.remove('d-none');
                document.getElementById('txn-modal-label').textContent = 'Transaction: ' + txnNumber;
            } catch (e) {
                _showError('stage1-error', 'Unable to start transaction: ' + e.message);
                document.getElementById('btn-to-weight').disabled = false;
                return;
            }
        
            _setStage(2);
            _startWeightPoll();
        });
        
        // ── Stage 2 — Weight ──────────────────────────────────────────────────────────
        
        async function _invalidateAcceptedWeight() {
            if (devMode || !pendingId) return;
            const resp = await API.del('/api/transaction/' + pendingId + '/weight');
            if (!resp.ok) throw new Error((await resp.json()).detail || 'Unable to reset sample weight');
            imageAb64 = imageBb64 = currentAnalysis = null;
            acceptedA = acceptedB = false;
        }

        function _startWeightPoll() {
            _stopWeightPoll();
            currentWeight = null;
            document.getElementById('btn-to-capture').disabled = !sensorTestMode;
            weightReadAt = Date.now();
            document.getElementById('live-weight-value').textContent = '— g';
            document.getElementById('weight-status-badge').textContent = 'Stabilizing…';
            weightPollTimer = setInterval(() => {
                if (Date.now() - weightReadAt > 10000) {
                    currentWeight = null;
                    document.getElementById('btn-to-capture').disabled = !sensorTestMode;
                    document.getElementById('live-weight-value').textContent = '—';
                    document.getElementById('weight-status-badge').textContent = 'Reading expired — reconnecting…';
                }
                _pollWeight();
            }, 250);
            _pollWeight();
        }
        
        function _stopWeightPoll() {
            weightPollGeneration++;
            if (weightPollTimer) {
                clearInterval(weightPollTimer);
                weightPollTimer = null;
            }
        }
        
        async function _pollWeight() {
            if (weightRequestBusy || weightSaving || tareBusy || !weightPollTimer) return;
            const generation = weightPollGeneration;
            weightRequestBusy = true;
            try {
                let w, stable, inRange, gatePassed = false, samplePresent = false, testMode = false;
        
                if (devMode) {
                    currentWeight = null;
                    document.getElementById('live-weight-value').textContent = '— g';
                    document.getElementById('weight-status-badge').textContent = 'Live weight requires hardware mode. Disable Development Mode before starting.';
                    document.getElementById('btn-to-capture').disabled = !sensorTestMode;
                    return;
                } else {
                    try {
                        const resp = await API.get('/api/hardware/weight');
                        const data = await resp.json();
                        if (generation !== weightPollGeneration) return;
                        if (data.sensor_test_mode === true) sensorTestMode = true;
                        if (sensorTestMode) {
                            document.getElementById('btn-to-capture').disabled = false;
                            document.getElementById('weight-range-bypass').textContent = 'Sensor testing — weight validation bypassed';
                            const reading = data.sensor_reading;
                            const age = Date.now() - Date.parse(data.measured_at);
                            const responding = data.scale === 'ready' && data.simulated === false;
                            hwScale = responding ? 'ready' : 'error';
                            _updateHwCard('scale', hwScale, data.error || '');
                            const live = responding && reading && Number.isFinite(reading.value) && Number.isFinite(age) && age >= 0 && age <= 10000;
                            document.getElementById('live-weight-value').classList.toggle('raw-sensor-reading', reading?.unit === 'ADC counts');
                            document.getElementById('live-weight-value').textContent = live
                                ? String(reading.value) + ' ' + reading.unit : '—';
                            document.getElementById('weight-status-badge').textContent = !responding
                                ? (data.error || 'Scale unavailable') : !live ? 'Reading expired — reconnecting…'
                                : reading.calibrated ? 'Live calibrated reading — testing' : 'Live raw reading — calibration unavailable';
                            if (live) weightReadAt = Date.parse(data.measured_at);
                            return;
                        }
                        if (!resp.ok) throw new Error('Scale unavailable: ' + (data.detail || data.error || 'Read failed'));
                        if (generation !== weightPollGeneration) return;
                        const responseAge = Date.now() - Date.parse(data.measured_at);
                        if (Number.isFinite(responseAge) && responseAge >= 0 && responseAge <= 10000) weightReadAt = Date.parse(data.measured_at);
                        document.getElementById('weight-range-bypass').textContent =
                            data.bypass_weight_range === true ? 'Weight range bypass enabled' : '';
                        if (data.measurement_state === 'unstable')
                            throw new Error('Scale unstable');
                        if (data.measurement_state === 'uncalibrated' || data.status_message === 'Calibration required') {
                            hwScale = 'ready';
                            _updateHwCard('scale', 'ready');
                            document.getElementById('live-weight-value').classList.add('raw-sensor-reading');
                            currentWeight = null;
                            weightMeasuredAt = null;
                            document.getElementById('btn-to-capture').disabled = !sensorTestMode;
                            document.getElementById('live-weight-value').textContent = '— g';
                            document.getElementById('weight-status-badge').textContent =
                                'Calibration required';
                            return;
                        }
                        const age = Date.now() - Date.parse(data.measured_at);
                        if (data.scale !== 'ready' || data.simulated !== false || !Number.isFinite(age) || age < 0 || age > 10000)
                            throw new Error(data.status_message || 'Reading expired — reconnecting…');
                        if (data.calibrated !== true) throw new Error('Calibration required');
                        if (data.stable !== true || data.valid_weight !== true) throw new Error(data.status_message || 'Stabilizing…');
                        w = Number(data.weight_g);
                        if (data.weight_g == null || !Number.isFinite(w)) throw new Error('Invalid weight');
                        hwScale = 'ready';
                        _updateHwCard('scale', 'ready');
                        testMode = data.weight_test_mode === true && data.simulated === false;
                        weightMeasuredAt = data.measured_at || null;
                        stable  = data.stable;
                        inRange = data.in_range;
                        gatePassed = data.weight_gate_passed === true;
                        samplePresent = data.sample_present === true;
                    } catch (e) {
                        if (generation !== weightPollGeneration) return;
                        hwScale = 'error';
                        _updateHwCard('scale', 'error', e.message);
                        currentWeight = null;
                        weightMeasuredAt = null;
                        document.getElementById('btn-to-capture').disabled = !sensorTestMode;
                        document.getElementById('live-weight-value').textContent = '— g';
                        document.getElementById('weight-status-badge').innerHTML =
                            '<span class="badge bg-secondary"></span>';
                        document.querySelector('#weight-status-badge span').textContent = e.message;
                        return;
                    }
                }
        
                document.getElementById('live-weight-value').classList.remove('raw-sensor-reading');
                document.getElementById('live-weight-value').textContent = w.toFixed(2) + ' g';
        
                let badgeHtml = '';
                if (!stable) {
                    badgeHtml = '<span class="badge bg-warning text-dark fs-6">Stabilizing…</span>';
                } else if (!samplePresent) {
                    badgeHtml = '<span class="badge bg-warning text-dark fs-6">Empty tray — add beans</span>';
                } else if (testMode) {
                    badgeHtml = '<span class="badge bg-warning text-dark fs-6">Stable — weight range bypass enabled</span>';
                } else if (w < 340) {
                    badgeHtml = '<span class="badge bg-danger fs-6">Stable — add beans</span>';
                } else if (w > 360) {
                    badgeHtml = '<span class="badge bg-danger fs-6">Stable — remove beans</span>';
                } else {
                    badgeHtml = '<span class="badge bg-success fs-6">Stable — proceed</span>' +
                                (devMode ? ' <span class="badge bg-warning text-dark">Simulated</span>' : '');
                }
                document.getElementById('weight-status-badge').innerHTML = badgeHtml;

                const canProceed = gatePassed && Number.isFinite(w) && stable;
                document.getElementById('btn-to-capture').disabled = !canProceed;
                currentWeight = canProceed ? w : null;
            } finally {
                weightRequestBusy = false;
            }
        }

        document.getElementById('btn-tare-scale').addEventListener('click', async () => {
            if (tareBusy || weightSaving) return;
            if (!devMode && !window.confirm('Remove all samples and leave the empty tray installed before taring.')) return;
            tareBusy = true;
            _stopWeightPoll();
            currentWeight = null;
            document.getElementById('live-weight-value').textContent = '— g';
            document.getElementById('weight-status-badge').textContent = 'Taring — keep the scale still…';
            document.getElementById('btn-to-capture').disabled = true;
            document.getElementById('btn-tare-scale').disabled = true;
            document.getElementById('btn-calibrate-scale').disabled = true;
            _hideError('stage2-error');
            try {
                if (!devMode) {
                    await _invalidateAcceptedWeight();
                    const resp = await API.post('/api/hardware/weight', { action: 'tare' });
                    if (!resp.ok) {
                        const err = await resp.json();
                        throw new Error(err.detail || 'Tare failed');
                    }
                }
            } catch (e) {
                _showError('stage2-error', e.message);
            } finally {
                tareBusy = false;
                document.getElementById('btn-tare-scale').disabled = false;
                document.getElementById('btn-calibrate-scale').disabled = false;
                if (document.getElementById('stage-2').classList.contains('d-none') === false) _startWeightPoll();
            }
        });
        
        document.getElementById('btn-calibrate-scale').addEventListener('click', async () => {
            if (tareBusy || weightSaving) return;
            if (devMode) {
                _showError('stage2-error', 'Calibration requires real HX711 hardware. Turn off Development Mode.');
                return;
            }
            if (!window.confirm('Remove all samples. Leave the empty tray installed, let it settle, then press OK to measure zero.')) return;
            tareBusy = true;
            _stopWeightPoll();
            currentWeight = null;
            document.getElementById('btn-to-capture').disabled = true;
            document.getElementById('live-weight-value').textContent = '— g';
            for (const id of ['btn-tare-scale', 'btn-calibrate-scale', 'btn-back-to-prepare'])
                document.getElementById(id).disabled = true;
            _hideError('stage2-error');
            let token = null;
            async function action(name, extra = {}) {
                document.getElementById('weight-status-badge').textContent = 'Calibrating — keep the scale still…';
                const resp = await API.post('/api/hardware/weight', {action: name, token, ...extra});
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || data.error || 'Calibration failed');
                return data;
            }
            try {
                token = (await action('calibration_zero')).token;
                const entered = window.prompt('Enter the accurately known reference mass in grams (prefer near 350 g).');
                if (entered === null) return;
                const known = Number(entered);
                if (!Number.isFinite(known) || known <= 0) throw new Error('Reference mass must be a positive number in grams.');
                if (!window.confirm('Place ONLY the known ' + known + ' g reference in the empty tray. Let it settle, then press OK.')) return;
                await action('calibration_load', {known_g: known});
                if (!window.confirm('Remove the reference mass. Leave the empty tray installed, let it settle, then press OK to verify zero and save.')) return;
                await action('calibration_finish');
                token = null;
                window.alert('Calibration saved. Verify an independent known mass, then tare with the empty tray installed before adding beans.');
            } catch (e) {
                _showError('stage2-error', e.message);
            } finally {
                if (token) {
                    try { await action('calibration_cancel'); }
                    catch (e) { _showError('stage2-error', 'Calibration session could not be cancelled: ' + e.message + '. It expires after 10 minutes.'); }
                }
                tareBusy = false;
                for (const id of ['btn-tare-scale', 'btn-calibrate-scale', 'btn-back-to-prepare'])
                    document.getElementById(id).disabled = false;
                if (!document.getElementById('stage-2').classList.contains('d-none')) _startWeightPoll();
            }
        });

        document.getElementById('btn-back-to-prepare').addEventListener('click', () => {
            _stopWeightPoll();
            _setStage(1);
            _validateStage1();
        });
        
        document.getElementById('btn-to-capture').addEventListener('click', async () => {
            if (weightSaving || tareBusy || (!sensorTestMode && (currentWeight === null || Date.now() - weightReadAt > 10000))) return;
            _stopWeightPoll();
            weightSaving = true;
            _hideError('stage2-error');
            document.getElementById('btn-to-capture').disabled = true;
        
            if (devMode) {
                // Skip weight persistence API call in dev mode
                weightSaving = false;
                _stopWeightPoll();
                _setStage(3);
                return;
            }
        
            // Production: persist weight to pending row
            try {
                const resp = await API.put('/api/transaction/' + pendingId + '/weight',
                                           { weight_g: currentWeight, measured_at: weightMeasuredAt });
                if (!resp.ok) {
                    const err = await resp.json();
                    _showError('stage2-error', err.detail || 'Failed to save weight.');
                    weightSaving = false;
                    _startWeightPoll();
                    return;
                }
                const accepted = await resp.json();
                currentWeight = accepted.weight_g == null ? null : Number(accepted.weight_g);
            } catch (e) {
                _showError('stage2-error', 'Network error: ' + e.message);
                weightSaving = false;
                _startWeightPoll();
                return;
            }
        
            weightSaving = false;
            _stopWeightPoll();
            _setStage(3);
        });
        
        // ── Stage 3 — Capture ─────────────────────────────────────────────────────────
        
        function _stopCameraPreview() {
            previewGeneration++;
            clearTimeout(cameraPreviewTimer);
            cameraPreviewTimer = null;
            const image = document.getElementById('camera-live-preview');
            image.classList.add('d-none');
            image.removeAttribute('src');
        }

        function _startCameraPreview() {
            if (!captureStage || captureBusy) return;
            _stopCameraPreview();
            const generation = previewGeneration;
            const label = document.getElementById('camera-live-status');
            label.textContent = 'Connecting to camera…';
            const tick = async () => {
                if (generation !== previewGeneration || !captureStage || captureBusy) return;
                if (cameraPreviewRequest) {
                    cameraPreviewTimer = setTimeout(tick, 300);
                    return;
                }
                const image = document.getElementById('camera-live-preview');
                cameraPreviewRequest = (async () => {
                    try {
                        let source, simulated = devMode;
                        if (devMode) source = DEV._makePlaceholderImg('Live preview (Simulated)');
                        else {
                            const resp = await API.post('/api/hardware/capture', {
                                view: acceptedA ? 'B' : 'A', preview: true
                            });
                            const data = await resp.json();
                            if (!resp.ok || !data.image_b64) throw new Error(data.detail || 'Camera unavailable');
                            source = 'data:image/jpeg;base64,' + data.image_b64;
                            simulated = data.simulated === true;
                        }
                        if (generation !== previewGeneration) return;
                        image.src = source;
                        image.classList.remove('d-none');
                        label.textContent = simulated ? 'Live preview — Simulated' : 'Live camera — Ready';
                        hwCamera = 'ready';
                        _updateHwCard('camera', 'ready');
                    } catch (e) {
                        if (generation !== previewGeneration) return;
                        image.classList.add('d-none');
                        image.removeAttribute('src');
                        label.textContent = 'Camera unavailable — retrying…';
                        hwCamera = 'error';
                        _updateHwCard('camera', 'error');
                    }
                })();
                await cameraPreviewRequest;
                cameraPreviewRequest = null;
                if (generation === previewGeneration && captureStage && !captureBusy)
                    cameraPreviewTimer = setTimeout(tick, 500);
            };
            tick();
        }

        async function _doCapture(view) {
            if (!captureStage || captureBusy || (view === 'B' && !acceptedA)) return;
            captureBusy = true;
            const generation = stageGeneration;
            _stopCameraPreview();
            document.getElementById('camera-live-status').textContent = 'Capturing…';
            try {
                // Finish the outstanding preview before requesting the still.
                if (cameraPreviewRequest) await cameraPreviewRequest;
                if (generation !== stageGeneration) return;
                const viewLower    = view.toLowerCase();
                const btnCapture   = document.getElementById('btn-capture-' + viewLower);
                const btnRetake    = document.getElementById('btn-retake-'  + viewLower);
                const btnAccept    = document.getElementById('btn-accept-'  + viewLower);
                const previewEl    = document.getElementById('view-' + viewLower + '-preview');
                const countEl      = document.getElementById('view-' + viewLower + '-count');
                const countdownDiv = document.getElementById('view-' + viewLower + '-countdown');
                const badgeEl      = document.getElementById('view-' + viewLower + '-badge');

                btnCapture.disabled = true;
                btnRetake.classList.add('d-none');
                btnAccept.classList.add('d-none');
                previewEl.classList.add('d-none');
                _hideError('stage3-error');

                // 3-second countdown — identical in both modes
                countdownDiv.classList.remove('d-none');
                for (let i = 3; i >= 1; i--) {
                    countEl.textContent = i;
                    await new Promise(r => setTimeout(r, 1000));
                    if (generation !== stageGeneration) return;
                }
                countEl.textContent = '📷';
                await new Promise(r => setTimeout(r, 400));
                if (generation !== stageGeneration) return;
                countdownDiv.classList.add('d-none');

                let imgSrc;

                if (devMode) {
                    // Use a placeholder SVG image — no Pi camera call
                    imgSrc = DEV._makePlaceholderImg('View ' + view);
                    // Store as dataURI string; the backend call in Analyze will also be mocked
                    if (view === 'A') imageAb64 = imgSrc;
                    else              imageBb64 = imgSrc;
                } else {
                    // Production: trigger Pi camera
                    try {
                        const resp = await API.post('/api/hardware/capture', { view });
                        if (generation !== stageGeneration) return;
                        if (!resp.ok) {
                            const err = await resp.json();
                            hwCamera = 'error';
                            _updateHwCard('camera', 'error');
                            _showError('stage3-error', 'Capture failed: ' + (err.detail || 'Unknown error'));
                            btnCapture.disabled = false;
                            return;
                        }
                        const data = await resp.json();
                        if (generation !== stageGeneration) return;
                        if (!data.image_b64 || data.preview === true) throw new Error('No captured image returned');
                        hwCamera = 'ready';
                        _updateHwCard('camera', 'ready');
                        imgSrc = 'data:image/jpeg;base64,' + data.image_b64;
                        if (view === 'A') imageAb64 = data.image_b64;
                        else              imageBb64 = data.image_b64;
                    } catch (e) {
                        if (generation !== stageGeneration) return;
                        hwCamera = 'error';
                        _updateHwCard('camera', 'error');
                        _showError('stage3-error', 'Capture failed: ' + e.message);
                        btnCapture.disabled = false;
                        return;
                    }
                }

                previewEl.src = imgSrc;
                previewEl.classList.remove('d-none');
                btnRetake.classList.remove('d-none');
                btnAccept.classList.remove('d-none');
                badgeEl.textContent = devMode ? 'Preview (Simulated) — Accept or Retake' : 'Preview — Accept or Retake';
                badgeEl.className   = 'badge bg-warning text-dark';
            } finally {
                captureBusy = false;
                if (generation === stageGeneration) {
                    document.getElementById('view-' + view.toLowerCase() + '-countdown').classList.add('d-none');
                }
                if (captureStage) _startCameraPreview();
            }
        }
        
        document.getElementById('btn-capture-a').addEventListener('click', () => _doCapture('A'));
        document.getElementById('btn-capture-b').addEventListener('click', () => _doCapture('B'));
        
        function _retakeView(view, force = false) {
            if (captureBusy && !force) return;
            if (view === 'A') {
                _retakeView('B', force);
                document.getElementById('btn-capture-b').disabled = true;
                document.getElementById('reorient-instruction').classList.add('d-none');
            }
            const vl = view.toLowerCase();
            document.getElementById('view-' + vl + '-preview').classList.add('d-none');
            document.getElementById('btn-retake-' + vl).classList.add('d-none');
            document.getElementById('btn-accept-' + vl).classList.add('d-none');
            document.getElementById('btn-capture-' + vl).disabled = false;
            document.getElementById('view-' + vl + '-badge').textContent = 'Pending';
            document.getElementById('view-' + vl + '-badge').className   = 'badge bg-secondary';
            if (view === 'A') { imageAb64 = null; acceptedA = false; }
            else              { imageBb64 = null; acceptedB = false; }
            document.getElementById('btn-to-analyze').disabled = true;
            _hideError('stage3-error');
        }
        
        function _acceptView(view) {
            if (captureBusy || (view === 'A' ? !imageAb64 : !imageBb64 || !acceptedA)) return;
            const vl      = view.toLowerCase();
            const badgeEl = document.getElementById('view-' + vl + '-badge');
            badgeEl.textContent = '✓ Accepted';
            badgeEl.className   = 'badge bg-success';
            document.getElementById('btn-retake-' + vl).classList.remove('d-none');
            document.getElementById('btn-accept-' + vl).classList.add('d-none');
            document.getElementById('btn-capture-' + vl).disabled = true;
        
            if (view === 'A') acceptedA = true;
            else acceptedB = true;
            if (view === 'A') {
                document.getElementById('reorient-instruction').classList.remove('d-none');
                document.getElementById('btn-capture-b').disabled = false;
            }
            if (imageAb64 && imageBb64 && acceptedA && acceptedB) {
                document.getElementById('btn-to-analyze').disabled = false;
            }
        }
        
        document.getElementById('btn-retake-a').addEventListener('click', () => _retakeView('A'));
        document.getElementById('btn-retake-b').addEventListener('click', () => _retakeView('B'));
        document.getElementById('btn-accept-a').addEventListener('click', () => _acceptView('A'));
        document.getElementById('btn-accept-b').addEventListener('click', () => _acceptView('B'));
        
        document.getElementById('btn-back-to-weight').addEventListener('click', async () => {
            try { await _invalidateAcceptedWeight(); }
            catch (e) { _showError('stage3-error', e.message); return; }
            imageAb64 = imageBb64 = null;
            acceptedA = acceptedB = false;
            document.getElementById('btn-to-analyze').disabled = true;
            _retakeView('A', true);
            _retakeView('B', true);
            document.getElementById('btn-capture-b').disabled = true;
            document.getElementById('reorient-instruction').classList.add('d-none');
            _setStage(2);
            _startWeightPoll();
        });
        
        document.getElementById('btn-to-analyze').addEventListener('click', () => {
            if (captureBusy || !acceptedA || !acceptedB || !imageAb64 || !imageBb64) return;
            document.getElementById('analyze-view-a').src = devMode ? imageAb64 : ('data:image/jpeg;base64,' + imageAb64);
            document.getElementById('analyze-view-b').src = devMode ? imageBb64 : ('data:image/jpeg;base64,' + imageBb64);
            _setStage(4);
        });
        
        // ── Stage 4 — Analyze ─────────────────────────────────────────────────────────
        
        document.getElementById('btn-back-to-capture').addEventListener('click', () => _setStage(3));
        
        document.getElementById('btn-start-analysis').addEventListener('click', async () => {
            if (analysisRunning) return;
            analysisRunning = true;
        
            const btnStart   = document.getElementById('btn-start-analysis');
            const progress   = document.getElementById('analysis-progress');
            const progLabel  = document.getElementById('analysis-progress-label');
            _hideError('stage4-error');
            btnStart.disabled = true;
            progress.classList.remove('d-none');
        
            if (devMode) {
                progLabel.textContent = '[DEV] Simulating YOLOv8 analysis…';
                // Simulate processing delay
                await new Promise(r => setTimeout(r, 1800));
                progress.classList.add('d-none');
                currentAnalysis = DEV.makeMockAnalysis(txnNumber, currentWeight || 350.0, farmerName);
                txnId = null;  // No DB record in dev mode
                _renderResults(currentAnalysis);
                _setStage(5);
                analysisRunning = false;
                return;
            }
        
            progLabel.textContent = 'Running YOLOv8 analysis — please wait…';
        
            try {
                const resp = await API.post('/api/inspection/capture-dual', {
                    pending_id:  pendingId,
                    image_a_b64: imageAb64,
                    image_b_b64: imageBb64,
                });
        
                if (!resp.ok) {
                    const err = await resp.json();
                    _showError('stage4-error',
                        'Analysis failed: ' + (err.detail || 'Unknown error. No result was fabricated.'));
                    btnStart.disabled = false;
                    analysisRunning   = false;
                    progress.classList.add('d-none');
                    return;
                }
        
                currentAnalysis = await resp.json();
                txnId = currentAnalysis.txn_id;
                progress.classList.add('d-none');
                _renderResults(currentAnalysis);
                _setStage(5);
        
            } catch (e) {
                _showError('stage4-error', 'Network error: ' + e.message);
                btnStart.disabled = false;
                analysisRunning   = false;
                progress.classList.add('d-none');
            }
        });
        
        // ── Stage 5 — Results ─────────────────────────────────────────────────────────
        
        function _renderResults(data) {
            document.getElementById('btn-to-receipt').textContent = data.sensor_test_mode ? 'Review test summary →' : 'Continue to Receipt →';
            document.getElementById('btn-complete-txn').textContent = data.sensor_test_mode ? 'Close sensor test' : '✔ Complete Transaction';
            document.getElementById('res-txn-number').textContent = data.txn_number || txnNumber;
            document.getElementById('res-date').textContent =
                data.created_at ? data.created_at.replace('T', ' ').slice(0, 16) : '—';
            document.getElementById('res-farmer').textContent = farmerName || '—';
            document.getElementById('res-weight').textContent = data.sample_weight_g == null
                ? (data.sensor_reading ? String(data.sensor_reading.value) + ' ' + data.sensor_reading.unit + ' (testing; grams unavailable)' : 'Unavailable — sensor testing')
                : parseFloat(data.sample_weight_g).toFixed(1) + ' g  (' +
                (parseFloat(data.sample_weight_g)/1000).toFixed(3) + ' kg)';
        
            const gradeBadge = document.getElementById('res-grade-badge');
            gradeBadge.textContent = data.analysis_skipped ? 'Analysis skipped — model unavailable' : _gradeLabel(data.grade);
            gradeBadge.className   = 'badge fs-5 px-3 py-2 bg-' + (data.analysis_skipped ? 'warning text-dark' : _gradeClass(data.grade));
            document.getElementById('res-threshold-badge')
                .classList.toggle('d-none', !data.over_threshold_flag);
        
            const tbody = document.getElementById('res-defect-tbody');
            tbody.innerHTML = '';
            for (const dr of (data.defect_results || [])) {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${dr.defect_type.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</td>
                    <td>${dr.bean_count}</td>
                    <td>${parseFloat(dr.defect_percentage).toFixed(2)}%</td>
                    <td><span class="badge bg-${_gradeClass(dr.assigned_class)}">${_gradeLabel(dr.assigned_class)}</span></td>
                    <td>${dr.over_threshold ? '⚠' : '—'}</td>`;
                tbody.appendChild(tr);
            }
        
            // Keep each accepted capture available if Apache cannot serve its saved URL.
            function _setImg(imgId, linkId, path, captured = null) {
                const img = document.getElementById(imgId);
                const link = document.getElementById(linkId);
                const fallback = captured && (captured.startsWith('data:')
                    ? captured : 'data:image/jpeg;base64,' + captured);
                const url = path ? _staticUrl(path) : fallback;
                img.onload = null;
                img.onerror = null;
                img.hidden = !url;
                link.style.display = url ? '' : 'none';
                link.removeAttribute('href');
                img.removeAttribute('src');
                if (!url) return;
                img.onerror = () => {
                    if (fallback && img.getAttribute('src') !== fallback) {
                        link.href = fallback;
                        img.src = fallback;
                        return;
                    }
                    img.onerror = null;
                    img.hidden = true;
                    link.removeAttribute('href');
                    link.style.display = 'none';
                };
                link.href = url;
                img.src = url;
            }

            if (devMode) {
                // Show the captured placeholder images; annotated thumbnails = same placeholder
                _setImg('res-img-a',     'res-img-a-link',     imageAb64);
                _setImg('res-img-a-ann', 'res-img-a-ann-link', DEV._makePlaceholderImg('View A — Annotated'));
                _setImg('res-img-b',     'res-img-b-link',     imageBb64);
                _setImg('res-img-b-ann', 'res-img-b-ann-link', DEV._makePlaceholderImg('View B — Annotated'));
            } else {
                _setImg('res-img-a',     'res-img-a-link',     data.image_path, imageAb64);
                _setImg('res-img-a-ann', 'res-img-a-ann-link', data.image_path_annotated_a);
                _setImg('res-img-b',     'res-img-b-link',     data.image_path_b, imageBb64);
                _setImg('res-img-b-ann', 'res-img-b-ann-link', data.image_path_annotated_b);
            }
        
            if (data.analysis_skipped || data.pricing_unavailable) {
                for (const id of ['res-market-rate', 'res-multiplier', 'res-price-per-kg', 'res-total-price'])
                    document.getElementById(id).textContent = 'Unavailable';
                document.getElementById('res-price-source').textContent = data.message;
                return;
            }

            document.getElementById('res-market-rate').textContent  = _phpFormat(data.market_rate_per_kg) + '/kg';
            document.getElementById('res-multiplier').textContent   = 'x' + parseFloat(data.multiplier).toFixed(4);
            document.getElementById('res-price-per-kg').textContent = _phpFormat(data.price_per_kg) + '/kg';
            document.getElementById('res-total-price').textContent  = _phpFormat(data.total_price);
            document.getElementById('res-price-source').textContent =
                'Price source: ' + (devMode ? 'dev-mock (simulated)' : (data.price_source || '—'));
        }
        
        document.getElementById('btn-to-receipt').addEventListener('click', () => {
            _buildReceiptPreview();
            _setStage(6);
        });
        
        // ── Stage 6 — Receipt ─────────────────────────────────────────────────────────
        
        function _pad32(label, value) {
            return (label + value).padEnd(36);
        }
        
        function _buildReceiptPreview() {
            const d = currentAnalysis;
            if (!d) return;
            const gradeLabel = d.analysis_skipped ? 'SKIPPED — MODEL UNAVAILABLE' : _gradeLabel(d.grade);
            const date       = (d.created_at || '').replace('T', ' ').slice(0, 16);
            const weightLabel = d.sample_weight_g == null ? 'Unavailable — sensor test' : (parseFloat(d.sample_weight_g) / 1000).toFixed(3) + ' kg';
            const lines = [
                '            CGI',
                '  Coffee Grade Identification',
                d.sensor_test_mode ? '  SENSOR TEST — NO SALE OR SAMPLE PRICE' : devMode ? '  *** DEVELOPMENT MODE — NOT A REAL RECORD ***' : '',
                '─'.repeat(36),
                _pad32('Txn No  : ', d.txn_number || txnNumber),
                _pad32('Date    : ', date),
                _pad32('Farmer  : ', farmerName || '—'),
                '─'.repeat(36),
                _pad32('Grade   : ', gradeLabel),
                d.over_threshold_flag ? '! OVER THRESHOLD - LOW VALUE !' : '',
                _pad32('Weight  : ', weightLabel),
                _pad32('Price/kg: ', (d.analysis_skipped || d.pricing_unavailable) ? 'Unavailable' : _phpFormat(d.price_per_kg)),
                '─'.repeat(36),
                _pad32('TOTAL   : ', (d.analysis_skipped || d.pricing_unavailable) ? 'Unavailable — test only' : _phpFormat(d.total_price)),
                '─'.repeat(36),
                devMode ? '     [DEV] Simulated — no printer required' : '         Thank you!',
                '       CGI System v1.0',
            ].filter(l => l !== '');
        
            document.getElementById('receipt-preview-box').textContent = lines.join('\n');
        }
        
        document.getElementById('btn-print-receipt').addEventListener('click', async () => {
            const btn      = document.getElementById('btn-print-receipt');
            const statusEl = document.getElementById('print-status-badge');
            btn.disabled   = true;
            _hideError('stage6-error');
        
            if (devMode) {
                // Simulate a short printing delay
                statusEl.innerHTML = '<span class="badge bg-secondary">Simulating print…</span>';
                await new Promise(r => setTimeout(r, 1200));
                statusEl.innerHTML = '<span class="badge bg-success">✓ Printed (Simulated)</span>';
                btn.textContent    = '🖨 Reprint';
                btn.disabled       = false;
                return;
            }
        
            if (currentAnalysis?.sensor_test_mode) {
                _showError('stage6-error', 'Sensor test only: no sale or priced receipt was created.');
                btn.disabled = false;
                return;
            }
            if (currentAnalysis?.analysis_skipped) {
                _showError('stage6-error', 'Analysis was skipped. No finalized transaction or printable graded receipt was created.');
                btn.disabled = false;
                return;
            }
            if (!txnId) { btn.disabled = false; return; }
            statusEl.innerHTML = '<span class="badge bg-secondary">Sending to printer…</span>';
        
            try {
                const resp = await API.post('/api/reports/transaction/' + txnId + '/print', {});
                const data = await resp.json();
        
                if (data.status === 'printed') {
                    statusEl.innerHTML = '<span class="badge bg-success">✓ Printed successfully</span>';
                    btn.textContent    = '🖨 Reprint';
                    btn.disabled       = false;
                } else {
                    statusEl.innerHTML = '<span class="badge bg-danger">Printer error — Retry</span>';
                    _showError('stage6-error',
                        'Printing failed: ' + (data.detail || 'Unknown printer error.') +
                        ' You can retry or proceed to complete the transaction.');
                    btn.disabled = false;
                }
            } catch (e) {
                statusEl.innerHTML = '<span class="badge bg-danger">Network error</span>';
                _showError('stage6-error', 'Could not reach printer endpoint: ' + e.message);
                btn.disabled = false;
            }
        });
        
        document.getElementById('btn-complete-txn').addEventListener('click', async () => {
            const btn = document.getElementById('btn-complete-txn');
            btn.disabled = true;
            _hideError('stage6-error');
        
            if (devMode) {
                // In dev mode no DB record was created — just close the modal
                txnModal.hide();
                return;
            }
        
            if (currentAnalysis?.analysis_skipped || currentAnalysis?.sensor_test_mode) { txnModal.hide(); return; }
            if (!txnId) { btn.disabled = false; return; }
        
            try {
                const resp = await API.put('/api/transactions/' + txnId, { status: 'completed' });
                if (resp.ok) {
                    txnModal.hide();
                    location.reload();
                } else {
                    const err = await resp.json();
                    _showError('stage6-error', err.detail || 'Failed to complete transaction.');
                    btn.disabled = false;
                }
            } catch (e) {
                _showError('stage6-error', 'Network error: ' + e.message);
                btn.disabled = false;
            }
        });
        
    }

    function initializeDashboard() {
        initializePopupUi();
        initializeClock();
        initializeTransactionWorkflow();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeDashboard, { once: true });
    } else {
        initializeDashboard();
    }
})();
