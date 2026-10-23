# Camera Module 3 + HX711 integration

## Existing architecture and API audit

The touchscreen uses `frontend/assets/js/dashboard.js` through the existing
JWT-authenticated FastAPI hardware proxy. The Pi runs **pi_server.py**:

| Browser/backend API | Pi operation | Purpose |
|---|---|---|
| GET `/api/hardware/status` | GET `/weight` | Independent camera/scale readiness; printer stays non-blocking |
| GET `/api/hardware/weight` | GET `/weight` | Grams, consecutive-reading stability (≤0.5 g), 340–360 g range |
| POST `/api/hardware/weight` `{ "action": "tare" }` | POST `/weight`, same body | Zero the empty tray, save offset |
| POST `/api/hardware/capture` `{ "view": "A" }` (or B) | POST `/capture` | Picamera2 full-resolution JPEG |
| POST `/api/hardware/capture` `{ "view": "A", "preview": true }` | POST `/capture`, same body | Fresh JPEG preview, maximum 640×360; never saved as A/B |
| POST `/api/transaction/init` | Existing backend workflow | Creates pending transaction |
| PUT `/api/transaction/{id}/weight` | Existing backend workflow | Validates and saves grams |
| POST `/api/inspection/capture-dual` | Existing YOLO service | Analyzes A/B, saves images and inspection/transaction |

No new URL paths or database structures are needed. Tare adds a POST operation
to the existing weight resource. Weight is carried from `pending_transactions.weight_g`
to `inspections.sample_weight_g` and `transactions.weight_kg`. Both accepted views
are sent together to the existing dual analysis endpoint; retakes remain available.

The old `sensor_node.py` is a legacy single-image push utility, not the touchscreen
transaction service. Do not run it beside pi_server.py: both would own the GPIO/camera,
and its old token/payload does not implement the current authenticated A/B workflow.

## Scale sampling cadence

The shared HX711 reader spaces acquisition attempts by at least 12.5 ms (80 Hz)
for weight reads, tare, and calibration, including across consecutive batches.
Set the HX711 module's RATE input HIGH/DVDD for its native 80 Hz conversion mode;
software pacing does not change the chip's hardware conversion rate.
`READINGS_TO_AVERAGE = 10` is a sample count, not a frequency: a ten-sample
batch takes about 0.125 seconds, and a three-batch calibration reference about
0.375 seconds. GPIO delays or retries can reduce the achieved rate.

## Hardware and OS

Use Raspberry Pi OS Bookworm **64-bit**, OS Python 3.11, Camera Module 3 and
an HX711 with a load cell suitable for a 350 g sample. Shut down the Pi before
connecting the CSI ribbon; use the correct ribbon for the Pi model.
Keep the normal libcamera camera stack (`camera_auto_detect=1`); do not enable
legacy camera mode. No camera preview window is opened, preserving touchscreen space.

Default BCM wiring:

| HX711 | Raspberry Pi |
|---|---|
| DT / DOUT | GPIO5, physical pin 29 |
| SCK / PD_SCK | GPIO6, physical pin 31 |
| GND | GND, physical pin 6 |
| VCC / digital supply | 3.3 V, physical pin 1 (module must support 3.3 V operation) |

Connect the cell's excitation/signal wires to E+/E−/A+/A− according to its datasheet;
wire colors vary. GPIO inputs must use 3.3 V logic. For modules with separate analog
and digital supplies follow the module datasheet and keep the digital supply at 3.3 V.

## Install (Pi 4)

These commands assume the deployment path used by the existing service:
`/var/www/html/CGI-V2` and service user `cgi`. Substitute your checkout path and user if different.

```bash
sudo apt update
sudo apt install -y python3-venv python3-picamera2 python3-libcamera python3-rpi.gpio python3-pil rpicam-apps
cd /var/www/html/CGI-V2/pi_node
python3 -m venv --system-site-packages venv
venv/bin/python -m pip install -r requirements.txt
# Only on a fresh checkout without config.ini:
test -f config.ini || cp config.ini.example config.ini
venv/bin/python -c "from picamera2 import Picamera2; import RPi.GPIO; from hx711 import HX711; print('Drivers imported')"
rpicam-hello --list-cameras
```

For **Pi 5**, use the RPi.GPIO-compatible lgpio implementation instead of the
Pi 4 RPi.GPIO package (the code keeps the existing `RPi.GPIO` API):

```bash
sudo apt remove -y python3-rpi.gpio
sudo apt install -y python3-rpi-lgpio
```

