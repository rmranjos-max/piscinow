import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from piscinow.rate_limit import limiter
from piscinow.web.app import create_app
from piscinow.web.deps import get_db


@pytest.fixture()
def db_session():
    """
    Fallback fixture for tests that don't require a real database.
    When Docker/Postgres is not available, this mock session allows
    tests to run (e.g., test_app.py which only serves pages without DB queries).
    """
    session = MagicMock()
    yield session


@pytest.fixture()
def client(db_session):
    limiter.reset()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)
