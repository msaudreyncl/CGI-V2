# Raspberry Pi backend/database audit — 2026-10-20

## Root cause and credential loading

A real TCP connection using the original configuration reproduced MariaDB error
1698: `Access denied for user 'root'@'localhost'`. Both the local `.env` and the
previous `Settings.DB_USER` default selected root. PyMySQL connects over TCP even
when its host is `localhost`; it does not automatically use the CLI's Unix socket.
MariaDB commonly authenticates local root through OS identity / `unix_socket`.
That explains this failure, but the installed root plugin could not be inspected:
`sudo -n mariadb` required a password. Do not change root authentication to fix CGI.

`backend/config.py` loads the project-root `.env` using an absolute path, independent
of working directory. `load_dotenv()` does not override existing environment values.
The systemd unit also loads this file with `EnvironmentFile=`. Settings are evaluated
at module import and cached; restart the process after editing configuration.
Do not `source .env`: it is dotenv configuration, not a shell script. Use simple,
single-quoted literal secrets without variable expansion, compatible with dotenv
and systemd. The URL already escapes username/password special characters.

## Changes

- Default DB host/account: `127.0.0.1` / `cgi_app`; existing `.env` is deliberately
  preserved until an administrator provisions matching credentials.
- Startup now rejects root and performs only connectivity and required table/column
  checks. It never calls `create_all()`. An explicit helper remains for isolated
  tests/new database initialization. Missing schema reports fail startup without DDL.
- SQL echo is disabled and exception parameters hidden to reduce sensitive logging;
  connection establishment has a ten-second timeout. Shutdown disposes the pool.
- Configured uploads are served at the existing `/static/uploads/` URLs, including
  when `UPLOAD_DIR` points outside the default directory. Static mount import no
  longer requires a pre-existing directory; lifespan creates the upload directory.
- Apache's example document root now matches `/var/www/html/CGI-V2/frontend`.
  The backend unit orders after `mariadb.service` on Raspberry Pi OS.
- The environment example no longer suggests root or an unsupported CIDR CORS origin.
- Integration tests use a fresh temporary SQLite database rather than dropping and
  deleting the tracked `backend/tests/test_run.db`. Added read-only startup checks.

No live schema, grants, rows, hardware configuration, or local secrets were changed.

## Exact Raspberry Pi OS recovery commands

Run these in an interactive terminal with sudo access. Commands below target the
existing `cgi_db`; first confirm that this is the intended database. Stop on an
unexpected result. Do not import seed.sql, reset_admin.py, or the base schema over
an existing installation as part of this authentication fix.

### 1. Inspect and back up before any administrative changes

```bash
cd /var/www/html/CGI-V2
sudo systemctl status mariadb --no-pager
sudo mariadb --execute="SELECT VERSION(); SHOW DATABASES; SELECT User,Host,plugin FROM mysql.user WHERE User IN ('root','cgi_app');"
sudo mariadb cgi_db --execute="SHOW TABLES; SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='cgi_db' ORDER BY TABLE_NAME,ORDINAL_POSITION;"
sudo install -d -m 700 /var/backups/cgi
sudo sh -c 'umask 077; mariadb-dump --single-transaction --routines --triggers --events cgi_db > /var/backups/cgi/cgi_db-$(date +%Y%m%d-%H%M%S).sql'
```

Verify the dump command succeeded and the file is nonempty. `--single-transaction`
assumes InnoDB and no concurrent schema changes. This is a backup, not a restore.

### 2. Create the dedicated account

Generate a password locally (keep it in your password manager):

```bash
openssl rand -hex 32
sudo env MYSQL_HISTFILE=/dev/null mariadb
```

In the MariaDB prompt, replace `PASTE_GENERATED_PASSWORD` with that generated value:

```sql
CREATE USER 'cgi_app'@'127.0.0.1' IDENTIFIED BY 'PASTE_GENERATED_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE ON cgi_db.* TO 'cgi_app'@'127.0.0.1';
SHOW GRANTS FOR 'cgi_app'@'127.0.0.1';
EXIT;
```

Use a new account name if this account already exists unexpectedly; do not reset
an existing account's password or grants without checking its consumers. Do not use
`CREATE USER IF NOT EXISTS` to mask a password mismatch. No global privileges,
DDL privileges, `GRANT OPTION`, wildcard host, or `FLUSH PRIVILEGES` are needed.
These four data privileges support current routes, including deletion and login's
`last_login_at` update. Root's authentication remains untouched.

### 3. Update only the relevant local environment values

```bash
nano /var/www/html/CGI-V2/.env
```