Edit `config.ini`: set `[hardware] MODE = hardware` (add the section if absent),
verify DT/SCK pins, and later save calibration with the wizard below. On the
backend, set the existing `.env` `PI_NODE_URL=http://<PI_LAN_IP>:5000`, then restart
the backend using your deployment's normal procedure. The browser continues to
use the existing backend URL and JWT, never the Pi URL directly.

The Pi HTTP service has no user authentication of its own, as in the original
architecture; expose port 5000 only on the trusted device/backend network.

## Calibration and tare (exact commands)

Stop the service before CLI calibration so there is one GPIO owner:

```bash
cd /var/www/html/CGI-V2/pi_node
sudo systemctl stop cgi-node
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py --calibrate
```

The updated wizard requires a **bare-platform reference**, a known mass, loaded
verification and a return-to-zero check. Remove the removable tray for calibration;
then weigh the empty tray and tare it separately. Recalibrate once after deploying
the verified-calibration update; older factors are not silently trusted.

See [WEIGHT_CALIBRATION.md](WEIGHT_CALIBRATION.md) for the complete commands,
noise/polarity audit, tray/beans test sequence and verification limits.

```bash
# Raw counts/spread without requiring calibration (Ctrl+C to exit):
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py --raw
# Signed grams after calibration (Ctrl+C to exit):
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py
# Tare the empty tray while the service is stopped:
CGI_HARDWARE_MODE=hardware venv/bin/python hx711_reader.py --tare
# Camera smoke test:
CGI_HARDWARE_MODE=hardware venv/bin/python camera_capture.py /tmp/cgi-camera.jpg
```

At runtime use **Tare empty scale** in Step 2 with the tray present and beans
removed. Tare persists only after stable batches and a fresh zero verification.
Do not run CLI calibration while the service is active.

## Start the touchscreen hardware service

```bash
cd /var/www/html/CGI-V2/pi_node
sudo cp cgi-node.service /etc/systemd/system/cgi-node.service
sudo systemctl daemon-reload
sudo systemctl enable --now cgi-node
sudo systemctl restart cgi-node
sudo systemctl status cgi-node --no-pager
sudo journalctl -u cgi-node -n 50 --no-pager
curl --fail http://127.0.0.1:5000/weight
curl --fail -H 'Content-Type: application/json' -d '{"view":"A"}' http://127.0.0.1:5000/capture > /tmp/cgi-view-a.json
```

`cgi-node.service` now launches pi_server.py and forces hardware mode. Ensure its
User/WorkingDirectory/ExecStart match the checkout and that user has camera/GPIO
access (normally the `video` and `gpio` groups on Raspberry Pi OS).

## Development and failure behavior

On non-Pi hosts `MODE=auto` retains simulation. On a Raspberry Pi auto uses real
hardware; missing drivers or disconnections never trigger dummy data. To explicitly
simulate on either host (stop the hardware service first if it owns port 5000):

```bash
cd /var/www/html/CGI-V2/pi_node
CGI_HARDWARE_MODE=simulation venv/bin/python pi_server.py
```

The dashboard's existing Development Mode remains a separate UI-only simulation
without database writes. To exercise real API/database paths with simulated Pi
hardware, leave dashboard Development Mode **off** and run the simulated Pi server.
API responses mark simulated readings/captures. These are test images, not meaningful
YOLO samples.

Scale reads have an 8-second deadline; verified tare allows 25 seconds; camera readiness has an 8-second
first-frame deadline and capture/preview requests a 20-second deadline. Failed
camera workers are terminated and reaped, then recreated on the next request.
Scale and camera operations have separate locks. Readiness uses a short (2-second)
cache and verifies an actual JPEG frame rather than only sensor enumeration.

The existing Pi server owns one persistent Picamera2 child process for both live
preview and still capture. It releases the device after 15 seconds with no camera
requests, or when the server stops. Stop `cgi-node` before using terminal camera
tools so there is only one camera owner. No additional service or URL is required.
The browser requests a fresh preview JPEG 500 ms after the preceding request
completes (actual refresh rate depends on the Pi and network). Requests do not
overlap. Preview pauses during the existing countdown/capture, and stops on leaving
Capture or closing the transaction. Preview frames never replace accepted A/B
images or enter YOLO. On errors the stale preview is hidden and subsequent requests
retry the camera; capture failures leave the affected view available for retry.

### Focus configuration for the working camera

In `pi_node/config.ini`, under the existing `[camera]` section:

```ini
FOCUS_MODE = manual
LENS_POSITION =
```

