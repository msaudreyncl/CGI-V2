# CGI Six-Stage Transaction Workflow — Upgrade Plan

## Top-Level Overview

**Goal:** Replace the existing 4-step inspection workflow in `dashboard.php` with the
six-stage specification: **Prepare → Weight → Capture → Analyze → Results → Receipt**.

**Approach:** Minimal, additive change strategy.
- Every existing working API endpoint is reused where possible.
- New backend endpoints are added only where the spec requires genuinely new behaviour.
- The database schema gains new columns and one new table (`pending_transactions`); all
  existing tables and columns are preserved unchanged.
- The frontend (`dashboard.php`) admin/officer section is rewritten as a 6-panel Bootstrap
  modal workflow; the farmer view and all other pages remain completely untouched.

**Confirmed Design Decisions:**
1. **`pending_transactions` table** — In-progress workflow state lives here. The `inspections`
   table receives only finalized, analyzed data. On Analyze completion the `txn_number`,
   `farmer_id`, and original `created_at` are carried forward from the pending row.
2. **Printer non-blocking** — Only Camera and Scale must be Ready to proceed past Prepare.
   Printer shows a warning if unavailable but does not block. Receipt is always generated
   digitally; printing is optional and retryable at any time from Stage 6.
3. **Annotated images** — YOLOv8 annotated images (bounding boxes + labels + confidence
   scores) are generated during Stage 4 (Analyze), not at capture time. Both original and
   annotated paths are stored in `inspections` and served to Results and Transaction History.
4. **Manual Start Analysis** — Stage 4 opens with a review panel showing both captured images.
   The officer must click "Start Analysis" explicitly. A processing indicator is shown during
   the YOLOv8 run. Duplicate requests are prevented. Continue to Results unlocks only on
   successful completion.

**Non-goals for this upgrade:**
- Real-time video streaming from the Pi camera.
- Changing the grading engine, pricing engine, auth system, or any other page.
- Model retraining or YOLO class changes.

---

## Architecture of New API Surface

```
GET  /api/hardware/status              → {camera, scale, printer} readiness
GET  /api/hardware/weight              → {weight_g, stable, in_range}
POST /api/hardware/capture             → trigger Pi camera, return base64 image (view=A|B)
POST /api/transaction/init             → generate txn_number, create pending row → {txn_number, pending_id}
PUT  /api/transaction/{pid}/weight     → save validated weight to pending row
GET  /api/transaction/{pid}            → fetch pending row state
POST /api/inspection/capture-dual      → run dual-view YOLOv8, annotate, reconcile, grade,
                                         price, finalize inspection + transaction → DualInspectionOut
POST /api/reports/transaction/{id}/print  → (existing) + now persists print_status
```

The Pi node gains `pi_node/pi_server.py` — a lightweight stdlib HTTP server the backend calls
to poll weight and trigger camera captures. The existing `sensor_node.py` is untouched.

---

## Sub-Task 1 — Database Schema Additions

**Status:** `[x] done`

**Intent:**
Add the columns and tables needed to support the new six-stage lifecycle without modifying
any existing column. All changes are additive and backward-compatible.

**Expected Outcomes:**
- New table `pending_transactions` tracks in-progress workflow state from Prepare through
  the moment analysis is finalized.
- `inspections` gains: `txn_number VARCHAR(20) UNIQUE NULL`, `image_path_b VARCHAR(500) NULL`,
  `image_path_annotated_a VARCHAR(500) NULL`, `image_path_annotated_b VARCHAR(500) NULL`.
- `transactions` gains: `status ENUM('in_progress','analyzed','completed') DEFAULT 'in_progress'`,
  `print_status ENUM('pending','printed','failed') DEFAULT 'pending'`.
- Migration SQL file created; existing rows are valid because all new columns are nullable
  or carry defaults.

