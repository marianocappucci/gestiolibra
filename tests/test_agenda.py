import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def seeded_client(admin_client: TestClient) -> TestClient:
    client = admin_client
    client.post("/branches", json={"id": "branch-1", "name": "Sucursal demo"})
    client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "09:00:00", "ends_at": "18:00:00",
        })
    return client


def test_agenda_returns_appointments_within_range(seeded_client: TestClient):
    client = seeded_client
    client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-22T11:00:00",
    })

    response = client.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-20",
    })
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    # 13:00Z y no 10:00Z: la sucursal del fixture esta en UTC-3 (el default
    # de `POST /branches`), asi que "10:00" en el formulario son las diez
    # del reloj de la sucursal.
    assert body[0]["starts_at"] == "2026-07-20T13:00:00Z"


def test_agenda_covers_a_full_week_and_is_sorted(seeded_client: TestClient):
    client = seeded_client
    client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-22T11:00:00",
    })
    client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })

    response = client.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-26",
    })
    body = response.json()
    assert [item["starts_at"] for item in body] == [
        "2026-07-20T13:00:00Z", "2026-07-22T14:00:00Z",
    ]


def test_agenda_ignores_other_resources(seeded_client: TestClient):
    client = seeded_client
    client.post("/resources", json={"id": "resource-2", "name": "Box 2"})
    for weekday in range(7):
        client.post("/resources/resource-2/availability", json={
            "weekday": weekday, "starts_at": "09:00:00", "ends_at": "18:00:00",
        })
    client.post("/appointments", json={
        "resource_id": "resource-2", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })

    response = client.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-20",
    })
    assert response.json() == []


def test_agenda_rejects_date_to_before_date_from(seeded_client: TestClient):
    response = seeded_client.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-19",
    })
    assert response.status_code == 422


def test_naive_starts_at_is_interpreted_as_branch_local_time(admin_client: TestClient):
    # Sucursal en UTC-3 (Buenos Aires, sin horario de verano): un turno
    # ingresado como "10:00" en el formulario debe guardarse como
    # 13:00 UTC, no como 10:00 UTC (ver DECISIONS.md ADR-028).
    client = admin_client
    client.post("/branches", json={
        "id": "branch-1", "name": "Sucursal BA", "timezone": "America/Argentina/Buenos_Aires",
    })
    client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "00:00:00", "ends_at": "23:59:00",
        })

    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    assert created.status_code == 201

    response = client.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-20",
    })
    assert response.json()[0]["starts_at"] == "2026-07-20T13:00:00Z"


def test_naive_starts_at_defaults_to_utc_when_resource_has_no_branch(admin_client: TestClient):
    client = admin_client
    client.post("/resources", json={"id": "resource-1", "name": "Box sin sucursal"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "00:00:00", "ends_at": "23:59:00",
        })

    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": "2026-07-20T10:00:00",
    })
    assert created.status_code == 201

    response = client.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-20",
    })
    assert response.json()[0]["starts_at"] == "2026-07-20T10:00:00Z"


# ── El defecto del 2026-08-22: validar en el terreno horario equivocado ─────
#
# Reportado por el humano como *"la agenda no funciona: se quiere otorgar un
# turno y dice que el horario elegido esta fuera del horario de atencion"*.
#
# La causa: el turno se convertia a UTC ANTES de validarlo, y las dos
# comparaciones -- `Availability.contains()` del motor y `is_within_hours()`
# del horario comercial -- lo median contra ventanas cargadas en hora de pared.
# Con UTC-3 eso corre la comparacion tres horas.
#
# 🔴 **Van dos sucursales y no una**, y la razon es que el primer intento de
# estos tests tenia UNA sola, abierta de 9 a 23 para que entraran los turnos de
# la noche. Con esa ventana el caso reportado deja de reproducirse: las 17:00
# de UTC-3 son las 20:00 UTC, que caen adentro de 9-23, asi que el test pasaba
# en verde CONTRA EL CODIGO VIEJO. Cada sintoma necesita la ventana en la que
# se manifiesta.


def _sembrar_peluqueria(client: TestClient, cierra: str) -> TestClient:
    """Una sucursal real: UTC-3, con horario de atencion y un box disponible en
    esa misma franja. Es la forma en que la carga cualquier cliente."""
    client.post("/branches", json={
        "id": "branch-1", "name": "Estilo Norte",
        "timezone": "America/Argentina/Buenos_Aires",
    })
    client.post("/resources", json={
        "id": "resource-1", "name": "Box 1", "branch_id": "branch-1",
    })
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json={"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        client.post("/branches/branch-1/hours", json={
            "weekday": weekday, "starts_at": "09:00:00", "ends_at": cierra,
        })
        client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "09:00:00", "ends_at": cierra,
        })
    return client


