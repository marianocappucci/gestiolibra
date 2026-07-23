from fastapi.testclient import TestClient


def _disable(admin_client: TestClient, modulo: str) -> None:
    admin_client.app.state.modules.set_enabled(modulo, False)


def test_all_modules_enabled_by_default(admin_client: TestClient):
    assert admin_client.app.state.modules.get_all() == {
        "recordatorios": True, "senas": True, "facturacion": True, "dashboard": True,
    }


def test_reminders_dispatch_requires_recordatorios_module(admin_client: TestClient):
    _disable(admin_client, "recordatorios")
    response = admin_client.post("/reminders/dispatch")
    assert response.status_code == 403


def test_reminders_dispatch_works_when_module_enabled(admin_client: TestClient):
    response = admin_client.post("/reminders/dispatch")
    assert response.status_code == 200


def test_deposits_require_senas_module(admin_client: TestClient):
    client = admin_client
    client.post("/branches", json={"id": "branch-1", "name": "Sucursal"})
    client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    client.post("/resources/resource-1/availability", json={
        "weekday": 0, "starts_at": "00:00:00", "ends_at": "23:59:00",
    })
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    appointment_id = created.json()["id"]

    _disable(client, "senas")
    response = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "500.00"})
    assert response.status_code == 403


def test_billing_config_requires_facturacion_module(admin_client: TestClient):
    _disable(admin_client, "facturacion")
    assert admin_client.get("/config/arca").status_code == 403


def test_dashboard_requires_dashboard_module(admin_client: TestClient):
    _disable(admin_client, "dashboard")
    response = admin_client.get("/dashboard?date_from=2026-07-20&date_to=2026-07-20")
    assert response.status_code == 403


def test_complete_skips_invoicing_when_facturacion_module_disabled(admin_client: TestClient):
    client = admin_client
    client.post("/branches", json={"id": "branch-1", "name": "Sucursal"})
    client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.put("/services/service-1/prices", json={"branch_id": "branch-1", "price": "1000.00"})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    client.post("/resources/resource-1/availability", json={
        "weekday": 0, "starts_at": "00:00:00", "ends_at": "23:59:00",
    })
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    appointment_id = created.json()["id"]
    client.post(f"/appointments/{appointment_id}/confirm")

    _disable(client, "facturacion")
    # Sin el modulo, completar el turno nunca pide medio_pago ni factura,
    # aunque el servicio tenga precio configurado -- el plan no incluye
    # facturacion, pero eso nunca bloquea completar el turno en si.
    response = client.post(f"/appointments/{appointment_id}/complete")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["factura"] is None


def test_turnos_and_catalog_are_never_gated(admin_client: TestClient):
    client = admin_client
    for modulo in ("recordatorios", "senas", "facturacion", "dashboard"):
        _disable(client, modulo)

    assert client.post("/branches", json={"id": "branch-1", "name": "Sucursal"}).status_code == 201
    assert client.post(
        "/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"},
    ).status_code == 201
    assert client.post(
        "/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30},
    ).status_code == 201
    assert client.post("/clients", json={"id": "client-1", "name": "Ana"}).status_code == 201
    client.post("/resources/resource-1/availability", json={
        "weekday": 0, "starts_at": "00:00:00", "ends_at": "23:59:00",
    })
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    assert created.status_code == 201
    assert client.post(f"/appointments/{created.json()['id']}/confirm").status_code == 200