**Todo List:**
- [ ] Create `database/migrations/` directory.
- [ ] Write `database/migrations/001_six_stage_workflow.sql`:
  - `CREATE TABLE pending_transactions` with columns:
    `id INT UNSIGNED AUTO_INCREMENT PK`, `txn_number VARCHAR(20) NOT NULL UNIQUE`,
    `farmer_id INT UNSIGNED NOT NULL FK→farmers(id)`,
    `officer_id INT UNSIGNED NOT NULL FK→users(id)`,
    `weight_g DECIMAL(7,2) NULL`,
    `status ENUM('prepared','weighed','captured','analyzed','completed') NOT NULL DEFAULT 'prepared'`,
    `created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP`.
  - `ALTER TABLE inspections ADD COLUMN txn_number VARCHAR(20) UNIQUE NULL AFTER notes`
  - `ALTER TABLE inspections ADD COLUMN image_path_b VARCHAR(500) NULL AFTER image_path`
  - `ALTER TABLE inspections ADD COLUMN image_path_annotated_a VARCHAR(500) NULL AFTER image_path_b`
  - `ALTER TABLE inspections ADD COLUMN image_path_annotated_b VARCHAR(500) NULL AFTER image_path_annotated_a`
  - `ALTER TABLE transactions ADD COLUMN status ENUM('in_progress','analyzed','completed') NOT NULL DEFAULT 'in_progress' AFTER notes`
  - `ALTER TABLE transactions ADD COLUMN print_status ENUM('pending','printed','failed') NOT NULL DEFAULT 'pending' AFTER status`
- [ ] Create `backend/models/pending_transaction.py` ORM model mapping `pending_transactions`.
- [ ] Update `backend/models/inspection.py` — add the four new `Column` declarations.
- [ ] Update `backend/models/transaction.py` — add `status` and `print_status` columns.
- [ ] Update `backend/schemas/inspection.py` `InspectionOut` to expose the four new image path fields and `txn_number`.
- [ ] Update `backend/schemas/transaction.py` `TransactionOut` to expose `status` and `print_status`.
- [ ] Add a new `backend/schemas/pending_transaction.py` with `PendingTransactionOut` schema.

**Relevant Context:**
- `backend/models/inspection.py` — current ORM model, 5 existing columns after `grade`.
- `backend/models/transaction.py` — current ORM model, `notes` is the last content column.
- `database/schema.sql` — original schema; do NOT edit it (migration file is additive).
- `Base.metadata.create_all()` in `backend/database.py` only creates missing tables; it
  will not add columns to existing tables on an already-initialized database — hence the
  `ALTER TABLE` migration.

---

## Sub-Task 2 — Pi Node HTTP Server

**Status:** `[x] done`

**Intent:**
Add `pi_node/pi_server.py` — a lightweight HTTP server on the Pi that the FastAPI backend
calls to (a) poll live weight and (b) trigger a single camera capture. This keeps the Pi
controllable from the browser workflow without adding any external dependencies.

**Expected Outcomes:**
- `pi_node/pi_server.py` runs a `http.server.BaseHTTPRequestHandler` on `PI_SERVER_PORT`
  (default 5000, configurable in `config.ini`).
- `GET /weight` → JSON `{"weight_g": float, "stable": bool, "in_range": bool}`.
  Stability is detected by comparing the latest two consecutive readings; if they differ
  by ≤ 0.5 g the reading is considered stable.
- `POST /capture` with JSON body `{"view": "A"|"B"}` → JSON `{"image_b64": "<base64 jpeg>"}`.
- On non-Pi machines both endpoints return simulated values
  (`weight_g=350.0, stable=true, in_range=true`; a 1×1 white JPEG for capture).
- `pi_node/config.ini.example` updated with `PI_SERVER_PORT = 5000` under `[server]`.
- No new Python dependencies required (stdlib `http.server`, `json`, `base64`).

**Todo List:**
- [ ] Create `pi_node/pi_server.py`:
  - Import and conditionally initialize HX711 (`_build_hx711`) and camera.
  - Keep a module-level `_last_weight` variable for stability comparison.
  - Implement `GET /weight` handler.
  - Implement `POST /capture` handler.
  - `if __name__ == "__main__"` entry point reads `[server] PI_SERVER_PORT` from config.
- [ ] Add `PI_SERVER_PORT = 5000` and `PI_SERVER_HOST = 0.0.0.0` to `pi_node/config.ini.example`
  under a `[server]` section.
- [ ] Document in `README.md` that `pi_server.py` should be run alongside `sensor_node.py`
  (separate terminal / systemd unit).

