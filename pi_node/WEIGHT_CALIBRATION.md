# HX711 weight accuracy and calibration

## Website calibration in Step 2

Use **Calibrate scale** beside the existing tare control. Follow the native browser
prompts: remove removable loads → measure zero → enter the accurately known mass
in grams → place that mass → remove it for the zero-return check. Settings are
saved only after repeated loaded measurements and zero return pass the existing
noise tolerance. Afterwards verify an independent known mass, put the empty tray
back, and use **Tare empty scale** before adding beans. The layout and other
transaction stages are unchanged.

The existing authenticated `POST /api/hardware/weight` proxies to Pi `POST /weight`.
It retains `action: tare` and now supports `calibration_zero`, `calibration_load`
(with `known_g` and `token`), `calibration_finish`, and `calibration_cancel`.
A zero request returns an unpredictable session token; later actions require it.
The session expires after ten minutes. Cancelling, expiring, invalid reference
masses, and failed verification leave the persisted calibration unchanged. Only
one calibration can run at a time, and tare is blocked until it finishes/cancels.
Simulation cannot save a hardware calibration. Weight POST timeout is 55 seconds
for the two loaded reference acquisitions; camera timeouts are unchanged.

A responding but uncalibrated HX711 reports readiness with a null weight so the
existing Prepare gate can reach Weight for calibration. A disconnected ADC still
reports an error. During calibration readings remain null and Continue is disabled.
No new calibration overwrites `config.ini` until verification succeeds; the
existing atomic config writer and continuous GPIO worker are reused.

Software tests include Chromium running the actual Step 2 script through the
actual authenticated API and local Pi HTTP server, with only ADC counts and
camera readiness substituted. They exercise zero, known mass, save, tray tare,
live grams and the 340–360 g gate. Additional checks cover negative polarity,
failed zero return, cancellation, expiry, and persistence by reopening config.
These controlled samples establish software behavior, not hardware accuracy.

A read-only hardware diagnostic on 2026-10-23 reported an unstable acquisition,
then raw mean 1636369.1703703704 with spread 88140 counts across 30 samples and
two statistical outliers rejected. No known mass was available for that check.
The running Pi HTTP service was unavailable at port 5000. No calibration/tare was
written to the deployed config, and physical calibration remains unverified.
Do not infer gram accuracy or the physical cause of noise from this raw check.

## Audit findings and limits

Step 1 farmer selection and the existing APIs/database structures are unchanged.
The old scale path started a new process, initialized/reset the ADC and discarded
startup samples on **every** read. Tare, empty calibration and loaded calibration
were measured by different ADC instances. This repeatedly introduced startup
settling and GPIO setup into what should be continuous measurements.

The old code averaged every sample without outlier/spread checks and accepted a
single empty/loaded average as a calibration. It accepted a tiny or noisy load
response as long as it was nonzero, without checking repeatability or returning
to zero. Tare also accepted a single average. Comparing consecutive averages
could call a noisy scale stable.

At audit time the local config contained factor **-4.978260869565218 counts/g**.
A 100-count raw error with this factor becomes about **20.09 g** of weight error.
The sign alone is not a fault: reversed load-cell signal polarity legitimately
requires a negative factor. The actual wiring polarity, raw noise, mounting and
accuracy must be checked on the Pi; software inspection cannot establish which
physical issue caused the earlier -524.16 g result. The previous 23 g calibration
was saved without the verification now required.

## What changed

- One persistent HX711 worker owns GPIO for reads and tare. It reinitializes only
  after faults, pin changes or service restart. Factor/offset reload each request.
