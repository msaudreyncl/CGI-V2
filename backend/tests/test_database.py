"""Ensure production startup validation cannot create or migrate schemas."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database


@pytest.fixture
def isolated_database(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database.settings, "DB_USER", "cgi_app")
    yield engine
    engine.dispose()


def test_empty_schema_is_reported_without_creating_tables(isolated_database):
    with pytest.raises(RuntimeError, match="table users"):
        database.check_database()
    assert inspect(isolated_database).get_table_names() == []


def test_existing_schema_validation_issues_no_writes(isolated_database):
    database.create_tables()
    statements = []
    event.listen(isolated_database, "before_cursor_execute",
                 lambda conn, cursor, statement, parameters, context, many:
                 statements.append(statement.strip().split()[0].upper()))
    database.check_database()
    assert statements
    assert set(statements) <= {"SELECT", "PRAGMA"}


def test_missing_columns_are_reported_without_migration(isolated_database):
    database.create_tables()
    with isolated_database.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE users DROP COLUMN last_login_at")
    with pytest.raises(RuntimeError, match=r"users.last_login_at"):
        database.check_database()
    assert "last_login_at" not in {
        column["name"] for column in inspect(isolated_database).get_columns("users")
    }


def test_root_is_rejected_before_connection(isolated_database, monkeypatch):
    monkeypatch.setattr(database.settings, "DB_USER", "root")
    with pytest.raises(RuntimeError, match="dedicated CGI account"):
        database.check_database()