**Relevant Context:**
- `pi_node/hx711_reader.py` — `_load_config()`, `_build_hx711(cfg)`, `read_weight_g(hx, cfg)`,
  `is_weight_in_range(weight, cfg)`.
- `pi_node/camera_capture.py` — `capture_image() → bytes`.
- `pi_node/sensor_node.py` — existing autonomous loop; `pi_server.py` is a peer process, not
  a replacement.

---

## Sub-Task 3 — Backend: Hardware Status, Weight Poll & Capture Proxy Endpoints

**Status:** `[x] done`

**Intent:**
Add `backend/routers/hardware.py` so the browser only ever speaks to the FastAPI backend
(single origin). The three new endpoints proxy calls to the Pi node HTTP server and also
perform a printer reachability check. Camera and scale failures are blocking; printer
failure is non-blocking (warning only).

**Expected Outcomes:**
- `GET /api/hardware/status` → JSON:
  ```json
  {
    "camera":  "ready"|"error",
    "scale":   "ready"|"error",
    "printer": "ready"|"warning"
  }
  ```
  - Camera + scale: attempt `GET {PI_NODE_URL}/weight`; reachable with HTTP 200 → `"ready"`,
    any exception → `"error"`.
  - Printer: attempt TCP connect to `THERMAL_PRINTER_HOST:THERMAL_PRINTER_PORT` (3 s timeout);
    success → `"ready"`, failure → `"warning"` (not `"error"` — non-blocking per design decision 2).
- `GET /api/hardware/weight` → proxies `GET {PI_NODE_URL}/weight`, returns the JSON unchanged.
- `POST /api/hardware/capture` body `{"view": "A"|"B"}` → proxies `POST {PI_NODE_URL}/capture`,
  returns `{"image_b64": str}`.
- All endpoints require officer/admin JWT.
- `backend/config.py` gains `PI_NODE_URL: str = os.getenv("PI_NODE_URL", "http://localhost:5000")`.
- New router registered in `backend/main.py`.

**Todo List:**
- [ ] Add `PI_NODE_URL` to `backend/config.py` Settings class.
- [ ] Add `PI_NODE_URL=http://localhost:5000` to `.env.example`.
- [ ] Create `backend/routers/hardware.py`:
  - Define `HardwareCaptureRequest` inline Pydantic model `{view: str}`.
  - Implement the three route functions using `httpx.AsyncClient` for Pi calls and
    `asyncio.open_connection` (with timeout) for the TCP printer check.
- [ ] Register `hardware_router` in `backend/main.py`.

**Relevant Context:**
- `backend/config.py` — `THERMAL_PRINTER_HOST`, `THERMAL_PRINTER_PORT` already present.
- `backend/main.py` — router registration pattern (lines 59–66).
- httpx is already in `backend/requirements.txt`.

---

## Sub-Task 4 — Backend: Transaction Initialization & Weight Persistence Endpoints

**Status:** `[x] done`

**Intent:**
Add `backend/routers/transaction_workflow.py` with three endpoints that manage the
`pending_transactions` lifecycle: initialization (with unique transaction number generation),
weight persistence (Stage 2 confirmation), and state fetch (for page reload resilience).

**Expected Outcomes:**
- `POST /api/transaction/init` body `{"farmer_id": int}`:
  - Generates `CGI-YYYYMMDD-XXXXXX` (6-char uppercase alphanumeric suffix).
  - Retries generation in a loop until the number does not exist in `pending_transactions.txn_number`.
  - Inserts a new `pending_transactions` row with `status='prepared'`.
  - Returns `{"txn_number": str, "pending_id": int, "created_at": datetime}`.
- `PUT /api/transaction/{pending_id}/weight` body `{"weight_g": float}`:
  - Validates `340 ≤ weight_g ≤ 360` (HTTP 422 if out of range).
  - Updates `pending_transactions.weight_g` and `status='weighed'`.
  - Returns the updated `PendingTransactionOut`.
- `GET /api/transaction/{pending_id}` — returns current `PendingTransactionOut` row.
- All endpoints require officer/admin JWT.
- New router registered in `backend/main.py`.

**Todo List:**
- [ ] Create `backend/schemas/pending_transaction.py` with `PendingTransactionOut`.
- [ ] Create `backend/routers/transaction_workflow.py` with the three endpoints.
- [ ] Register `transaction_workflow_router` in `backend/main.py`.