Set (use the exact password from step 2):

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=cgi_db
DB_USER=cgi_app
DB_PASSWORD='PASTE_GENERATED_PASSWORD'
APP_ENV=production
APP_DEBUG=false
```

Replace the existing placeholder `JWT_SECRET` with another independent random
value from `openssl rand -hex 32`. A JWT secret change invalidates existing sessions.
Set exact browser origins if cross-origin access is needed; same-origin Apache
requests do not need additional CORS entries. Retain existing printer, camera,
scale, pricing, and model settings.

Keep `.env` private; PID 1 reads `EnvironmentFile` before starting `www-data`, so
the service does not require Apache/PHP to read `.env`. For manual checks use the
file owner (`cgi` here). Do not make it world-readable or put DB credentials in PHP.

### 4. Verify account matching and the schema without changing it

```bash
mariadb --protocol=TCP --host=127.0.0.1 --port=3306 --user=cgi_app --password cgi_db --execute="SELECT VERSION(),DATABASE(),USER(),CURRENT_USER(); SHOW GRANTS; SELECT 1;"
cd /var/www/html/CGI-V2
env -u DB_HOST -u DB_PORT -u DB_NAME -u DB_USER -u DB_PASSWORD venv/bin/python backend/database.py
```

The CLI prompts for the password; never pass it in argv. `CURRENT_USER()` must
identify the dedicated account; inspect host/account precedence if it does not.
The Python command deliberately clears inherited DB overrides so it tests `.env`.
The schema check verifies required names only, not all types, indexes, constraints,
privileges, row consistency, or version compatibility.

If schema fields are missing, **stop here**. `schema.sql` is the original seven-table
baseline. Models additionally require `pending_transactions`, inspection dual-image
fields/txn_number, transaction status/print_status (migration 001), and user display
ID/last_login_at (migration 002). `create_all()` cannot add columns to existing tables.
Have a DBA compare `SHOW CREATE TABLE` with the migrations and review only missing
changes after a verified backup. Migration 002 updates existing display IDs that are
NULL; it is not purely DDL. The scripts use MariaDB `ADD COLUMN IF NOT EXISTS` and
window functions; do not assume they execute unchanged on every MySQL version.
ORM IDs use signed `Integer` while the supplied SQL uses unsigned IDs; do not use
ORM table creation to fill individual gaps in this existing schema with foreign keys.

### 5. Verify service permissions and install configuration

The current upload directory is owned by `cgi:nogroup`, mode 775; `www-data` is
not in that group. Grant write access only to uploads, not the entire repository:

```bash
sudo install -d -o cgi -g www-data -m 2770 /var/www/html/CGI-V2/backend/static/uploads
sudo -u www-data test -w /var/www/html/CGI-V2/backend/static/uploads
sudo -u www-data test -x /var/www/html/CGI-V2/venv/bin/uvicorn
sudo -u www-data test -r /var/www/html/CGI-V2/models/cgi_yolov8.pt
sudo cp deployment/cgi-backend.service /etc/systemd/system/cgi-backend.service
sudo systemctl daemon-reload
sudo systemctl restart cgi-backend
sudo systemctl status cgi-backend --no-pager --full
sudo journalctl -u cgi-backend -n 100 --no-pager
curl --fail-with-body http://127.0.0.1:8000/api/health
```

The model read check currently fails: supply the existing trained model at the
configured path before testing inference. Do not substitute or retrain a model
as part of this database repair. Existing upload files may separately need readable
permissions. Keep uploads out of source control.

If Apache already has a CGI virtual host, update that host instead of enabling a
duplicate. Otherwise install the example, then validate before reloading:

```bash
sudo a2enmod proxy proxy_http
sudo cp deployment/apache-frontend.conf /etc/apache2/sites-available/cgi.conf
sudo a2ensite cgi.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
curl --fail-with-body -H 'Host: cgi.local' http://127.0.0.1/api/health
curl --fail-with-body -H 'Host: cgi.local' http://127.0.0.1/login.php
```

PHP's `frontend/api.php` uses cURL to FastAPI (`CGI_API_BASE`, default localhost:8000).
There is no PHP database connection or second set of MySQL credentials. Browser JS
uses same-origin `/api/*`; Apache must proxy those absolute paths and `/static/*`.
Do not use `localhost` in browser configuration to refer to a remote Pi. When PHP
and FastAPI are on the same Pi the existing PHP default is appropriate; set Apache
`SetEnv CGI_API_BASE http://127.0.0.1:8000` if local IPv6 resolution is problematic.

### 6. Authenticate and smoke-test read endpoints

The following prompts privately for an existing user's password and keeps its JWT
in memory. Successful login updates `last_login_at`; all subsequent requests are
GETs. Use an administrator/officer to verify the administrative endpoints (farmer
accounts should receive 403 for restricted endpoints).

```bash
cd /var/www/html/CGI-V2
venv/bin/python - <<'PY'
from getpass import getpass
import httpx
with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30) as client:
    response = client.post('/api/auth/login', json={
        'email': input('Existing account email: '), 'password': getpass('Password: ')})
    print('login:', response.status_code)
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
    for path in ('/api/auth/me', '/api/dashboard/summary', '/api/users/farmers',
                 '/api/inspection', '/api/transactions', '/api/pricing/config',
                 '/api/reports/transactions/csv'):
        result = client.get(path)
        print(path, result.status_code)
PY
```

Hardware validation is separate: `/api/hardware/status` assumes camera readiness
from `/weight`; a 200 or `ready` is not proof of a working camera, accurate scale,
printer, or model. Test physical capture/printing in a controlled workflow after
database checks. Do not send synthetic inspections to the production database.

## Broader audit findings (business/hardware behavior retained)

- All backend Python modules, routes, models, schemas, services, tests and requirements
  were reviewed, together with PHP API integration, schema/seed/migrations, deployment
  examples and the Pi integration contract. Python imports assume `backend` on
  `sys.path`; use the service working directory or `uvicorn --app-dir backend main:app`.
  `uvicorn backend.main:app` from root does not resolve those absolute imports.
- Paths for `.env`, model and uploads already resolve from project root. Linux is
  case-sensitive; preserve exact filenames and path casing. No Windows drive paths
  were found in backend code. `.env` is ignored and not tracked by Git.
- The installed environment is aarch64/Python 3.11.17. Every pinned direct requirement
  is installed at its specified version; `pip check` passes. NumPy, cv2, Torch,
  TorchVision and Ultralytics actually imported successfully. Keep the separate Pi
  hardware environment and apt-managed libcamera/Picamera2/GPIO stack. This verifies
  compatibility here, not security currency of the older pins or 32-bit Pi support.
  Writable Matplotlib/Ultralytics cache locations should be provided for `www-data`
  if default home cache warnings occur. Two workers may hold two model copies in RAM.
- The trained `.pt` file is absent; inference cannot succeed until it is supplied.
  Price API credentials/provider semantics and external connectivity are unverified;
  the service falls back to cached/configured prices. Coffee-rate direction/units
  should be confirmed with the actual provider before relying on monetary outputs.
- The local JWT secret is a placeholder and must be replaced before production use.
  Existing password reset/seed scripts contain a known default admin password;
  neither script was run. Existing accounts and password hashes were preserved.
- Existing authentication/authorization concerns remain: farmer inspection/PDF
  detail ownership checks do not deny a farmer with no profile; legacy single-image
  capture accepts any authenticated role. Role-prefixed user IDs use `count + 1`,
  which can collide after deletion or concurrent registration. Farmer deletion may
  encounter linked-row constraints. These need separately tested business/security
  changes rather than incidental changes during the database startup repair.
- Other retained behavior: JWT subjects are converted to integers without a guard;
  malformed stored bcrypt hashes can raise; passwords over bcrypt's byte limit need
  an explicit policy. Login.php emits HTML before session/redirect logic and trims
  passwords, which can cause header failures without output buffering or change a
  whitespace-bearing password. Confirm PHP session storage and output buffering.
- Workflow operations do not consistently enforce state transitions or ownership;
  repeated analysis relies on uniqueness/transaction rollback. File writes and DB
  transactions are not fully atomic (especially legacy single-image capture).
  These were not redesigned, and grading/pricing rules were preserved.
- Datetimes mix UTC application values, DB-local defaults and local date-based IDs;
  check OS/DB timezone assumptions before interpreting daily totals after migration.
- `pi_node/cgi-node.service` still targets user `pi` and `/home/pi/CGI`, and starts
  `sensor_node.py`, not the separately required `pi_server.py`. Inspect the installed
  units before changing those paths/processes. The sensor's configured static token
  is not a replacement for FastAPI's expiring user JWT. Pi HTTP endpoints have no
  authentication; keep their access limited to trusted hosts. Missing hardware
  imports can select simulated values, so validate actual physical operation.
- All frontend PHP files passed `php -l`; PHP cURL and session extensions are present.
  Syntax checks do not prove web login, Apache routing or session persistence.

## Verification record

- Confirmed original live error 1698 using original credentials, without writes.
- Live schema/plugin inspection and account provisioning could not proceed because
  administrator sudo authentication was unavailable. No production CRUD/login,
  successful live startup, hardware operation or external-price request is claimed.
- Python compilation (43 backend modules) and `git diff --check` passed. Dependency
  metadata and actual ARM64 imports passed as described above.
- Installed pytest into the existing venv for verification. All **51 tests passed**
  in 10.44 seconds, with one Starlette/AnyIO deprecation warning. These include four
  new schema-validation tests and existing grading/authentication/inspection/pricing/
  transaction/PDF/CSV/dashboard tests. The initial sandboxed TestClient run stalled
  and was stopped; the same suite completed outside the sandbox. Tests used fresh
  temporary SQLite/uploads and mocked detection/printer/external pricing. They do
  not establish MariaDB compatibility, dual-view workflow coverage or real hardware
  functionality. The tracked test database was untouched.

Reproduce the isolated suite (no production database needed):

```bash
cd /var/www/html/CGI-V2
DB_USER=cgi_app UPLOAD_DIR=/tmp/cgi-audit-test-uploads venv/bin/python -m pytest backend/tests -q
```

References: [MariaDB socket authentication](https://mariadb.com/docs/server/reference/plugins/authentication-plugins/authentication-plugin-unix-socket),
[SQLAlchemy metadata and schema lifecycle](https://docs.sqlalchemy.org/en/20/core/metadata.html),
[PyTorch 2.2.2 release files](https://pypi.org/project/torch/2.2.2/).
