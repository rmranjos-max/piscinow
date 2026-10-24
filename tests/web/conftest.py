import pytest
from fastapi.testclient import TestClient

from piscinow.rate_limit import limiter
from piscinow.web.app import create_app
from piscinow.web.deps import get_db


@pytest.fixture()
def client(db_session):
    limiter.reset()
    app = create_app()

    def override_get_db():
        yield db_session
        # Mesmo ciclo do get_db real: o commit descarrega as mudancas da rota. A sessao de
        # teste esta ligada a uma transacao externa, que continua sendo revertida no fim.
        db_session.commit()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)
