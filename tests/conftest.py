import os
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Force testing configuration
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "False"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_NAME"] = "DataPulse AI"

from app.core.config import get_settings
get_settings.cache_clear()

from app.core.database import Base, get_db
import app.core.database as database_module
from app.main import app
from app.models.user import User
from app.api.deps import get_current_user
from app.core.security import hash_password, create_access_token

# Shared in-memory SQLite test engine with StaticPool
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all schema tables in test engine once per session."""
    # Point the database engine to the in-memory test engine
    original_engine = database_module.engine
    database_module.engine = test_engine
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    database_module.engine = original_engine


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a fresh, transactional database session for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def default_user(db_session: Session) -> User:
    """Create or retrieve a default test user for regression and authenticated testing."""
    user = db_session.query(User).filter_by(id=1).first()
    if not user:
        user = User(
            id=1,
            email="testuser@datapulse.io",
            hashed_password=hash_password("Password123!"),
            full_name="Default Test User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(default_user: User) -> dict:
    """Provide valid JWT bearer authorization headers for default_user."""
    token = create_access_token({"sub": str(default_user.id), "email": default_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session: Session, default_user: User) -> Generator[TestClient, None, None]:
    """TestClient pre-authenticated with default_user for backward-compatible regression tests."""
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_current_user() -> User:
        return default_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with no auth override to test unauthenticated & real token verification."""
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Explicitly ensure get_current_user is not overridden
    app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