**Relevant Context:**
- `backend/models/pending_transaction.py` — created in Sub-Task 1.
- Transaction number format: `"CGI-" + date.strftime("%Y%m%d") + "-" + random_alphanum(6)`.
- Python `random.choices(string.ascii_uppercase + string.digits, k=6)` for the suffix.
- `backend/routers/transactions.py` — existing finalized-transaction CRUD, fully unchanged.

---

## Sub-Task 5 — Backend: Dual-View Capture & Analysis Endpoint

**Status:** `[x] done`

**Intent:**
Add `POST /api/inspection/capture-dual` — the core Analyze-stage endpoint. It accepts both
captured images, runs YOLOv8 on each, produces annotated images with bounding boxes, reconciles
counts (sum ÷ 2), grades, prices, and atomically finalizes the `Inspection`, `DefectResult`,
and `Transaction` records — carrying forward the `txn_number`, `farmer_id`, and `created_at`
from the `pending_transactions` row.

**Expected Outcomes:**
- Request body: `{pending_id: int, image_a_b64: str, image_b_b64: str}`.
  Weight is read from `pending_transactions.weight_g` (already validated in Stage 2).
- Both raw images saved to `UPLOAD_DIR` as `{uuid}_a.jpg` / `{uuid}_b.jpg`.
- `run_detection(image_path)` called independently on both images.
- Annotated images generated by calling YOLOv8's `result.plot()` output and saved as
  `{uuid}_a_annotated.jpg` / `{uuid}_b_annotated.jpg`.
- Reconciliation (explicit two-view averaging):
  ```
  total_beans = round((total_A + total_B) / 2)
  for each defect_type:
      reconciled_count = round((count_A + count_B) / 2)
  ```
  Code comment in-file: "Two-view reconciliation: average of both views as per spec §4.2."
- `evaluate_grade(reconciled_detection)` called on reconciled dict.
- `suggest_price(inspection, db)` called after inspection row is flushed.
- `Inspection` row created with:
  - `txn_number`, `farmer_id`, `created_at` from the `pending_transactions` row.
  - `officer_id` from the authenticated user.
  - `image_path` = raw View A path, `image_path_b` = raw View B path.
  - `image_path_annotated_a`, `image_path_annotated_b` = annotated paths.
- `Transaction` row created with `status='analyzed'`, `print_status='pending'`.
- `pending_transactions.status` updated to `'analyzed'`.
- If any step raises an exception: both raw and annotated image files are deleted, the
  database transaction is rolled back, and HTTP 500 is returned.
- Response schema `DualInspectionOut`: all `InspectionOut` fields + `{txn_id, price_per_kg,
  market_rate_per_kg, multiplier, total_price, currency, price_source}`.
- Existing `POST /api/inspection/capture` endpoint is untouched.

**Todo List:**
- [ ] Update `backend/services/detection.py` to expose `run_detection_with_annotation(image_path)
  → {total_beans, class_counts, annotated_image_bytes}` using `result.plot()` from YOLOv8.
- [ ] Add `DualCapturePayload` and `DualInspectionOut` Pydantic schemas to
  `backend/schemas/inspection.py`.
- [ ] Add `POST /api/inspection/capture-dual` route to `backend/routers/inspection.py`.
- [ ] Implement the reconciliation and file-cleanup error handling inline in the new route.
- [ ] Update `backend/schemas/inspection.py` `InspectionOut` to include the four new image
  path fields (from Sub-Task 1 model additions) so they are returned in the response.

**Relevant Context:**
- `backend/services/detection.py` — current `run_detection(image_path)` uses Ultralytics
  `model.predict()`; `results[0].plot()` returns a NumPy array (BGR) that can be encoded
  with `cv2.imencode` or `PIL.Image`.
- `backend/services/grading.py` — `evaluate_grade(detection_result)` unchanged.
- `backend/services/pricing.py` — `suggest_price(inspection, db)` unchanged async function.
- `backend/routers/inspection.py` — existing `capture_and_analyze` is the structural template.
- `backend/models/pending_transaction.py` — created in Sub-Task 1.

---

