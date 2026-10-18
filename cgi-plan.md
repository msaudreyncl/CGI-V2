# Coffee Grade Identification (CGI) — Project Plan

## Top-Level Overview

**Goal:** Build an automated coffee bean quality assessment and suggested transactional pricing
system (CGI) for a thesis project. The system combines computer vision (YOLOv8), load-sensing
hardware (HX711 + 1 kg load cell), and a web application to identify coffee bean defects,
calculate defect percentages, assign a quality grade, and recommend a fair market price.

**Scope:**
- Raspberry Pi sensor node (camera + load cell) communicates with a LAN-hosted backend server.
- FastAPI (Python) backend handles YOLOv8 inference, grading logic, pricing, and data persistence.
- PHP/HTML/CSS/JS frontend served by the backend, optimized for a 7-inch touchscreen browser.
- MySQL database for all persistent data.
- Three user roles: Admin, Cooperative Officer, Farmer.
- PDF inspection reports, CSV exports, and ESC/POS thermal receipt printing.

**Confirmed Design Decisions:**
1. **Grading Logic:** Final grade = lowest class returned by any defect category. Any defect
   percentage that falls below the Class II lower bound but above Extra Class or Class I threshold
   is still graded at that class. Any defect exceeding the Class II upper bound retains Class II
   grade + over-threshold warning flag (no rejection class).
2. **Sample Weight Enforcement:** System enforces 350 g ± 10 g (340–360 g). If weight is outside
   this range, a warning is displayed and the inspection cannot proceed.
3. **Pricing:** Commodity price API used as placeholder (e.g., Commodities-API). Architecture
   isolates the price-fetch layer for a future BAFS swap.
4. **Frontend:** Bootstrap 5, touch-optimized for 7-inch LCD (1024×600), large tap targets.
5. **Database:** MySQL (XAMPP-compatible).

**Non-Goals:**
- Cloud deployment (local LAN only for thesis).
- Real-time video streaming (single-shot image capture per inspection).
- BAFS-connected pricing (placeholder external API used; architecture supports future swap).
- Training the YOLOv8 model from scratch (model training is a separate dataset task).

**Grading Standard (ASEAN Table of Defects):**

| Defect Class | Extra Class | Class I | Class II | Over-Threshold |
|---|---|---|---|---|
| Black bean | <4% | 4–6% | >6–15% | Warning flag |
| Moldy / Infested | <5% | 5–6% | >6–8% | Warning flag |
| Immature bean | <2% | 2–3% | >3–8% | Warning flag |
| Broken bean | <3% | 3–5% | >5–10% | Warning flag |
| Dried cherries | <0.5% | 0.5–1% | >1–2% | Warning flag |
| Foreign matter | <1% | 1–1.5% | 1.5–2% | Warning flag |

- **Final grade = lowest class returned by any single defect evaluation.**
- Any defect % exceeding its Class II upper bound → grade stays Class II + over-threshold warning flag.
- Weight outside 340–360 g → inspection blocked with on-screen warning; cannot proceed.

---

## Sub-Task 1 — Project Scaffolding & Environment Setup

**Status:** `[x] done`

**Intent:**
Establish the folder structure, dependency manifests, environment configuration, and database
schema so every subsequent sub-task has a stable foundation to build on.

**Expected Outcomes:**
- Repository root with clearly separated `backend/`, `frontend/`, `pi_node/`, and `database/` directories.
- `backend/requirements.txt` lists FastAPI, Uvicorn, SQLAlchemy, PyMySQL, Ultralytics (YOLOv8),
  OpenCV, Pillow, ReportLab (PDF), and python-escpos.
- `database/schema.sql` defines all tables: `users`, `farmers`, `inspections`, `defect_results`,
  `transactions`, `pricing_config`.
- `.env.example` documents all required environment variables (DB credentials, API keys, model path).
- `README.md` documents local setup steps for server and Pi node.

**Todo List:**
- [ ] Create top-level directory structure: `backend/`, `frontend/`, `pi_node/`, `database/`, `models/`.
- [ ] Write `backend/requirements.txt` with all Python dependencies.
- [ ] Write `database/schema.sql` with full table definitions (see Relevant Context below).
- [ ] Write `.env.example` with placeholder values for all config keys.
- [ ] Write `README.md` with setup instructions for server and Pi node.

