import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from piscinow.db import Base

# Importing every model module here ensures Base.metadata knows about all
# tables before `create_all` runs in the `engine` fixture below.
import piscinow.models.member  # noqa: E402,F401
import piscinow.models.conversation  # noqa: E402,F401
import piscinow.models.memory  # noqa: E402,F401
import piscinow.models.admin  # noqa: E402,F401
import piscinow.models.product  # noqa: E402,F401
import piscinow.models.service  # noqa: E402,F401
import piscinow.models.project  # noqa: E402,F401
import piscinow.models.payment  # noqa: E402,F401
import piscinow.models.qualification  # noqa: E402,F401


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="session")
def engine(postgres_container):
    url = postgres_container.get_connection_url().replace("psycopg2", "psycopg")
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