Manual mode is the default when these keys are absent, matching the successful
terminal `--autofocus-mode manual` test. A blank `LENS_POSITION` preserves the
camera's initial position; inspect sharpness at the mounted tray distance.
To set a verified fixed focus, supply a lens position in dioptres (approximately
1 / distance in metres). Only use `FOCUS_MODE = auto` after the autofocus terminal
and Picamera2 tests succeed; `auto` focuses before each accepted still, while
`continuous` keeps autofocus running during preview. Autofocus errors do not
silently fall back to manual mode. Configuration changes reopen the camera worker
on the next request; restart the service for a clean deployment.

The browser still sends only the two accepted full-resolution JPEGs and pending
transaction ID to `/api/inspection/capture-dual`. As before, Analyze persists both
images and corresponding transaction data through the existing database workflow.
The standalone `camera-test/` directory is for terminal tests; transaction image
storage stays in the backend's configured `UPLOAD_DIR`.

Stable weight requires a filtered within-batch spread of at most 0.5 g and two
consecutive readings within 0.5 g. This is not a metrology certification; verify
physical accuracy with independent known masses under deployment load.

## End-to-end verification on the Pi touchscreen

1. Sign in as officer/admin; disable dashboard Development Mode. Select a farmer,
   check preparation items, and check hardware. Camera and scale must be ready;
   printer warning remains non-blocking.
2. Continue to Weight, tare the empty tray, then place 350 g. Confirm live grams
   stabilize. Below 340 g and above 360 g must block Continue; both boundaries pass.
3. Continue and verify the live image changes when you move a hand above the tray.
   Capture/accept A, physically reorient the sample, then capture/accept B.
   Verify focus, previews, retake, and both accept actions before Analyze.
4. Analyze with the deployed trained YOLO model. Verify both raw/annotated images,
   transaction number, sample grams and transaction kilograms in results/history.
5. Disconnect the scale/camera between attempts. Recheck must report the affected
   device unavailable; scale polling/capture must show errors without advancing on
   stale weight or fabricating an image. Reconnect and retry.
6. Verify controls and modal scrolling on the physical 7-inch display at its actual
   resolution; the existing layout is retained with one large tare button.

Automated tests use simulated Pi HTTP, authenticated backend routes, temporary SQLite,
and mocked detection/pricing to verify A/B delivery and weight persistence. They do
not validate physical wiring, autofocus quality, calibrated accuracy, deployed MySQL,
trained-model accuracy, or touchscreen ergonomics.

```bash
# From repository root, using the backend environment:
venv/bin/python -m pytest backend/tests/test_hardware_workflow.py backend/tests/test_integration.py -q
```

Implementation follows the [Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
for autofocus/capture. The pinned [HX711 package](https://pypi.org/project/hx711/1.1.2.3/)
provides `get_raw_data(times=...)`; it does not provide the former reader's
`tare()` or `get_current_weight()` methods.

Optional reproducible frontend behavior check (Chromium must already be installed):

```bash
venv/bin/python -m pip install pytest==8.3.5 playwright==1.51.0
venv/bin/python backend/tests/hardware_frontend_check.py
```

The browser check loads the existing template/JavaScript at an 800×480 viewport
with substituted PHP-generated values, Bootstrap modal behavior and API responses.
It verifies readiness gating, weight range/disconnect recovery, tare, saved grams,
and A/B acceptance/retake behavior without accessing production data. Physical
layout and the deployment's Bootstrap assets still require the touchscreen check above.


### Camera Capture deployment commands (existing checkout)

```bash
cd /var/www/html/CGI-V2/pi_node
# Stop the service before terminal camera tests; skip if not yet installed.
sudo systemctl stop cgi-node
mkdir -p camera-test
CGI_HARDWARE_MODE=hardware venv/bin/python camera_capture.py camera-test/cgi-camera.jpg
sudo cp cgi-node.service /etc/systemd/system/cgi-node.service
sudo systemctl daemon-reload
sudo systemctl enable --now cgi-node
sudo systemctl restart cgi-node
curl --fail -H 'Content-Type: application/json' -d '{"view":"A","preview":true}' http://127.0.0.1:5000/capture > /tmp/cgi-live-preview.json
```

Keep dashboard Development Mode off for hardware use. The existing backend `.env`
`PI_NODE_URL` must point at this Pi (`http://127.0.0.1:5000` if backend and Pi node
run on the same machine). Restart the backend after deploying the hardware proxy
change and reload the dashboard to load the updated JavaScript.