## Sub-Task 6 — Frontend: Six-Stage Modal Workflow in dashboard.php

**Status:** `[x] done`

**Intent:**
Rewrite only the admin/officer section of `dashboard.php` as a full-screen Bootstrap 5 modal
containing 6 stage panels. The farmer view (PHP lines 29–67) and all other pages are untouched.

**Expected Outcomes:**

**Page structure:**
- A "Start Transaction" button (officer/admin view header) opens `#txn-modal`.
- Modal contains: a progress bar (6 labelled steps), a close/cancel button, and the 6 stage
  panels (only one visible at a time using `d-none`).

**Stage 1 — Prepare:**
- On modal open: `POST /api/transaction/init` with selected farmer_id (or pre-selected if only
  one farmer). Transaction number displayed immediately in a read-only badge.
- Farmer `<select>` (server-rendered `$farmers` array, unchanged). Changing farmer re-calls init.
- Hardware status cards (Camera / Scale / Printer), each showing a spinner → Ready/Error/Warning.
  Polled once on open via `GET /api/hardware/status` with a manual "Re-check" button.
- Printer card shows a yellow "Unavailable — printing may be skipped" warning; Camera and Scale
  cards show a red "Error — cannot proceed" if not ready.
- Preparation checklist: 4 Bootstrap `<input type="checkbox">` items (sample ready, tray clean,
  single layer, camera positioned).
- "Continue to Weight" button disabled until: txn_number set + farmer selected + camera ready +
  scale ready + all 4 checklist items checked. Printer status does NOT block.

**Stage 2 — Weight:**
- On stage enter: starts `setInterval` polling `GET /api/hardware/weight` every 500 ms.
- Large numeric display (e.g., `<span id="live-weight">` styled with `fs-1`).
- Color-coded feedback row beneath weight:
  - `< 340 g` → red badge "Insufficient — add beans"
  - `340–360 g` + `stable: true` → green badge "Valid — proceed"
  - `340–360 g` + `stable: false` → amber badge "Stabilizing…"
  - `> 360 g` → red badge "Excess — remove beans"
- "Continue to Capture" button enabled only when `in_range && stable`.
- On continue: calls `PUT /api/transaction/{pending_id}/weight` with `{weight_g}`, then clears
  the weight poll interval and advances to Stage 3.

**Stage 3 — Capture:**
- View A subsection:
  - "Capture View A" button → disables itself → calls `POST /api/hardware/capture {view:"A"}`.
  - While waiting: shows a 3-second countdown overlay (`3… 2… 1… Capturing`).
  - On return: displays `<img>` preview of the returned `image_b64`.
  - "Retake" button (re-enables Capture View A, clears preview) and "Accept View A" button.
  - On accept: stores `imageAb64` in JS state, marks View A as accepted with a ✓ badge.
- Reorientation instruction card (Bootstrap info alert): shown after View A is accepted.
- View B subsection: identical flow, gated — the "Capture View B" button is disabled until
  View A is accepted.
- "Continue to Analyze" button enabled only when both views are accepted.

**Stage 4 — Analyze:**
- Image review panel: displays both accepted View A and View B previews side by side.
- "Start Analysis" button (primary, large). Clicking it:
  1. Disables the button and shows a Bootstrap spinner + "Running YOLOv8 analysis…" text.
  2. Sets an `analysisRunning = true` guard to prevent duplicate requests.
  3. Calls `POST /api/inspection/capture-dual {pending_id, image_a_b64, image_b_b64}`.
  4. On success: stores `DualInspectionOut` in `currentAnalysis` JS var, auto-advances to Stage 5.
  5. On failure: re-enables the button, clears guard, shows error alert with API detail message.
     No fabricated result is ever displayed.

**Stage 5 — Results:**
- Read-only display sections:
  - Transaction info card: number, farmer name, date/time, weight (g and kg).
  - Defect table: 6 rows, columns Type / Count / % / Class (badge) / Over?
  - Image pair: View A original | View A annotated | View B original | View B annotated
    (4 thumbnails, loaded from `backend/static/uploads/{path}`; links open full-size).
  - Grade banner: large Bootstrap badge, color-coded. Over-threshold red warning banner if flagged.
  - Pricing card: Commodity price, multiplier, Suggested Price/kg, Suggested Sample Value.
