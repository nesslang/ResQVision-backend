"""
Database engine and session factory for ResQVision 2.0.

Supports:
  - PostgreSQL + PostGIS  (production)
  - SQLite + optional SpatiaLite  (development / testing)

Usage:
    from app.core.database import get_db, Base, engine

    # In FastAPI dependency
    db: Session = Depends(get_db)
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

Base = declarative_base()


def _make_engine():
    """Build the SQLAlchemy engine from settings."""
    settings = get_settings()
    db_url = settings.active_database_url

    if db_url.startswith("sqlite"):
        _engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            echo=settings.debug,
        )

        @event.listens_for(_engine, "connect")
        def _load_spatialite(dbapi_conn, connection_record):
            """Try to load SpatiaLite extension for spatial queries in dev."""
            try:
                dbapi_conn.enable_load_extension(True)
                dbapi_conn.load_extension("mod_spatialite")
                logger.debug("SpatiaLite extension loaded")
            except Exception:
                # SpatiaLite not installed — proceed with plain SQLite
                pass

        logger.info("database_engine_ready", backend="sqlite", url=db_url)
    else:
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,      # detect stale connections
            pool_size=10,            # base pool size
            max_overflow=20,         # extra connections allowed under load
            pool_timeout=30,         # seconds to wait for a connection
            pool_recycle=1800,       # recycle connections after 30 min
            echo=settings.debug,
        )
        logger.info("database_engine_ready", backend="postgresql")

    return _engine


engine = _make_engine()

SessionLocal: sessionmaker = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session for the duration of a request.
    Rolls back on unhandled exceptions; always closes the session.

    Usage:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def create_tables() -> None:
    """
    Create all tables registered on Base.metadata.
    Called once at application startup in main.py lifespan.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("database_tables_created")


def check_db_connection() -> bool:
    """
    Return True if the database is reachable, False otherwise.
    Used in /health endpoints.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database_connection_failed", error=str(exc))
        return False
