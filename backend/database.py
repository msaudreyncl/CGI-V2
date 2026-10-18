"""
database.py — SQLAlchemy engine, session factory, and get_db dependency.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.APP_DEBUG,
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


def create_tables():
    """Create all tables defined in ORM models (called at app startup)."""
    # Import all models so SQLAlchemy knows about them before create_all
    import models.user                # noqa: F401
    import models.cooperative         # noqa: F401
    import models.farmer              # noqa: F401
    import models.inspection          # noqa: F401
    import models.defect_result       # noqa: F401
    import models.pricing_config      # noqa: F401
    import models.transaction         # noqa: F401
    import models.pending_transaction # noqa: F401

    # Use the module-level `engine` variable (allows tests to swap it before calling)
    import database as _self
    Base.metadata.create_all(bind=_self.engine)
