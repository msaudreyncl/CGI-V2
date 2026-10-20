# Pi Node — Dependency Installation Guide

**Target OS:** Raspberry Pi OS Bookworm 64-bit (Debian 12)  
**Hardware:** Raspberry Pi 4 or 5, Pi Camera Module 3, HX711 load cell amplifier

Use the OS-provided Python 3.11 for this environment. Do not create this venv
with a separately installed Python 3.13: apt-installed Picamera2/libcamera modules
are built for the OS Python ABI and may not be importable from it.

---

## Why a two-phase install is required

| Package | Source | Reason |
|---|---|---|
| `picamera2` | `apt` only | Not on PyPI. Requires libcamera C-extensions tied to OS ABI. |
| `python3-libcamera` | `apt` only | C-extension dependency of picamera2; not available from pip. |
| `RPi.GPIO` | `apt` preferred | System package is pre-patched for the running Bookworm kernel. |
| `hx711==1.1.2.3` | `pip` | Pure-Python; safe to install from PyPI. |
| `requests==2.31.0` | `pip` | Pure-Python; safe to install from PyPI. |

A standard `python -m venv venv` is fully isolated and cannot see apt-installed
packages. The `--system-site-packages` flag makes the venv inherit the system Python
site-packages, bridging both sources cleanly.

---

## Step-by-step installation

### 1. Install system packages via apt

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-rpi.gpio python3-libcamera
```

### 2. Navigate to the pi_node directory

```bash
cd /home/pi/CGI/pi_node
```

### 3. Create the virtual environment

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

Your prompt will change to `(venv) pi@cgi-node:...`.

### 4. Install pip-only packages

```bash
pip install -r requirements.txt
```

Expected output:
```
Successfully installed hx711-1.1.2.3 requests-2.31.0
```

### 5. Verify all four libraries import correctly

```bash
python3 -c "from picamera2 import Picamera2; print('picamera2 OK')"
python3 -c "import RPi.GPIO; print('RPi.GPIO OK')"
python3 -c "from hx711 import HX711; print('hx711 OK')"
python3 -c "import requests; print('requests OK')"
```

All four lines must print `OK` with no errors before proceeding.

The current `pi_node` source has no DHT22 import or reader service. If a DHT22 is
added later, install the driver against the same OS Python/venv and add a hardware
smoke test here; no unused DHT package is installed by this project today.

---

## Troubleshooting

### `ImportError: No module named 'picamera2'` or `RPi`

The venv was created without `--system-site-packages`. Recreate it:

```bash
deactivate
rm -rf venv
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'hx711'` or `requests`

The pip install step was skipped or ran outside the active venv:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### `apt install python3-picamera2` says "Unable to locate package"

The package index is outdated. Run `sudo apt update` first, then retry.

On very old Raspberry Pi OS images (Bullseye or earlier), the package name is
`python3-picamera2` on Bookworm only. Upgrade to **Raspberry Pi OS Bookworm 64-bit**
via Raspberry Pi Imager — Bullseye does not ship Camera Module 3 support by default.

### Camera not detected — `RuntimeError: Camera is not enabled`

Enable the camera interface:
```bash
sudo raspi-config
# Interface Options → Camera → Enable → OK → Finish → Reboot
```

After rebooting, verify the camera is seen:
```bash
libcamera-hello --list-cameras
```

---

## Running the sensor node

**Interactive / development:**
```bash
source venv/bin/activate
python sensor_node.py --once
```

**Continuous loop (GPIO button or ENTER):**
```bash
source venv/bin/activate
python sensor_node.py
```

**As a systemd service (production):**

The `cgi-node.service` file already points to `venv/bin/python3` so no manual
activation is needed when running under systemd:

```bash
sudo cp cgi-node.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cgi-node
sudo systemctl start cgi-node
sudo systemctl status cgi-node
```

---

## After a fresh `git clone`

The `venv/` directory is not committed to Git (it is in `.gitignore`).
Run the full installation from Step 1 above every time you clone or re-image the Pi.
