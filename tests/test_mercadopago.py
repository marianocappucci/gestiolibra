"""MercadoPago en Gestiolibra.

El mecanismo lo prueba `libracore`. Lo que se prueba acá es lo único que es de
este producto: **de dónde salen los clientes** — y, sobre todo, que un cobro de
alguien que no es cliente **no dé de alta un cliente de la agenda**.
"""

import json

import pytest
from libracore import config_manager
from libracore import mp_sync
from libracore.db import clients as db_clients
from libracore.db import facturas as db_facturas
from libracore.db import mp as db_mp

EMAIL = "ana@cliente.test"
CUIT = "20111111112"


def _con_credenciales():
    cfg = config_manager.load()
    cfg["mp_access_token"] = "token-de-prueba"
    cfg["empresa_iva_condition"] = "Monotributista"
    config_manager.save(cfg)


def _cliente(admin_client, **datos):
    cuerpo = {"id": "client-1", "name": "Ana Cliente", "email": EMAIL,
              "cuit": CUIT, "condicion_iva": "Responsable Inscripto"}
    cuerpo.update(datos)
    r = admin_client.post("/clients", json=cuerpo)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _pago(**over):
    pago = {
        "status": "approved", "transaction_amount": 9000.0,
        "description": "Cobro", "payment_type_id": "credit_card",
        "payment_method_id": "visa", "external_reference": "",
        "payer": {"email": EMAIL, "first_name": "Ana", "last_name": "Cliente",
                  "identification": {"type": "CUIT", "number": CUIT}},
    }
    pago.update(over)
    return pago


def _webhook(admin_client, payment_id="pago-1"):
    return admin_client.post(
        "/webhooks/mercadopago",
        content=json.dumps({"type": "payment", "data": {"id": payment_id}}).encode(),
        headers={"content-type": "application/json"},
    )


# ── Los gates ───────────────────────────────────────────────────────────────

def test_la_bandeja_es_de_admin(staff_client, admin_client):
    """Las dos mitades, y la de abajo con un usuario **logueado**: un staff no
    entra. Contra un cliente anónimo pasaría igual con cualquier gate."""
    assert staff_client.get("/api/mp-bandeja").status_code == 403
    assert admin_client.get("/api/mp-bandeja").status_code == 200


def test_la_configuracion_de_mercadopago_es_de_admin(staff_client, admin_client):
    assert staff_client.get("/api/config/mercadopago").status_code == 403
    assert admin_client.get("/api/config/mercadopago").status_code == 200