@pytest.fixture
def peluqueria(admin_client: TestClient) -> TestClient:
    """De 9 a 19 — el horario del caso reportado."""
    return _sembrar_peluqueria(admin_client, "19:00:00")


@pytest.fixture
def peluqueria_nocturna(admin_client: TestClient) -> TestClient:
    """De 9 a 23, para los turnos que en UTC caen del otro lado de la
    medianoche. Con el cierre a las 19 esos turnos se rechazarian por estar
    cerrado, que es un rechazo correcto y no dice nada sobre husos."""
    return _sembrar_peluqueria(admin_client, "23:00:00")


def _turno(client: TestClient, hora: str, dia: str = "2026-07-20"):
    return client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": "client-1", "starts_at": f"{dia}T{hora}:00",
    })


def test_un_turno_de_la_tarde_entra_en_el_horario_de_atencion(peluqueria: TestClient):
    """El caso reportado, tal cual. Con la sucursal abierta de 9 a 19 las 17:00
    estan adentro; hasta el arreglo daban 409 porque lo que se comparaba contra
    la ventana eran las 20:00 UTC."""
    creado = _turno(peluqueria, "17:00")
    assert creado.status_code == 201, creado.text


def test_un_turno_fuera_del_horario_sigue_rechazandose(peluqueria: TestClient):
    """🔴 El control. Sin esto, el test de arriba pasaria en verde con la
    validacion de horarios apagada del todo, que es la otra forma de "arreglar"
    un 409 molesto.

    Las 08:00, antes de abrir, y no un horario de la noche: un turno de 23:30
    terminaria a las 00:00 del dia siguiente y lo rechazaria la regla de
    "empieza y termina el mismo dia" del motor -- otro rechazo, con lo cual el
    control estaria mirando una cosa distinta de la que dice mirar."""
    rechazado = _turno(peluqueria, "08:00")
    assert rechazado.status_code == 409
    assert "fuera del horario de atenci" in rechazado.json()["detail"]


def test_dos_turnos_a_la_misma_hora_siguen_chocando(peluqueria: TestClient):
    """🔴 El control de la traduccion del repositorio. `_TurnosEnHoraLocal`
    filtra y traduce los turnos que el motor usa para buscar choques: si
    devolviera de menos, el segundo turno entraria sin quejarse y la agenda
    dejaria de servir para lo unico que tiene que hacer."""
    assert _turno(peluqueria, "17:00").status_code == 201
    segundo = _turno(peluqueria, "17:00")
    assert segundo.status_code == 409
    assert "ocupado" in segundo.json()["detail"]


def test_un_turno_de_la_noche_no_se_cae_por_la_medianoche_utc(
    peluqueria_nocturna: TestClient,
):
    """El segundo sintoma del mismo defecto, y el que no dependia de las
    ventanas: `contains()` exige que el turno empiece y termine el MISMO dia, y
    en UTC-3 todo lo de 21:00 en adelante cruza la medianoche UTC. Con la
    sucursal abierta hasta las 23, un turno a las 22:00 es legal por el reloj de
    la pared y era irrechazable por el reloj de Greenwich."""
    creado = _turno(peluqueria_nocturna, "22:00")
    assert creado.status_code == 201, creado.text


def test_el_turno_de_la_noche_aparece_en_su_dia_local(peluqueria_nocturna: TestClient):
    """Y una vez guardado, se lista en el dia en que ocurre para quien atiende.

    Un turno de las 21:30 del lunes es 00:30Z del martes: filtrando por la
    fecha del instante no aparecia al pedir el lunes. La agenda se pide por dia
    de calendario, y el calendario es el de la sucursal."""
    assert _turno(peluqueria_nocturna, "21:30", dia="2026-07-20").status_code == 201

    del_lunes = peluqueria_nocturna.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-20", "date_to": "2026-07-20",
    }).json()
    assert len(del_lunes) == 1
    # Guardado como instante: 21:30 en UTC-3 son las 00:30Z del dia siguiente.
    assert del_lunes[0]["starts_at"] == "2026-07-21T00:30:00Z"

    del_martes = peluqueria_nocturna.get("/resources/resource-1/agenda", params={
        "date_from": "2026-07-21", "date_to": "2026-07-21",
    }).json()
    assert del_martes == []
