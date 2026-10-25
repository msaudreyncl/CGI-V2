# HX711 measurement interpretation — 2026-10-25

Current behavior: range bypass only. Calibrated acquisition retains filtering,
noise checks and frontend stability gating. Missing verified calibration shows
“Calibration required” alongside raw ADC diagnostics. This supersedes the
initial acquisition-test bypass described in the historical observations below.

## Confirmed cause and data flow

BCM DT=5/SCK=6 → guarded HX711 channel A/gain 128 → persistent
ScaleWorker → Pi GET /weight → backend GET /api/hardware/weight →
Stage 2 in dashboard.js.

Previously sample_weight() skipped calibration verification in WEIGHT_TEST_MODE,
but still calculated (raw - ZERO_OFFSET) / CALIBRATION_FACTOR. The deployed
config has factor 1.0, offset 0, and no verified calibration. Consequently each
ADC count became one purported gram. The backend passed that number through,
and Stage 2 appended “g”. No repeated unit multiplication was found.

There is no 9999.9 g display cap in Stage 2: toFixed(2) formats precision only.
The existing transaction endpoint rejects magnitudes above 99999.99 g to fit
DECIMAL(7,2). That storage safeguard and schema are unchanged. Raw counts now
remain outside the weight transaction path.

## Behavior

The worker's measurement operation returns raw_adc (ADC counts) independently
of weight_g. Unverified/missing/invalid calibration produces weight_g=null,
calibrated=false, measurement_state=uncalibrated. Verified calibration uses the
existing signed factor/offset formula. No calibration, tare, factor adjustment,
clamping, invented readings or GPIO/channel/gain changes were performed.

The bypass now skips only the 340–360 g restriction. Both modes retain
verified ADC-to-gram conversion, filtering, gram noise checks and frontend
stability gating. Uncalibrated diagnostics continue reading individual ADC
conversions without treating them as grams. Raw-only readings cannot enable Continue or become stored grams.
The original gram-only reader now also requires verified calibration in test mode.

Raw acquisition still rejects failed/nonfinite/saturated conversions, bounds
attempts and applies clock timing guards. Single readings in test mode do not
establish stability: inspect a series of raw readings for physical diagnosis.

## Physical observations

Existing cgi-node service was active but the first HTTP probe timed out after
12 seconds. Restarted that service to load the fix; subsequent /weight response
reported scale=ready, camera=ready, simulated=false, raw_adc=2395780,
weight_g=null, calibrated=false, stable=false, in_range=false.

User stated a 290 g object was on the platform. Six successive readings from
13:45:05 to 13:45:14 Asia/Manila were:
2363493, 2363150, 2363807, 2364218, 2364817, 1181244 ADC counts.
No API errors occurred in this series. The last reading is a large jump, so
these results do not prove stable communication or a repeatable load response.
They are not gram measurements. No saturation was observed in that series.
Physical disconnection and return-to-empty checks require operator coordination.

## Files

Implementation: pi_node/hx711_reader.py, pi_node/hardware_runtime.py,
pi_node/pi_server.py, frontend/assets/js/dashboard.js, frontend/dashboard.php
(raw label fit within the existing panel and dashboard script cache version).
API contract documentation: backend/routers/hardware.py.
Regression checks: backend/tests/test_scale_readings.py,
backend/tests/test_hardware_workflow.py, backend/tests/test_pi_readiness_response.py,
backend/tests/hardware_frontend_check.py.

Existing History edits were left untouched. No database schema, camera capture,
YOLO, grading, pricing, History or receipt implementation was modified.

After the user confirmed removal, six readings from 13:48:00 to 13:48:09
Asia/Manila were 1897317, 1893546, 1897077, 1893040, 1893167, 1892387 counts.
All six returned uncalibrated/null grams without API errors. This is below the
loaded group, but an initial empty baseline was not recorded before the first
load, so it does not alone establish return-to-baseline repeatability.

## Software and display verification

- Scale/acquisition/readiness/hardware workflow pytest run: 69 passed; one
  broader existing workflow test reached the deployed missing-model YOLO bypass
  and failed its expectation that mocked detection was called. No YOLO code or
  deployed setting was changed.
