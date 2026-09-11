from fastapi.testclient import TestClient


def _seeded_appointment(client: TestClient) -> str:
    client.post("/branches", json={"id": "branch-1", "name": "Centro"})
    client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "00:00:00", "ends_at": "23:59:00",
        })
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2099-01-01T10:00:00",
    })
    return created.json()["id"]


def test_request_and_get_deposit(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)

    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    assert created.status_code == 201
    assert created.json()["appointment_id"] == appointment_id
    assert created.json()["amount"] == "1000.00"
    assert created.json()["status"] == "pending"

    fetched = client.get(f"/appointments/{appointment_id}/deposit")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "pending"


def test_get_deposit_not_found_returns_404(admin_client: TestClient):
    appointment_id = _seeded_appointment(admin_client)
    assert admin_client.get(f"/appointments/{appointment_id}/deposit").status_code == 404


def test_admin_marks_deposit_paid(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    deposit_id = created.json()["id"]

    paid = client.post(f"/deposits/{deposit_id}/mark-paid")
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"


def test_admin_marks_deposit_paid_with_medio_pago(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    deposit_id = created.json()["id"]

    paid = client.post(f"/deposits/{deposit_id}/mark-paid", json={"medio_pago": "transferencia"})
    assert paid.status_code == 200
    assert paid.json()["medio_pago"] == "transferencia"


def test_admin_marks_deposit_failed(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    deposit_id = created.json()["id"]

    failed = client.post(f"/deposits/{deposit_id}/mark-failed")
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"


def test_admin_refunds_a_paid_deposit(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    deposit_id = created.json()["id"]
    client.post(f"/deposits/{deposit_id}/mark-paid")

    refunded = client.post(f"/deposits/{deposit_id}/refund")
    assert refunded.status_code == 200
    assert refunded.json()["status"] == "refunded"


def test_cannot_refund_a_pending_deposit(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    deposit_id = created.json()["id"]

    response = client.post(f"/deposits/{deposit_id}/refund")
    assert response.status_code == 409


def test_mark_paid_on_unknown_deposit_returns_404(admin_client: TestClient):
    assert admin_client.post("/deposits/missing/mark-paid").status_code == 404


def test_staff_can_request_a_deposit_but_not_confirm_it(staff_client: TestClient, admin_client: TestClient):
    appointment_id = _seeded_appointment(admin_client)
    created = staff_client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    assert created.status_code == 201

    deposit_id = created.json()["id"]
    assert staff_client.post(f"/deposits/{deposit_id}/mark-paid").status_code == 403


# ── El listado (`GET /deposits`) ────────────────────────────────────────────
#
# Hasta el 2026-09-11 una seña sólo se podía ver conociendo su turno: el
# Dashboard contaba las pendientes y no había dónde verlas. El listado es lo
# que alimenta la pantalla de Señas.


def _otro_turno(client: TestClient, starts_at: str) -> str:
    """Un turno más sobre el catálogo que ya sembró `_seeded_appointment`."""
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": starts_at,
    })
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _sena(client: TestClient, appointment_id: str, amount: str = "1000.00") -> str:
    created = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": amount})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_list_deposits_brings_every_status_with_its_appointment(admin_client: TestClient):
    client = admin_client
    primero = _seeded_appointment(client)
    segundo = _otro_turno(client, "2099-01-01T12:00:00")
    pendiente = _sena(client, primero, "1000.00")
    cobrada = _sena(client, segundo, "2500.50")
    client.post(f"/deposits/{cobrada}/mark-paid", json={"medio_pago": "efectivo"})

    response = client.get("/deposits")
    assert response.status_code == 200
    por_id = {d["id"]: d for d in response.json()}
    assert set(por_id) == {pendiente, cobrada}

    assert por_id[pendiente]["status"] == "pending"
    assert por_id[pendiente]["amount"] == "1000.00"
    assert por_id[cobrada]["status"] == "paid"
    assert por_id[cobrada]["medio_pago"] == "efectivo"

    # El turno viaja pegado a la seña: es lo que dice de quién es y de cuándo.
    fila = por_id[pendiente]
    assert fila["appointment_id"] == primero
    assert fila["client_id"] == "client-1"
    assert fila["service_id"] == "service-1"
    assert fila["resource_id"] == "resource-1"
    assert fila["appointment_status"] == "pending"
    # El mismo instante que publica la agenda, en UTC: comparado contra el
    # endpoint y no contra una cuenta hecha acá, que dependería de la zona
    # por defecto de la sucursal del fixture.
    agenda = client.get(
        "/resources/resource-1/agenda?date_from=2099-01-01&date_to=2099-01-01"
    ).json()
    inicio = {t["id"]: t["starts_at"] for t in agenda}
    assert fila["appointment_starts_at"] == inicio[primero]
    assert fila["appointment_starts_at"].endswith("Z")


def test_list_deposits_filters_by_status(admin_client: TestClient):
    client = admin_client
    primero = _seeded_appointment(client)
    segundo = _otro_turno(client, "2099-01-01T12:00:00")
    pendiente = _sena(client, primero)
    cobrada = _sena(client, segundo)
    client.post(f"/deposits/{cobrada}/mark-paid")

    solo_pendientes = client.get("/deposits?status=pending")
    assert solo_pendientes.status_code == 200
    assert [d["id"] for d in solo_pendientes.json()] == [pendiente]

    solo_cobradas = client.get("/deposits?status=paid")
    assert [d["id"] for d in solo_cobradas.json()] == [cobrada]


def test_list_deposits_orders_by_the_appointment_start(admin_client: TestClient):
    # La seña que hay que cobrar antes es la del turno que viene antes. Se
    # crean al revés a propósito: el orden de alta no puede ser el que gane.
    client = admin_client
    temprano = _seeded_appointment(client)  # 10:00
    tarde = _otro_turno(client, "2099-01-01T15:00:00")
    de_la_tarde = _sena(client, tarde)
    de_la_manana = _sena(client, temprano)

    ids = [d["id"] for d in client.get("/deposits").json()]
    assert ids == [de_la_manana, de_la_tarde]


def test_list_deposits_is_empty_without_deposits(admin_client: TestClient):
    _seeded_appointment(admin_client)
    response = admin_client.get("/deposits")
    assert response.status_code == 200
    assert response.json() == []


def test_list_deposits_rejects_an_unknown_status(admin_client: TestClient):
    assert admin_client.get("/deposits?status=cobrada").status_code == 422


def test_staff_cannot_list_deposits(staff_client: TestClient, admin_client: TestClient):
    # Mismo criterio que confirmar el cobro: la lista de plata a cobrar y a
    # devolver es del admin. El staff pide la seña desde el turno.
    appointment_id = _seeded_appointment(admin_client)
    _sena(admin_client, appointment_id)
    assert staff_client.get("/deposits").status_code == 403
