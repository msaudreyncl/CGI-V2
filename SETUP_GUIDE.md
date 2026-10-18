# Coffee Grade Identification (CGI) — Complete Setup Guide

This guide walks through setting up the full CGI system from scratch on a Windows machine
running XAMPP. Follow every section in order.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Project Folder Placement](#2-project-folder-placement)
3. [Start XAMPP Services](#3-start-xampp-services)
4. [Database Setup](#4-database-setup)
5. [Environment Configuration .env](#5-environment-configuration-env)
6. [Python Virtual Environment](#6-python-virtual-environment)
7. [Install Python Dependencies](#7-install-python-dependencies)
8. [Fix the Admin Password](#8-fix-the-admin-password)
9. [Start the FastAPI Backend](#9-start-the-fastapi-backend)
10. [Verify Everything Works](#10-verify-everything-works)
11. [Log In to the Web UI](#11-log-in-to-the-web-ui)
12. [YOLOv8 Model Setup](#12-yolov8-model-setup)
13. [Raspberry Pi Node Setup](#13-raspberry-pi-node-setup)
14. [User and Role Management](#14-user-and-role-management)
15. [Troubleshooting](#15-troubleshooting)
16. [Quick-Start Checklist](#16-quick-start-checklist-daily-use)

---

## 1. System Requirements

### Server Machine (your laptop or PC)

| Software | Minimum Version | Download |
|---|---|---|
| XAMPP | 8.2+ | https://www.apachefriends.org |
| Python | 3.11 or 3.12 | https://www.python.org/downloads |

> During Python installation, tick **"Add Python to PATH"** before clicking Install.

XAMPP provides three things you need:
- **Apache** — serves the PHP frontend on port 80
- **MySQL** — the database on port 3306
- **PHP** — bundled with Apache, no separate install needed

### Raspberry Pi (sensor node — set up in Section 13)

| Hardware | Specification |
|---|---|
| Board | Raspberry Pi 4 or 5 |
| OS | Raspberry Pi OS Bookworm 64-bit |
| Camera | Pi Camera Module 3 |
| Scale | HX711 amplifier + 1 kg Straight Bar Load Cell |
| Screen | 7-inch LCD Touchscreen 1024x600 |

---

## 2. Project Folder Placement

The CGI project must live inside XAMPP's web root so Apache can serve the PHP files.

**XAMPP web root location:**
- Default C drive install: `C:\xampp\htdocs\`
- D drive install: `D:\xampp\htdocs\`

**Your project must be placed at:**
```
D:\xampp\htdocs\CGI\
```

Correct structure inside htdocs:
```
htdocs\
└── CGI\
    ├── backend\
    ├── frontend\
    ├── database\
    ├── models\
    ├── pi_node\
    ├── deployment\
    ├── .env.example
    ├── README.md
    └── SETUP_GUIDE.md
```

If your downloaded folder is named differently (e.g. `CGI-main`), rename it to `CGI`.

---

## 3. Start XAMPP Services

1. Open **XAMPP Control Panel** — right-click and Run as Administrator if needed
2. Click **Start** next to **Apache**
3. Click **Start** next to **MySQL**
4. Both rows should turn green

**Apache port 80 conflict (another program uses port 80):**
- Click Config → Apache → `httpd.conf`
- Find `Listen 80` and change it to `Listen 8080`
- Save, then click Start
- All frontend URLs in this guide become `http://localhost:8080/CGI/frontend/...`

**MySQL port 3306 conflict:**
- Open Windows Services (Win+R → type `services.msc` → Enter)
- Find any MySQL entry → right-click → Stop
- Then start MySQL from XAMPP Control Panel

---

## 4. Database Setup

### Step 4a — Open phpMyAdmin

Go to: `http://localhost/phpmyadmin`

Log in with:
- **Username:** `root`
- **Password:** leave blank (XAMPP default has no root password)

### Step 4b — Run schema.sql

1. Click the **SQL** tab at the top of phpMyAdmin
2. Open `D:\xampp\htdocs\CGI\database\schema.sql` in Notepad or VS Code
3. Press Ctrl+A to select all → Ctrl+C to copy
4. Click inside the phpMyAdmin SQL text box → Ctrl+V to paste
5. Click **Go**

A success message appears. A new `cgi_db` database shows in the left sidebar with 7 tables:

```
cgi_db
├── cooperatives
├── defect_results
├── farmers
├── inspections
├── pricing_config
├── transactions
└── users
```

### Step 4c — Run seed.sql

1. Make sure `cgi_db` is selected in the left sidebar
2. Click the **SQL** tab again
3. Open `D:\xampp\htdocs\CGI\database\seed.sql` in a text editor
4. Copy all → paste into the SQL tab → click **Go**

This inserts:
- 1 default cooperative named "Default Cooperative"
- 1 admin user with email `admin@cgi.local`
- 3 pricing multiplier rows (Extra Class, Class I, Class II)

### Step 4d — Verify the data was inserted

In phpMyAdmin: click `cgi_db` in the left sidebar → click `users` → click **Browse**

You should see one row:

| id | name | email | role | is_active |
|----|------|-------|------|-----------|
| 1 | System Admin | admin@cgi.local | admin | 1 |

---

## 5. Environment Configuration (.env)

The Python backend reads all settings from a `.env` file in the project root.

### Step 5a — Create the .env file

**In File Explorer:**
1. Open `D:\xampp\htdocs\CGI\`
2. Right-click `.env.example` → Copy
3. Right-click in the same folder → Paste
4. Right-click the new file → Rename → type `.env` → Enter

**In PowerShell:**
```powershell
cd D:\xampp\htdocs\CGI
copy .env.example .env
```

### Step 5b — Edit .env

Open `.env` in VS Code or Notepad and fill in your values:

```env
# Application
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=true

# Database — match your XAMPP MySQL settings
DB_HOST=localhost
DB_PORT=3306
DB_NAME=cgi_db
DB_USER=root
DB_PASSWORD=

# JWT — change this to any long random string
JWT_SECRET=cgi-thesis-2024-change-this-string
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480

# YOLOv8 model
YOLO_MODEL_PATH=models/cgi_yolov8.pt
YOLO_CONFIDENCE=0.50

# File storage
UPLOAD_DIR=backend/static/uploads

# Pricing API — leave PRICE_API_KEY blank to use the fallback price only
PRICE_API_URL=https://commodities-api.com/api/latest
PRICE_API_KEY=
PRICE_BASE_CURRENCY=PHP
PRICE_CACHE_TTL_SECONDS=3600
PRICE_FALLBACK_PHP_PER_KG=300.00

# Thermal printer — configure when hardware is connected
THERMAL_PRINTER_TYPE=network
THERMAL_PRINTER_HOST=192.168.1.100
THERMAL_PRINTER_PORT=9100

# CORS
CORS_ORIGINS=http://localhost,http://127.0.0.1
```

**Key things to check:**
- `DB_PASSWORD` — leave blank if XAMPP MySQL has no password (default). Set to your password if you configured one.
- `JWT_SECRET` — change to any random string. This signs login tokens.
- `PRICE_API_KEY` — leave blank for now. The system will use `PRICE_FALLBACK_PHP_PER_KG` instead.

---

## 6. Python Virtual Environment

A virtual environment keeps the project's Python packages isolated from the rest of your system.

Open **PowerShell** (search for it in the Start Menu):

```powershell
cd D:\xampp\htdocs\CGI

# Create the virtual environment (only once — skip if already done)
python -m venv venv

# Activate it
venv\Scripts\activate
```

Your prompt should now start with `(venv)`:
```
(venv) PS D:\xampp\htdocs\CGI>
```

> You must run `venv\Scripts\activate` every time you open a new PowerShell window
> before running any Python commands for this project.

---

## 7. Install Python Dependencies

With `(venv)` active, install all required packages:

```powershell
pip install -r backend\requirements.txt
```

This installs: FastAPI, Uvicorn, SQLAlchemy, PyMySQL, bcrypt, python-jose, ReportLab,
Ultralytics YOLOv8, OpenCV, Pillow, httpx, python-escpos, and more.

> This may take 5-15 minutes on first install — YOLOv8 and OpenCV are large packages.

Confirm the install succeeded:
```powershell
pip show fastapi
```
You should see `Name: fastapi` and a version number.

---

## 8. Fix the Admin Password

The `seed.sql` stores a pre-computed bcrypt hash that may not match your specific
Python and bcrypt version. Run the reset script to generate and store a fresh verified hash:

```powershell
# Make sure (venv) is active and you are in D:\xampp\htdocs\CGI
python database\reset_admin.py
```

Expected output:
```
Connecting to MySQL at localhost:3306/cgi_db...
Generated hash for 'Admin@1234'
Updated existing admin user (id=1)

Done. Login credentials:
  Email   : admin@cgi.local
  Password: Admin@1234
```

**If you see "Cannot connect to MySQL":**
- Confirm MySQL is green in XAMPP Control Panel
- Confirm `DB_PASSWORD` in `.env` is correct
- Try running `D:\xampp\mysql\bin\mysql.exe -u root -p` to test the connection manually

---

## 9. Start the FastAPI Backend

Open a **dedicated PowerShell window** and keep it open while using the system.
The backend must stay running for the web UI to work.

```powershell
cd D:\xampp\htdocs\CGI\backend
..\venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

> The `--reload` flag auto-restarts the server when you edit code.
> Remove it during thesis demonstrations for a more stable session.

---

## 10. Verify Everything Works

Check each component before opening the web UI.

### Check MySQL
Open `http://localhost/phpmyadmin` — phpMyAdmin should load without errors.

### Check Apache
Open `http://localhost` — the XAMPP welcome page should appear.

### Check FastAPI backend
Open `http://localhost:8000/api/health` in your browser.

Expected response:
```json
{"status": "ok", "version": "1.0.0"}
```

If this page does not load, the backend is not running — go back to Step 9.

### Check interactive API documentation
Open `http://localhost:8000/api/docs`

This page lists all API endpoints and lets you test them directly from the browser.

### Check PHP can reach the backend (optional)

Create a temporary test file at `D:\xampp\htdocs\CGI\frontend\test_api.php`:

```php
<?php
$ch = curl_init('http://localhost:8000/api/health');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$result = curl_exec($ch);
$code   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
echo "HTTP $code: $result";
```

Open `http://localhost/CGI/frontend/test_api.php`

Expected output: `HTTP 200: {"status":"ok","version":"1.0.0"}`

Delete this file after testing — it is not part of the system.

---

## 11. Log In to the Web UI

Open your browser and go to:
```
http://localhost/CGI/frontend/login.php
```

Default admin credentials:

| Field | Value |
|---|---|
| Email | `admin@cgi.local` |
| Password | `Admin@1234` |

After a successful login you will be redirected to the **Dashboard**.

> Change the admin password after first login.

### If login does not work

| Symptom | Fix |
|---|---|
| "Invalid email or password" | Run `python database\reset_admin.py` again |
| "URL not found" after login | Apache must be running; always access via `http://localhost/...` |
| Blank page | FastAPI backend must be running (Step 9) |
| PHP warning about `require_once` | A file path in PHP is wrong — check Step 15 |

---

## 12. YOLOv8 Model Setup

The New Inspection feature requires a trained YOLOv8 `.pt` model file. Without it the
backend starts normally but any inspection attempt will return a FileNotFoundError.

### Place the model file

Copy your trained model to:
```
D:\xampp\htdocs\CGI\models\cgi_yolov8.pt
```

### Required class labels

The model must be trained to detect exactly these 6 classes in this order:

| Class ID | Label |
|---|---|
| 0 | `black_bean` |
| 1 | `moldy_infested` |
| 2 | `immature` |
| 3 | `broken` |
| 4 | `dried_cherry` |
| 5 | `foreign_matter` |

This mapping is defined in `backend\services\detection.py` — `CLASS_ID_MAP`.
If your training used different class names or order, edit that dictionary to match.

### Update .env if the filename differs

```env
YOLO_MODEL_PATH=models/your_model_filename.pt
```

### Test the model loads

```powershell
cd D:\xampp\htdocs\CGI\backend
..\venv\Scripts\activate
python -c "from services.detection import _get_model; _get_model(); print('Model loaded OK')"
```

---

## 13. Raspberry Pi Node Setup

The Raspberry Pi is the physical sensor node. It reads the scale weight using the HX711
and captures the coffee sample image using the Pi Camera, then sends both to the backend
server over the local network.

### Step 13a — Flash Raspberry Pi OS

1. Download **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Insert a microSD card (16 GB or larger) into your computer
3. Open Raspberry Pi Imager:
   - **Choose OS:** Raspberry Pi OS (64-bit) — Bookworm
   - **Choose Storage:** your microSD card
   - **Click the gear icon** (Advanced Options):
     - Enable SSH
     - Set hostname: `cgi-node`
     - Set username: `pi` with a password you choose
     - Configure WiFi: enter your network SSID and password
4. Click **Write** and wait for it to finish
5. Insert the SD card into the Raspberry Pi and power it on
6. Wait 2 minutes for the first boot to complete

Find the Pi's IP address — check your WiFi router's admin page for connected devices,
or run `ping cgi-node.local` from PowerShell on your Windows machine.

### Step 13b — Wire the hardware

**HX711 to Raspberry Pi (BCM pin numbering):**

| HX711 Pin | Raspberry Pi Pin |
|---|---|
| VCC | Pin 2 (5V) |
| GND | Pin 6 (GND) |
| DT | GPIO 5 (Pin 29) |
| SCK | GPIO 6 (Pin 31) |

**Load cell to HX711:**
Follow the color code on your load cell datasheet.
Typical: Red = E+, Black = E-, White = A-, Green = A+

**Pi Camera Module 3:**
Connect the ribbon cable to the Camera port on the Pi board.
The blue side of the ribbon must face toward the USB ports.

### Step 13c — Enable camera and I2C

SSH into the Pi from PowerShell on your Windows machine:
```powershell
ssh pi@192.168.1.x
```
Replace `192.168.1.x` with your Pi's actual IP address.

Run the configuration tool:
```bash
sudo raspi-config
```

Navigate:
- Interface Options → Camera → Enable → OK
- Interface Options → I2C → Enable → OK
- Finish → select Yes to reboot

### Step 13d — Copy the Pi node files to the Pi

From PowerShell on your Windows machine:
```powershell
scp -r D:\xampp\htdocs\CGI\pi_node pi@192.168.1.x:/home/pi/CGI/
```

Alternatively use **WinSCP** (free GUI tool at https://winscp.net) to drag and drop files.

### Step 13e — Install Pi node dependencies

SSH back into the Pi after the reboot:
```bash
ssh pi@192.168.1.x
cd /home/pi/CGI/pi_node
pip install -r requirements.txt
```

### Step 13f — Configure the sensor node

```bash
cp config.ini.example config.ini
nano config.ini
```

Update these values:

```ini
[server]
# Your Windows server LAN IP address
# Run ipconfig on Windows, look for IPv4 Address under your WiFi adapter
SERVER_URL = http://192.168.1.10:8000

[load_cell]
HX711_DT_PIN  = 5
HX711_SCK_PIN = 6
CALIBRATION_FACTOR = 1.0   # Update after running calibration below
WEIGHT_MIN_G = 340
WEIGHT_MAX_G = 360

[camera]
RESOLUTION_WIDTH  = 1920
RESOLUTION_HEIGHT = 1080
AUTOFOCUS_WAIT    = 1.5

[gpio]
TRIGGER_BUTTON_PIN = 17
```

Save with Ctrl+X → Y → Enter.

### Step 13g — Calibrate the load cell

```bash
cd /home/pi/CGI/pi_node
python hx711_reader.py --calibrate
```

Follow the prompts:
1. Remove all weight from the scale → press Enter (sets the zero/tare point)
2. Place an object of known weight on the scale — for example a 350 g bag of rice
3. Type the exact known weight in grams → press Enter
4. The script prints a `CALIBRATION_FACTOR` — copy this number
5. Open `config.ini` → paste the value into `CALIBRATION_FACTOR` → save

Verify calibration:
```bash
python hx711_reader.py
```
Place your known weight and confirm the reading matches.

### Step 13h — Test the sensor node

Place a coffee sample on the scale, then:
```bash
python sensor_node.py --once
```

This reads the weight, captures an image, and sends both to the backend server.
Check the Uvicorn PowerShell window on your server — you should see an incoming POST request.

### Step 13i — Auto-start on boot (optional)

```bash
sudo cp /home/pi/CGI/pi_node/cgi-node.service /etc/systemd/system/
sudo systemctl enable cgi-node
sudo systemctl start cgi-node
```

The sensor node will now start automatically every time the Pi boots.

---

## 14. User and Role Management

### Create a Cooperative Officer account

1. Log in as Admin → click **Users** in the navigation bar
2. Click **+ Add User**
3. Fill in:
   - **Name:** Officer's full name
   - **Email:** their email address
   - **Password:** a temporary password they can change
   - **Role:** Cooperative Officer
4. Click **Create User**

### Create a Farmer account

Same steps but set **Role** to **Farmer**.

### Role permissions summary

| Feature | Admin | Officer | Farmer |
|---|---|---|---|
| Start new inspection | Yes | Yes | No |
| View all inspections | Yes | Yes | No |
| View own inspections only | — | — | Yes |
| Create transaction | Yes | Yes | No |
| View all transactions | Yes | Yes | No |
| View own transactions only | — | — | Yes |
| Download inspection PDF | Yes | Yes | Own only |
| Export transaction CSV | Yes | Yes | No |
| Print thermal receipt | Yes | Yes | No |
| Configure pricing multipliers | Yes | Yes | No |
| Manage users | Yes | No | No |
| View dashboard and charts | Yes | Yes | No |

---

## 15. Troubleshooting

### "Invalid email or password" when logging in

The bcrypt hash in the database does not match your Python/bcrypt version.

Fix:
```powershell
cd D:\xampp\htdocs\CGI
venv\Scripts\activate
python database\reset_admin.py
```

---

### "URL not found" or 404 error after logging in

The PHP redirect is sending you to the wrong path.

Fix:
- Always access the site via `http://localhost/CGI/frontend/login.php`
- Never open PHP files directly as `file:///D:/...` — they must go through Apache
- Confirm Apache is running (green) in XAMPP Control Panel

---

### FastAPI backend won't start — "error: [WinError 10048] Address already in use"

Port 8000 is being used by another process.

Fix — change the port in `.env`:
```env
APP_PORT=8001
```
Then start with:
```powershell
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

---

### "Cannot connect to MySQL" or "Access denied for user root"

Checklist:
1. Is MySQL Started (green) in XAMPP Control Panel?
2. Is `DB_PASSWORD` in `.env` correct? (Blank if XAMPP has no root password)
3. Test manually:
   ```
   Open D:\xampp\mysql\bin\ in File Explorer
   Double-click mysql.exe
   Press Enter when asked for password
   ```
   If you see the mysql> prompt, the connection works.

---

### "ModuleNotFoundError" when starting the backend

The virtual environment is not active or packages were not installed.

Fix:
```powershell
cd D:\xampp\htdocs\CGI
venv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
uvicorn main:app --reload
```

---

### "FileNotFoundError: models/cgi_yolov8.pt"

The trained YOLOv8 model file is missing.

Fix: Place your `.pt` file at `D:\xampp\htdocs\CGI\models\cgi_yolov8.pt`

The backend and all other features still work — only the inspection analyze endpoint
is unavailable until the model is placed.

---

### PHP warning about require_once — "Failed to open stream: No such file or directory"

A PHP file is looking for `api.php` at the wrong relative path.

Example error:
```
Warning: require_once(D:\xampp\htdocs\CGI\frontend/../api.php): Failed to open stream
```

Fix: Check the PHP file shown in the error.
The `require_once` path should be `__DIR__ . '/api.php'` (for files inside `frontend/`)
not `__DIR__ . '/../api.php'` (which goes one level up).

---

### PHP shows raw source code instead of a rendered page

You opened the PHP file directly in the browser as a file path.

Fix: Always access through Apache: `http://localhost/CGI/frontend/...`

---

### The web page cannot reach the backend — curl error or empty response from API

Checklist:
1. Is the Uvicorn backend running? Check the dedicated PowerShell window.
2. Test directly: open `http://localhost:8000/api/health` in the browser.
3. Enable curl in PHP if it is disabled:
   - Open `D:\xampp\php\php.ini` in a text editor
   - Search for `;extension=curl`
   - Remove the semicolon: `extension=curl`
   - Save the file → restart Apache in XAMPP Control Panel

---

### Pi sensor node sends data but the backend returns 401 Unauthorized

The Pi node token does not match the backend configuration.

Fix:
1. Add `PI_NODE_TOKEN=your-secret-token` to `.env` on the server
2. Set the same value in `pi_node/config.ini` under `[server] PI_NODE_TOKEN`
3. Restart the backend

---

### Dashboard or pages show "Unauthorized" errors after some time

The JWT login token has expired (default 480 minutes = 8 hours).

Fix: Log out and log back in.

---

## 16. Quick-Start Checklist (Daily Use)

Run through this every time you want to use the system:

```
XAMPP
[ ] Open XAMPP Control Panel
[ ] Start Apache     (wait for green)
[ ] Start MySQL      (wait for green)

Backend
[ ] Open a new PowerShell window
[ ] cd D:\xampp\htdocs\CGI\backend
[ ] ..\venv\Scripts\activate
[ ] uvicorn main:app --host 0.0.0.0 --port 8000 --reload
[ ] Keep this window open (do not close it)

Browser
[ ] Open http://localhost/CGI/frontend/login.php
[ ] Log in with your credentials

To stop the system
[ ] Press Ctrl+C in the Uvicorn PowerShell window
[ ] Stop Apache in XAMPP Control Panel
[ ] Stop MySQL in XAMPP Control Panel
```

---

*CGI System — Complete Setup Guide v1.0*
*Coffee Grade Identification — Thesis Project*