- Standalone Chromium DOM harness passed, including raw 1,000,000 counts,
  uncalibrated status, Continue disabled/no grams saved, retained calibrated
  development bypass and normal Stage 2 behavior.
- A separate live check called the backend get_weight proxy against the real
  Pi service, then rendered the returned payload in the existing Stage 2 JS
  under isolated Chromium: “Raw Sensor Value: 2,378,995 ADC counts”; uncalibrated
  message shown, Continue disabled. This used an isolated template and API
  scaffolding; it was not a logged-in deployed browser session and created no
  production transaction.
- Python compilation and git diff --check passed.
- The remaining workflow test passed when rerun with
  YOLO_ALLOW_MISSING_MODEL=false for that test process only (1 passed). Thus
  all 70 selected cases passed across the main run and isolated rerun.

User placed the same 290 g object again. Six readings from 13:50:14 to
13:50:23 Asia/Manila were 2436297, 2427084, 2424625, 2423757, 2422753,
2420631 counts. Each returned null grams/uncalibrated without an API error.
This confirms another upward response relative to the empty group, with visible
downward drift. The two loaded groups differ, so repeatable measurement accuracy
has not been established and no counts-per-gram calibration was derived.

After the second removal, six readings from 13:51:10 to 13:51:19 Asia/Manila
were 1747755, 1738800, 1917153, 1735489, 1733317, 1730189 counts. All
returned null grams/uncalibrated without API errors. The final empty group did
NOT consistently return to the earlier 1.89 million baseline. Drift and jumps
remain visible. A physical/mechanical/electrical/timing cause cannot be isolated
from these readings alone; no hardware accuracy or stability claim is made.
No physical disconnect/unplug test was performed; software fault/timeout and
saturation guards were covered by regression tests. The initial real service
HTTP timeout remains an observed fault, not proof of a specific wiring issue.


## Follow-up: range-only bypass

Confirmed config remains unchanged: WEIGHT_TEST_MODE=true, hardware mode,
CALIBRATION_FACTOR=1.0, ZERO_OFFSET=0, no CALIBRATION_VERIFIED flag.
Thus no verified calibration is currently available. Historical backup factors
were not restored or assumed valid. No tare/calibration values were written.
The ADC-to-gram formula is applied once in the Pi measurement path. The backend
passes weight_g through and the frontend formats it; neither converts it again.

Removed the test-mode shortcut from the gram-only reader; the measurement
reader also always filters and checks gram spread when calibration is valid.
Stage 2 requires stability even with range bypass; a stable calibrated weight
outside 340–360 g may proceed. Uncalibrated raw readings cannot proceed and
show “Calibration required”. Existing backend, database and transaction logic
were preserved. Restarted cgi-node to load the measurement correction.

Follow-up changed implementation: pi_node/hx711_reader.py,
frontend/assets/js/dashboard.js, frontend/dashboard.php (script version).
Updated scale and Chromium regression checks as well.

Follow-up verification: 49 scale/sampling tests passed; 22 hardware workflow/
readiness tests passed with the existing missing-model bypass disabled only
inside the test process. Chromium Stage 2 checks passed with no JS errors,
including Calibration required, out-of-range calibrated weight acceptance, and
unstable-reading rejection. PHP syntax, Python compilation and whitespace
checks passed. Real restarted service returned raw_adc=2326973,
weight_g=null, calibrated=false, simulated=false, scale=ready at
2026-10-25T06:09:22.378493+00:00. This confirms live acquisition, not gram accuracy.
No backend transaction logic, database, calibration settings or other hardware
features were changed in this follow-up. No commit or push was performed.

## Follow-up: insufficient valid samples

Reproduced real Pi /weight failure at 14:11 Asia/Manila. Found a deterministic
recovery bug in raw_samples(): one-sample probes had four attempts, but every
rejected conversion requires six subsequent settling conversions before a valid
sample may be accepted. Such a probe could never recover within that budget.
Added six settling attempts to the bounded budget; retained the existing
four-second deadline, invalid/saturation rejection and six-conversion settling.
Failure messages now report received/requested samples, attempts, rejections
and remaining settling conversions. No fabricated fallback is used.

