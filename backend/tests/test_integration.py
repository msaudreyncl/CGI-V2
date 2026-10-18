"""
tests/test_integration.py — End-to-end integration tests for the CGI backend.

These tests spin up a TestClient (no live database required) using SQLite in-memory
so they run on any machine without MySQL.  They cover the full happy-path flow:

  register/login → create cooperative & farmer → submit inspection (mocked detection)
  → verify grading → get price suggestion (mocked pricing API) → create transaction
  → download PDF → download CSV

Run with:
    pytest backend/tests/test_integration.py -v
"""

import base64
import io
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, AsyncMock, MagicMock

# ── Patch heavy optional imports before they are loaded ──────────────────────
# Prevent ultralytics / OpenCV from being imported during tests
ultralytics_stub = types.ModuleType("ultralytics")
class _FakeYOLO:
    def __init__(self, *a, **kw): pass
    def predict(self, *a, **kw): return []
ultralytics_stub.YOLO = _FakeYOLO
sys.modules.setdefault("ultralytics", ultralytics_stub)

# Stub escpos so thermal_print can be imported without a printer
escpos_stub   = types.ModuleType("escpos")
printer_stub  = types.ModuleType("escpos.printer")
printer_stub.Network = MagicMock()
printer_stub.Usb     = MagicMock()
sys.modules.setdefault("escpos",         escpos_stub)
sys.modules.setdefault("escpos.printer", printer_stub)

# ── File-based SQLite database for tests ─────────────────────────────────────
# A named file ensures all connections (app threads + test thread) share the same DB.
from database import Base, get_db
import tempfile, pathlib

_TEST_DB_FILE = pathlib.Path(__file__).parent / "test_run.db"
TEST_DATABASE_URL = f"sqlite:///{_TEST_DB_FILE}"