def test_el_webhook_NO_tiene_gate(admin_client):
    """🔑 Lo llama MercadoPago desde internet, **sin cookie**. Lo que lo protege
    es la firma, no una sesión: si estuviera gateado, no llegaría nunca.

    Se usa un cliente sin sesión sobre la misma app, no el de admin.
    """
    from fastapi.testclient import TestClient

    sin_sesion = TestClient(admin_client.app)
    r = sin_sesion.post(
        "/webhooks/mercadopago",
        content=json.dumps({"type": "payment", "data": {"id": "x"}}).encode(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200, r.text


def test_el_token_no_vuelve_en_claro(admin_client):
    _con_credenciales()
    datos = admin_client.get("/api/config/mercadopago").json()
    assert "token-de-prueba" not in str(datos)
    assert datos["mp_access_token_cargado"] is True


# ── El registro: los clientes salen de la agenda ────────────────────────────

def test_la_factura_sale_a_nombre_del_cliente_de_la_agenda(admin_client, monkeypatch):
    _con_credenciales()
    _cliente(admin_client)

    import libracore.mp_webhook as mw

    async def obtener_pago(_pid, _tok):
        return _pago()

    monkeypatch.setattr(mw.mp_api, "obtener_pago", obtener_pago)
    assert _webhook(admin_client).status_code == 200

    # El webhook no auto-factura acá, así que el cobro queda pendiente: se
    # emite con el botón de la bandeja.
    pago = db_mp.get_mp_pago("pago-1")
    assert pago["estado_factura"] == "pendiente"

    r = admin_client.post(f"/api/mp-bandeja/pagos/{pago['id']}/facturar", json={})
    assert r.status_code == 200, r.text
    factura = db_facturas.get_factura(r.json()["factura_id"])
    assert factura["cliente_razon"] == "Ana Cliente"
    assert factura["cliente_cuit"] == CUIT


def test_un_cobro_de_un_desconocido_no_da_de_alta_un_cliente_de_la_agenda(
    admin_client, monkeypatch,
):
    """🔴 El defecto que la costura evita, y el motivo por el que `crear()` no
    persiste.

    Sin esto, cualquiera que pague por MercadoPago aparecería en la agenda del
    negocio, con el nombre que traiga el pagador de MP.
    """
    _con_credenciales()
    _cliente(admin_client)  # existe OTRO cliente, para que la lista no sea vacía

    import libracore.mp_webhook as mw

    async def obtener_pago(_pid, _tok):
        return _pago(payer={"email": "nadie@desconocido.test",
                            "first_name": "Un", "last_name": "Desconocido",
                            "identification": {}})

    monkeypatch.setattr(mw.mp_api, "obtener_pago", obtener_pago)
    _webhook(admin_client, "pago-2")

    pago = db_mp.get_mp_pago("pago-2")
    r = admin_client.post(f"/api/mp-bandeja/pagos/{pago['id']}/facturar", json={})
    assert r.status_code == 200, r.text

    agenda = admin_client.get("/clients").json()
    assert [c["id"] for c in agenda] == ["client-1"], "la agenda no puede haber crecido"
    factura = db_facturas.get_factura(r.json()["factura_id"])
    assert factura["cliente_razon"] == "Un Desconocido"
    assert factura["cliente_cuit"] == ""


def test_no_se_tocan_los_clientes_de_libracore(admin_client, monkeypatch):
    """La tabla `clients` de LibraCore existe en esta instancia —la crea
    `init_core_schema` para que vivan `facturas` y `caja`— pero este producto no
    la usa. Tiene que quedar vacía."""
    _con_credenciales()
    _cliente(admin_client)

    import libracore.mp_webhook as mw

    async def obtener_pago(_pid, _tok):
        return _pago(payer={"email": "otro@test", "first_name": "Otro",
                            "last_name": "", "identification": {}})

    monkeypatch.setattr(mw.mp_api, "obtener_pago", obtener_pago)
    _webhook(admin_client, "pago-3")
    pago = db_mp.get_mp_pago("pago-3")
    admin_client.post(f"/api/mp-bandeja/pagos/{pago['id']}/facturar", json={})

    assert db_clients.get_all_clients() == []


def test_la_bandeja_muestra_el_cliente_de_la_agenda(admin_client):
    _con_credenciales()
    _cliente(admin_client)
    db_mp.create_mp_pago(mp_payment_id="p9", status="approved", monto=1.0,
                         payer_email=EMAIL, payer_name="", estado_factura="pendiente")
    db_mp.create_mp_pago(mp_payment_id="p10", status="approved", monto=1.0,
                         payer_email="nadie@test", payer_name="",
                         estado_factura="pendiente")

    por_id = {p["mp_payment_id"]: p
              for p in admin_client.get("/api/mp-bandeja").json()["pendientes"]}
    assert por_id["p9"]["cliente"]["name"] == "Ana Cliente"
    assert por_id["p10"]["cliente"] is None


def test_facturar_un_cobro_sin_email_encuentra_al_cliente_por_cuit(admin_client):
    """🔑 Este va por `resolver()`, no por `buscar_muchos()`.

    Son dos caminos distintos del registro y cada uno tiene su match por CUIT.
    El test de abajo --el de la bandeja-- pasaba en verde con el match por CUIT
    de `resolver` roto, porque la bandeja usa el otro. Verificado por mutacion.
    """
    _con_credenciales()
    _cliente(admin_client, email=None)
    pago_id = db_mp.create_mp_pago(
        mp_payment_id="p12", status="approved", monto=7000.0,
        payer_email="", payer_name="Quien Transfirio", estado_factura="pendiente",
        payer_id_number=CUIT,
    )
    r = admin_client.post(f"/api/mp-bandeja/pagos/{pago_id}/facturar", json={})
    assert r.status_code == 200, r.text
    factura = db_facturas.get_factura(r.json()["factura_id"])
    assert factura["cliente_razon"] == "Ana Cliente", "tenia que resolver por CUIT"


def test_el_cuit_tambien_matchea_en_la_bandeja(admin_client):
    """La otra mitad: el listado enriquece por CUIT con `buscar_muchos()`."""
    _con_credenciales()
    _cliente(admin_client, email=None)
    db_mp.create_mp_pago(mp_payment_id="p11", status="approved", monto=1.0,
                         payer_email="", payer_name="", estado_factura="pendiente",
                         payer_id_number=CUIT)
    por_id = {p["mp_payment_id"]: p
              for p in admin_client.get("/api/mp-bandeja").json()["pendientes"]}
    assert por_id["p11"]["cliente"]["name"] == "Ana Cliente"


# ── El cron no factura solo ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_el_cron_deja_todo_en_la_bandeja(admin_client, monkeypatch):
    """🔑 En un negocio de turnos la factura sale del turno completado, no de un
    cobro suelto. El cron trae y no emite."""
    _con_credenciales()
    _cliente(admin_client)

    async def usuario_info(_t):
        return {"id": "555", "email": "yo@negocio.test"}

    async def movimientos(_t, _d, _h):
        return [{
            "id": "mov-1", "collector_id": "555", "transaction_amount": 3000.0,
            "external_reference": "", "description": "Cobro",
            "payment_type_id": "bank_transfer", "payment_method_id": "cvu",
            "date_approved": "2026-08-24T10:00:00.000-03:00",
            "payer": {"email": EMAIL, "first_name": "Ana", "last_name": "Cliente",
                      "identification": {"type": "CUIT", "number": CUIT}},
        }]

    monkeypatch.setattr(mp_sync.mp_api, "obtener_usuario_info", usuario_info)
    monkeypatch.setattr(mp_sync.mp_api, "obtener_movimientos", movimientos)

    resultado = await mp_sync.sincronizar_y_facturar(
        dias=2, registro=admin_client.app.state.registro_mp,
    )
    assert resultado == {"nuevos": 1, "facturados": 0, "pendientes": 1}, resultado
    assert db_mp.get_mp_movimiento_by_mp_id("mov-1")["estado_factura"] == "pendiente"
