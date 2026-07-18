from fastapi.testclient import TestClient

from app.main import create_app


def _seeded_client():
    client = TestClient(create_app("sqlite:///:memory:"))
    assert client.post("/branches", json={"id": "branch-1", "name": "Sucursal demo"}).status_code == 201
    assert client.post("/resources", json={
        "id": "resource-1", "name": "Box 1", "branch_id": "branch-1",
    }).status_code == 201
    assert client.post("/services", json={
        "id": "service-1", "name": "Corte", "duration_minutes": 30,
    }).status_code == 201
    assert client.post("/clients", json={"id": "client-1", "name": "Ana"}).status_code == 201
    return client


def test_health_reports_ok():
    client = TestClient(create_app("sqlite:///:memory:"))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "product": "gestiolibra"}


def test_gestiolibra_creates_and_confirms_appointment():
    client = _seeded_client()
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    assert created.status_code == 201
    confirmed = client.post(f"/appointments/{created.json()['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_create_appointment_rejects_unknown_service():
    client = _seeded_client()
    response = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "missing-service",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    assert response.status_code == 404


def test_create_appointment_rejects_conflicting_slot():
    client = _seeded_client()
    payload = {
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    }
    first = client.post("/appointments", json=payload)
    assert first.status_code == 201
    second = client.post("/appointments", json=payload)
    assert second.status_code == 409


def test_create_appointment_rejects_slot_outside_availability():
    client = _seeded_client()
    response = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T20:00:00",
    })
    assert response.status_code == 409


def test_confirm_unknown_appointment_returns_404():
    client = TestClient(create_app("sqlite:///:memory:"))
    response = client.post("/appointments/missing/confirm")
    assert response.status_code == 404


def test_confirming_twice_returns_409():
    client = _seeded_client()
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    appointment_id = created.json()["id"]
    assert client.post(f"/appointments/{appointment_id}/confirm").status_code == 200
    assert client.post(f"/appointments/{appointment_id}/confirm").status_code == 409
