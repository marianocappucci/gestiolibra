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


def test_client_not_found_returns_404(admin_client: TestClient):
    assert admin_client.get("/clients/missing").status_code == 404
    assert admin_client.put("/clients/missing", json={"name": "x"}).status_code == 404
    assert admin_client.delete("/clients/missing").status_code == 404


def test_client_duplicate_id_returns_409(admin_client: TestClient):
    admin_client.post("/clients", json={"id": "client-1", "name": "Ana"})
    response = admin_client.post("/clients", json={"id": "client-1", "name": "Otra"})
    assert response.status_code == 409
