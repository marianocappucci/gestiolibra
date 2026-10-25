"""La sincronización por HTTP, de punta a punta, contra las rutas reales del central (ADR-036).

Los otros tests aplican las operaciones con el receptor de LibraEdge; acá van por `POST /sync/v1/push` con el secreto del nodo,
para probar el cableado entero: el montaje del router, la autenticación, el control de esquema, el despachador del producto y el
ticket de ARCA que presta el central.
"""
from __future__ import annotations

import pytest
from nodo_apoyo import NODO


@pytest.fixture
def cabeceras(escenario):
    from libracore.db import core
    from libraedge.sync.esquema import CABECERA, version_de_alembic

    conn = core.conectar(escenario.url_central)
    try:
        version = version_de_alembic(conn)
    finally:
        conn.close()
    return {"Authorization": f"Bearer {escenario.secreto}", CABECERA: version}


def test_el_push_del_nodo_se_aplica_en_el_central_por_la_ruta_real(escenario, cabeceras):
    e = escenario
    assert e.cliente.post(f"/appointments/{e.datos['turno']}/complete", json={"medio_pago": "efectivo"}).status_code == 200
    operaciones = e.pendientes()
    assert [op.operation_type for op in operaciones] == ["caja.movimiento", "cola.pedido", "turno.atendido"]
    with e.en_el_central():
        for op in operaciones:
            r = e.cliente.post("/sync/v1/push", json=op.como_dict(), headers=cabeceras)
            assert r.status_code == 200, r.text
            assert r.json()["result"] == "accepted", r.json()
        # El mismo push otra vez: el receptor lo deduplica.
        assert e.cliente.post("/sync/v1/push", json=operaciones[2].como_dict(),
                              headers=cabeceras).json()["result"] == "duplicate"
        # Un secreto que no es el del nodo no entra.
        assert e.cliente.post("/sync/v1/push", json=operaciones[2].como_dict(),
                              headers={**cabeceras, "Authorization": "Bearer otro"}).status_code == 401
    assert e.sql_central("SELECT status FROM appointments WHERE id = ?", e.datos["turno"]) == [("completed",)]
    assert e.sql_central("SELECT count(*) FROM caja_movimientos") == [(1,)]


def test_un_esquema_distinto_no_sincroniza(escenario, cabeceras):
    e = escenario
    with e.en_el_central():
        r = e.cliente.post("/sync/v1/push", json={
            "operation_id": "x:1", "node_id": NODO, "sequence": 1, "operation_type": "turno.atendido",
            "aggregate_type": "turno", "aggregate_id": "x", "occurred_at": "2026-10-24T00:00:00+00:00",
            "schema_version": 1, "payload": {}}, headers={**cabeceras, "X-LibraEdge-Esquema": "alembic_version=viejo"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "esquema_incompatible"


def test_una_operacion_que_el_central_no_conoce_va_a_revision_y_no_se_pierde(escenario, cabeceras):
    e = escenario
    with e.en_el_central():
        r = e.cliente.post("/sync/v1/push", json={
            "operation_id": "x:2", "node_id": NODO, "sequence": 2, "operation_type": "gestio.invento",
            "aggregate_type": "x", "aggregate_id": "x", "occurred_at": "2026-10-24T00:00:00+00:00",
            "schema_version": 1, "payload": {}}, headers=cabeceras)
    assert r.status_code == 200 and r.json()["result"] == "rejected"
    assert "sin manejador para gestio.invento" in r.json()["error"]
    assert e.sql_central("SELECT status FROM sync_inbox WHERE operation_id = 'x:2'") == [("manual_review",)]


def test_el_central_le_presta_al_nodo_el_ticket_de_wsfe_y_dice_que_no_presta_el_de_wscpe(escenario, cabeceras, monkeypatch):
    """El ticket de `wsfe` es el del certificado del central (que no sale del VPS); GestioLibra no tiene `wscpe`."""
    from libracore import arca_credenciales, arca_wsaa

    e = escenario
    pedidos = []

    async def autenticar(cert, clave, ambiente, servicio="wsfe"):
        pedidos.append((ambiente, servicio))
        return {"token": "TKN", "sign": "SGN", "expiracion": "2099-01-01T00:00:00+00:00"}

    monkeypatch.setattr(arca_credenciales, "paths_en_disco", lambda arca: ("/tmp/cert.crt", "/tmp/clave.key"))
    monkeypatch.setattr(arca_wsaa, "autenticar", autenticar)
    with e.en_el_central():
        wsfe = e.cliente.post("/sync/v1/ticket-arca", json={"node_id": NODO, "servicio": "wsfe"}, headers=cabeceras)
        wscpe = e.cliente.post("/sync/v1/ticket-arca", json={"node_id": NODO, "servicio": "wscpe"}, headers=cabeceras)
    assert wsfe.status_code == 200, wsfe.text
    assert wsfe.json()["token"] == "TKN" and wsfe.json()["servicio"] == "wsfe" and wsfe.json()["cuit"] == "20111222339"
    assert pedidos == [("produccion", "wsfe")]
    assert wscpe.status_code in (422, 501), wscpe.text
    assert len(pedidos) == 1, "nunca se pidió un ticket de wscpe"
