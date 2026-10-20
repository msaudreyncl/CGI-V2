# Raspberry Pi backend dependencies

## Supported baseline

- Raspberry Pi OS Bookworm 64-bit (aarch64)
- The OS-provided CPython 3.11
- A project virtual environment at `/var/www/html/CGI-V2/venv`

Python 3.13 is deliberately not the production baseline. `Pillow==10.3.0` has no
CPython 3.13 ARM64 wheel, so pip falls back to its source distribution; its old
build metadata then fails with `KeyError: '__version__'` (sometimes rendered as
`'**version**'`). The same unsupported-version risk applies to the older pinned
PyTorch/TorchVision stack. On CPython 3.11 all pinned native packages resolve to
pre-built ARM64 wheels.

## Recreate and install

These commands replace only the virtual environment; they do not touch the
database, uploads, model, `.env`, frontend, or source code.

```bash
cd /var/www/html/CGI-V2
deactivate 2>/dev/null || true
mv venv "venv.backup.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
python3 --version                    # must report Python 3.11.x on Bookworm
test "$(python3 -c 'import sys; print(str(sys.version_info.major)+"."+str(sys.version_info.minor))')" = "3.11" || { echo "Use Raspberry Pi OS Bookworm 64-bit with Python 3.11"; exit 1; }
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: -r backend/requirements.txt
python -m pip check
```

The old environment is renamed, not deleted. Remove the backup only after the
new service has been verified.

## Verify

```bash
cd /var/www/html/CGI-V2
source venv/bin/activate
python -c "import fastapi, uvicorn, sqlalchemy, pymysql, httpx; print('web/database imports OK')"
python -c "import numpy, cv2; from PIL import Image; print('vision imports OK', numpy.__version__, cv2.__version__)"
python -c "import torch, torchvision; from ultralytics import YOLO; print('ML imports OK', torch.__version__, torchvision.__version__)"
python -m pip check

cd backend
python -c "import main; print('FastAPI app import OK:', main.app.title)"
uvicorn main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8000/api/health
sudo cp /var/www/html/CGI-V2/deployment/cgi-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart cgi-backend
sudo systemctl --no-pager --full status cgi-backend
sudo journalctl -u cgi-backend -n 100 --no-pager
```

To test an actual model without changing data:

```bash
cd /var/www/html/CGI-V2/backend
source ../venv/bin/activate
python -c "from services.detection import _get_model; print(type(_get_model()).__name__, 'loaded OK')"
```

## Dependency decisions

- NumPy is pinned to 1.26.4 to avoid NumPy 2 API/ABI changes in this 2024 stack.
- PyTorch 2.2.2 and TorchVision 0.17.2 are a matched pair with CPython 3.11
  manylinux2014 aarch64 wheels.
- `opencv-python` is used because Ultralytics declares that distribution. Do not
  install `opencv-python-headless` alongside it: both own the `cv2` package.
- `httpx` replaces the unrelated `httpx2` distribution because backend code
  imports `httpx`.
- FastAPI and the remaining direct dependencies are pure Python or publish
  compatible CPython 3.11 ARM64/abi3 wheels.

The Pi sensor process has a separate environment and requirements file. Follow
`pi_node/INSTALL.md`; Picamera2, libcamera, and RPi.GPIO remain apt-managed and
visible through its `--system-site-packages` venv. HX711 and Requests remain
pip-managed. The backend dependency changes do not alter those hardware APIs.
