"""La lista «Turnos a revisar» (ADR-036, libra-ui ADR-095): las atenciones hechas sin conexión que en la web chocaron.

La arma el central al aplicar `turno.atendido`; baja al nodo por el espejo de sólo lectura. Se prueba en el central, que es
donde se resuelve.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from libragenda import atencion_en_nodo
from libragenda.database import get_session_factory
from test_billing import _seeded_appointment


def atencion_del_nodo(turno: str, estado: str = "completed", *, atencion_id: str = "a" * 36, visto_estado: str = "confirmed"):
    """Lo que entrega el receptor de LibraEdge para un `turno.atendido`."""
    return SimpleNamespace(
        node_id="local-1", operation_type="turno.atendido", schema_version=1,
        payload={"version": 1, "atencion_id": atencion_id, "turno_id": turno, "estado": estado,
                 "at": datetime(2026, 10, 25, 10, 40, tzinfo=UTC).isoformat(), "actor": "Ana",
                 "visto": {"estado": visto_estado}, "extra": {"cobro": {"saldo": "1000.00"}}})


def aplicar(op):
    with get_session_factory().begin() as sesion:
        return atencion_en_nodo.aplicar_turno_atendido(sesion, op)


def test_la_lista_trae_las_atenciones_que_chocaron_con_la_web(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    assert c.get("/api/nodo/turnos-a-revisar").json() == []
    assert c.post(f"/appointments/{turno}/cancel").status_code == 200   # la web lo canceló mientras tanto
    aplicar(atencion_del_nodo(turno))

    (fila,) = c.get("/api/nodo/turnos-a-revisar").json()
    # Los nombres de `AtencionAplicada` de LibraGenda, que es lo que espera `TurnosARevisar` del kit.
    assert fila["appointment_id"] == turno and fila["estado"] == "completed" and fila["actor"] == "Ana"
    assert fila["motivo"] == "cancelado" and fila["resultado"] == "a_revisar" and fila["estado_despues"] == "cancelled"
    assert fila["revisada_at"] is None and fila["at"].startswith("2026-10-25T10:40")
    # Y de qué turno se trata, para que la tarjeta no diga un uuid.
    assert (fila["cliente"], fila["servicio"]) == ("Ana", "Corte") and fila["starts_at"].startswith("2099-01-01")


def test_una_atencion_que_se_aplico_sin_problemas_no_esta_en_la_lista(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    aplicar(atencion_del_nodo(turno))
    assert c.get("/api/nodo/turnos-a-revisar").json() == []
    assert c.get("/resources/resource-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"}
                 ).json()[0]["status"] == "completed"


def test_ya_lo_revise_saca_el_turno_de_la_lista_y_no_cambia_el_turno(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    c.post(f"/appointments/{turno}/cancel")
    aplicar(atencion_del_nodo(turno))
    aplicar(atencion_del_nodo(turno, atencion_id="b" * 36, estado="in_progress"))
    assert len(c.get("/api/nodo/turnos-a-revisar").json()) == 2

    r = c.post("/api/nodo/turnos-a-revisar/revisar", json={"atenciones": ["a" * 36, "b" * 36]})
    assert r.status_code == 200, r.text
    assert all(f["revisada_at"] for f in r.json())
    assert c.get("/api/nodo/turnos-a-revisar").json() == []
    # El turno sigue cancelado: acomodarlo es a mano.
    agenda = c.get("/resources/resource-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"}).json()
    assert agenda[0]["status"] == "cancelled" and agenda[0]["a_revisar"] is False
    # Marcar de nuevo no pisa quién lo revisó la primera vez.
    otra = c.post("/api/nodo/turnos-a-revisar/revisar", json={"atenciones": ["a" * 36]})
    assert otra.status_code == 200 and otra.json()[0]["revisada_at"] == r.json()[0]["revisada_at"]


def test_un_turno_que_ya_no_existe_sale_en_la_lista_sin_nombres(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    aplicar(atencion_del_nodo("se-borro-en-la-web"))
    (fila,) = c.get("/api/nodo/turnos-a-revisar").json()
    assert fila["motivo"] == "turno_inexistente" and fila["appointment_id"] == "se-borro-en-la-web"
    assert (fila["cliente"], fila["servicio"], fila["starts_at"]) == (None, None, None)
    assert turno != fila["appointment_id"]


def test_la_agenda_marca_el_turno_a_revisar_con_su_motivo(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    c.post(f"/appointments/{turno}/cancel")
    aplicar(atencion_del_nodo(turno))
    (t,) = c.get("/resources/resource-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"}).json()
    assert (t["a_revisar"], t["motivo"], t["atendido_sin_conexion"]) == (True, "cancelado", False)


def test_una_atencion_inexistente_es_404_y_no_hay_nada_a_medias(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    c.post(f"/appointments/{turno}/cancel")
    aplicar(atencion_del_nodo(turno))
    r = c.post("/api/nodo/turnos-a-revisar/revisar", json={"atenciones": ["a" * 36, "no-existe"]})
    assert r.status_code == 404
    assert len(c.get("/api/nodo/turnos-a-revisar").json()) == 1, "la primera no quedó marcada: es todo o nada"


def test_la_revisa_cualquier_usuario_de_la_instancia(admin_client, staff_client):
    c = admin_client
    turno = _seeded_appointment(c)
    c.post(f"/appointments/{turno}/cancel")
    aplicar(atencion_del_nodo(turno))
    assert len(staff_client.get("/api/nodo/turnos-a-revisar").json()) == 1
    assert staff_client.post("/api/nodo/turnos-a-revisar/revisar", json={"atenciones": ["a" * 36]}).status_code == 200


def test_el_pedido_sin_atenciones_es_422(admin_client):
    assert admin_client.post("/api/nodo/turnos-a-revisar/revisar", json={"atenciones": []}).status_code == 422
