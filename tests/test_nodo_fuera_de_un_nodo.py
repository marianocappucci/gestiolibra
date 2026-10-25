"""Fuera de un nodo no cambia nada (ADR-036).

La instancia sin nodo (la demo, el desarrollo, un cliente sin escritorio) y el **central** de una con nodo vinculado
siguen operando como siempre: la web da, mueve y cancela turnos, completa y factura en el momento con ARCA, y no hay outbox.
Esto es lo que más importa de todo el cambio: ningún cliente actual tiene que enterarse de que existe el modo sin conexión.
"""
from __future__ import annotations

from libracore.db import core
from test_billing import _seeded_appointment

from app import offline


def test_sin_identidad_de_nodo_no_hay_nodo_ni_cola_ni_conexion(admin_client):
    assert offline.nodo() is None
    assert offline.cola().conexion.es_nodo() is False
    assert offline.CONEXION.sin_conexion() is False
    assert offline.arrancar_cola() is None


def test_completar_en_la_web_factura_en_el_momento_y_no_deja_nada_en_el_outbox(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    r = c.post(f"/appointments/{turno}/complete", json={"medio_pago": "efectivo"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["status"] == "completed" and cuerpo["factura"]["cae"]
    assert "factura_en_cola" not in cuerpo and "atendido_sin_conexion" not in cuerpo, "la respuesta es la de siempre"
    with core.get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM sync_outbox").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM cola_arca").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM agenda_node_attendances").fetchone()[0] == 0
        # La caja y la factura, como siempre: la caja atada a la factura.
        assert conn.execute("SELECT count(*) FROM facturas WHERE observaciones = ''").fetchone()[0] == 1
        assert conn.execute("SELECT factura_id IS NOT NULL FROM caja_movimientos").fetchone()[0] is True


def test_la_agenda_de_la_web_trae_los_tres_campos_nuevos_en_su_valor_neutro(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    r = c.get("/resources/resource-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"})
    (t,) = r.json()
    assert t["id"] == turno
    assert (t["atendido_sin_conexion"], t["a_revisar"], t["motivo"]) == (False, False, None)


def test_marcar_en_curso_y_no_vino_es_del_nodo_y_la_web_lo_dice(admin_client):
    c = admin_client
    turno = _seeded_appointment(c)
    for accion in ("start", "no-show"):
        r = c.post(f"/appointments/{turno}/{accion}")
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "solo_en_el_nodo", r.text
    # Y el turno sigue como estaba: se puede completar como siempre.
    assert c.post(f"/appointments/{turno}/complete", json={"medio_pago": "efectivo"}).status_code == 200


def test_el_comprobante_no_fiscal_no_existe_fuera_de_un_nodo(admin_client):
    turno = _seeded_appointment(admin_client)
    assert admin_client.get(f"/appointments/{turno}/comprobante-no-fiscal").status_code == 404


def test_el_alta_de_un_cliente_en_la_web_sigue_siendo_un_uuid_y_se_edita(admin_client):
    c = admin_client
    r = c.post("/clients", json={"name": "Ana", "cuit": "20111222339"})
    assert r.status_code == 201
    assert len(r.json()["id"]) == 36
    assert c.put(f"/clients/{r.json()['id']}", json={"name": "Ana B."}).status_code == 200
    assert c.delete(f"/clients/{r.json()['id']}").status_code == 204


def test_el_catalogo_y_la_configuracion_se_escriben_en_la_web(admin_client):
    c = admin_client
    assert c.post("/branches", json={"id": "b1", "name": "Sucursal"}).status_code == 201
    assert c.put("/config/arca", json={"empresa": "negocio", "cuit": "20111222339", "punto_venta": 3}).status_code == 200
    assert c.get("/api/nodo/cola").json()["es_nodo"] is False
    assert c.get("/api/nodo/conexion").json() == {"es_nodo": False, "en_linea": True, "node_id": None, "a_facturar": 0}
    assert c.get("/api/nodo/turnos-a-revisar").json() == []


def test_los_modulos_se_siembran_en_la_web(admin_client):
    """En un nodo `ensure_seeded` no corre (los módulos son los del central); en la web sí."""
    assert admin_client.app.state.modules.get_all(), "los módulos de plan se sembraron al arrancar"