**Relevant Context:**
- Database tables needed:
  - `users` — id, name, email, password_hash, role (admin | officer | farmer), created_at
  - `farmers` — id, user_id (FK), cooperative_id, contact_number, address
  - `inspections` — id, farmer_id (FK), officer_id (FK), sample_weight_g, total_beans_detected,
    image_path, grade (extra_class | class_i | class_ii), over_threshold_flag (bool), created_at
  - `defect_results` — id, inspection_id (FK), defect_type (enum), bean_count, defect_percentage,
    assigned_class (extra_class | class_i | class_ii), over_threshold (bool)
  - `transactions` — id, inspection_id (FK), weight_kg, price_per_kg, total_price, currency,
    price_source (api | manual), notes, created_at
  - `pricing_config` — id, grade (extra_class | class_i | class_ii), multiplier, updated_at, updated_by
  - `cooperatives` — id, name, location, contact

---

## Sub-Task 2 — Raspberry Pi Sensor Node

**Status:** `[x] done`

**Intent:**
Build the Pi-side script that reads the load cell weight via HX711, triggers the Pi Camera Module 3
to capture an image of the 350 g coffee sample, and POSTs both to the backend API endpoint. This
node is the physical data-collection layer.

**Expected Outcomes:**
- `pi_node/sensor_node.py` reads stable weight from HX711 (tare + calibration supported).
- On trigger (button press or API call), captures image with Pi Camera Module 3.
- POSTs `{ weight_g, image (base64 or multipart) }` to `POST /api/inspection/capture`.
- Simple CLI + optional GPIO button trigger.
- Config file (`pi_node/config.ini`) for server URL, calibration factor.

**Todo List:**
- [ ] Write `pi_node/requirements.txt` (RPi.GPIO, hx711-rpi, picamera2, requests).
- [ ] Implement HX711 weight reading with tare and calibration factor in `pi_node/hx711_reader.py`.
- [ ] Implement camera capture using `picamera2` in `pi_node/camera_capture.py`.
- [ ] Write main `pi_node/sensor_node.py` that ties weight + capture together and POSTs to backend.
- [ ] Write `pi_node/config.ini` with server URL, GPIO pin config, calibration factor placeholders.

**Relevant Context:**
- HX711 library: `hx711-rpi` or `RPi-hx711`.
- Pi Camera Module 3 uses `picamera2` (libcamera-based, not legacy `picamera`).
- Target sample weight is 350 g (system checks that weight is within ±10 g tolerance).
- Image should be captured at sufficient resolution for YOLOv8 (e.g., 1920×1080 or 1280×960).

---

## Sub-Task 3 — FastAPI Backend Core & Database Layer

**Status:** `[x] done`

**Intent:**
Build the FastAPI application skeleton, SQLAlchemy models, and all database access patterns.
This provides the shared infrastructure that all other backend sub-tasks depend on.

**Expected Outcomes:**
- `backend/main.py` initializes FastAPI with CORS, route registration, and startup events.
- `backend/models/` contains SQLAlchemy ORM models matching the schema from Sub-Task 1.
- `backend/database.py` provides a session factory and `get_db` dependency.
- `backend/config.py` loads all settings from `.env`.
- All tables created automatically on first run via `Base.metadata.create_all()`.
- Health-check endpoint `GET /api/health` returns `{ status: ok }`.

**Todo List:**
- [ ] Create `backend/main.py` with FastAPI app, CORS middleware, and router includes.
- [ ] Create `backend/database.py` with SQLAlchemy engine, session factory, and `get_db`.
- [ ] Create `backend/config.py` loading env vars (DB URL, JWT secret, model path, pricing API key).
- [ ] Create `backend/models/` — one file per domain: `user.py`, `inspection.py`,
  `defect_result.py`, `transaction.py`, `pricing_config.py`, `cooperative.py`.
- [ ] Create `backend/schemas/` — Pydantic request/response schemas for each model.
- [ ] Add `GET /api/health` endpoint.

**Relevant Context:**
- Use `python-dotenv` to load `.env`.
- Use `PyMySQL` as the MySQL driver with SQLAlchemy (`mysql+pymysql://`).
- JWT-based authentication will be added in Sub-Task 5; for now stubs are enough.

---

## Sub-Task 4 — YOLOv8 Detection & Grading Engine

**Status:** `[x] done`

**Intent:**
Implement the image processing pipeline: receive the captured image, run YOLOv8 inference to
count defective beans per class, then apply the ASEAN grading rules to determine the final
quality grade and any over-threshold warnings.

