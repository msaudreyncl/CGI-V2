# Weight stage implementation

The HX711 package installed under pi_node/venv returns signed two's-complement
ADC counts from `_read`; it does not return grams. The oversized display came
from test mode permitting unverified placeholder calibration (factor 1, zero 0).
Counts were consequently labelled grams. No second conversion was found.

`pi_node/hx711_reader.py` is the sole ADC-to-gram conversion authority:
(filtered counts - ZERO_OFFSET) / CALIBRATION_FACTOR. Signed factors are valid;
missing, zero, nonfinite or unverified calibration cannot produce usable grams.
Calibration writes remain atomic and only occur after load/zero verification.
Tare preserves the factor and saves only a stable empty-tray reference. Entering
Weight never tares. The operator must explicitly confirm the empty tray.

A rolling median of five conversions and short average reject brief spikes.
The Pi now uses a recent window rather than just two matching requests.
MAX_SPREAD_G, STABILITY_DURATION_S, UNSTABLE_AFTER_S and SAMPLE_NOISE_FLOOR_G
are documented in pi_node/config.ini.example. Defaults are starting acceptance
settings, not physically validated noise measurements. Calibration/stability
checks never repair defective hardware.

The existing WEIGHT_TEST_MODE configuration is retained as a range-only bypass;
both backend environment and Pi configuration must enable it. Backend responses
expose bypass_weight_range, sample_present and weight_gate_passed. Both modes
require real connected, calibrated, finite, fresh, stable grams above the noise
floor. Signed/zero readings may be displayed but never accepted as samples.

Continue re-reads and validates the authoritative Pi measurement and saves those
grams, ignoring submitted grams/bypass flags. The UI uses the accepted response.
Polling is serialized and generation guarded; leaving Weight stops its loop.
Returning clears captures and requires confirmation again. Tare/calibration
invalidate unanalysed pending weights; analysed records remain immutable through
the weight endpoint and require a new transaction to change the sample.
Inspection, transaction, pricing, Results and receipt continue using the saved
sample. UI development simulation cannot authorize the Weight stage.

## Deployment

Apply database/migrations/003_weight_measurement_metadata.sql once to the existing
application database before loading this backend version. It adds one nullable
TEXT column to pending_transactions; it does not modify existing weights or
completed records. This column is necessary because pending transactions had no
metadata field. Acceptance saves timestamp, actual weight and range-bypass usage;
analysis copies these to the existing inspections.notes field. Existing/new
installations must run migrations in numeric order. ORM-created test databases
include the column automatically. Migration 003 was subsequently applied to the configured live database to
resolve the reported startup failure. The application account lacked ALTER
permission, so local database administration access added the nullable column.
The normal application account then passed all required schema checks.
Services were not restarted by this fix.

Then reload the backend and Pi service and refresh the dashboard (asset version 7).
No calibration values, production transactions, or unrelated History edits were
changed by this turn.

## Files

- pi_node/hx711_reader.py, pi_node/pi_server.py, pi_node/config.ini.example:
  conversion, filtering, tare/calibration preservation, timed stability/noise.
- backend/services/scale_measurement.py, backend/routers/hardware.py:
  shared server validation and invalidation after a zero/calibration change.
- backend/routers/transaction_workflow.py, backend/routers/inspection.py,
  backend/models/pending_transaction.py, database/migrations/003_weight_measurement_metadata.sql:
  authoritative acceptance, persistent provenance and sample lifecycle locks.
- frontend/assets/js/dashboard.js, frontend/dashboard.php:
  status/range guidance, placeholders, polling lifecycle, tare and accepted grams.
- backend/tests/test_weight_gate_validity.py, test_weight_stability_window.py,
  test_hardware_workflow.py, hardware_frontend_check.py; retained scale/sampling
  and readiness regressions cover the existing ADC implementation.

## Verification and physical work

Focused pytest checks use mocked ADC/Pi input, isolated SQLite, fake clocks and
stubbed detection/pricing/printers. They cover million-count conversion, signed
polarity, spike/noise rejection, tare persistence, failed calibration preservation,
range boundaries, range-only bypass, empty/negative/nonfinite/stale/disconnected
readings, forged client weights, metadata persistence, reacceptance/invalidation,
post-analysis locks, actual grams in Results, history and thermal receipt output.
Chromium runs the actual dashboard JavaScript at 800x480 using substituted APIs;
it is not a physical touchscreen or production browser session. PHP syntax,
Python compilation and git whitespace checks are also performed.

No physical hardware verification was performed in this turn. Earlier observations
in pi_node/HX711_MEASUREMENT_FIX.md are historical, not verification of these new
changes. The recorded saturation/drift needs physical investigation. Verify the
wiring, bridge excitation, mounting and acquisition timing; obtain stable empty
tray and known-mass references; verify return to zero and an independent mass;
then tune the stability duration, spread and sample floor from real observations.
Do not guess a calibration factor or restore an unverified historical value.

Final software result: 112 focused pytest cases passed in the consolidated run.
The separate Chromium dashboard harness passed with no JavaScript page errors.
Python compilation, PHP syntax and git diff --check passed. Pytest emitted one
existing Starlette/AnyIO deprecation warning. No physical measurement or printer
output was tested.

## Temporary Stage 2 sensor acquisition mode (current testing configuration)

