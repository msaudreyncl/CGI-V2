"""Registration IDs remain unique after role changes and deletions."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import Base, load_models
from models.user import User, UserRole
from routers.auth import register
from schemas.user import UserCreate


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    load_models()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_registration_after_role_change_and_deletion(db):
    db.add_all([
        User(name="Changed role", email="changed@example.com", password_hash="unused",
             role=UserRole.officer, user_id_display="FF00001"),
        User(name="Remaining", email="remaining@example.com", password_hash="unused",
             role=UserRole.farmer, user_id_display="FF00003"),
    ])
    db.commit()
    body = UserCreate(name="New farmer", email="new@example.com", password="password123")
    result = register(body, db, None)
    assert result.user_id_display == "FF00004"
    assert result.role == UserRole.farmer


def test_registration_retries_a_conflicting_insert(db, monkeypatch):
    commit = db.commit
    attempts = []

    def conflict_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise IntegrityError("insert", {}, Exception("duplicate"))
        commit()

    monkeypatch.setattr(db, "commit", conflict_once)
    result = register(UserCreate(name="New", email="new@example.com", password="password123"), db, None)
    assert result.user_id_display == "FF00001"
    assert len(attempts) == 2
    assert db.query(User).count() == 1
