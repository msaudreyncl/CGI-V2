# Temporary HX711 acquisition test — 2026-10-23

Temporary mode uses BCM DT=5 / SCK=6, hardware mode, and the existing signed
factor/zero conversion. It takes a fresh valid ADC conversion without averaging,
outlier filtering, calibration verification, stability gating or sample-range gating.
Invalid conversions, timing failures and disconnects still fail; no fallback weight
is supplied. Tare/calibration paths and normal validation remain available.
No physical calibration or tare was performed.

Configuration: `load_cell.WEIGHT_TEST_MODE=true` in pi_node/config.ini and
`WEIGHT_TEST_MODE=true` in backend .env. Both default false in examples.
Disable both flags to restore normal Step 2 restrictions. Backend settings load
at process startup; restart the existing backend process to pick up the .env flag.
The existing cgi-node service was restarted and verified against /weight.

Verified physical results:
- Bounded standalone GPIO read: -119432.89344978165 g.
- Updated existing GET http://127.0.0.1:5000/weight returned scale=ready,
  simulated=false, weight_test_mode=true, weight_g=-142269.38253275107,
  measured_at=2026-10-23T04:42:29.995106+00:00, stable=false, in_range=false.
- These values use an unverified existing conversion and do not establish accuracy.
- The sandbox itself cannot access /dev/mem; physical checks required permitted
  execution outside it. The earlier running service reported acquisition failure.
  Successful reads do not prove reliable wiring or sustained communication.

Software results:
- Targeted scale + hardware workflow pytest run: 60 passed, one existing
  Starlette deprecation warning. Uses substitute ADC/camera data and a test DB.
- Standalone scale tests: 42 passed.
- Chromium DOM harness: passed, no JavaScript errors; includes negative unstable
  readings in test mode, disconnect/recovery, and retained normal workflow checks.
- Python compilation and git diff whitespace checks: passed.
- Node CLI unavailable; Chromium exercised the JavaScript instead.

Storage and deployment limitations:
- Existing pending_transactions.weight_g is DECIMAL(7,2): two decimal precision,
  maximum absolute value 99999.99 g. The actual observed readings exceed this.
  They display unchanged apart from the existing two-decimal screen format, and
  are logged at full received precision. Confirming an over-capacity reading logs
  its value, sensor timestamp and transaction ID, then returns an explicit 422;
  it does not clamp, silently overflow or advance the transaction.
- In-capacity readings are stored on the current pending transaction as before.
  No timestamp column or history table exists: transaction created_at is preserved;
  sensor measured_at and receipt/save times are retained in service/backend logs.
  Logs follow the host's existing retention policy. No schema changes were made.
- No real production transaction was created for testing. Authenticated proxy and
  transaction persistence were verified with test fixtures, including -123.456789
  received unchanged and -123.46 stored according to the existing column precision.
- Full deployed backend/browser verification and physical unplug/replug testing
  remain outstanding. Browser development simulation must be switched off.

Files changed for this task (other pre-existing edits were retained):
.env, .env.example, backend/config.py, backend/routers/hardware.py,
backend/routers/transaction_workflow.py, frontend/assets/js/dashboard.js,
pi_node/config.ini, pi_node/config.ini.example, pi_node/hx711_reader.py,
pi_node/pi_server.py, backend/tests/test_scale_readings.py,
backend/tests/test_hardware_workflow.py, backend/tests/hardware_frontend_check.py,
and this report. No schema, camera implementation, UI layout, or APIs added.