**Expected Outcomes:**
- `backend/services/detection.py` loads a YOLOv8 model and returns per-class bean counts from
  an input image.
- `backend/services/grading.py` takes defect counts + total bean count, calculates defect
  percentages, evaluates each against the ASEAN thresholds, and returns:
  `{ grade, over_threshold_flag, defect_breakdown: [{ defect_type, count, percentage, class }] }`.
- `POST /api/inspection/analyze` accepts image + weight, validates weight is within 340–360 g
  (returns HTTP 422 with descriptive error if out of range), calls detection + grading,
  persists `Inspection` + `DefectResult` rows, and returns the full grading result.
- Unit tests for the grading logic covering boundary conditions.

**Todo List:**
- [ ] Create `backend/services/detection.py` — load YOLOv8 model from configured path, run
  inference, map YOLO class IDs to defect names, return counts dict.
- [ ] Create `backend/services/grading.py` — implement ASEAN threshold table as a constant,
  calculate defect %, evaluate each class, return lowest-grade result + over_threshold flag.
- [ ] Create `backend/routers/inspection.py` with `POST /api/inspection/analyze` endpoint.
- [ ] Save uploaded image to `backend/static/uploads/` with UUID filename.
- [ ] Persist `Inspection` and `DefectResult` rows via SQLAlchemy.
- [ ] Validate weight range (340–360 g) at the API layer before running inference.
- [ ] Write `backend/tests/test_grading.py` with boundary-condition unit tests.

**Relevant Context:**
- YOLOv8 model file (`.pt`) is stored in `models/` directory; path set via env var `YOLO_MODEL_PATH`.
- Defect class names in YOLO must match exactly: `black_bean`, `moldy_infested`, `immature`,
  `broken`, `dried_cherry`, `foreign_matter`.
- Grading thresholds (from ASEAN table):
  - black_bean: Extra <4%, Class I 4–6%, Class II >6–15%
  - moldy_infested: Extra <5%, Class I 5–6%, Class II >6–8%
  - immature: Extra <2%, Class I 2–3%, Class II >3–8%
  - broken: Extra <3%, Class I 3–5%, Class II >5–10%
  - dried_cherry: Extra <0.5%, Class I 0.5–1%, Class II >1–2%
  - foreign_matter: Extra <1%, Class I 1–1.5%, Class II 1.5–2%
- Final grade = lowest class among all defect evaluations.
- Over-threshold flag = True if any defect % exceeds its Class II upper bound.

---

## Sub-Task 5 — Authentication & User Role Management

**Status:** `[x] done`

**Intent:**
Secure all API endpoints with JWT-based authentication. Implement user registration, login, and
role-based access control (RBAC) for Admin, Cooperative Officer, and Farmer roles.

**Expected Outcomes:**
- `POST /api/auth/login` returns a signed JWT on valid credentials.
- `GET /api/auth/me` returns the logged-in user's profile.
- `POST /api/auth/register` (Admin only) creates a new user.
- FastAPI dependency `require_role(roles)` guards all sensitive endpoints.
- Farmer users can only read their own inspection/transaction records.
- Passwords stored as bcrypt hashes.

**Todo List:**
- [ ] Add `python-jose`, `passlib[bcrypt]` to `requirements.txt`.
- [ ] Create `backend/auth.py` — JWT encode/decode, `get_current_user` dependency,
  `require_role` dependency factory.
- [ ] Create `backend/routers/auth.py` — login, me, register endpoints.
- [ ] Apply `require_role` guards to all existing and future routers.
- [ ] Seed an initial Admin user in `database/seed.sql`.

**Relevant Context:**
- JWT secret loaded from `JWT_SECRET` env var.
- Token expiry configurable via `JWT_EXPIRE_MINUTES` env var (default 480 = 8 hours for
  shift-length sessions).
- Farmer role restriction: all queries on `inspections` and `transactions` filter by `farmer_id`
  matching the current user.

---

## Sub-Task 6 — Pricing Engine

**Status:** `[x] done`

**Intent:**
Build the pricing recommendation layer. Fetch a live coffee market price from an external API
(e.g., Commodities API or similar), apply a per-grade multiplier from the `pricing_config` table,
and compute the suggested transaction price for a given inspection.

**Expected Outcomes:**
- `backend/services/pricing.py` fetches current green coffee price (USD/kg or PHP/kg) from
  external API, caches the result for a configurable TTL (e.g., 1 hour).
