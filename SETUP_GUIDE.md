# Coffee Grade Identification (CGI) — Complete Setup Guide

This guide covers setting up the full CGI system from scratch on either a
**Windows machine (XAMPP)** or a **Linux machine (Raspberry Pi OS / Debian/Ubuntu)**.
Follow the section that matches your server environment, then continue from
Section 12 onward — those sections apply to both platforms.

---

## Table of Contents

**Server Setup — choose your platform:**
- [Part A — Windows Server (XAMPP)](#part-a--windows-server-xampp)
  - [A1. System Requirements (Windows)](#a1-system-requirements-windows)
  - [A2. Project Folder Placement](#a2-project-folder-placement)
  - [A3. Start XAMPP Services](#a3-start-xampp-services)
  - [A4. Database Setup (Windows)](#a4-database-setup-windows)
  - [A5. Environment Configuration (Windows)](#a5-environment-configuration-windows)
  - [A6. Python Virtual Environment (Windows)](#a6-python-virtual-environment-windows)
  - [A7. Install Python Dependencies (Windows)](#a7-install-python-dependencies-windows)
  - [A8. Fix the Admin Password (Windows)](#a8-fix-the-admin-password-windows)
  - [A9. Start the FastAPI Backend (Windows)](#a9-start-the-fastapi-backend-windows)

- [Part B — Linux Server (Raspberry Pi OS / Debian / Ubuntu)](#part-b--linux-server-raspberry-pi-os--debian--ubuntu)
  - [B1. System Requirements (Linux)](#b1-system-requirements-linux)
  - [B2. Project Folder Placement (Linux)](#b2-project-folder-placement-linux)
  - [B3. Install Apache, MySQL, and PHP](#b3-install-apache-mysql-and-php)
  - [B4. Database Setup (Linux)](#b4-database-setup-linux)
  - [B5. Environment Configuration (Linux)](#b5-environment-configuration-linux)
  - [B6. Python Virtual Environment (Linux)](#b6-python-virtual-environment-linux)
  - [B7. Install Python Dependencies (Linux)](#b7-install-python-dependencies-linux)
  - [B8. Fix the Admin Password (Linux)](#b8-fix-the-admin-password-linux)
  - [B9. Start the FastAPI Backend (Linux)](#b9-start-the-fastapi-backend-linux)

**Common — both platforms:**
- [10. Verify Everything Works](#10-verify-everything-works)
- [11. Log In to the Web UI](#11-log-in-to-the-web-ui)
- [12. YOLOv8 Model Setup](#12-yolov8-model-setup)
- [13. Raspberry Pi Sensor Node Setup](#13-raspberry-pi-sensor-node-setup)
- [14. User and Role Management](#14-user-and-role-management)
- [15. Troubleshooting](#15-troubleshooting)
- [16. Quick-Start Checklist (Daily Use)](#16-quick-start-checklist-daily-use)

---

# Part A — Windows Server (XAMPP)

## A1. System Requirements (Windows)

| Software | Minimum Version | Download |
|---|---|---|
| Windows | 10 or 11 | — |
| XAMPP | 8.2+ | https://www.apachefriends.org |
| Python | 3.11 or 3.12 | https://www.python.org/downloads |

> During Python installation, tick **"Add Python to PATH"** before clicking Install.

XAMPP provides three things you need:
- **Apache** — serves the PHP frontend on port 80
- **MySQL** — the database on port 3306
- **PHP** — bundled with Apache, no separate install needed

---

## A2. Project Folder Placement

The CGI project must live inside XAMPP's web root so Apache can serve the PHP files.

**XAMPP web root location:**
- Default C drive install: `C:\xampp\htdocs\`
- D drive install: `D:\xampp\htdocs\`

**Place the project at:**
```
D:\xampp\htdocs\CGI\
```

Correct structure inside `htdocs\`:
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

If your downloaded or cloned folder is named differently (e.g. `CGI-main` or `CGI-V2`),
rename it to `CGI`.

**Clone from GitHub directly into the right place:**
```powershell
cd D:\xampp\htdocs
git clone https://github.com/YOUR_ORG/CGI.git CGI
```

---

## A3. Start XAMPP Services

1. Open **XAMPP Control Panel** — right-click → Run as Administrator if needed
2. Click **Start** next to **Apache**
3. Click **Start** next to **MySQL**
4. Both rows should turn green

**Apache port 80 conflict (another program uses port 80):**
- Click Config → Apache → `httpd.conf`
- Find `Listen 80` → change to `Listen 8080` → Save → Start
- All frontend URLs in this guide become `http://localhost:8080/CGI/frontend/...`

**MySQL port 3306 conflict:**
- Press Win+R → type `services.msc` → Enter
- Find any existing MySQL entry → right-click → Stop
- Then start MySQL from XAMPP Control Panel

---

## A4. Database Setup (Windows)

### Step A4a — Open phpMyAdmin

Go to: `http://localhost/phpmyadmin`

Log in with:
- **Username:** `root`
- **Password:** leave blank (XAMPP default has no root password)

### Step A4b — Run schema.sql

1. Click the **SQL** tab at the top of phpMyAdmin
2. Open `D:\xampp\htdocs\CGI\database\schema.sql` in Notepad or VS Code
3. Press Ctrl+A → Ctrl+C to copy everything
4. Click inside the phpMyAdmin SQL box → Ctrl+V to paste
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

### Step A4c — Run seed.sql

1. Make sure `cgi_db` is selected in the left sidebar
2. Click the **SQL** tab again
3. Open `D:\xampp\htdocs\CGI\database\seed.sql` in a text editor
4. Copy all → paste into the SQL tab → click **Go**

This inserts:
- 1 default cooperative named "Default Cooperative"
- 1 admin user (`admin@cgi.local`)
- 3 pricing multiplier rows (Extra Class, Class I, Class II)

### Step A4d — Verify the data was inserted

In phpMyAdmin: click `cgi_db` → click `users` → click **Browse**

You should see one row:

| id | name | email | role | is_active |
|----|------|-------|------|-----------|
| 1 | System Admin | admin@cgi.local | admin | 1 |

---

## A5. Environment Configuration (Windows)

The Python backend reads all settings from a `.env` file in the project root.

**In PowerShell:**
```powershell
cd D:\xampp\htdocs\CGI
copy .env.example .env
```

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

# Pi node URL (update to Pi's LAN IP when the sensor node is set up)
PI_NODE_URL=http://localhost:5000

# Thermal printer — configure when hardware is connected
THERMAL_PRINTER_TYPE=network
THERMAL_PRINTER_HOST=192.168.1.100
THERMAL_PRINTER_PORT=9100

# CORS
CORS_ORIGINS=http://localhost,http://127.0.0.1
```

**Key things to check:**
- `DB_PASSWORD` — leave blank if XAMPP MySQL has no password (default)
- `JWT_SECRET` — change to any long random string; this signs login tokens
- `PRICE_API_KEY` — leave blank; the system will use `PRICE_FALLBACK_PHP_PER_KG`

---

## A6. Python Virtual Environment (Windows)

A virtual environment keeps the project's Python packages isolated from the rest of your system.

Open **PowerShell**:

```powershell
cd D:\xampp\htdocs\CGI

# Create the virtual environment (only once)
python -m venv venv

# Activate it
venv\Scripts\activate
```

Your prompt should now start with `(venv)`:
```
(venv) PS D:\xampp\htdocs\CGI>
```

> Run `venv\Scripts\activate` every time you open a new PowerShell window
> before running any Python commands for this project.

---

## A7. Install Python Dependencies (Windows)

With `(venv)` active:

```powershell
pip install -r backend\requirements.txt
```

This installs: FastAPI, Uvicorn, SQLAlchemy, PyMySQL, bcrypt, python-jose, ReportLab,
Ultralytics YOLOv8, OpenCV, Pillow, httpx, python-escpos, and more.

> This may take 5–15 minutes on first install — YOLOv8 and OpenCV are large packages.

Confirm the install succeeded:
```powershell
pip show fastapi
```
You should see `Name: fastapi` and a version number.

---

## A8. Fix the Admin Password (Windows)

The `seed.sql` stores a pre-computed bcrypt hash that may not match your Python/bcrypt
version. Run the reset script to generate and store a fresh verified hash:

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

---

## A9. Start the FastAPI Backend (Windows)

Open a **dedicated PowerShell window** and keep it open while using the system.

```powershell
cd D:\xampp\htdocs\CGI\backend
..\venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

> The `--reload` flag auto-restarts the server when you edit code.
> Remove it during demonstrations for a more stable session.

**→ Continue to [Section 10 — Verify Everything Works](#10-verify-everything-works)**

---

# Part B — Linux Server (Raspberry Pi OS / Debian / Ubuntu)

> These steps apply to any Debian-based Linux. Commands are tested on
> **Raspberry Pi OS Bookworm 64-bit** (Debian 12) and **Ubuntu 22.04 LTS**.

## B1. System Requirements (Linux)

| Software | Minimum Version | Install method |
|---|---|---|
| Apache2 | 2.4+ | `apt` |
| MySQL / MariaDB | 8.0+ / 10.6+ | `apt` |
| PHP | 8.1+ | `apt` |
| Python | 3.11 or 3.12 | `apt` |
| Git | any | `apt` |

---

## B2. Project Folder Placement (Linux)

The CGI project must live inside Apache's web root so it can serve the PHP files.

**Default Apache web root:** `/var/www/html/`

**Place the project at:** `/var/www/html/CGI/`

**Clone from GitHub:**
```bash
cd /var/www/html
sudo git clone https://github.com/YOUR_ORG/CGI.git CGI
sudo chown -R $USER:www-data CGI
sudo chmod -R 755 CGI
```

Or copy files manually via SCP/SFTP.

Correct structure inside `/var/www/html/`:
```
html/
└── CGI/
    ├── backend/
    ├── frontend/
    ├── database/
    ├── models/
    ├── pi_node/
    ├── deployment/
    ├── .env.example
    ├── README.md
    └── SETUP_GUIDE.md
```

---

## B3. Install Apache, MySQL, and PHP

```bash
sudo apt update && sudo apt upgrade -y

# Apache web server
sudo apt install -y apache2

# MySQL (or MariaDB — fully compatible)
sudo apt install -y mysql-server

# PHP and required extensions
sudo apt install -y php php-mysql php-curl php-json php-mbstring libapache2-mod-php

# Python and pip
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Git (if not already installed)
sudo apt install -y git
```

### Enable and start services

```bash
sudo systemctl enable apache2 mysql
sudo systemctl start apache2 mysql
```

### Secure MySQL (Raspberry Pi OS / Debian)

```bash
sudo mysql_secure_installation
```

When prompted:
- Set a root password (remember it — you'll need it for `.env`)
- Remove anonymous users: **Yes**
- Disallow root login remotely: **Yes**
- Remove test database: **Yes**
- Reload privilege tables: **Yes**

> **Note:** On Raspberry Pi OS the default MySQL auth plugin for root uses
> `auth_socket`, which means you must use `sudo mysql` without a password locally.
> If you plan to connect from Python via `pymysql`, create a dedicated database user
> (Step B4b below).

### Enable Apache mod_rewrite (needed for PHP routing)

```bash
sudo a2enmod rewrite
sudo systemctl restart apache2
```

### Allow Apache to serve from `/var/www/html/CGI/`

Edit the default site config to allow `.htaccess` overrides:

```bash
sudo nano /etc/apache2/sites-available/000-default.conf
```

Add or update the `<Directory>` block inside `<VirtualHost>`:

```apache
<Directory /var/www/html>
    AllowOverride All
    Require all granted
</Directory>
```

Save (Ctrl+X → Y → Enter), then:
```bash
sudo systemctl restart apache2
```

---

## B4. Database Setup (Linux)

### Step B4a — Create the database

Log in to MySQL:
```bash
# On Raspberry Pi OS / Debian — root uses auth_socket, so use sudo:
sudo mysql

# On Ubuntu with a root password set:
mysql -u root -p
```

Inside the MySQL shell:
```sql
CREATE DATABASE cgi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Step B4b — Create a dedicated MySQL user

Still inside the MySQL shell:
```sql
CREATE USER 'cgiuser'@'localhost' IDENTIFIED BY 'your_strong_password';
GRANT ALL PRIVILEGES ON cgi_db.* TO 'cgiuser'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> Replace `your_strong_password` with a real password. You will put this in `.env`.

### Step B4c — Run schema.sql

```bash
mysql -u cgiuser -p cgi_db < /var/www/html/CGI/database/schema.sql
```

Enter the password when prompted. A success exit (no error output) means it worked.

Verify the tables were created:
```bash
mysql -u cgiuser -p cgi_db -e "SHOW TABLES;"
```

Expected output:
```
cooperatives
defect_results
farmers
inspections
pricing_config
transactions
users
```

### Step B4d — Run seed.sql

```bash
mysql -u cgiuser -p cgi_db < /var/www/html/CGI/database/seed.sql
```

Verify:
```bash
mysql -u cgiuser -p cgi_db -e "SELECT id, name, email, role FROM users;"
```

Expected:
```
+----+--------------+-----------------+-------+
| id | name         | email           | role  |
+----+--------------+-----------------+-------+
|  1 | System Admin | admin@cgi.local | admin |
+----+--------------+-----------------+-------+
```

---

## B5. Environment Configuration (Linux)

```bash
cd /var/www/html/CGI
cp .env.example .env
nano .env
```

Fill in your values:

```env
# Application
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=true

# Database — use the dedicated user created in Step B4b
DB_HOST=localhost
DB_PORT=3306
DB_NAME=cgi_db
DB_USER=cgiuser
DB_PASSWORD=your_strong_password

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

# Pi node URL (update to Pi's LAN IP when the sensor node is set up)
PI_NODE_URL=http://localhost:5000

# Thermal printer — configure when hardware is connected
THERMAL_PRINTER_TYPE=network
THERMAL_PRINTER_HOST=192.168.1.100
THERMAL_PRINTER_PORT=9100

# CORS — add your server's IP if accessing from another machine
CORS_ORIGINS=http://localhost,http://127.0.0.1
```

Save with Ctrl+X → Y → Enter.

---

## B6. Python Virtual Environment (Linux)

```bash
cd /var/www/html/CGI

# Create the virtual environment (only once)
python3 -m venv venv

# Activate it
source venv/bin/activate
```

Your prompt should now start with `(venv)`:
```
(venv) user@hostname:/var/www/html/CGI$
```

> Run `source venv/bin/activate` every time you open a new terminal
> before running any Python commands for this project.

---

## B7. Install Python Dependencies (Linux)

With `(venv)` active:

```bash
pip install -r backend/requirements.txt
```

This installs: FastAPI, Uvicorn, SQLAlchemy, PyMySQL, bcrypt, python-jose, ReportLab,
Ultralytics YOLOv8, OpenCV, Pillow, httpx, python-escpos, and more.

> This may take 5–15 minutes — YOLOv8 and OpenCV are large packages.
> On a Raspberry Pi 4/5 running the server role it may take up to 30 minutes.

Confirm the install succeeded:
```bash
pip show fastapi
```
You should see `Name: fastapi` and a version number.

---

## B8. Fix the Admin Password (Linux)

```bash
# Make sure (venv) is active and you are in /var/www/html/CGI
python database/reset_admin.py
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

---

## B9. Start the FastAPI Backend (Linux)

### Option 1 — Manual (development / testing)

Open a terminal and keep it running:

```bash
cd /var/www/html/CGI/backend
source ../venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Option 2 — systemd service (production / auto-start on boot)

A service file is already included at `deployment/cgi-backend.service`. Install it:

```bash
sudo cp /var/www/html/CGI/deployment/cgi-backend.service /etc/systemd/system/
```

Edit the service file to match your paths if needed:
```bash
sudo nano /etc/systemd/system/cgi-backend.service
```

Then enable and start it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cgi-backend
sudo systemctl start cgi-backend
sudo systemctl status cgi-backend
```

To view live logs:
```bash
sudo journalctl -u cgi-backend -f
```

**→ Continue to [Section 10 — Verify Everything Works](#10-verify-everything-works)**

---

# 10. Verify Everything Works

Check each component before opening the web UI.
For Linux, replace `localhost` with your server's IP address if accessing from another machine.

### Check MySQL / MariaDB

- **Windows:** Open `http://localhost/phpmyadmin` — phpMyAdmin should load.
- **Linux:** Run `mysql -u cgiuser -p cgi_db -e "SELECT COUNT(*) FROM users;"` — should return `1`.

### Check Apache

Open `http://localhost` in a browser — the Apache default page should appear.

### Check FastAPI backend

Open `http://localhost:8000/api/health` in a browser.

Expected response:
```json
{"status": "ok", "version": "1.0.0"}
```

If this page does not load, the backend is not running — go back to Step A9 or B9.

### Check interactive API documentation

Open `http://localhost:8000/api/docs`

This lists all API endpoints and lets you test them directly from the browser.

### Check PHP can reach the backend (optional)

**Windows** — create `D:\xampp\htdocs\CGI\frontend\test_api.php`:

**Linux** — create `/var/www/html/CGI/frontend/test_api.php`:

```php
<?php
$ch = curl_init('http://localhost:8000/api/health');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$result = curl_exec($ch);
$code   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
echo "HTTP $code: $result";
```

Open `http://localhost/CGI/frontend/test_api.php`

Expected: `HTTP 200: {"status":"ok","version":"1.0.0"}`

Delete this file after testing.

---

# 11. Log In to the Web UI

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
| "Invalid email or password" | Re-run `reset_admin.py` (Step A8 or B8) |
| "URL not found" after login | Apache must be running; always use `http://localhost/...` |
| Blank page | FastAPI backend must be running (Step A9 or B9) |
| PHP warning about `require_once` | Check Section 15 — Troubleshooting |

---

# 12. YOLOv8 Model Setup

The New Inspection feature requires a trained YOLOv8 `.pt` model file. Without it the
backend starts normally but any inspection attempt will return a FileNotFoundError.

### Place the model file

- **Windows:** `D:\xampp\htdocs\CGI\models\cgi_yolov8.pt`
- **Linux:** `/var/www/html/CGI/models/cgi_yolov8.pt`

```bash
# Linux — copy from a USB drive or SCP from another machine:
cp /media/usb/cgi_yolov8.pt /var/www/html/CGI/models/cgi_yolov8.pt
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

This mapping is defined in `backend/services/detection.py` — `CLASS_ID_MAP`.
If your training used different class names or a different order, edit that dictionary to match.

### Update .env if the filename differs

```env
YOLO_MODEL_PATH=models/your_model_filename.pt
```

### Test the model loads

**Windows:**
```powershell
cd D:\xampp\htdocs\CGI\backend
..\venv\Scripts\activate
python -c "from services.detection import _get_model; _get_model(); print('Model loaded OK')"
```

**Linux:**
```bash
cd /var/www/html/CGI/backend
source ../venv/bin/activate
python -c "from services.detection import _get_model; _get_model(); print('Model loaded OK')"
```

---

# 13. Raspberry Pi Sensor Node Setup

The Raspberry Pi is the physical sensor node. It reads scale weight using the HX711,
captures a coffee sample image with the Pi Camera Module 3, and POSTs both to the
CGI backend over the local network.

> This section applies regardless of whether your backend server is Windows or Linux.

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
or run the following from your server machine:

- **Windows:** `ping cgi-node.local` in PowerShell
- **Linux:** `ping cgi-node.local` in a terminal

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
Typical: Red = E+, Black = E−, White = A−, Green = A+

**Pi Camera Module 3:**
Connect the ribbon cable to the Camera port on the Pi board.
The blue side of the ribbon must face toward the USB ports.

### Step 13c — Enable camera interface

SSH into the Pi:

**From Windows (PowerShell):**
```powershell
ssh pi@192.168.1.x
```

**From Linux (terminal):**
```bash
ssh pi@192.168.1.x
```

Replace `192.168.1.x` with your Pi's actual IP address.

Run the configuration tool:
```bash
sudo raspi-config
```

Navigate:
- Interface Options → Camera → Enable → OK
- Finish → select Yes to reboot

Verify the camera is detected after reboot:
```bash
libcamera-hello --list-cameras
```

You should see at least one camera listed (e.g., `imx708`).

### Step 13d — Copy the Pi node files to the Pi

**From Windows (PowerShell):**
```powershell
scp -r D:\xampp\htdocs\CGI\pi_node pi@192.168.1.x:/home/pi/CGI/
```

**From Linux (terminal):**
```bash
scp -r /var/www/html/CGI/pi_node pi@192.168.1.x:/home/pi/CGI/
```

Alternatively use **WinSCP** (Windows GUI, https://winscp.net) or `rsync` (Linux) to
transfer files.

### Step 13e — Install Pi node dependencies

`picamera2` and `RPi.GPIO` are **system packages** distributed by Raspberry Pi Ltd via
`apt`. They do not exist on PyPI — running `pip install picamera2` will always fail.
They must be installed through `apt` first, then made accessible to the virtual
environment via `--system-site-packages`.

SSH back into the Pi after the reboot:
```bash
ssh pi@192.168.1.x
```

**Phase 1 — apt system packages (requires sudo):**

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-rpi.gpio python3-libcamera
```

This installs:
- `python3-picamera2` — Picamera2 library with full libcamera backend (works with Camera Module 3)
- `python3-libcamera` — required C-extension bindings; not available from pip at all
- `python3-rpi.gpio` — RPi.GPIO pre-patched for the installed Bookworm kernel

**Phase 2 — Create the virtual environment with system-site-packages access:**

A standard isolated venv cannot see apt-installed packages. The `--system-site-packages`
flag bridges the two:

```bash
cd /home/pi/CGI/pi_node
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

**Phase 3 — Install the remaining pip-only packages:**

```bash
pip install -r requirements.txt
```

This installs `hx711==1.1.2.3` and `requests==2.31.0` — the only two packages that
are pip-installable. `picamera2` and `RPi.GPIO` are available via the system link.

**Verify all four libraries import correctly:**

```bash
python3 -c "from picamera2 import Picamera2; print('picamera2 OK')"
python3 -c "import RPi.GPIO; print('RPi.GPIO OK')"
python3 -c "from hx711 import HX711; print('hx711 OK')"
python3 -c "import requests; print('requests OK')"
```

All four lines must print `OK`. If `picamera2` or `RPi.GPIO` print an ImportError, the
venv was created without `--system-site-packages`. Delete it and recreate:

```bash
deactivate
rm -rf venv
python3 -m venv --system-site-packages venv
source venv/bin/activate
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
# LAN IP address of the CGI backend server
# Windows: run ipconfig → look for IPv4 Address under your WiFi adapter
# Linux:   run ip addr   → look for inet under your network interface
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
source venv/bin/activate
python hx711_reader.py --calibrate
```

Follow the prompts:
1. Remove all weight from the scale → press Enter (sets the tare/zero point)
2. Place a known-weight object on the scale — for example a 350 g bag of rice
3. Type the exact known weight in grams → press Enter
4. The script prints a `CALIBRATION_FACTOR` — copy this number
5. Open `config.ini` → paste the value into `CALIBRATION_FACTOR` → save

Verify calibration:
```bash
python hx711_reader.py
```
Place your known weight and confirm the reading matches.

### Step 13h — Test the sensor node

Make sure the venv is active (`source venv/bin/activate`), place a coffee sample on
the scale, then:
```bash
python sensor_node.py --once
```

This reads the weight, captures an image, and sends both to the backend server.
Check the Uvicorn terminal on your server — you should see an incoming POST request.

### Step 13i — Auto-start on boot (optional)

The service file points to `venv/bin/python3` directly so systemd does not need to
activate the venv manually:

```bash
sudo cp /home/pi/CGI/pi_node/cgi-node.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cgi-node
sudo systemctl start cgi-node
sudo systemctl status cgi-node
```

The sensor node will now start automatically every time the Pi boots.

---

# 14. User and Role Management

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

# 15. Troubleshooting

### "Invalid email or password" when logging in

The bcrypt hash in the database does not match your Python/bcrypt version.

**Windows fix:**
```powershell
cd D:\xampp\htdocs\CGI
venv\Scripts\activate
python database\reset_admin.py
```

**Linux fix:**
```bash
cd /var/www/html/CGI
source venv/bin/activate
python database/reset_admin.py
```

---

### "URL not found" or 404 error after logging in

The PHP redirect is sending you to the wrong path.

- Always access the site via `http://localhost/CGI/frontend/login.php`
- Never open PHP files directly as `file:///...` — they must go through Apache
- Confirm Apache is running

---

### FastAPI backend won't start — "Address already in use"

Port 8000 is already used by another process.

Fix — change the port in `.env`:
```env
APP_PORT=8001
```
Then start with:
```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

---

### "Cannot connect to MySQL" or "Access denied for user"

**Windows checklist:**
1. Is MySQL green in XAMPP Control Panel?
2. Is `DB_PASSWORD` in `.env` correct? (Blank for XAMPP default)
3. Test: open `D:\xampp\mysql\bin\mysql.exe` → press Enter when asked for password

**Linux checklist:**
1. Is MySQL/MariaDB running? `sudo systemctl status mysql`
2. Is `DB_USER` and `DB_PASSWORD` in `.env` correct?
3. Test: `mysql -u cgiuser -p cgi_db` — you should reach the `mysql>` prompt
4. If using the root socket auth on Raspberry Pi OS, create a dedicated user (Step B4b)

---

### "ModuleNotFoundError" when starting the backend

The virtual environment is not active or packages were not installed.

**Windows fix:**
```powershell
cd D:\xampp\htdocs\CGI
venv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
uvicorn main:app --reload
```

**Linux fix:**
```bash
cd /var/www/html/CGI
source venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

---

### "FileNotFoundError: models/cgi_yolov8.pt"

The trained YOLOv8 model file is missing.

- **Windows:** place at `D:\xampp\htdocs\CGI\models\cgi_yolov8.pt`
- **Linux:** place at `/var/www/html/CGI/models/cgi_yolov8.pt`

The backend and all other features still work — only the inspection analyze endpoint
is unavailable until the model is placed.

---

### PHP warning about require_once — "Failed to open stream"

A PHP file is looking for another file at the wrong relative path.

Fix: Check the PHP file shown in the error. The `require_once` path should be
`__DIR__ . '/api.php'` (for files inside `frontend/`) not `__DIR__ . '/../api.php'`.

---

### PHP shows raw source code instead of a rendered page

You opened the PHP file directly in the browser as a file path.

Fix: Always access through Apache: `http://localhost/CGI/frontend/...`

---

### The web page cannot reach the backend — curl error or empty response from API

Checklist:
1. Is the Uvicorn backend running?
2. Test directly: open `http://localhost:8000/api/health` in the browser.
3. **Windows** — enable curl in PHP:
   - Open `D:\xampp\php\php.ini`
   - Find `;extension=curl` → remove the semicolon: `extension=curl`
   - Save → restart Apache in XAMPP Control Panel
4. **Linux** — ensure `php-curl` is installed:
   ```bash
   sudo apt install -y php-curl
   sudo systemctl restart apache2
   ```

---

### Pi sensor node — `pip install picamera2` fails with "No matching distribution"

`picamera2` is not on PyPI. It must be installed via `apt`, not `pip`.

Fix (run on the Raspberry Pi):
```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-rpi.gpio python3-libcamera
cd /home/pi/CGI/pi_node
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

See `pi_node/INSTALL.md` for the full procedure and verification commands.

---

### Pi sensor node — `ImportError: No module named 'picamera2'` inside the venv

The venv was created without `--system-site-packages` and cannot see the apt-installed package.

Fix (on the Pi, inside `pi_node/`):
```bash
deactivate
rm -rf venv
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

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

# 16. Quick-Start Checklist (Daily Use)

## Windows (XAMPP)

```
XAMPP
[ ] Open XAMPP Control Panel (Run as Administrator)
[ ] Start Apache     (wait for green)
[ ] Start MySQL      (wait for green)

Backend
[ ] Open a new PowerShell window
[ ] cd D:\xampp\htdocs\CGI\backend
[ ] ..\venv\Scripts\activate
[ ] uvicorn main:app --host 0.0.0.0 --port 8000 --reload
[ ] Keep this window open

Browser
[ ] Open http://localhost/CGI/frontend/login.php
[ ] Log in with your credentials

To stop
[ ] Press Ctrl+C in the Uvicorn PowerShell window
[ ] Stop Apache in XAMPP Control Panel
[ ] Stop MySQL in XAMPP Control Panel
```

## Linux (Raspberry Pi OS / Debian / Ubuntu)

```
Services (should already be running on boot if enabled)
[ ] sudo systemctl status apache2    — must be active
[ ] sudo systemctl status mysql      — must be active

Backend (if running manually)
[ ] Open a terminal
[ ] cd /var/www/html/CGI/backend
[ ] source ../venv/bin/activate
[ ] uvicorn main:app --host 0.0.0.0 --port 8000 --reload
[ ] Keep this terminal open

Backend (if running as systemd service)
[ ] sudo systemctl start cgi-backend
[ ] sudo systemctl status cgi-backend   — must show "active (running)"

Browser
[ ] Open http://localhost/CGI/frontend/login.php
[ ] Log in with your credentials

To stop (manual mode)
[ ] Press Ctrl+C in the Uvicorn terminal

To stop (systemd mode)
[ ] sudo systemctl stop cgi-backend
```

---

*CGI System — Complete Setup Guide v2.0*
*Coffee Grade Identification — Thesis Project*
*Covers: Windows (XAMPP) and Linux (Raspberry Pi OS / Debian / Ubuntu)*
