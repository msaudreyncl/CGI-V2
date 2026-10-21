# Coffee Grade Identification (CGI) — Complete Setup Guide

This guide covers setting up the full CGI system from scratch on either a
**Windows machine (XAMPP)** or a **Linux machine (Raspberry Pi OS / Debian/Ubuntu)**.
Follow the section that matches your server environment, then continue from
Section 10 onward — those sections apply to both platforms.

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
  - [B2. Update Raspberry Pi OS and Install Services](#b2-update-raspberry-pi-os-and-install-services)
  - [B3. Clone the Project and Configure Apache](#b3-clone-the-project-and-configure-apache)
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

The backend uses the following pinned direct dependencies on Windows and Linux:

| Component | Package version |
|---|---:|
| FastAPI | `fastapi==0.111.0` |
| Pydantic | `pydantic==2.7.1` |
| Starlette | `starlette==0.37.2` |
| Uvicorn | `uvicorn[standard]==0.29.0` |
| SQLAlchemy | `sqlalchemy==2.0.30` |
| PyMySQL | `pymysql==1.1.1` |
| Cryptography | `cryptography==42.0.7` |
| Python JOSE | `python-jose[cryptography]==3.3.0` |
| bcrypt | `bcrypt==4.2.1` |
| Python Multipart | `python-multipart==0.0.9` |
| Python Dotenv | `python-dotenv==1.0.1` |
| HTTPX | `httpx==0.27.0` |
| Ultralytics | `ultralytics==8.2.18` |
| PyTorch | `torch==2.2.2` |
| TorchVision | `torchvision==0.17.2` |
| NumPy | `numpy==1.26.4` |
| OpenCV | `opencv-python==4.9.0.80` |
| Pillow | `Pillow==10.3.0` |
| ReportLab | `reportlab==4.1.0` |
| Python ESC/POS | `python-escpos==3.1` |
| aiofiles | `aiofiles==23.2.1` |
| Email Validator | `email-validator==2.2.0` |

`httpx2` and `opencv-python-headless` are intentionally not installed. The code
imports `httpx`, and Ultralytics declares the full `opencv-python` distribution.
Installing both OpenCV distributions can cause them to overwrite the same `cv2`
package.

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
> **Raspberry Pi OS Bookworm 64-bit** (Debian 12, system Python 3.11) and
> **Ubuntu 22.04 LTS**. Python 3.13 is not supported by this pinned Raspberry Pi
> ML stack; using Bookworm's Python 3.11 avoids source builds on ARM64.

## B1. System Requirements (Linux)

| Software | Minimum Version | Install method |
|---|---|---|
| Apache2 | 2.4+ | `apt` |
| MySQL / MariaDB | 8.0+ / 10.6+ | `apt` |
| PHP | 8.1+ | `apt` |
| Python | 3.11 (Raspberry Pi recommended) | `apt` |
| Git | any | `apt` |

---

## B2. Update Raspberry Pi OS and Install Services

The working deployment uses Raspberry Pi OS Bookworm 64-bit, the Linux account
`cgi`, Apache's default site, and `/var/www/html/CGI-V2`. Run these steps on the Pi.
For an existing installation, skip packages and initialization already completed;
do not overwrite `.env` or re-import seed data.

### Update and upgrade the OS

```bash
sudo apt update
sudo apt full-upgrade -y
```

Expect package lists to finish without errors and upgrades to complete. Reboot
if kernel updates require it, then reconnect before continuing:

```bash
sudo reboot
```

This updates the installed OS release; it is not an instruction to change from
Bookworm to a newer major release. Raspberry Pi recommends `full-upgrade` for
package dependency updates ([OS documentation](https://www.raspberrypi.com/documentation/computers/os.html)).

### Install Apache2, PHP, MariaDB, Python, and Git

```bash
sudo apt install -y apache2 mariadb-server mariadb-client
sudo apt install -y php libapache2-mod-php php-mysql php-curl php-mbstring php-xml php-zip php-gd
sudo apt install -y python3 python3-pip python3-venv python3-dev libgl1 libglib2.0-0 curl git
sudo systemctl enable --now apache2 mariadb
sudo systemctl status apache2 mariadb --no-pager
php --version
php -m
python3 --version
git --version
```

Both services should show `active (running)`. Expect PHP 8.x, Python 3.11.x,
and a Git version. PHP modules must include `curl`, `mbstring`, `mysqli`,
`pdo_mysql`, `xml`, `zip`, `gd`, and `json`. JSON is built into PHP 8; a separate
`php-json` package is unnecessary here.

Find the Pi's LAN address:

```bash
hostname -I
```

Use its LAN IP in place of `<PI_IP>` in browser URLs throughout this guide.
`http://<PI_IP>/` should initially show Apache's default page.

### Secure MariaDB

```bash
sudo mariadb-secure-installation
```

On a fresh installation, press Enter for the current root password. Retain
`unix_socket` authentication (answer Yes if asked to switch to it), and answer
No to changing the root password when socket authentication is already enabled.
Answer Yes to removing anonymous users, disallowing remote root login, removing
the test database, and reloading privileges. Prompts vary by installed version.

Use `sudo mysql` for local database administration. Do not put the database root
account in `.env` or use it for phpMyAdmin browser login. MariaDB's default root
socket authentication does not need a root password
([MariaDB security documentation](https://mariadb.com/docs/server/clients-and-utilities/deployment-tools/mariadb-secure-installation)).

### Install and configure phpMyAdmin

```bash
sudo apt install -y phpmyadmin
```

In the installer, use **Space** to select `apache2`, then Tab and Enter to confirm.
Choose Yes for configuration with `dbconfig-common`; choose and confirm the
phpMyAdmin internal database password when prompted. This internal account is
separate from the CGI database account created in B4.

Ensure Apache loads the packaged configuration:

```bash
ls -l /etc/apache2/conf-available/phpmyadmin.conf
```

If that file is missing, link the package configuration once:

```bash
sudo ln -s /etc/phpmyadmin/apache.conf /etc/apache2/conf-available/phpmyadmin.conf
```

Then enable it:

```bash
sudo a2enconf phpmyadmin
sudo apache2ctl configtest
```

Continue only after `Syntax OK`:

```bash
sudo systemctl restart apache2
```

Open `http://<PI_IP>/phpmyadmin/`; the phpMyAdmin login page should appear.
Log in using `cgi_admin` after B4. Debian packages keep phpMyAdmin settings under
`/etc/phpmyadmin/` ([installation documentation](https://docs.phpmyadmin.net/en/latest/setup.html)).

---

## B3. Clone the Project and Configure Apache

### Configure Git and clone the repository

Replace the Git author placeholders with your own details:

```bash
git config --global user.name "YOUR_NAME"
git config --global user.email "YOUR_EMAIL"
git config --global --list
sudo mkdir -p /var/www/html/CGI-V2
sudo chown "$USER":www-data /var/www/html/CGI-V2
git clone https://github.com/msaudreyncl/CGI-V2.git /var/www/html/CGI-V2
cd /var/www/html/CGI-V2
```

Clone only into an empty directory. If the project already exists, skip the
`mkdir`, `chown`, and clone commands above and inspect it instead:

```bash
cd /var/www/html/CGI-V2
git status
git remote -v
```

The origin should be `https://github.com/msaudreyncl/CGI-V2.git`.

### Project ownership and permissions

Run as the deployment user (`cgi` on this Pi):

```bash
sudo chown -R "$USER":www-data /var/www/html/CGI-V2
sudo chmod -R u+rwX,g+rX,o-rwx /var/www/html/CGI-V2
mkdir -p backend/static/uploads
chmod 2770 backend/static/uploads
```

The owner can edit the project and Apache's `www-data` group can read it.
The uploads directory is writable by the deployment user and `www-data`.
Do not use `chmod -R 777`. Restrict `.env` separately in B5.

Expected project structure:

```text
/var/www/html/CGI-V2/
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

### Configure the working default Apache site and reverse proxy

Identify the active site:

```bash
sudo apache2ctl -S
```

For this deployment, expect a line like:

```text
*:80  127.0.1.1 (/etc/apache2/sites-enabled/000-default.conf:1)
```

Edit the corresponding site configuration:

```bash
sudo nano /etc/apache2/sites-available/000-default.conf
```

Keep the existing `DocumentRoot /var/www/html`. Inside the existing
`<VirtualHost *:80>` block, before `</VirtualHost>`, add these rules once:

```apache
ProxyPass        /api/ http://127.0.0.1:8000/api/
ProxyPassReverse /api/ http://127.0.0.1:8000/api/

# Uploaded and annotated images served by FastAPI
ProxyPass        /static/ http://127.0.0.1:8000/static/
ProxyPassReverse /static/ http://127.0.0.1:8000/static/

# Serve only the PHP frontend from this project directory
<Directory /var/www/html/CGI-V2>
    Require all denied
</Directory>
<Directory /var/www/html/CGI-V2/frontend>
    Require all granted
    DirectoryIndex index.php
    Options -Indexes +FollowSymLinks
</Directory>
```

The directory rules keep the project's `.env`, source, and Git data outside the
served frontend. Keep any existing logging directives. Save with Ctrl+O, Enter,
then Ctrl+X. Do not also enable the separate `deployment/apache-frontend.conf`
virtual host for this setup: it uses a different document root and URL layout.

Enable the proxy modules, validate, and restart:

```bash
sudo a2enmod proxy proxy_http
sudo apache2ctl configtest
```

Expected: `Syntax OK`. Only then run:

```bash
sudo systemctl restart apache2
sudo systemctl status apache2 --no-pager
```

Expected: `active (running)`. The warning below is **non-blocking** and can appear
alongside `Syntax OK`; it does not cause the user update failure:

```text
AH00558: apache2: Could not reliably determine the server's fully qualified domain name
```

Optionally suppress it by creating `/etc/apache2/conf-available/servername.conf`
with `sudo nano /etc/apache2/conf-available/servername.conf` and adding:

```apache
ServerName localhost
```

Then run `sudo a2enconf servername`, `sudo apache2ctl configtest`, and, after
`Syntax OK`, `sudo systemctl reload apache2`.

The CGI frontend URL is `http://<PI_IP>/CGI-V2/frontend/login.php`.
Browser requests to `/api/` now reach FastAPI on port 8000; PHP's server-side
requests use `http://localhost:8000`. No hosts-file entry is required for IP URLs.
If you optionally map `cgi.local`, edit `/etc/hosts` on the computer running the
browser (`sudo nano /etc/hosts` on Linux), add `<PI_IP> cgi.local`, and retain the
`/CGI-V2/frontend/` path in the URL. A hosts entry does not replace the API proxy.

---

## B4. Database Setup (Linux)

### Step B4a — Create cgi_db and the cgi_admin account

`cgi_db` is the database name hard-coded in the supplied SQL files.
`cgi_admin` below is a MariaDB login for that database, not a different database
name and not the application's `admin@cgi.local` login.

```bash
sudo mysql
```

Run inside the MariaDB console, replacing `YOUR_STRONG_PASSWORD`:

```sql
CREATE DATABASE IF NOT EXISTS cgi_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'cgi_admin'@'localhost'
    IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON cgi_db.* TO 'cgi_admin'@'localhost';
SHOW GRANTS FOR 'cgi_admin'@'localhost';
EXIT;
```

Expect `Query OK` and grants scoped to `cgi_db.*`. `CREATE USER IF NOT EXISTS`
does not reset an existing password. If repairing an existing login, use
`ALTER USER 'cgi_admin'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';`
inside `sudo mysql`, then match that password in `.env`.

If your existing working installation uses `cgiuser`, keep that account and
substitute `cgiuser` for `cgi_admin` in the commands and `.env` below. Do not
rename existing accounts merely to follow this guide.

### Step B4b — Import schema and seed (new installations only)

```bash
cd /var/www/html/CGI-V2
sudo mysql cgi_db < database/schema.sql
sudo mysql cgi_db < database/seed.sql
```

Successful imports exit without errors. Do not re-import seed data into a
populated installation. For an existing database, first back up and apply only
the outstanding migrations in the next step.

### Step B4c — Apply required migrations

Back up before upgrading an existing database; confirm the command succeeds:

```bash
sudo mysqldump --single-transaction cgi_db > "$HOME/cgi_db_before_migrations_$(date +%Y%m%d_%H%M%S).sql"
```

Both fresh installations and older schemas need these migrations, in order:

```bash
sudo mysql cgi_db < database/migrations/001_six_stage_workflow.sql
sudo mysql cgi_db < database/migrations/002_user_management.sql
```

Stop if an import reports an error. These files use MariaDB's
`ADD COLUMN IF NOT EXISTS`; do not assume the same syntax works on MySQL 8.
They add workflow columns, `pending_transactions`, and user display/login fields.

### Step B4d — Verify the account and database over TCP

```bash
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u cgi_admin -p cgi_db -e "SELECT CURRENT_USER(); SHOW TABLES;"
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u cgi_admin -p cgi_db -e "SELECT id, name, email, role FROM users;"
```

Enter the account password when prompted. Expect these eight tables:

```text
cooperatives
defect_results
farmers
inspections
pending_transactions
pricing_config
transactions
users
```

A freshly seeded database has `id=1`, `System Admin`, `admin@cgi.local`, role
`admin`. Existing databases may have additional users.

Open `http://<PI_IP>/phpmyadmin/` and log in with `cgi_admin` and its database
password. Select `cgi_db`, inspect the eight tables, and browse `users` to verify
the same data. The phpMyAdmin internal account is not the CGI login.

---

## B5. Environment Configuration (Linux)

```bash
cd /var/www/html/CGI-V2
# Copy only if .env does not already exist
[ -f .env ] || cp .env.example .env
chmod 640 .env
nano .env
```

Fill in your values:

```env
# Application
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=true

# Database — use the dedicated user created in Step B4a
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=cgi_db
DB_USER=cgi_admin
DB_PASSWORD="YOUR_STRONG_PASSWORD"

# JWT — generate using: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=REPLACE_WITH_GENERATED_SECRET
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

Save with Ctrl+X → Y → Enter. Match the database account and password from B4.
Keep the existing working credentials when updating an installation.

---

## B6. Python Virtual Environment (Linux)

```bash
cd /var/www/html/CGI-V2

# Create the virtual environment (only once)
python3 -m venv venv

# Activate it
source venv/bin/activate
```

Your prompt should now start with `(venv)`:
```
(venv) user@hostname:/var/www/html/CGI-V2$
```

> Run `source venv/bin/activate` every time you open a new terminal
> before running any Python commands for this project.

---

## B7. Install Python Dependencies (Linux)

With `(venv)` active:

```bash
python --version
# Expected on Raspberry Pi OS Bookworm: Python 3.11.x

python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: -r backend/requirements.txt
python -m pip check
```

This installs the exact versions listed in **A7. Install Python Dependencies
(Windows)**, including matching CPU PyTorch/TorchVision ARM64 wheels.
`--only-binary=:all:` is intentional: it fails early instead of attempting long,
fragile native builds.

> This may take 5–15 minutes — YOLOv8 and OpenCV are large packages.
> On a Raspberry Pi 4/5 running the server role it may take up to 30 minutes.

Confirm the install succeeded:
```bash
python -c "import fastapi, uvicorn, sqlalchemy, httpx, numpy, cv2, PIL, torch, torchvision, ultralytics; print('backend imports OK')"
python -c "import platform, torch; print(platform.machine(), torch.__version__, 'CUDA:', torch.cuda.is_available())"
```
The first command must print `backend imports OK`. On a Raspberry Pi CPU install,
`CUDA: False` is expected.

---

## B8. Fix the Admin Password (Linux)

```bash
# Make sure (venv) is active and you are in /var/www/html/CGI-V2
python database/reset_admin.py
```

Expected output:
```
Connecting to MySQL at 127.0.0.1:3306/cgi_db...
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
cd /var/www/html/CGI-V2
source venv/bin/activate
python backend/database.py
python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

The database check must report:

```text
Database connectivity and required tables/columns OK (read-only check).
```

Keep the terminal open. Ctrl+C stops the backend; Apache alone cannot serve API
requests. `--app-dir backend` is required when starting from the project root.
The reload flag is for development and restarts the server when source changes.

### Option 2 — systemd service (production / auto-start on boot)

Do not run the manual server and systemd service simultaneously on port 8000.
A service file is already included at `deployment/cgi-backend.service`. Install it:

```bash
sudo cp /var/www/html/CGI-V2/deployment/cgi-backend.service /etc/systemd/system/
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
- **Linux:** Run `mysql --protocol=TCP -h 127.0.0.1 -u cgi_admin -p cgi_db -e "SELECT COUNT(*) FROM users;"`. A fresh seed returns `1`; an existing installation can return more. Use `cgiuser` instead if retaining that account.

### Check Apache

On Windows, open `http://localhost` — the Apache default page should appear.
On Raspberry Pi OS, open `http://<PI_IP>/CGI-V2/frontend/login.php`.
Apache's document root remains `/var/www/html`; visiting `/` may show its default page.

### Check the Apache-to-FastAPI proxy (Raspberry Pi)

With Uvicorn running in its dedicated terminal, open a second terminal:

```bash
curl -i http://127.0.0.1/api/health
```

Expected response (header order and date may vary):

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok","version":"1.0.0"}
```

This uses port 80 and verifies Apache forwarding, not just direct port 8000 access.
From another computer, open `http://<PI_IP>/api/health` and expect the same JSON.
If this fails, compare with `curl -i http://127.0.0.1:8000/api/health` on the Pi.
If port 8000 works but port 80 fails, check the active default-site proxy in B3.

### Check phpMyAdmin (Raspberry Pi)

Open `http://<PI_IP>/phpmyadmin/`. Log in with the database account from B4,
select `cgi_db`, and confirm its tables and users. This login differs from the
CGI application's email/password login.

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

**Linux** — create `/var/www/html/CGI-V2/frontend/test_api.php`:

```php
<?php
$ch = curl_init('http://localhost:8000/api/health');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$result = curl_exec($ch);
$code   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
echo "HTTP $code: $result";
```

Open `http://localhost/CGI/frontend/test_api.php` on Windows or
`http://<PI_IP>/CGI-V2/frontend/test_api.php` on Linux.

Expected: `HTTP 200: {"status":"ok","version":"1.0.0"}`

Delete this file after testing.

---

# 11. Log In to the Web UI

Open your browser and go to:

- **Windows (XAMPP):** `http://localhost/CGI/frontend/login.php`
- **Raspberry Pi OS / Linux (default site):** `http://<PI_IP>/CGI-V2/frontend/login.php`

Default admin credentials:

| Field | Value |
|---|---|
| Email | `admin@cgi.local` |
| Password | `Admin@1234` |

After a successful login you will be redirected to the **Dashboard**.

> The original System Admin (id 1) is protected from modification through the
> Users page. The reset script restores its documented default credentials;
> use additional admin accounts for normal account management.

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
- **Linux:** `/var/www/html/CGI-V2/models/cgi_yolov8.pt`

```bash
# Linux — copy from a USB drive or SCP from another machine:
cp /media/usb/cgi_yolov8.pt /var/www/html/CGI-V2/models/cgi_yolov8.pt
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
cd /var/www/html/CGI-V2/backend
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
scp -r /var/www/html/CGI-V2/pi_node pi@192.168.1.x:/home/pi/CGI/
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
cd /var/www/html/CGI-V2
source venv/bin/activate
python database/reset_admin.py
```

---

### "URL not found" or 404 error after logging in

The PHP redirect is sending you to the wrong path.

- Windows: use `http://localhost/CGI/frontend/login.php`.
- Raspberry Pi: use `http://<PI_IP>/CGI-V2/frontend/login.php`.
- Never open PHP files directly as `file:///...` — they must go through Apache
- Confirm Apache is running

---

### FastAPI backend won't start — "Address already in use"

Port 8000 is already used by another process.

Check whether the optional service already owns port 8000:

```bash
sudo systemctl status cgi-backend --no-pager
sudo ss -ltnp 'sport = :8000'
```

Use the running backend, or stop it before starting a manual instance:

```bash
sudo systemctl stop cgi-backend
```

Keep port 8000 for this deployment: Apache's proxy and PHP's backend URL use it.
Changing `APP_PORT` alone does not change an explicit Uvicorn `--port` argument.

---

### "Cannot connect to MySQL" or "Access denied for user"

**Windows checklist:**
1. Is MySQL green in XAMPP Control Panel?
2. Is `DB_PASSWORD` in `.env` correct? (Blank for XAMPP default)
3. Test: open `D:\xampp\mysql\bin\mysql.exe` → press Enter when asked for password

**Linux checklist:**
1. Is MySQL/MariaDB running? `sudo systemctl status mariadb`
2. Is `DB_USER` and `DB_PASSWORD` in `.env` correct?
3. Test: `mysql --protocol=TCP -h 127.0.0.1 -u cgi_admin -p cgi_db` — you should reach the MariaDB prompt
4. If using the root socket auth on Raspberry Pi OS, create a dedicated user (Step B4a)

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
cd /var/www/html/CGI-V2
source venv/bin/activate
python -m pip install --only-binary=:all: -r backend/requirements.txt
python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

---

### "FileNotFoundError: models/cgi_yolov8.pt"

The trained YOLOv8 model file is missing.

- **Windows:** place at `D:\xampp\htdocs\CGI\models\cgi_yolov8.pt`
- **Linux:** place at `/var/www/html/CGI-V2/models/cgi_yolov8.pt`

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

### Account updates fail with "Update failed (HTTP 405)"

The browser sends `PUT /api/users/{id}` to Apache. If no corresponding PUT appears
in Uvicorn's log, Apache is likely handling the request without forwarding it.
Account creation can still work because PHP calls FastAPI directly.

Follow B3: inspect `sudo apache2ctl -S`, add `/api/` proxy rules inside the active
`000-default.conf` virtual host, enable `proxy proxy_http`, run `configtest`, then
restart Apache. Verify with the port-80 health check in Section 10. Do not add a
second virtual host or change `/etc/hosts` to fix a missing proxy.

### Account updates fail with "Network error: Failed to fetch" / OPTIONS 400

A rejected `OPTIONS /api/users/{id}` indicates a CORS preflight failure. Use the
PHP website through Apache and keep browser API requests on same-origin `/api/`.
Hard-refresh with Ctrl+Shift+R. For intentional cross-origin requests,
`CORS_ORIGINS` must contain the exact browser origin (scheme, hostname, port);
subnet entries such as `http://192.168.1.0/24` are unsupported. Restart the backend
after editing `.env`.

### "Could not import module main"

From `/var/www/html/CGI-V2`, use the B9 command with `--app-dir backend`.
The entry point is `backend/main.py`, not a root-level `main.py`.

### "Database schema is missing"

Startup checks are read-only and do not upgrade the schema. Back up the database
and apply the outstanding B4c migrations, then run `python backend/database.py`
inside the active venv. Do not drop tables or re-import seed data as a repair.

### "Backend returned an invalid JSON response" when adding a user

This means PHP received a non-JSON response, often a backend HTTP 500. Reproduce
once while watching the Uvicorn traceback. A confirmed historical cause was
`Duplicate entry 'FF00001' for key 'user_id_display'`: older registration code
used role counts to allocate display IDs. Use the corrected registration code
that checks existing IDs across all roles and handles conflicts. Do not delete
existing users or reset the database to repair it. Other errors need their own
traceback diagnosis; do not assume every invalid response is an ID collision.

### phpMyAdmin returns 404 or rejects login

For 404, check `/etc/apache2/conf-available/phpmyadmin.conf`, run
`sudo a2enconf phpmyadmin`, validate Apache, then restart as in B2.
For access denied, use the database account/password from B4, not the application
email/password or MariaDB's socket-authenticated root account. Test the same
credentials over TCP using B4d.

### Apache warns AH00558 about ServerName

This warning is non-blocking if `configtest` also reports `Syntax OK`.
The optional global `ServerName localhost` configuration in B3 suppresses it.
An actual syntax error must be fixed before restarting Apache.

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
[ ] sudo systemctl start apache2 mariadb
[ ] sudo systemctl status apache2    — must be active
[ ] sudo systemctl status mariadb    — must be active

Backend (if running manually)
[ ] Open a terminal
[ ] cd /var/www/html/CGI-V2
[ ] source venv/bin/activate
[ ] python backend/database.py
[ ] python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
[ ] Keep this terminal open

Backend (if running as systemd service)
[ ] sudo systemctl start cgi-backend
[ ] sudo systemctl status cgi-backend   — must show "active (running)"

Browser
[ ] curl -i http://127.0.0.1/api/health — must return HTTP 200
[ ] Open http://<PI_IP>/CGI-V2/frontend/login.php
[ ] Verify http://<PI_IP>/phpmyadmin/ when database administration is needed
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
