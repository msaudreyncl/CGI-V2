"""
database.py — SQLAlchemy engine, session factory, and get_db dependency.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    # SQL parameter logs can contain password hashes and personal information.
    echo=False,
    hide_parameters=True,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def load_models():
    """Register ORM metadata without connecting or changing the database."""
    # Import all models so SQLAlchemy knows about them before create_all
    import models.user                # noqa: F401
    import models.cooperative         # noqa: F401
    import models.farmer              # noqa: F401
    import models.inspection          # noqa: F401
    import models.defect_result       # noqa: F401
    import models.pricing_config      # noqa: F401
    import models.transaction         # noqa: F401
    import models.pending_transaction # noqa: F401


def create_tables():
    """Explicit initialization helper for isolated tests/new databases only.

    Never called by application startup; existing schemas require reviewed migrations.
    """
    load_models()
    Base.metadata.create_all(bind=engine)


def check_database():
    """Read-only connectivity and required table/column check; never issue DDL."""
    if not settings.DB_USER.strip() or settings.DB_USER.lower() == "root":
        raise RuntimeError(
            "Configure DB_USER with a dedicated CGI account in the project .env "
            "or service environment. See backend/RASPBERRY_PI_AUDIT.md."
        )
    load_models()
    missing = []
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                missing.append(f"table {table.name}")
                continue
            columns = {column["name"] for column in inspector.get_columns(table.name)}
            missing.extend(
                f"{table.name}.{column.name}" for column in table.columns
                if column.name not in columns
            )
    if missing:
        raise RuntimeError(
            "Database schema is missing: " + ", ".join(missing)
            + ". No schema changes were made. Review database/migrations with a DBA."
        )


if __name__ == "__main__":
    # Models import `database.Base`; keep the CLI and model registry identical.
    import sys
    sys.modules["database"] = sys.modules[__name__]
    # Avoid printing connection URLs/passwords or SQL exception parameters.
    from sqlalchemy.exc import SQLAlchemyError
    try:
        check_database()
    except (RuntimeError, SQLAlchemyError) as exc:
        if isinstance(exc, SQLAlchemyError):
            code = getattr(getattr(exc, "orig", None), "args", ("unknown",))[0]
            print(f"Database check failed (driver code {code}); verify credentials, grants and server availability.")
        else:
            print(str(exc))
        raise SystemExit(1)
    print("Database connectivity and required tables/columns OK (read-only check).")
