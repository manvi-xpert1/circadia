import os
import tempfile

import pytest

os.environ["EAP_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import reset_failures  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    init_db()
    reset_failures()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    r = client.post("/api/auth/setup", json={"username": "manvi", "password": "secret-pass"})
    assert r.status_code == 201
    return client