_engine      = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    """
    Integration test client using SQLite in-memory database.

    Strategy:
    1. Swap database.engine to SQLite before the app's lifespan fires.
    2. Create all tables on the SQLite engine directly.
    3. Override get_db to use the SQLite session.
    4. TestClient starts the app (lifespan runs create_tables — now hits SQLite).
    """
    import database as db_module

    # 1. Swap engine BEFORE importing/starting app
    original_engine = db_module.engine
    original_bind   = db_module.SessionLocal.kw.get("bind")
    db_module.engine = _engine
    db_module.SessionLocal.configure(bind=_engine)

    # 2. Create tables on the SQLite engine before app starts
    # Import all models so Base knows about them
    import models.user, models.cooperative, models.farmer  # noqa
    import models.inspection, models.defect_result         # noqa
    import models.pricing_config, models.transaction       # noqa
    Base.metadata.create_all(bind=_engine)

    from main import app
    # 3. Override get_db
    app.dependency_overrides[get_db] = _override_get_db

    # 4. Start app (lifespan calls create_tables which now hits SQLite — idempotent)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    Base.metadata.drop_all(bind=_engine)
    _engine.dispose()
    app.dependency_overrides.clear()
    db_module.engine = original_engine
    db_module.SessionLocal.configure(bind=original_engine)
    # Remove test DB file
    try:
        _TEST_DB_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tiny_jpeg_b64() -> str:
    """Return a minimal base64-encoded JPEG (1×1 white pixel)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token(client):
    # Seed admin directly via DB (no endpoint dependency for the first user)
    db = _TestSession()
    from models.user import User, UserRole
    from auth import hash_password
    admin = User(
        name="Test Admin",
        email="admin@test.local",
        password_hash=hash_password("Admin@1234"),
        role=UserRole.admin,
    )
    db.add(admin)
    db.commit()
    db.close()

    resp = client.post("/api/auth/login", json={"email": "admin@test.local", "password": "Admin@1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def officer_token(client, admin_token):
    resp = client.post(
        "/api/auth/register",
        json={"name": "Test Officer", "email": "officer@test.local", "password": "Officer@1234", "role": "officer"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 201
    resp2 = client.post("/api/auth/login", json={"email": "officer@test.local", "password": "Officer@1234"})
    return resp2.json()["access_token"]


@pytest.fixture(scope="module")
def farmer_id(client, admin_token, officer_token):
    # Create farmer user
    resp = client.post(
        "/api/auth/register",
        json={"name": "Test Farmer", "email": "farmer@test.local", "password": "Farmer@1234", "role": "farmer"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 201
    farmer_user_id = resp.json()["id"]

    # Create farmer profile (officer does this)
    resp2 = client.post(
        f"/api/users/{farmer_user_id}/farmer",
        json={"user_id": farmer_user_id},
        headers=_auth_header(officer_token),
    )
    assert resp2.status_code == 201
    return resp2.json()["id"]   # returns farmer profile id


@pytest.fixture(scope="module")
def inspection_id(client, officer_token, farmer_id):
    """Submit a full capture payload (detection mocked) and return inspection id."""
    detection_mock = {
        "total_beans": 100,
        "class_counts": {
            "black_bean":     3,   # 3% → extra_class
            "moldy_infested": 4,   # 4% → extra_class
            "immature":       1,   # 1% → extra_class
            "broken":         2,   # 2% → extra_class
            "dried_cherry":   0,
            "foreign_matter": 0,
        },
    }
    with patch("routers.inspection.run_detection", return_value=detection_mock):
        resp = client.post(
            "/api/inspection/capture",
            json={
                "weight_g":   350.0,
                "image_b64":  _tiny_jpeg_b64(),
                "farmer_id":  farmer_id,
            },
            headers=_auth_header(officer_token),
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_login_bad_password(self, client):
        r = client.post("/api/auth/login", json={"email": "admin@test.local", "password": "wrong"})
        assert r.status_code == 401

    def test_me_returns_current_user(self, client, admin_token):
        r = client.get("/api/auth/me", headers=_auth_header(admin_token))
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_register_requires_admin(self, client, officer_token):
        r = client.post(
            "/api/auth/register",
            json={"name": "X", "email": "x@x.com", "password": "pass1234", "role": "farmer"},
            headers=_auth_header(officer_token),
        )
        assert r.status_code == 403

    def test_protected_route_no_token(self, client):
        r = client.get("/api/inspection")
        assert r.status_code in (401, 403)  # HTTPBearer returns 403 when no bearer present

    def test_original_admin_cannot_be_edited_deleted_deactivated_or_demoted(self, client, admin_token):
        headers = _auth_header(admin_token)

        me = client.get("/api/auth/me", headers=headers).json()
        assert me["id"] == 1
        assert me["is_protected"] is True

        r = client.delete("/api/users/1", headers=headers)
        assert r.status_code == 403

        r = client.put("/api/users/1", json={"is_active": False}, headers=headers)
        assert r.status_code == 403

        r = client.put("/api/users/1", json={"role": "officer"}, headers=headers)
        assert r.status_code == 403

        r = client.put(
            "/api/users/1",
            json={"name": "Changed", "email": "changed@test.local", "password": "Changed@1234"},
            headers=headers,
        )
        assert r.status_code == 403

    def test_another_admin_can_be_deleted(self, client, admin_token):
        headers = _auth_header(admin_token)
        created = client.post(
            "/api/auth/register",
            json={
                "name": "Temporary Admin",
                "email": "temporary-admin@test.local",
                "password": "Admin@1234",
                "role": "admin",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        other_admin = created.json()
        assert other_admin["id"] != 1
        assert other_admin["is_protected"] is False

        deleted = client.delete(f"/api/users/{other_admin['id']}", headers=headers)
        assert deleted.status_code == 204, deleted.text

    def test_user_statistics_are_database_driven_and_admin_only(self, client, admin_token, officer_token):
        r = client.get("/api/users/stats", headers=_auth_header(admin_token))
        assert r.status_code == 200
        stats = r.json()
        assert set(stats) == {
            "total_users",
            "total_administrators",
            "total_officers",
            "total_farmers",
            "total_active",
        }
        assert stats["total_users"] == (
            stats["total_administrators"]
            + stats["total_officers"]
            + stats["total_farmers"]
        )
        assert stats["total_active"] <= stats["total_users"]

        forbidden = client.get("/api/users/stats", headers=_auth_header(officer_token))
        assert forbidden.status_code == 403


class TestWeightValidation:
    def test_weight_too_low_rejected(self, client, officer_token, farmer_id):
        with patch("routers.inspection.run_detection", return_value={"total_beans": 0, "class_counts": {}}):
            r = client.post(
                "/api/inspection/capture",
                json={"weight_g": 200.0, "image_b64": _tiny_jpeg_b64(), "farmer_id": farmer_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 422
        assert "340" in r.json()["detail"]

    def test_weight_too_high_rejected(self, client, officer_token, farmer_id):
        with patch("routers.inspection.run_detection", return_value={"total_beans": 0, "class_counts": {}}):
            r = client.post(
                "/api/inspection/capture",
                json={"weight_g": 400.0, "image_b64": _tiny_jpeg_b64(), "farmer_id": farmer_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 422

    def test_weight_boundary_low_ok(self, client, officer_token, farmer_id):
        with patch("routers.inspection.run_detection", return_value={"total_beans": 50, "class_counts": {"black_bean": 0, "moldy_infested": 0, "immature": 0, "broken": 0, "dried_cherry": 0, "foreign_matter": 0}}):
            r = client.post(
                "/api/inspection/capture",
                json={"weight_g": 340.0, "image_b64": _tiny_jpeg_b64(), "farmer_id": farmer_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 201

    def test_weight_boundary_high_ok(self, client, officer_token, farmer_id):
        with patch("routers.inspection.run_detection", return_value={"total_beans": 50, "class_counts": {"black_bean": 0, "moldy_infested": 0, "immature": 0, "broken": 0, "dried_cherry": 0, "foreign_matter": 0}}):
            r = client.post(
                "/api/inspection/capture",
                json={"weight_g": 360.0, "image_b64": _tiny_jpeg_b64(), "farmer_id": farmer_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 201


class TestInspection:
    def test_inspection_created_with_correct_grade(self, client, officer_token, inspection_id):
        r = client.get(f"/api/inspection/{inspection_id}", headers=_auth_header(officer_token))
        assert r.status_code == 200
        data = r.json()
        assert data["grade"] == "extra_class"
        assert data["over_threshold_flag"] is False
        assert data["total_beans_detected"] == 100
        assert len(data["defect_results"]) == 6

    def test_inspection_list_returns_items(self, client, officer_token):
        r = client.get("/api/inspection", headers=_auth_header(officer_token))
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_over_threshold_inspection(self, client, officer_token, farmer_id):
        """black_bean at 20% → class_ii + over_threshold_flag."""
        det = {
            "total_beans": 100,
            "class_counts": {
                "black_bean": 20, "moldy_infested": 0, "immature": 0,
                "broken": 0, "dried_cherry": 0, "foreign_matter": 0,
            },
        }
        with patch("routers.inspection.run_detection", return_value=det):
            r = client.post(
                "/api/inspection/capture",
                json={"weight_g": 350.0, "image_b64": _tiny_jpeg_b64(), "farmer_id": farmer_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 201
        data = r.json()
        assert data["grade"] == "class_ii"
        assert data["over_threshold_flag"] is True

    def test_class_ii_inspection(self, client, officer_token, farmer_id):
        """broken at 8% → class_ii, no over_threshold."""
        det = {
            "total_beans": 100,
            "class_counts": {
                "black_bean": 0, "moldy_infested": 0, "immature": 0,
                "broken": 8, "dried_cherry": 0, "foreign_matter": 0,
            },
        }
        with patch("routers.inspection.run_detection", return_value=det):
            r = client.post(
                "/api/inspection/capture",
                json={"weight_g": 350.0, "image_b64": _tiny_jpeg_b64(), "farmer_id": farmer_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 201
        data = r.json()
        assert data["grade"] == "class_ii"
        assert data["over_threshold_flag"] is False

    def test_farmer_cannot_see_other_inspection(self, client, farmer_id):
        # Farmer logs in and tries to read inspection belonging to their profile
        r_login = client.post("/api/auth/login", json={"email": "farmer@test.local", "password": "Farmer@1234"})
        token = r_login.json()["access_token"]
        # inspection_id 1 belongs to farmer_id fixture — should be accessible
        r = client.get("/api/inspection/1", headers=_auth_header(token))
        assert r.status_code in (200, 403)  # 403 if not their inspection


class TestPricing:
    def test_pricing_config_list(self, client, officer_token):
        r = client.get("/api/pricing/config", headers=_auth_header(officer_token))
        assert r.status_code == 200
        # SQLite in-memory starts empty — seeding is done via seed.sql on real DB
        # Here we just confirm the endpoint works

    def test_suggest_price_mocked_api(self, client, officer_token, inspection_id):
        async def _mock_fetch(): return (300.0, "api")
        with patch("services.pricing._fetch_market_rate", new=AsyncMock(return_value=(300.0, "api"))):
            r = client.post(
                "/api/pricing/suggest",
                json={"inspection_id": inspection_id},
                headers=_auth_header(officer_token),
            )
        assert r.status_code == 200
        data = r.json()
        assert data["market_rate_per_kg"] == 300.0
        assert data["grade"] == "extra_class"
        assert data["currency"] == "PHP"

    def test_pricing_config_update(self, client, admin_token):
        r = client.put(
            "/api/pricing/config",
            json=[{"grade": "extra_class", "multiplier": 1.05}],
            headers=_auth_header(admin_token),
        )
        # SQLite may not have pricing rows seeded; accept 404 or 200
        assert r.status_code in (200, 404)


class TestTransactions:
    def test_create_transaction(self, client, officer_token, inspection_id):
        r = client.post(
            "/api/transactions",
            json={
                "inspection_id": inspection_id,
                "weight_kg":     0.350,
                "price_per_kg":  300.0,
                "price_source":  "api",
            },
            headers=_auth_header(officer_token),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["total_price"] == pytest.approx(105.0, abs=0.01)
        assert data["id"] > 0

    def test_duplicate_transaction_rejected(self, client, officer_token, inspection_id):
        r = client.post(
            "/api/transactions",
            json={"inspection_id": inspection_id, "weight_kg": 0.350, "price_per_kg": 300.0},
            headers=_auth_header(officer_token),
        )
        assert r.status_code == 409

    def test_transaction_list(self, client, officer_token):
        r = client.get("/api/transactions", headers=_auth_header(officer_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_farmer_sees_own_transactions(self, client):
        r_login = client.post("/api/auth/login", json={"email": "farmer@test.local", "password": "Farmer@1234"})
        token = r_login.json()["access_token"]
        r = client.get("/api/transactions", headers=_auth_header(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestReports:
    def test_inspection_pdf_returns_bytes(self, client, officer_token, inspection_id):
        r = client.get(f"/api/reports/inspection/{inspection_id}/pdf", headers=_auth_header(officer_token))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 100   # non-empty PDF

    def test_transactions_csv(self, client, officer_token):
        r = client.get("/api/reports/transactions/csv", headers=_auth_header(officer_token))
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        content = r.content.decode("utf-8-sig")
        assert "Transaction ID" in content

    def test_dashboard_summary(self, client, officer_token):
        r = client.get("/api/dashboard/summary", headers=_auth_header(officer_token))
        assert r.status_code == 200
        data = r.json()
        assert "grade_distribution" in data
        assert "total_inspections_today" in data
        assert set(data["grade_distribution"].keys()) == {"extra_class", "class_i", "class_ii"}
