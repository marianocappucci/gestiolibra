import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch, tmp_path):
    # SessionAuth's SECRET_KEY resolution and the admin bootstrap both
    # fail closed unless ENV=development -- see app/auth.py and
    # app/services/users.py::ensure_default_admin.
    monkeypatch.setenv("ENV", "development")
    # libracore.db is raw sqlite3 (a fresh connection per call, unlike
    # SQLAlchemy's pooled engine) -- ":memory:" would give every call an
    # empty, unrelated database. A real temp file per test is required.
    monkeypatch.setenv("GESTIOLIBRA_LIBRACORE_DB_PATH", str(tmp_path / "gestiolibra_libracore.db"))


def https_client(app) -> TestClient:
    """SessionAuth's cookie is Secure-flagged (see libracore.auth); httpx's
    cookie jar won't send a Secure cookie back over plain http, and
    TestClient defaults to http://testserver. A dotted hostname is required
    too: httpx's cookie jar domain-matching is unreliable for single-label
    hosts like the default "testserver" -- reproduced standalone as an
    intermittent ~5% rate of an already-logged-in session getting 401'd on
    the very next request, with the valid signed cookie still sitting in
    the jar (i.e. not a signature/expiry problem, a domain-matching one).
    0 failures in 300 iterations once the host has a dot."""
    return TestClient(app, base_url="https://gestiolibra.test")


@pytest.fixture
def admin_client():
    """Fresh app + logged in as the dev bootstrap admin (admin/admin).

    Entered as a context manager and kept open for the whole test: outside
    a `with` block, TestClient spins up a brand new anyio portal thread per
    request instead of reusing one (see starlette.testclient.TestClient),
    which raced with SQLite's single StaticPool connection often enough to
    intermittently 401 an already-authenticated session mid-test.
    """
    with https_client(create_app("sqlite:///:memory:")) as client:
        response = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200, response.text
        yield client


@pytest.fixture
def staff_client(admin_client: TestClient):
    """A second client logged in as a staff user that admin_client just
    created -- same app/database, separate session/cookie."""
    created = admin_client.post("/users", json={
        "id": "staff-1", "username": "staff-1", "name": "Empleada",
        "password": "staff-pass", "role": "staff",
    })
    assert created.status_code == 201, created.text
    with https_client(admin_client.app) as client:
        response = client.post("/auth/login", json={"username": "staff-1", "password": "staff-pass"})
        assert response.status_code == 200, response.text
        yield client