- "Continue to Receipt" button.

**Stage 6 — Receipt:**
- Receipt preview card styled to approximate the thermal print layout:
  ```
  CGI — Coffee Grade Identification
  ──────────────────────────────────
  Txn No : CGI-YYYYMMDD-XXXXXX
  Date   : YYYY-MM-DD HH:MM
  Farmer : [name]
  ──────────────────────────────────
  Grade  : [grade label]
  Weight : X.XXX kg
  Price/kg: PHP XXX.XX
  ──────────────────────────────────
  TOTAL  : PHP XXXX.XX
  ```
- Printer status indicator (initially blank).
- "Print Receipt" button → calls `POST /api/reports/transaction/{txn_id}/print`.
  - On `{status:"printed"}` → green success badge; button relabelled "Reprint".
  - On `{status:"failed"}` → red "Printer error — Retry" badge; button stays enabled for retry.
- "Complete Transaction" button (always enabled once Stage 6 is reached, independent of print):
  - Calls `PUT /api/transactions/{txn_id}` with body `{status: "completed"}`.
  - On success: closes modal, reloads the dashboard page.
- All interval timers cleared on modal `hidden.bs.modal` event.

**Todo List:**
- [ ] Keep PHP lines 1–27 (auth, farmer load) and lines 29–67 (farmer view) exactly as-is.
- [ ] Replace PHP lines 69–176 with: dashboard summary section + "Start Transaction" button +
  `<div class="modal fade" id="txn-modal">` containing the 6 stage panels.
- [ ] Replace JS lines 184–360 with a new `<script>` block implementing the functions listed
  in Expected Outcomes above. Key state variables:
  - `pendingId`, `txnNumber`, `txnId` (set at init and analysis completion).
  - `imageAb64`, `imageBb64` (set on accept in Stage 3).
  - `currentWeight` (set on Stage 2 continue).
  - `currentAnalysis` (set on Stage 4 success).
  - `weightPollInterval`, `hwStatusPollInterval` (cleared on stage change and modal close).
  - `analysisRunning = false` (guard flag).
- [ ] Ensure `modal.addEventListener('hidden.bs.modal', cleanupTimers)` clears all intervals.
- [ ] Image thumbnails in Stage 5 use `src="/static/uploads/{path}"` (same-origin Apache proxy).

**Relevant Context:**
- `frontend/assets/js/api.js` — `CGI_API.get(path)`, `.post(path, body)`, `.put(path, body)`.
- `frontend/assets/css/main.css` — `.cgi-step { animation: fadeIn … }`, 48 px min tap targets.
- `frontend/api.php` — `$farmers` array available as PHP variable; `APP_BASE` constant.
- Bootstrap 5 modal: `new bootstrap.Modal(el)`, `modal.show()`, `modal.hide()`,
  `modal._element.addEventListener('hidden.bs.modal', fn)`.

---

## Sub-Task 7 — Update Receipt Service & Print Status Tracking

**Status:** `[x] done`

**Intent:**
Update the thermal receipt to include the transaction number, and make the print endpoint
return a retry-friendly response (HTTP 200 with `status: "printed"|"failed"`) while
persisting print outcome to `transactions.print_status`.

**Expected Outcomes:**
- Receipt ESC/POS output includes a `Txn No : {txn_number}` line after the date.
- `POST /api/reports/transaction/{id}/print` always returns HTTP 200 with body
  `{"status": "printed"|"failed", "transaction_id": int, "detail": str|null}`.
- On success: `txn.print_status = 'printed'`, committed to DB.
- On exception: `txn.print_status = 'failed'`, committed to DB, exception message in `detail`.
- `TransactionOut` schema exposes `print_status` so the Receipt stage can reflect current state.

**Todo List:**
- [ ] In `backend/services/thermal_print.py` `print_receipt()`:
  - After the `Insp ID` line, add `printer.text(f"Txn No  : {inspection.txn_number or 'N/A'}\n")`.
