"""La fecha de negocio sale del reloj de Argentina del motor, no del proceso.

`libracore.fechas.hoy()` (ADR-070) es la fuente única: la factura de un turno y
los movimientos de caja de su seña y su saldo tienen que llevar el día de
Argentina aunque el proceso corra en UTC —como los contenedores que no tienen
`TZ`— y sea de noche allá.

🔴 Con `date.today()` el día salía de la `TZ` del proceso: entre las 21:00 y la
medianoche de Argentina la factura se fechaba **mañana**. La suite entera corre
con `TZ=America/Argentina/Buenos_Aires` (ver `conftest.py`), así que ningún otro
test lo podía ver: éste vuelve el proceso a UTC y pisa el instante.
"""
import os
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from libracore import fechas
from libracore.db import caja as db_caja
from libracore.db import facturas as db_facturas

#: 02:30 UTC del 10 de marzo de 2031 = 23:30 del 9 en Argentina. Una fecha lejana a
#: propósito: así `date.today()` nunca puede coincidir con el día esperado.
INSTANTE = datetime(2031, 3, 10, 2, 30, tzinfo=UTC)
DIA_EN_ARGENTINA = "2031-03-09"


@pytest.fixture
def _proceso_en_utc_a_las_23_30_de_argentina(monkeypatch):
    """El proceso en UTC y el reloj del motor clavado en `INSTANTE`."""
    antes = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    monkeypatch.setattr(fechas, "_ahora_utc", lambda: INSTANTE)
    try:
        yield
    finally:
        if antes is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = antes
        time.tzset()


def test_la_factura_y_la_caja_del_turno_llevan_el_dia_de_argentina(
    admin_client: TestClient, _proceso_en_utc_a_las_23_30_de_argentina,
):
    from tests.test_billing import _seeded_appointment

    appointment_id = _seeded_appointment(admin_client)
    deposit = admin_client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "400.00"})
    admin_client.post(f"/deposits/{deposit.json()['id']}/mark-paid", json={"medio_pago": "mercadopago"})
    r = admin_client.post(f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"})
    assert r.status_code == 200, r.text
    factura = db_facturas.get_factura(r.json()["factura"]["id"])

    assert factura["fecha"] == DIA_EN_ARGENTINA
    conceptos = {
        m["concepto"].split()[0]: m["fecha"]
        for m in db_caja.get_caja_movimientos(limit=500)
        if m["concepto"].endswith(f"factura {factura['numero']}")
    }
    assert conceptos == {"Sena": DIA_EN_ARGENTINA, "Saldo": DIA_EN_ARGENTINA}


def test_los_turnos_de_hoy_del_dashboard_cuentan_el_dia_de_argentina(
    admin_client: TestClient, _proceso_en_utc_a_las_23_30_de_argentina,
):
    """Un turno a las 22:00 de Argentina es de «mañana» en UTC (01:00): `turnos.hoy`
    lo contaba mal justo en la franja en la que el negocio sigue atendiendo."""
    admin_client.post("/branches", json={"id": "branch-1", "name": "Sucursal demo"})
    admin_client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    admin_client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    admin_client.post("/clients", json={"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        admin_client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "00:00:00", "ends_at": "23:59:00",
        })
    # Sin zona, la API lee la hora como de Argentina: 22:00 del 9 = 01:00 UTC del 10.
    creado = admin_client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1", "client_id": "client-1",
        "starts_at": "2031-03-09T22:00:00",
    })
    assert creado.status_code == 201, creado.text

    r = admin_client.get(f"/dashboard?date_from={DIA_EN_ARGENTINA}&date_to={DIA_EN_ARGENTINA}")
    assert r.status_code == 200, r.text
    assert r.json()["turnos"]["hoy"] == 1
