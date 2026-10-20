# Coffee Grade Identification (CGI)

Automated coffee bean quality assessment and suggested transactional pricing system using
computer vision (YOLOv8), load-sensing hardware, and a web application.

---

## System Architecture

```
[Raspberry Pi Node]               [LAN Server]
  Pi Camera Module 3  ──┐         ┌─ FastAPI (Python) :8000
  HX711 + Load Cell   ──┼─ HTTP ──┤─ MySQL Database
  7" LCD Touchscreen  ──┘  LAN    ├─ Apache + PHP Frontend :80
                                  └─ YOLOv8 Inference Engine
```

---

## Prerequisites

### Server Machine
- Python 3.11 (recommended and supported for the Raspberry Pi backend dependency set)
- MySQL 8.0+ (or XAMPP with MySQL)
- Apache 2.4+ (for PHP frontend)
- PHP 8.1+

### Raspberry Pi
- Raspberry Pi OS (Bookworm or later)
- Pi Camera Module 3
- HX711 Load Cell Amplifier + 1 kg Straight Bar Load Cell
- 7-inch LCD Touchscreen (1024×600)

---

## Server Setup

### 1. Clone / copy project files to the server

```bash
# Example: place in XAMPP htdocs
# C:\xampp\htdocs\CGI\   (Windows)
# /var/www/html/CGI-V2/  (Linux)
```

### 2. Create and activate a Python virtual environment

```bash
cd CGI-V2
python3.11 -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: -r backend/requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your DB credentials, API keys, model path, etc.
```

### 5. Set up the database

```bash
# Using MySQL CLI or phpMyAdmin:
mysql -u root -p < database/schema.sql
mysql -u root -p < database/seed.sql
```

Default admin credentials (change immediately after first login):
- Email: `admin@cgi.local`
- Password: `Admin@1234`

### 6. Place the YOLOv8 model

Copy your trained `.pt` model file to:
```
models/cgi_yolov8.pt
```
Update `YOLO_MODEL_PATH` in `.env` if the filename differs.

### 7. Start the FastAPI backend

```bash
cd CGI-V2/backend
source ../venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Or use the systemd service in production:
```bash
sudo cp deployment/cgi-backend.service /etc/systemd/system/
sudo systemctl enable cgi-backend
sudo systemctl start cgi-backend
```

### 8. Configure Apache for the PHP frontend

```bash
sudo cp deployment/apache-frontend.conf /etc/apache2/sites-available/cgi.conf
sudo a2ensite cgi
sudo a2enmod proxy proxy_http
sudo systemctl reload apache2
```

---

## Raspberry Pi Node Setup

See `pi_node/INSTALL.md` for the required apt packages and the
`--system-site-packages` virtual environment. Picamera2, libcamera, and GPIO
bindings must come from Raspberry Pi OS, not PyPI.

### 1. Enable Camera and I2C/SPI

```bash
sudo raspi-config
# Interface Options → Camera → Enable
# Interface Options → I2C → Enable (for HX711 via GPIO)
```

### 2. Install Pi node dependencies

```bash
cd CGI-V2/pi_node
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera python3-rpi.gpio
python3 -m venv --system-site-packages venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Configure the node

```bash
cp pi_node/config.ini.example pi_node/config.ini
# Edit SERVER_URL to point to your LAN server IP, e.g.:
# SERVER_URL = http://192.168.1.10:8000
# Set CALIBRATION_FACTOR for your specific load cell
```

### 4. Calibrate the load cell

```bash
python pi_node/hx711_reader.py --calibrate
# Follow the on-screen prompts with a known weight
```

### 5. Run the sensor node

```bash
python pi_node/sensor_node.py
```

Or auto-start on boot:
```bash
sudo cp pi_node/cgi-node.service /etc/systemd/system/
sudo systemctl enable cgi-node
sudo systemctl start cgi-node
```

---

## Grading Standard (ASEAN Table of Defects)

| Defect Type       | Extra Class | Class I   | Class II    |
|-------------------|-------------|-----------|-------------|
| Black bean        | < 4%        | 4 – 6%    | > 6 – 15%  |
| Moldy / Infested  | < 5%        | 5 – 6%    | > 6 – 8%   |
| Immature bean     | < 2%        | 2 – 3%    | > 3 – 8%   |
| Broken bean       | < 3%        | 3 – 5%    | > 5 – 10%  |
| Dried cherries    | < 0.5%      | 0.5 – 1%  | > 1 – 2%   |
| Foreign matter    | < 1%        | 1 – 1.5%  | 1.5 – 2%   |

- **Final grade** = lowest class returned by any single defect evaluation.
- Defects exceeding the Class II upper bound → Class II grade + **over-threshold warning**.
- Sample must be **340–360 g**; outside this range the inspection is blocked.

---

## User Roles

| Role              | Permissions |
|-------------------|-------------|
| Admin             | Full access — users, pricing config, all records, reports |
| Cooperative Officer | Inspections, transactions, pricing config, reports |
| Farmer            | Read-only access to own inspection and transaction records |

---

## API Reference

Base URL: `http://<server-ip>:8000`

| Method | Endpoint                          | Description                        |
|--------|-----------------------------------|------------------------------------|
| GET    | `/api/health`                     | Health check                       |
| POST   | `/api/auth/login`                 | Obtain JWT token                   |
| GET    | `/api/auth/me`                    | Current user profile               |
| POST   | `/api/auth/register`              | Create user (Admin only)           |
| POST   | `/api/inspection/analyze`         | Submit image + weight for grading  |
| GET    | `/api/inspections`                | List inspections (scoped by role)  |
| GET    | `/api/inspections/{id}`           | Inspection detail                  |
| POST   | `/api/pricing/suggest`            | Get suggested price for inspection |
| GET    | `/api/pricing/config`             | View grade multipliers             |
| PUT    | `/api/pricing/config`             | Update multipliers (Admin/Officer) |
| POST   | `/api/transactions`               | Create transaction                 |
| GET    | `/api/transactions`               | List transactions (scoped)         |
| GET    | `/api/transactions/{id}`          | Transaction detail                 |
| GET    | `/api/reports/inspection/{id}/pdf`| Download inspection PDF            |
| GET    | `/api/reports/transactions/csv`   | Download transaction CSV           |
| POST   | `/api/reports/transaction/{id}/print` | Print thermal receipt          |
| GET    | `/api/dashboard/summary`          | Dashboard summary stats            |

---

## Project Structure

```
CGI/
├── backend/                  # FastAPI Python application
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── auth.py
│   ├── models/               # SQLAlchemy ORM models
│   ├── schemas/              # Pydantic request/response schemas
│   ├── routers/              # FastAPI route handlers
│   ├── services/             # Business logic (detection, grading, pricing, reports)
│   ├── static/uploads/       # Uploaded inspection images
│   ├── tests/
│   └── requirements.txt
├── frontend/                 # PHP/HTML/CSS/JS web application
│   ├── index.php
│   ├── pages/
│   ├── components/
│   └── assets/
├── pi_node/                  # Raspberry Pi sensor node scripts
│   ├── sensor_node.py
│   ├── hx711_reader.py
│   ├── camera_capture.py
│   └── config.ini.example
├── database/
│   ├── schema.sql
│   └── seed.sql
├── models/                   # YOLOv8 .pt model files (not committed)
├── deployment/               # Apache vhost, systemd service files
├── .env.example
├── cgi-plan.md
└── README.md
```