Changes in this follow-up: pi_node/hx711_reader.py and
backend/tests/test_scale_readings.py. Added tests for a rejected conversion
followed by recovery, pre-existing settling, and bounded persistent failure.
52 scale/sampling tests passed; Python compilation and whitespace checks passed.

Restarted cgi-node and recorded eight consecutive real responses from
14:12:45 to 14:12:55 Asia/Manila, all scale=ready without API errors:
3772887, 4586008, 4567866, 2324614, 4705698, 4757913, 4815393, 4842754 counts.
All retained weight_g=null and measurement_state=uncalibrated. Large raw changes
remain visible; this test establishes recovery/API availability, not stable
sensor behavior. The original conversion rejection's electrical/timing cause
was not identified. Calibration, backend/database/transaction logic, and other
hardware code were not changed. No commit or push was performed.

## Follow-up: all startup conversions rejected

The user reported received 0/6, attempts 30, rejected 30. Performed an exclusive
bounded direct driver diagnostic with cgi-node stopped and automatically started
again in a finally block. No calibration or application code was changed for
this diagnostic. Only one pi_server process was observed; no competing
sensor_node/hx711_reader/pigpio process was observed. vcgencmd get_throttled
returned 0x0. GPIO5 was input/high and GPIO6 output/low when inspected.

First initialization succeeded, with raw counts 5242929, 5247869, 5280842,
5279319, 5270746. Second initialization failed after 26 rejected conversions;
third initialization failed after all 30 were rejected. Captured exact driver
DEBUG rejection reasons: 56 positive saturation codes (8388607 / 0x7fffff),
one data-not-ready timeout, one clock-overrun rejection. Thus persistent
saturation is now directly observed, beyond the earlier software recovery-budget
bug. The cause of saturation (bridge/wiring/mounting/power or communication)
has not been isolated. Operator wiring and empty-platform confirmation requested.
Do not accept saturation as weight or suppress this hardware fault. Service was
restored after diagnostics; no commit or push was performed.

## Current implementation: authoritative transaction validity

This change completes the range-only bypass in the existing working tree.
The pinned local hx711 1.1.2.3 `_read` implementation was inspected: it returns
signed, two's-complement ADC counts, rejects saturation, and performs no gram
calibration. HEAD's test-mode reader bypassed CALIBRATION_VERIFIED and used
(raw - zero) / factor even with the deployed placeholder factor=1, zero=0.
This confirms the software reason counts could appear as million-level grams;
it does not diagnose the underlying physical instability.

- Pi conversion now has one implementation in read_measurement; the gram-only
  reader delegates to it. raw_counts is the explicit diagnostic field; raw_adc
  remains an alias for existing consumers. No automatic tare was introduced.
- Each fresh batch uses rolling medians of five valid raw conversions followed
  by a short mean. Existing MAD spike rejection and gram-spread rejection remain.
  MAX_SPREAD_G (existing default 0.5 g) also governs consecutive-read stability.
  This is an existing acceptance target, not a physically validated noise estimate.
  Observed historical drift/saturation cannot justify declaring this scale stable.
- services/scale_measurement.py supplies shared backend validity and gate rules.
  Calibration, connection, stability, finite grams and a timestamp no more than
  10 seconds old are mandatory. Simulation cannot authorize real transactions.
- PUT transaction/{id}/weight independently re-reads the Pi; submitted grams and
  timestamps do not authorize or override a measurement. The fresh actual grams
  are saved with the existing database precision. No schema migration is needed.
- Existing WEIGHT_TEST_MODE must be enabled in both backend environment and Pi
  configuration to bypass range; the API adds bypass_weight_range and validity
  fields without removing existing fields. Grading/pricing conversions remain
  grams / 1000 for kilograms.
- Frontend polling is serialized, generation-guarded and paced at 250 ms. It
  checks calibration, connection, stability and timestamps; a stalled poll
  expires the display and Continue gate. The UI labels range bypass separately.