- Applies `pricing_config` grade multiplier: `suggested_price = market_rate × multiplier × weight_kg`.
- `POST /api/pricing/suggest` accepts `{ inspection_id }` and returns `{ price_per_kg, total_price, currency, source }`.
- Admin/Officer can override multipliers via `PUT /api/pricing/config`.
- API key and endpoint URL are env-var configurable to support future BAFS swap.

**Todo List:**
- [ ] Add `httpx` to `requirements.txt` for async external API calls.
- [ ] Create `backend/services/pricing.py` — external price fetch with in-memory TTL cache,
  grade multiplier lookup, price calculation.
- [ ] Create `backend/routers/pricing.py` — `POST /api/pricing/suggest`,
  `GET /api/pricing/config`, `PUT /api/pricing/config` (Admin/Officer only).
- [ ] Seed default multipliers in `database/seed.sql` (Extra=1.0, Class I=0.85, Class II=0.70).
- [ ] Add `PRICE_API_URL`, `PRICE_API_KEY`, `PRICE_CACHE_TTL_SECONDS` to `.env.example`.

**Relevant Context:**
- Suggested external API: Commodities-API (`https://commodities-api.com`) or
  Open Exchange Rates + a coffee commodity ticker. The integration point is isolated in
  `pricing.py` so it is trivially replaceable.
- Currency should default to PHP; conversion rate also fetched from API or set manually.
- If the external API is unavailable, fall back to the last cached price or a manually
  configured fallback price stored in `pricing_config`.

---

## Sub-Task 7 — Transaction Management

**Status:** `[x] done`

**Intent:**
Allow Cooperative Officers to finalize an inspection into a confirmed transaction (recording
actual agreed price, weight, and notes), and allow all roles to view transaction history
with appropriate data scoping.

**Expected Outcomes:**
- `POST /api/transactions` creates a transaction linked to an inspection (Officer/Admin only).
- `GET /api/transactions` returns paginated transaction list (Admin/Officer = all; Farmer = own).
- `GET /api/transactions/{id}` returns full transaction detail.
- `PUT /api/transactions/{id}` allows Officer/Admin to update notes or finalize price.
- Dashboard summary endpoint `GET /api/dashboard/summary` returns counts and totals.

**Todo List:**
- [ ] Create `backend/routers/transactions.py` with all CRUD endpoints.
- [ ] Implement farmer-scoped filtering in `GET /api/transactions` for Farmer role.
- [ ] Create `backend/routers/dashboard.py` with `GET /api/dashboard/summary`.
- [ ] Add pagination (limit/offset) to list endpoints.

**Relevant Context:**
- A transaction can only be created if the linked `inspection_id` does not already have a
  transaction (one inspection → one transaction).
- Dashboard summary should include: total inspections today/month, grade distribution counts,
  average price per grade, total weight processed.

---

## Sub-Task 8 — Reports, PDF Export & Thermal Printing

**Status:** `[x] done`

**Intent:**
Generate human-readable outputs: a PDF inspection report per inspection, a CSV transaction
history export, and an ESC/POS thermal receipt per transaction.

**Expected Outcomes:**
- `GET /api/reports/inspection/{id}/pdf` returns a PDF with: farmer info, sample weight,
  captured image thumbnail, defect breakdown table, grade, over-threshold warning, suggested price.
- `GET /api/reports/transactions/csv` returns a CSV download of transaction history
  (date-range filterable; scoped by role).
- `POST /api/reports/transaction/{id}/print` sends an ESC/POS receipt to the configured
  thermal printer over the network or USB.
- Receipt content: farmer name, date, grade, weight, price per kg, total price, officer name.

**Todo List:**
- [ ] Add `reportlab` and `python-escpos` to `requirements.txt`.
- [ ] Create `backend/services/pdf_report.py` — build inspection PDF using ReportLab.
- [ ] Create `backend/services/csv_export.py` — stream CSV from transaction query.
- [ ] Create `backend/services/thermal_print.py` — format and send ESC/POS receipt.
- [ ] Create `backend/routers/reports.py` — expose all three report endpoints.
- [ ] Add `THERMAL_PRINTER_HOST` and `THERMAL_PRINTER_PORT` to `.env.example`.

