"""La nota de crédito de la factura de un turno (ADR-039).

La nota la emite el motor (`libracore.notas_de_credito`, con el router de `libracore.facturas_router`): lo que él garantiza
—que una factura no se acredita dos veces, el tope de las parciales, el comprobante asociado, el CAE, el destino de la
plata— lo prueba el motor. **Acá se prueba el cableado y lo propio del producto**: que la ruta llegue desde el turno, que la
emita sólo un administrador, que pida el motivo y lo deje en el log, que la caja quede explicada y que el PDF salga.

ARCA es el simulado de desarrollo (`ENV=development`: CAE de mentira), el mismo de `test_billing.py`.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from libracore import fechas
from libracore.db import caja as db_caja

from tests.test_billing import _seeded_appointment

MOTIVO = "Se facturó el servicio equivocado"


def _facturado(client: TestClient, medio: str = "efectivo", client_data: dict | None = None) -> tuple[str, dict]:
    """Un turno completado y cobrado en `medio` ($1000), y su factura."""
    turno = _seeded_appointment(client, client_data=client_data)
    r = client.post(f"/appointments/{turno}/complete", json={"medio_pago": medio})
    assert r.status_code == 200, r.text
    return turno, r.json()["factura"]


def _emitir(client: TestClient, turno: str, **cuerpo):
    return client.post(f"/appointments/{turno}/nota-credito", json={"motivo": MOTIVO, **cuerpo})


def _neto_de_caja(factura_id: int) -> float:
    """Ingresos menos egresos de la factura, sin los movimientos anulados: lo que la caja dice que quedó cobrado."""
    movimientos = [m for m in db_caja.get_caja_movimientos() if m.get("factura_id") == factura_id and not m.get("anulado")]
    return sum(m["monto"] if m["tipo"] == "ingreso" else -m["monto"] for m in movimientos)


# ── Ver la factura del turno ──────────────────────────────────────────────────────────────────────────────────────────


def test_el_turno_facturado_trae_su_factura_sin_notas(admin_client: TestClient):
    turno, factura = _facturado(admin_client)
    r = admin_client.get(f"/appointments/{turno}/factura")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["factura"]["id"] == factura["id"] and cuerpo["factura"]["total"] == 1000.0
    assert cuerpo["notas_credito"] == []
    assert cuerpo["acreditado"] == 0.0 and cuerpo["saldo_acreditable"] == 1000.0
    assert cuerpo["puede_acreditar"] is True
    assert "pdf_path" not in cuerpo["factura"], "la fila entera (rutas de archivos) no sale"


def test_la_factura_se_encuentra_con_sena_y_saldo(admin_client: TestClient):
    """Con seña la factura se ata a dos movimientos (`<turno>-sena` y `<turno>-saldo`): es la misma factura."""
    turno = _seeded_appointment(admin_client)
    deposito = admin_client.post(f"/appointments/{turno}/deposit", json={"amount": "400.00"}).json()["id"]
    admin_client.post(f"/deposits/{deposito}/mark-paid", json={"medio_pago": "mercadopago"})
    factura = admin_client.post(f"/appointments/{turno}/complete", json={"medio_pago": "efectivo"}).json()["factura"]
    assert admin_client.get(f"/appointments/{turno}/factura").json()["factura"]["id"] == factura["id"]


def test_un_turno_sin_factura_da_404(admin_client: TestClient):
    turno = _seeded_appointment(admin_client, price=None)
    admin_client.post(f"/appointments/{turno}/complete")
    assert admin_client.get(f"/appointments/{turno}/factura").status_code == 404
    assert _emitir(admin_client, turno).status_code == 404


def test_el_staff_ve_la_factura_pero_no_emite_ni_pregunta_por_la_plata(admin_client: TestClient, staff_client: TestClient):
    turno, _ = _facturado(admin_client)
    assert staff_client.get(f"/appointments/{turno}/factura").status_code == 200
    assert staff_client.get(f"/appointments/{turno}/nota-credito/destino").status_code == 403
    assert _emitir(staff_client, turno, destino="devolver", medio_pago="efectivo").status_code == 403
    assert admin_client.get(f"/appointments/{turno}/factura").json()["notas_credito"] == []


def test_sin_el_modulo_de_facturacion_no_hay_nada_que_acreditar(admin_client: TestClient):
    turno, _ = _facturado(admin_client)
    admin_client.app.state.modules.set_enabled("facturacion", False)
    assert admin_client.get(f"/appointments/{turno}/factura").status_code == 403
    assert _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo").status_code == 403


# ── Emitir la nota ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_la_nota_total_anula_la_factura_con_su_comprobante_asociado(admin_client: TestClient):
    turno, factura = _facturado(admin_client)
    r = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")
    assert r.status_code == 200, r.text
    nota = r.json()
    assert nota["tipo"] == 8, "la nota de una factura B es una NC B"
    assert nota["total"] == 1000.0 and nota["cae"], "total, y con CAE"
    # El comprobante asociado que exige ARCA (`10197`): la factura que se anula.
    assert (nota["cbte_asoc_tipo"], nota["cbte_asoc_pv"], nota["cbte_asoc_nro"]) == (
        factura["tipo"], factura["punto_venta"], factura["numero"])
    assert nota["fecha"] == fechas.hoy().isoformat(), "la fecha de hoy: ARCA no admite otra y el motor no deja elegirla"

    despues = admin_client.get(f"/appointments/{turno}/factura").json()
    assert [n["id"] for n in despues["notas_credito"]] == [nota["id"]]
    assert despues["acreditado"] == 1000.0 and despues["saldo_acreditable"] == 0.0
    assert despues["puede_acreditar"] is False


def test_la_factura_a_responsable_inscripto_se_acredita_con_una_nota_a(admin_client: TestClient):
    turno, _ = _facturado(admin_client, client_data={
        "id": "client-1", "name": "Carlos", "cuit": "20111222339", "condicion_iva": "Responsable Inscripto"})
    r = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == 3


def test_acreditar_dos_veces_la_misma_factura_es_409_y_no_emite_otra(admin_client: TestClient):
    """Idempotencia: la guarda es del motor (`ya_tiene_nota`). El segundo pedido —un doble clic, un reintento— no emite nada."""
    turno, _ = _facturado(admin_client)
    assert _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo").status_code == 200
    segunda = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")
    assert segunda.status_code == 409, segunda.text
    assert len(admin_client.get(f"/appointments/{turno}/factura").json()["notas_credito"]) == 1


def test_la_nota_parcial_acredita_hasta_el_total_y_no_mas(admin_client: TestClient):
    turno, _ = _facturado(admin_client)
    primera = _emitir(admin_client, turno, importe="400.00", destino="devolver", medio_pago="efectivo")
    assert primera.status_code == 200, primera.text
    assert primera.json()["total"] == 400.0

    de_mas = _emitir(admin_client, turno, importe="700.00", destino="devolver", medio_pago="efectivo")
    assert de_mas.status_code == 409, "el tope acumulado es el total de la factura"

    intermedio = admin_client.get(f"/appointments/{turno}/factura").json()
    assert intermedio["acreditado"] == 400.0 and intermedio["saldo_acreditable"] == 600.0
    assert intermedio["puede_acreditar"] is True

    resto = _emitir(admin_client, turno, importe="600.00", destino="devolver", medio_pago="efectivo")
    assert resto.status_code == 200, resto.text
    assert admin_client.get(f"/appointments/{turno}/factura").json()["puede_acreditar"] is False


def test_una_nota_total_sobre_una_factura_con_una_parcial_es_409(admin_client: TestClient):
    turno, _ = _facturado(admin_client)
    assert _emitir(admin_client, turno, importe="400.00", destino="devolver", medio_pago="efectivo").status_code == 200
    assert _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo").status_code == 409


# ── El motivo ─────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("cuerpo", [{}, {"motivo": ""}, {"motivo": "   "}, {"motivo": "xx"}, {"motivo": "x" * 201}])
def test_sin_un_motivo_con_sentido_no_se_emite_nada(admin_client: TestClient, cuerpo: dict):
    turno, _ = _facturado(admin_client)
    r = admin_client.post(f"/appointments/{turno}/nota-credito", json={"destino": "devolver", "medio_pago": "efectivo", **cuerpo})
    assert r.status_code == 422, r.text
    assert admin_client.get(f"/appointments/{turno}/factura").json()["notas_credito"] == []


def test_un_campo_de_mas_en_el_cuerpo_es_422(admin_client: TestClient):
    turno, _ = _facturado(admin_client)
    assert _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo", fecha="2020-01-01").status_code == 422


def test_el_motivo_y_quien_la_emitio_quedan_en_el_log_de_actividad(admin_client: TestClient):
    turno, factura = _facturado(admin_client)
    nota = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo").json()

    filas = admin_client.get("/logs", params={"entidad": "nota_de_credito"}).json()["actividad"]
    assert len(filas) == 1, filas
    fila = filas[0]
    assert fila["usuario"] == "admin" and fila["accion"] == "crear" and fila["entidad_id"] == str(nota["id"])
    assert MOTIVO in fila["descripcion"] and turno in fila["descripcion"]
    # Con el tipo de cada una: la numeración es por tipo y la nota y su factura pueden llevar el mismo número.
    assert f"Nota de Crédito B {nota['punto_venta']:04d}-{nota['numero']:08d} sobre Factura B " \
           f"{factura['punto_venta']:04d}-{factura['numero']:08d}" in fila["descripcion"]
    # Y el selector de la pantalla de Logs ofrece la entidad aunque todavía no haya habido ninguna.
    assert "nota_de_credito" in admin_client.get("/logs").json()["entidades"]


def test_una_nota_rechazada_no_deja_rastro_en_el_log(admin_client: TestClient):
    turno, _ = _facturado(admin_client)
    _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")
    _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")  # 409
    assert len(admin_client.get("/logs", params={"entidad": "nota_de_credito"}).json()["actividad"]) == 1


# ── La plata: la caja queda explicada ─────────────────────────────────────────────────────────────────────────────────


def test_devolver_deja_un_egreso_con_la_marca_de_la_nota_y_la_caja_en_cero(admin_client: TestClient):
    turno, factura = _facturado(admin_client)
    assert _neto_de_caja(factura["id"]) == 1000.0
    nota = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")
    assert nota.status_code == 200, nota.text
    assert nota.json()["reintegro"]["movido"] is True and nota.json()["reintegro"]["monto"] == 1000.0

    egresos = [m for m in db_caja.get_caja_movimientos() if m.get("factura_id") == factura["id"] and m["tipo"] == "egreso"]
    assert len(egresos) == 1 and egresos[0]["monto"] == 1000.0 and egresos[0]["medio_pago"] == "efectivo"
    assert egresos[0]["referencia"] == f"nc:factura:{factura['id']}:{nota.json()['id']}"
    assert _neto_de_caja(factura["id"]) == 0.0


def test_la_nota_parcial_devuelve_solo_lo_acreditado(admin_client: TestClient):
    turno, factura = _facturado(admin_client)
    assert _emitir(admin_client, turno, importe="250.00", destino="devolver", medio_pago="efectivo").status_code == 200
    assert _neto_de_caja(factura["id"]) == 750.0


def test_con_plata_cobrada_hay_que_elegir_que_pasa_con_ella(admin_client: TestClient):
    """Sin destino el motor no movería nada y la caja quedaría con un cobro de una factura anulada: acá se pide elegir."""
    turno, factura = _facturado(admin_client)
    r = _emitir(admin_client, turno)
    assert r.status_code == 422, r.text
    assert "plata" in r.json()["detail"]
    assert admin_client.get(f"/appointments/{turno}/factura").json()["notas_credito"] == []
    assert _neto_de_caja(factura["id"]) == 1000.0


def test_la_pantalla_pregunta_al_motor_y_el_cliente_del_turno_no_se_ofrece_a_favor(admin_client: TestClient):
    """`a_favor` es un abono en la cuenta corriente del motor y los clientes de la agenda no viven ahí: no hay dónde dejarlo."""
    turno, _ = _facturado(admin_client)
    oferta = admin_client.get(f"/appointments/{turno}/nota-credito/destino").json()
    assert oferta["aplica"] is True and oferta["monto"] == 1000.0
    assert oferta["medio_sugerido"] == "efectivo" and oferta["cliente_identificado"] is False
    parcial = admin_client.get(f"/appointments/{turno}/nota-credito/destino", params={"importe": "300"}).json()
    assert parcial["monto"] == 300.0

    r = _emitir(admin_client, turno, destino="a_favor")
    assert r.status_code == 422, r.text
    assert admin_client.get(f"/appointments/{turno}/factura").json()["notas_credito"] == []


def test_cobrada_con_dos_medios_hay_que_decir_con_cual_se_devuelve(admin_client: TestClient):
    """Seña por Mercado Pago y saldo en efectivo: el motor no elige por la persona."""
    turno = _seeded_appointment(admin_client)
    deposito = admin_client.post(f"/appointments/{turno}/deposit", json={"amount": "400.00"}).json()["id"]
    admin_client.post(f"/deposits/{deposito}/mark-paid", json={"medio_pago": "mercadopago"})
    factura = admin_client.post(f"/appointments/{turno}/complete", json={"medio_pago": "efectivo"}).json()["factura"]

    oferta = admin_client.get(f"/appointments/{turno}/nota-credito/destino").json()
    assert oferta["medio_sugerido"] is None, "dos medios: no hay uno solo para sugerir"
    assert _emitir(admin_client, turno, destino="devolver").status_code == 422
    r = _emitir(admin_client, turno, destino="devolver", medio_pago="mercadopago")
    assert r.status_code == 200, r.text
    assert _neto_de_caja(factura["id"]) == 0.0


def test_el_estado_de_la_sena_no_se_toca(admin_client: TestClient):
    """La seña es un estado de LibraGenda (cobrada, devuelta…) y la devolución de la plata a quien pagó es una decisión
    aparte (`POST /deposits/{id}/refund`, de admin). La nota no la cambia."""
    turno = _seeded_appointment(admin_client)
    deposito = admin_client.post(f"/appointments/{turno}/deposit", json={"amount": "400.00"}).json()["id"]
    admin_client.post(f"/deposits/{deposito}/mark-paid", json={"medio_pago": "transferencia"})
    admin_client.post(f"/appointments/{turno}/complete", json={"medio_pago": "efectivo"})
    r = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo")
    assert r.status_code == 200, r.text
    assert admin_client.get(f"/appointments/{turno}/deposit").json()["status"] == "paid"


# ── El PDF ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_pdf_de_la_factura_y_el_de_la_nota_salen(admin_client: TestClient, staff_client: TestClient):
    turno, factura = _facturado(admin_client)
    nota = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo").json()
    for comprobante in (factura["id"], nota["id"]):
        for cliente in (admin_client, staff_client):
            r = cliente.get(f"/api/facturas/{comprobante}/pdf")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")


def test_el_pdf_de_un_comprobante_que_no_existe_da_404(admin_client: TestClient):
    assert admin_client.get("/api/facturas/999999/pdf").status_code == 404


# ── El motivo llega al motor ──────────────────────────────────────────────────────────────────────────────────────────


def test_el_motivo_va_a_las_observaciones_de_la_nota_y_a_su_pdf(admin_client: TestClient, monkeypatch):
    """Lo recibe el motor (ADR-089): queda en las `observaciones` de la nota, que es de donde sale el papel."""
    from libracore import pdf_generator

    vistas: list[str] = []
    generar = pdf_generator.generate_pdf_factura
    monkeypatch.setattr(
        pdf_generator, "generate_pdf_factura", lambda f, *a, **k: (vistas.append(f.get("observaciones")), generar(f, *a, **k))[1])
    turno, factura = _facturado(admin_client)
    nota = _emitir(admin_client, turno, destino="devolver", medio_pago="efectivo", motivo="  Se facturó   el servicio equivocado ")
    assert nota.status_code == 200, nota.text
    esperado = (f"Anula Factura B {factura['punto_venta']:04d}-{factura['numero']:08d}"
                " — Se facturó el servicio equivocado")
    assert nota.json()["observaciones"] == esperado
    assert vistas[-1] == esperado, "el PDF se arma con esas observaciones"