- The pinned hx711==1.1.2.3 GPIO bit reader is reused with bounded retries
  (see the [upstream driver](https://raw.githubusercontent.com/mpibpc-mroose/hx711/master/hx711/__init__.py)). Valid
  integer zero and -1 samples are accepted; false/invalid/saturated conversions
  never become weights. No additional GPIO library or hardware endpoint is added.
- Each new batch uses median/MAD outlier filtering. At least 80% of samples must
  agree; the retained spread must be ≤ `MAX_SPREAD_G` (default 0.5 g). Load changes
  are not averaged with old batches. Two consistent polls are still required to
  proceed. Sensor faults return unavailable; moving/noisy batches return
  `weight_g: null`, `stable: false`, `in_range: false` and `measurement_state: unstable`.
- Tare measures three batches and verifies a fresh fourth before atomically saving
  the new `ZERO_OFFSET`. Failed tare leaves the previous offset unchanged.
- Calibration measures repeated bare-platform/loaded references, checks noise and
  signal strength, rechecks the load, and requires return to the original zero.
  It derives the factor's sign from the measured load response. The saved settings
  include the known mass, timestamp, bare-platform reference and verification flag.
- The UI displays signed grams with two decimals, hides invalid/noisy measurements,
  invalidates stale requests during tare and never enables Continue for unstable
  or out-of-range samples. The 340–360 g requirement is unchanged.

**Recalibrate once after deploying this change.** Old factors without
`CALIBRATION_VERIFIED=true` are not trusted for grams or tare. Do not manually set
that flag to bypass the wizard. The existing config is preserved until successful
calibration. A valid signed factor is never automatically inverted or replaced.

## Exact Raspberry Pi commands

Use the deployed Pi checkout and its Pi venv. Stop the service so it is the only
GPIO owner during CLI calibration. Leave the sensor/mount stationary and let raw
readings settle after power-up. The load cell must support the tray plus beans
without overload; its mount must allow the sensing element to flex as designed.

```bash
cd /var/www/html/CGI-V2/pi_node
sudo systemctl stop cgi-node
cp config.ini config.ini.before-weight-calibration
# Inspect GPIO and sampling settings; DT/SCK are BCM numbers, not physical pins:
grep -iE 'hx711_.*pin|readings_to_average|calibration_factor|zero_offset' config.ini
# Raw diagnostic, including spread over three batches (Ctrl+C exits):
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py --raw
```

Default wiring remains DT=BCM5 (physical 29), SCK=BCM6 (physical 31), common ground,
and the module-appropriate supply with 3.3 V GPIO logic. Power off before altering
wiring. Do not guess load-cell wire colors; check E+/E−/A+/A− against its datasheet.

```bash
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py --calibrate
```

Follow all prompts:

1. Remove the tray and **all removable loads**; leave the fixed weighing platform.
2. Press Enter for the bare-platform reference.
3. Enter an accurately known mass in grams, preferably near **350 g**. Entering
   `350` does not make an unknown object a 350 g reference.
4. Place **only that known mass** on the fixed platform, let it settle, press Enter.
5. After loaded verification, remove the mass, wait, press Enter for zero return.
6. Confirm `Verified calibration and bare-platform zero saved to config.ini`.
   Any error means no new calibration was saved. Fix mounting, interference,
   wiring or supply noise before repeating; do not increase tolerances to mask it.

If the tray is permanently fixed to the platform, it belongs to the calibrated
platform zero and cannot subsequently be weighed separately without removing it
and establishing a new bare reference.

```bash
# Bare platform should now measure approximately zero. Ctrl+C exits.
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py
```

Place the empty tray: its weight should now appear. To tare it while the service
is stopped:

```bash
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py --tare
# Leave the empty tray in place and follow the prompt.
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py
```

The displayed value is always `(filtered_raw - ZERO_OFFSET) / signed_factor`.
There is no automatic zero, zero clamp, or negative-value suppression. Small
residual signed values around zero are actual measured noise/drift, not forced to
0.00. The configured spread threshold is an acceptance gate, not a guarantee of
absolute 0.5 g accuracy. A stable but incorrectly known calibration mass still
produces an inaccurate scale; verify with independent known masses.

## Service, API and frontend check

```bash
sudo systemctl start cgi-node
sudo systemctl status cgi-node --no-pager
curl --max-time 20 -sS http://127.0.0.1:5000/weight
```

If the immediate request fails while starting, retry after status reports the
server is listening. To tare via the running service (tray present, beans removed):

```bash
curl --max-time 30 -sS -H 'Content-Type: application/json' \
  -d '{"action":"tare"}' http://127.0.0.1:5000/weight
curl --max-time 20 -sS http://127.0.0.1:5000/weight
curl --max-time 20 -sS http://127.0.0.1:5000/weight
```

Reload the dashboard. Leave Development Mode off, start a transaction normally,
and verify Step 2 against these same API readings:

| Action | Expected result |
|---|---|
| Calibrated bare platform | Approximately 0 g |
| Place empty tray | Positive tray weight |
| Tare with tray, no beans | Approximately 0 g after fresh readings |
| Add independent known mass | That mass in grams, excluding tray |
| Remove mass, retain tray | Approximately 0 g |
| Remove tared tray too | Negative tray weight; this is legitimate |
| Verified 339 g / 361 g | Continue disabled |
| Verified 340 g / 350 g / 360 g, stable | Continue enabled within inclusive limits |
| Moving platform/noisy readings | No numeric weight, or Stabilizing for changing valid batches; Continue disabled |
| Sensor disconnected (power off before changing wires) | Unavailable, no stale numeric weight; Continue disabled |
| Service restart with unchanged tray/mount | Same persisted tare reference; verify actual zero after settling |

Do not tare while beans are present. To start over with a bare-platform zero after
previously taring a tray, remove every removable load and run `--tare` (or the same
API tare action). This deliberately establishes a new reference; the service does
not guess whether the tray is present.

Scale reads allow 8 seconds including cold startup; raw collection has a bounded
4-second sample window. Reference collection allows 20 seconds and tare 25 seconds
for repeated verification. The existing backend GET timeout is 15 seconds and
POST timeout 30 seconds. Camera readiness and scale reads run concurrently so a
cold/disconnected scale does not consume the camera's readiness budget.

## Automated verification

```bash
# Repository root, backend test environment:
venv/bin/python -m pytest backend/tests/test_scale_readings.py backend/tests/test_hardware_workflow.py backend/tests/test_integration.py backend/tests/test_grading.py -q
venv/bin/python backend/tests/hardware_frontend_check.py
```

Raw sample sequences and fake GPIO cover the scale driver/filter/tare/calibration.
Local Pi HTTP plus authenticated FastAPI tests cover signed readings, instability,
recovery and saved transaction weight. Chromium checks the actual dashboard script
with substituted API responses at 800×480, including 2-decimal values, tare,
negative loads, noise/errors and Continue gating. These tests do not establish
physical accuracy, noise, thermal drift, load-cell mounting, GPIO timing under
production load, or performance on the deployed Pi. Complete the known-weight
checks above before using this system for real transactions.

### Clock timing recovery

The diagnostic may report a clock timing overrun when Linux scheduling delays a
GPIO pulse. The adapter guards the gain-selection pulses rather than using the
pinned driver's recursive recovery loop. An elapsed pulse of 50 microseconds or
more is conservatively rejected (elapsed time includes both GPIO calls; this is
not a direct oscilloscope measurement of the high interval). The clock is always
returned low. After an invalid conversion or timing fault, partial sample batches
are abandoned and six fresh conversions are discarded before measuring again.
This prevents startup/recovery conversions from contaminating a reference or tare.

The [HX711 datasheet](https://cdn.sparkfun.com/datasheets/Sensors/ForceFlex/hx711_english.pdf)
specifies the clock timing and power-down behavior. Python GPIO timing remains
subject to scheduling; the guard detects/rejects overruns and cannot guarantee
hardware-timed pulses. If errors persist under deployment load, do not mask them
with a larger tolerance or a fabricated zero. Investigate GPIO timing, supply and
mounting separately from recalibration.


## Terminal-first noise recovery (pending physical verification)

The CLI now keeps running after acquisition faults, printing `ACQUISITION ERROR`
and retrying with a delay. `UNSTABLE` identifies a responding sensor whose samples
cannot be trusted. Neither state prints a replacement numeric weight. Ctrl+C exits.
Grams require two fresh batch results within 0.5 g (or the configured tolerance)
and less than 10 seconds apart. A load change or error invalidates that agreement;
no previous value is printed as a new measurement. This consistency gate does
not establish absolute accuracy or exclude slow drift.
Raw references include `samples` and `rejected`: these count completed batches'
conversions and statistical outliers, not invalid electrical conversions or all
failed attempts. Each reference covers three fresh batches; no stale load is mixed
into the next reference. This is bounded batch sampling, not a background ring buffer.

Calibration references retry up to six times within a 45-second request budget.
Loaded and zero-return verification print spread and reference shift separately.
The existing 0.5 g default tolerance and zero-return requirement are unchanged.
Tare retries at most three complete verified attempts within a 60-second request
budget. Worker shutdown can add cleanup time after an acquisition timeout.
A failed attempt does not save settings; permanent drift still prevents calibration.
If the initial empty reference is persistently noisy, restart only after correcting
that condition: it is not silently replaced after loading the known mass.

Run only the terminal commands above with `cgi-node` stopped. Record empty → known
292 g → empty three times, then calibrate, verify independent known masses, and
check tray/tare/removal. A printed stable value is not proof of absolute accuracy.
Do not restart the service for website integration until these physical checks pass.
No website or endpoint behavior was changed for this terminal recovery update.
