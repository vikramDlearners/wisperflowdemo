"""Shared test setup: point the app at an in-memory SQLite database, or at TEST_DATABASE_URL when set
(e.g. a throwaway PostgreSQL database: every test creates and then drops all tables in it).

DATABASE_URL and SCHEDULER_ENABLED are set before any `app` module is imported, because
app.core.config reads settings (and app.core.db builds its engine) at import time.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
# Never start the background scheduler thread in tests.
os.environ["SCHEDULER_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401  registers all tables on Base.metadata
from app.core.db import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

_TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
test_engine = (
    create_engine(_TEST_URL)
    if _TEST_URL
    else create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()