WEIGHT_SENSOR_TEST_MODE=true is now enabled in the backend .env and Pi config.ini.
This is separate from the retained range-only WEIGHT_TEST_MODE option. Set the
new switch false in both places, reload the backend, and restart cgi-node to
restore the original Stage 2 acceptance rules. Examples default the new mode off.
The Pi service was restarted to activate acquisition mode; no calibration/tare
was performed, and saved factors/offsets were not changed.

In this temporary mode, one valid physical ADC conversion is displayed without
median/gram-stability acceptance gates. Verified calibration is applied once if
available; otherwise the display explicitly labels ADC counts. Numerical values
are rendered without decimal truncation or clamping. Existing low-level driver
fault and invalid ADC conversion handling remains; faults never generate values.
The actual connection status is independent of the Continue gate.

Continue is enabled for raw, calibrated, negative, zero, unstable, large, stale
or unavailable readings. Backend confirmation attempts a fresh physical read;
if unavailable it preserves the latest server-observed diagnostic and timestamp,
or null if no reading exists. Client-supplied grams/mode flags cannot override
server data. Existing weight_metadata stores the unit-labelled diagnostic without
DECIMAL limits; weight_g stays null. Capture is allowed, but analysis/pricing
continues to require an accepted gram measurement through the unchanged existing
analysis gate. Raw counts are never passed off as transaction grams.

This turn does not change schema, History, camera, detection, grading or pricing.
Production transactions were not created for verification. Tests use isolated
SQLite records; optional LIVE_HX711_TEST=1 uses the real Pi acquisition endpoint.

Temporary mode verification: 128 focused software cases passed across the combined
run and the two fixture-isolation reruns; the opt-in live case also passed.
The Chromium harness passed raw/calibrated -500, 0, 9999.9, 100000 and 1000001,
unstable input, explicit disconnection and Stage 2 -> Stage 3 with no JS errors.
Real authenticated backend acquisition returned 1323460, 1212879 and 1211430
ADC counts; a subsequent reading of 1210380 was saved with raw units in isolated
SQLite metadata, not grams. The later live browser run encountered actual ADC
conversion failures, displayed a placeholder/error and still reached Stage 3
through the real backend acceptance endpoint. That run used Prepare/auth/profile
scaffolding, actual Stage 2 JS/backend/Pi requests and isolated SQLite; camera
preview was excluded. It did not establish continuous physical sensor reliability,
physical load-response accuracy or a successful real camera capture. No physical
unplug test was performed; disconnection is covered with mocks. The real module
still intermittently rejects conversions; no hardware guard was suppressed.

Files changed for temporary mode: .env (local mode activation), .env.example,
backend/config.py, backend/services/scale_measurement.py,
backend/routers/hardware.py, backend/routers/transaction_workflow.py,
backend/schemas/pending_transaction.py, frontend/assets/js/dashboard.js,
frontend/dashboard.php (asset cache version only), pi_node/hx711_reader.py,
pi_node/pi_server.py, pi_node/config.ini, pi_node/config.ini.example,
backend/tests/test_sensor_testing_mode.py,
backend/tests/hardware_frontend_check.py, backend/tests/test_hardware_workflow.py,
and this report. Existing unrelated working-tree edits were preserved.

## Image analysis without sample pricing in sensor testing

Sensor-testing transactions that completed Stage 2 may now submit both captured
images for the unchanged detection and ASEAN count-based grading pipeline even
when weight_g is null. The server requires the enabled sensor-testing setting
and server-recorded sensor-test metadata; an unprepared transaction or ordinary
transaction without grams still fails validation. Client flags do not enable it.

Successful test analysis returns grade, defect counts/percentages and annotated
image paths, with null sample_weight_g/transaction ID/prices. The test result and
original unit-labelled sensor reading are retained in pending weight_metadata;
no inspection or sale row is created because those require actual grams. The
pending sample is marked analyzed and locked against reweighing. Pricing is not
called. Detection failures still return errors and remove partially written
images. Existing trained-model-unavailable behavior remains capture-only with
no invented grade. Results and the test-summary preview display raw units and
Unavailable prices rather than NaN. Closing a sensor test does not complete a
sale, and the print handler does not request a priced receipt.

Changed for this extension: backend/routers/inspection.py,
backend/schemas/inspection.py, frontend/assets/js/dashboard.js,
frontend/dashboard.php (asset version 9), backend/tests/test_sensor_testing_mode.py,
backend/tests/hardware_frontend_check.py, and this report. No schema, model,
grading algorithm, pricing engine, camera or History changes were made.

51 focused backend tests passed (one opt-in physical check skipped), including
successful mocked inference/annotations, missing model, inference failure cleanup,
unprepared rejection, no pricing/sale writes, retained metadata and normal weight
acceptance. The actual configured trained model is missing at
/var/www/html/CGI-V2/models/cgi_yolov8.pt; no .pt/.onnx/.engine replacement was found
in the application model/backend/Pi directories outside virtual environments.
Thus real image inference is not physically verified. Install the actual trained
coffee-defect model or point YOLO_MODEL_PATH to its existing location; no generic
or simulated model was installed and no grade was fabricated.
The expanded Chromium harness also passed: a sensor-only analysis result renders
its real grade/defects, raw ADC unit and unavailable prices; the summary contains
no NaN or sale total, printing is blocked, and closing the test succeeds without
a sale completion request. Browser APIs/inference were substituted for this
check. PHP syntax, Python compilation and git diff --check passed.