- [ ] In `backend/routers/reports.py` `print_transaction_receipt()`:
  - Wrap `print_receipt(txn, db)` in try/except.
  - On success: `txn.print_status = 'printed'`; on exception: `txn.print_status = 'failed'`.
  - Commit after both branches.
  - Return `{"status": "printed"|"failed", "transaction_id": txn_id, "detail": ...}` with
    HTTP 200 in both cases (remove the `raise HTTPException(status_code=500)` pattern).
- [ ] Update `backend/schemas/transaction.py` `TransactionOut` to add `print_status` field.

**Relevant Context:**
- `backend/services/thermal_print.py` — `print_receipt()`, the `Insp ID` line is at line 54.
- `backend/routers/reports.py` — `print_transaction_receipt()` lines 56–69.
- `backend/schemas/transaction.py` — `TransactionOut` (to be read before editing).

---

## Sub-Task 8 — Integration Smoke Test Checklist

**Status:** `[x] done`

**Intent:**
Verify the complete six-stage workflow end-to-end and confirm that all existing features
remain unaffected.

**Expected Outcomes:**
- All six stages advance correctly.
- Every validation gate blocks premature progression (tested by deliberately skipping).
- Print failure in Stage 6 shows retry option; Complete Transaction still works.
- Transaction is marked Completed independently of print outcome.
- Annotated images appear in Stage 5 Results and Transaction History.
- `history.php`, `configuration.php`, `users.php`, and farmer dashboard view all work normally.
- `POST /api/inspection/capture` (Pi single-image endpoint) still responds correctly.

**Todo List:**
- [ ] Apply `database/migrations/001_six_stage_workflow.sql` to the dev MySQL database.
- [ ] Restart FastAPI backend (`uvicorn main:app --reload --port 8000`).
- [ ] Start Pi node server in simulation mode (`python pi_server.py`) or on real hardware.
- [ ] Open browser at `http://localhost/CGI/frontend/dashboard.php` as officer.
- [ ] Run the full 6-stage workflow: verify each stage, its gate, and its data in MySQL.
- [ ] Test each validation gate failure: missing farmer, weight out of range, missing View B,
  analysis error, printer offline.
- [ ] Verify Transaction History row includes txn_number, annotated image links, grade, price.
- [ ] Log in as farmer and verify the inspection appears in the farmer view.
- [ ] Confirm all other pages (history.php, configuration.php, users.php) are unaffected.

**Relevant Context:**
- Dev credentials: `admin@cgi.local` / `Admin@1234`.
- XAMPP Apache at `http://localhost/CGI/frontend/`.
- FastAPI docs at `http://localhost:8000/api/docs`.

---

## Implementation Order

Sub-tasks must be executed in this order (each depends on the previous):

```
ST-1  →  ST-2  →  ST-3  →  ST-4  →  ST-5  →  ST-6  →  ST-7  →  ST-8
 DB     Pi srv   HW API   Txn init  Dual     Frontend  Receipt  Smoke
schema           proxy    + weight  analyze   modal     print    test
```

ST-2 and ST-3 share no runtime dependency at development time, but ST-3 requires ST-2's
HTTP contract to be defined first.

---

## Key Design Decisions (Final)

| Decision | Choice | Rationale |
|---|---|---|
| In-progress state storage | `pending_transactions` table | `inspections` stays clean; only analyzed records written there |
| Data carry-forward on finalize | Copy `txn_number`, `farmer_id`, `created_at` from pending row | Preserves original timestamp and number as per spec |
| Printer gate in Prepare | Warning only, non-blocking | Receipt always generated digitally; print is retryable |
| Camera + Scale gate in Prepare | Hard block | Cannot weigh or capture without working hardware |
| Annotated image generation | At Analyze time, via `result.plot()` | Original images stay clean; annotations generated once on analysis |
| Annotated image storage | 4 new columns on `inspections` | Queryable, accessible in Transaction History |
| Two-view reconciliation | `round((A + B) / 2)` per defect and total | Per spec §4.2; clearly documented with comment |
| Start Analysis trigger | Manual button in Stage 4 | Officer reviews captured images before committing compute |
| Duplicate analysis guard | `analysisRunning` JS flag + disabled button | Prevents double YOLOv8 runs on slow connections |
| Print endpoint HTTP status | Always 200, `status` field in body | Allows retry without reloading the page |
| Transaction Completed vs print | Completed independently | Per spec §6.4; print is optional |