- Calibration wizard and tare prompts now require the empty tray installed.
  Candidate calibration still saves only after stable loaded and zero-return
  verification, via the existing fsync + atomic replacement mechanism.

Software verification in this turn uses mocked ADC/device input and isolated
SQLite records. 77 scale/sampling/new-gate tests passed, including one-million
counts converted to 125/350 g with known factors/offsets, signed polarity,
calibration restart/rejection preservation, all specified range boundaries,
invalid/stale/disconnected readings, and completed transactions retaining
125 g as 0.125 kg with the unchanged pricing formula. Browser checks use the
existing PHP template and JavaScript with mocked APIs, not physical hardware.

Physical calibration is still required: current config has no verified
calibration. Do not restore historical backup factors or guess sensitivity.
Investigate the recorded saturation/drift (connections, bridge excitation,
mounting and GPIO timing), collect stable empty-tray/known-mass references,
verify return to zero and an independent known mass, and assess the configurable
spread tolerance against those observed data. Accurate live grams have NOT
been physically verified by this turn. Existing History changes were untouched.

Final checks: 21 additional hardware/readiness regressions passed; the separate
browser calibration test through authenticated backend + mocked Pi HTTP passed;
the isolated Chromium harness passed all assertions with no JS errors, including
125 g bypass ON/OFF, 350 g either mode, boundaries and stale measurement blocking.
An additional status test verifies instability remains distinct from read failure.
This totals 100 unique passing pytest cases across the targeted runs. PHP syntax,
Python compilation and git diff --check also passed. The ordinary TestClient run
hung in sandbox startup; these API checks passed outside that restriction using
the same isolated SQLite/mock fixtures. No production test transactions created.

Reloaded the existing cgi-node service. The backend runs under uvicorn --reload
(cgi-backend.service is inactive); its health endpoint returned HTTP 200. A real
read-only Pi GET /weight after restart returned HTTP 200, raw_counts=639871,
weight_g=null, calibrated=false, measurement_state=uncalibrated, stable=false,
simulated=false. This confirms live raw acquisition and honest invalid-calibration
reporting only. No tare/calibration or physical gram accuracy test was performed.

Files involved in this completion: pi_node/hx711_reader.py, pi_node/pi_server.py,
pi_node/config.ini.example, pi_node/INSTALL.md; backend/services/scale_measurement.py,
backend/routers/hardware.py, backend/routers/transaction_workflow.py;
frontend/assets/js/dashboard.js, frontend/dashboard.php;
backend/tests/test_scale_readings.py, backend/tests/test_hardware_workflow.py,
backend/tests/test_weight_gate_validity.py, backend/tests/hardware_frontend_check.py;
and this report. Pre-existing hardware_runtime/readiness edits were retained;
unrelated History edits were not changed. No schema migration, commit or push.

## Recurring readiness failure: exclusive physical diagnostic

For the reported received 0/1, attempts 10, rejected 10, settling remaining 6
failure, temporarily stopped cgi-node and restored it in a finally block after a
bounded direct-driver diagnostic. No calibration, tare, gain/channel, acquisition
code or hardware configuration changed. First initialization produced raw counts
3092925, 3145422, 3749055, 3394839. Second initialization failed at received 0/6,
attempts 30, rejected 29, settling remaining 6. Captured driver DEBUG reasons
contained 31 positive saturation codes (8388607 / 0x7fffff); no data-ready timeout
or clock-overrun debug reason was recorded in this diagnostic. This does not
exclude acquisition corruption or isolate a wiring/mechanical/electrical cause.

Only one pi_server process was found; no standalone hx711_reader/sensor_node or
pigpiod process was found by the targeted process check. vcgencmd get_throttled
reported 0x0; this does not measure the HX711 analog/excitation supply. Service
was restored active. GPIO snapshots after worker cleanup cannot establish the
pin configuration during acquisition. Next step requires operator confirmation
of the unloaded tray state, bridge wiring and load-cell mounting/capacity.
