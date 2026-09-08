import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from piscinow.web.app import create_app
from piscinow.web.deps import get_db


@pytest.fixture()
def web_db_session():
    """Web-specific db_session that creates an engine without tables.

    The home route doesn't touch the database, so we just need a valid
    session object without requiring Docker or table creation.
    """
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def client(web_db_session):
    app = create_app()

    def override_get_db():
        yield web_db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)