**Relevant Context:**
- Thermal printer (80 mm) connected over network (TCP/IP) or USB to the server machine.
- `python-escpos` supports both network and USB printers via `Network` and `Usb` classes.
- PDF layout: CGI logo header, farmer + officer info, date/time, sample weight, YOLO image,
  defect table, grade badge (color-coded), price box, footer with system name + version.

---

## Sub-Task 9 — Frontend (PHP/HTML/CSS/JS)

**Status:** `[x] done`

**Intent:**
Build the web UI that runs in the Pi's 7-inch touchscreen browser. All pages communicate with
the FastAPI backend via REST API. The UI must be touch-friendly (large tap targets, minimal
typing) and work well at ~1024×600 resolution.

**Expected Outcomes:**
- Login page with role-based redirect.
- **Inspection Workflow** (Officer): trigger capture → view live weight → view detection result
  image with bounding boxes → view defect breakdown + grade + suggested price → confirm
  transaction or discard.
- **Transaction History** (Admin/Officer/Farmer — scoped): searchable, paginated table with
  PDF download and print buttons per row.
- **Dashboard** (Admin/Officer): grade distribution chart, totals, recent activity.
- **User Management** (Admin only): create/edit/deactivate users.
- **Pricing Config** (Admin/Officer): view and update grade multipliers.
- Responsive, touch-optimized layout using Bootstrap 5 or Tailwind CSS.

**Todo List:**
- [ ] Create `frontend/` directory structure: `pages/`, `components/`, `assets/css/`, `assets/js/`.
- [ ] Build `login.php` — auth form, calls `POST /api/auth/login`, stores JWT in sessionStorage.
- [ ] Build `dashboard.php` — summary cards, grade distribution chart (Chart.js).
- [ ] Build the inspection workflow in `dashboard.php` (trigger → weight → analyze →
  result → confirm).
- [ ] Build `history.php` — paginated transaction history table with search/filter and per-row actions.
- [ ] Build `users.php` (Admin) — user list, add/edit modal.
- [ ] Build `configuration.php` (Admin/Officer) — pricing multiplier configuration form.
- [ ] Create `assets/js/api.js` — shared fetch wrapper that injects JWT Authorization header.
- [ ] Create `assets/css/main.css` — touch-friendly overrides (min 44 px tap targets, large fonts).
- [ ] Add `index.php` that redirects to login or dashboard based on session.

**Relevant Context:**
- PHP is used only as a thin server-side template layer (session check, HTML output). All data
  operations go through the FastAPI JSON API.
- JWT stored in `sessionStorage`; PHP session stores user role for server-side redirect guards.
- Inspection workflow is the primary UX on the touchscreen — prioritize clarity and large buttons.
- Chart.js for dashboard charts (CDN import, no build step needed).
- Backend serves static files from `backend/static/`; frontend PHP files served by Apache/Nginx
  on the same machine.

---

## Sub-Task 10 — Integration, Testing & Deployment Config

**Status:** `[x] done`

**Intent:**
Wire all components together, run end-to-end tests, write the deployment configuration (Apache
vhost for PHP frontend, Uvicorn systemd service for FastAPI backend), and produce a final
demo-ready setup guide.

**Expected Outcomes:**
- `backend/tests/` contains integration tests covering the full inspection → transaction flow.
- Apache config (`deployment/apache-frontend.conf`) serves the PHP frontend on port 80.
- Systemd unit file (`deployment/cgi-backend.service`) runs FastAPI with Uvicorn on port 8000.
- Pi node `pi_node/cgi-node.service` systemd unit for auto-start on boot.
- Final `README.md` updated with complete setup checklist.

**Todo List:**
- [ ] Write `backend/tests/test_integration.py` — full flow: capture mock → analyze → grade →
  price → transaction → PDF.
- [ ] Write `deployment/apache-frontend.conf` — VirtualHost for PHP frontend, proxy
  `/api/` to `http://localhost:8000`.
- [ ] Write `deployment/cgi-backend.service` — systemd unit for Uvicorn.
- [ ] Write `pi_node/cgi-node.service` — systemd unit for Pi sensor node auto-start.
- [ ] Update `README.md` with end-to-end setup, calibration procedure, and troubleshooting.

**Relevant Context:**
- Apache mod_proxy + mod_proxy_http used to forward `/api/*` to FastAPI — single origin
  avoids CORS issues in production.
- Pi node must be configured with the server's LAN IP address in `pi_node/config.ini`.
- YOLOv8 model file must be placed in `models/` before first run; path set in `.env`.
