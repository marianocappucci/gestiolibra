from fastapi.testclient import TestClient


def test_client_crud_round_trip(admin_client: TestClient):
    client = admin_client
    created = client.post("/clients", json={"id": "client-1", "name": "Ana", "phone": "123"})
    assert created.status_code == 201
    assert created.json()["phone"] == "123"

    assert client.get("/clients/client-1").json()["name"] == "Ana"
    assert len(client.get("/clients").json()) == 1

    updated = client.put("/clients/client-1", json={
        "name": "Ana", "phone": "456", "email": "ana@x.com",
    })
    assert updated.status_code == 200
    assert updated.json()["phone"] == "456"
    assert updated.json()["email"] == "ana@x.com"

    assert client.delete("/clients/client-1").status_code == 204
    assert client.get("/clients/client-1").status_code == 404


def test_client_cuit_and_condicion_iva_round_trip(admin_client: TestClient):
    client = admin_client
    created = client.post("/clients", json={
        "id": "client-1", "name": "Carlos",
        "cuit": "20111222339", "condicion_iva": "Responsable Inscripto",
    })
    assert created.status_code == 201
    assert created.json()["cuit"] == "20111222339"
    assert created.json()["condicion_iva"] == "Responsable Inscripto"

    updated = client.put("/clients/client-1", json={
        "name": "Carlos", "cuit": "20111222339", "condicion_iva": "Monotributista",
    })
    assert updated.status_code == 200
    assert updated.json()["condicion_iva"] == "Monotributista"


def test_client_cuit_and_condicion_iva_are_optional(admin_client: TestClient):
    created = admin_client.post("/clients", json={"id": "client-1", "name": "Ana"})
    assert created.status_code == 201
    assert created.json()["cuit"] is None
    assert created.json()["condicion_iva"] is None


def test_client_not_found_returns_404(admin_client: TestClient):
    assert admin_client.get("/clients/missing").status_code == 404
    assert admin_client.put("/clients/missing", json={"name": "x"}).status_code == 404
    assert admin_client.delete("/clients/missing").status_code == 404


def test_client_duplicate_id_returns_409(admin_client: TestClient):
    admin_client.post("/clients", json={"id": "client-1", "name": "Ana"})
    response = admin_client.post("/clients", json={"id": "client-1", "name": "Otra"})
    assert response.status_code == 409


def test_cannot_delete_a_client_with_an_appointment_pointing_at_it(admin_client: TestClient):
    client = admin_client
    client.post("/resources", json={"id": "resource-1", "name": "Box 1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    client.post("/resources/resource-1/availability", json={
        "weekday": 0, "starts_at": "00:00:00", "ends_at": "23:59:00",
    })
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    assert created.status_code == 201
    response = client.delete("/clients/client-1")
    assert response.status_code == 409
