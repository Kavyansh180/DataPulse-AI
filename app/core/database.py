import logging
from typing import Generator, Tuple, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session, DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

logger = logging.getLogger("datapulse.database")
settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models in DataPulse AI."""
    pass


def create_db_engine():
    """Create SQLAlchemy engine with appropriate pooling and options.

    Configures connection pooling for PostgreSQL (Neon) and sets
    pool_pre_ping=True to automatically detect disconnected serverless sessions.
    """
    db_url = settings.DATABASE_URL

    if settings.is_sqlite:
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )

    return create_engine(
        db_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Crucial for Neon serverless idle timeout recovery
    )


_engine = None


def get_engine():
    """Retrieve or lazily initialize the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


class _LazyEngineProxy:
    """Proxy object that delays engine initialization until accessed."""

    def _get_engine(self):
        global _engine
        if _engine is None:
            _engine = create_db_engine()
        return _engine

    def __getattr__(self, name):
        return getattr(self._get_engine(), name)

    def connect(self, *args, **kwargs):
        return self._get_engine().connect(*args, **kwargs)

    def begin(self, *args, **kwargs):
        return self._get_engine().begin(*args, **kwargs)

    @property
    def url(self):
        return self._get_engine().url

    def __repr__(self):
        global _engine
        if _engine is not None:
            return repr(_engine)
        return "<LazyEngine(uninitialized)>"


engine = _LazyEngineProxy()


class _LazySessionLocal:
    """Proxy callable that provides Session instances bound to the active engine."""

    def __call__(self, *args, **kwargs):
        import sys
        mod = sys.modules.get(__name__)
        active_engine = getattr(mod, "engine", engine)
        if isinstance(active_engine, _LazyEngineProxy):
            active_engine = active_engine._get_engine()
        factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=active_engine,
        )
        return factory(*args, **kwargs)

    def __getattr__(self, name):
        import sys
        mod = sys.modules.get(__name__)
        active_engine = getattr(mod, "engine", engine)
        if isinstance(active_engine, _LazyEngineProxy):
            active_engine = active_engine._get_engine()
        factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=active_engine,
        )
        return getattr(factory, name)


SessionLocal = _LazySessionLocal()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session per request

    and guarantees proper closure when the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


import re


def _sanitize_db_error(msg: str) -> str:
    """Mask credentials in connection strings or database exception messages."""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", msg)


def check_database_connectivity(target_engine=None) -> Tuple[bool, Optional[str]]:
    """Test active database connectivity by executing a lightweight SELECT 1 query.

    Returns:
        (True, None) if database responds successfully.
        (False, error_message) if connectivity fails.
    """
    active_engine = target_engine or engine
    try:
        with active_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except SQLAlchemyError as err:
        sanitized = _sanitize_db_error(str(err))
        logger.error(f"Database readiness probe failed: {sanitized}")
        return False, sanitized
    except Exception as exc:
        sanitized = _sanitize_db_error(str(exc))
        logger.error(f"Unexpected error during database readiness check: {sanitized}")
        return False, sanitized
