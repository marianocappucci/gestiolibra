"""Atender y cobrar un turno en el nodo, sin conexión (ADR-036).

La agenda del nodo es de sólo consulta, pero un turno ya dado se atiende y se cobra. Lo que se mide acá es **el nodo**: qué
queda en su base, qué queda encolado para subir, y qué se le da al cliente en el momento. Lo que llega al central está en
`test_nodo_subida.py`.

🔑 Todo ocurre en **una transacción**: o queda el turno atendido con su plata y su factura en cola, o no queda nada.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from libracore.cola_arca import procesar_cola
from libracore.db import core
from nodo_apoyo import arca_responde, ticket_de_prueba

from app import offline


def completar(e, turno=None, **cuerpo):
    cuerpo = cuerpo or {"medio_pago": "efectivo"}
    return e.cliente.post(f"/appointments/{turno or e.datos['turno']}/complete", json=cuerpo)


def estado_en_la_base(e, turno):
    return e.sql_nodo("SELECT status FROM appointments WHERE id = ?", turno)[0][0]


# ── Sin conexión ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_completar_sin_conexion_cobra_deja_la_factura_en_cola_y_atiende_el_turno(escenario):
    e = escenario
    turno = e.datos["turno"]
    r = completar(e)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["status"] == "completed" and cuerpo["atendido_sin_conexion"] is True
    assert cuerpo["factura"] is None, "sin red no hay factura: sale al volver la conexión"
    assert cuerpo["factura_en_cola"]["estado"] == "esperando"
    assert cuerpo["comprobante_no_fiscal"] == f"/appointments/{turno}/comprobante-no-fiscal"
    assert "cola" in cuerpo["mensaje"]
    # La forma del 202 `en_cola` que reconoce el kit: la pantalla avisa «Se emite al volver la conexión».
    assert cuerpo["en_cola"] is True and cuerpo["estado"] == "esperando" and cuerpo["pedido_id"] == cuerpo["factura_en_cola"]["id"]

    # El saldo (todo el precio: no había seña) quedó en la caja, SIN factura: se ata cuando salga.
    assert e.sql_nodo("SELECT tipo, monto, medio_pago, referencia, factura_id FROM caja_movimientos") == [
        ("ingreso", Decimal("1000.00"), "efectivo", f"{turno}-saldo", None)]
    assert e.sql_nodo("SELECT count(*) FROM facturas") == [(0,)], "nunca se numera una factura local"
    # El pedido de la factura, con la foto de lo que se cobró.
    ((origen_id, estado, datos),) = e.sql_nodo("SELECT origen_id, estado, datos FROM cola_arca")
    assert (origen_id, estado) == (turno, "esperando")
    import json
    foto = json.loads(datos) if isinstance(datos, str) else datos
    assert foto["precio"] == "1000.00" and foto["saldo"] == "1000.00" and foto["sena"] == "0"
    assert foto["cliente"]["nombre"] == "Ana Gómez" and foto["cliente"]["cuit"] == "27111111113"
    # La atención quedó en la fila propia del nodo; el turno del espejo no se tocó (la guarda no lo dejaría).
    assert e.sql_nodo("SELECT status, appointment_id FROM agenda_node_attendances") == [("completed", turno)]
    assert estado_en_la_base(e, turno) == "confirmed"


def test_lo_que_sube_es_el_cobro_el_pedido_y_la_atencion_en_ese_orden_y_una_sola_vez(escenario):
    e = escenario
    assert completar(e).status_code == 200
    assert e.tipos_pendientes() == ["caja.movimiento", "cola.pedido", "turno.atendido"]
    atencion = e.pendientes()[2].payload
    assert atencion["estado"] == "completed" and atencion["turno_id"] == e.datos["turno"]
    # La plata viaja por `caja.movimiento`; en la atención va sólo para quien revisa.
    assert atencion["extra"]["cobro"]["saldo"] == "1000.00" and atencion["extra"]["cobro"]["factura"] == "en_cola"
    assert atencion["visto"]["estado"] == "confirmed"
    caja = e.pendientes()[0].payload
    assert caja["extra"] == {"turno_id": e.datos["turno"], "parte": "saldo"}
    assert caja["factura_id"] is None


def test_la_sena_cobrada_y_el_saldo_son_dos_movimientos_con_su_medio_de_pago(escenario):
    e = escenario
    turno = e.datos["turno_con_sena"]
    r = completar(e, turno, medio_pago="efectivo")
    assert r.status_code == 200, r.text
    assert e.sql_nodo("SELECT referencia, monto, medio_pago FROM caja_movimientos ORDER BY referencia") == [
        (f"{turno}-saldo", Decimal("600.00"), "efectivo"), (f"{turno}-sena", Decimal("400.00"), "transferencia")]
    assert e.tipos_pendientes() == ["caja.movimiento", "caja.movimiento", "cola.pedido", "turno.atendido"]


def test_las_validaciones_de_siempre_valen_en_el_nodo(escenario):
    e = escenario
    # Con saldo y sin medio de pago: 422, y no queda nada.
    assert e.cliente.post(f"/appointments/{e.datos['turno']}/complete").status_code == 422
    assert e.pendientes() == []
    assert e.cliente.post("/appointments/no-existe/complete", json={"medio_pago": "efectivo"}).status_code == 404


def test_si_el_turno_no_se_puede_atender_no_queda_nada_ni_el_cobro(escenario):
    e = escenario
    turno = e.datos["turno"]
    assert e.cliente.post(f"/appointments/{turno}/no-show").status_code == 200
    # «No vino» ya es el final: completar falla DESPUÉS de haber anotado los cobros en la transacción, y se deshace todo.
    r = completar(e)
    assert r.status_code == 409, r.text
    assert e.sql_nodo("SELECT count(*) FROM caja_movimientos") == [(0,)]
    assert e.sql_nodo("SELECT count(*) FROM cola_arca") == [(0,)]
    assert e.tipos_pendientes() == ["turno.atendido"], "sólo la atención de «no vino»: ninguna operación de más"


def test_completar_dos_veces_no_cobra_dos_veces(escenario):
    e = escenario
    assert completar(e).status_code == 200
    assert completar(e).status_code == 409
    assert e.sql_nodo("SELECT count(*) FROM caja_movimientos") == [(1,)]
    assert e.tipos_pendientes().count("turno.atendido") == 1


def test_sin_el_modulo_de_facturacion_se_atiende_y_no_se_cobra(escenario, monkeypatch):
    """El plan sin facturación (Básico, Estándar) sólo marca la atención: ni caja ni factura, como en la web."""
    e = escenario
    from app.services.modules import ModuleRepository

    monkeypatch.setattr(ModuleRepository, "is_enabled", lambda self, modulo: modulo != "facturacion")
    r = e.cliente.post(f"/appointments/{e.datos['turno']}/complete")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["factura_en_cola"] is None and r.json()["comprobante_no_fiscal"] is None
    assert e.sql_nodo("SELECT count(*) FROM caja_movimientos") == [(0,)]
    assert e.tipos_pendientes() == ["turno.atendido"]


# ── En curso y «no vino» ───────────────────────────────────────────────────────────────────────────────────────────────


def test_el_turno_pasa_a_en_curso_y_despues_se_completa(escenario):
    e = escenario
    turno = e.datos["turno"]
    assert e.cliente.post(f"/appointments/{turno}/start").json()["status"] == "in_progress"
    assert completar(e).status_code == 200
    assert e.sql_nodo("SELECT status FROM agenda_node_attendances ORDER BY orden") == [("in_progress",), ("completed",)]
    assert e.tipos_pendientes() == ["turno.atendido", "caja.movimiento", "cola.pedido", "turno.atendido"]


def test_no_vino_no_cobra_nada(escenario):
    e = escenario
    r = e.cliente.post(f"/appointments/{e.datos['turno']}/no-show")
    assert r.status_code == 200 and r.json()["status"] == "no_show"
    assert r.json()["factura_en_cola"] is None
    assert e.sql_nodo("SELECT count(*) FROM caja_movimientos") == [(0,)]


def test_la_agenda_del_nodo_muestra_la_atencion_encima_del_espejo(escenario):
    e = escenario
    antes = {t["id"]: t for t in e.cliente.get(
        "/resources/box-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"}).json()}
    assert antes[e.datos["turno"]]["atendido_sin_conexion"] is False
    assert completar(e).status_code == 200
    despues = {t["id"]: t for t in e.cliente.get(
        "/resources/box-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"}).json()}
    atendido, otro = despues[e.datos["turno"]], despues[e.datos["otro_turno"]]
    assert (atendido["status"], atendido["atendido_sin_conexion"], atendido["a_revisar"]) == ("completed", True, False)
    assert (otro["status"], otro["atendido_sin_conexion"]) == ("confirmed", False)


# ── El comprobante no fiscal ───────────────────────────────────────────────────────────────────────────────────────────


def test_el_comprobante_no_fiscal_lleva_la_leyenda_y_lo_que_se_cobro(escenario, monkeypatch):
    e = escenario
    from libracore import ticket_generator

    from libracore import config_manager

    # En la PC, los datos de empresa del encabezado los escribe el instalador en el `config.json` del nodo (la carga
    # de `libraedge-central nodo registrar`, `CLAVES_DEL_EMISOR`, ADR-017 de LibraEdge): acá se siembran igual.
    config_manager.save({**config_manager.load(), "empresa_nombre": "Peluquería Ejemplo SRL",
                         "empresa_cuit": "30999999006", "empresa_iva_condition": "Responsable Inscripto",
                         "empresa_direccion": "Calle Falsa 123"})
    encabezados = []
    real_encabezado = ticket_generator._empresa_header
    monkeypatch.setattr(ticket_generator, "_empresa_header",
                        lambda pdf, cfg, logo: (encabezados.append(cfg), real_encabezado(pdf, cfg, logo))[1])
    visto = []
    real = ticket_generator.generar_ticket_venta
    monkeypatch.setattr(ticket_generator, "generar_ticket_venta", lambda venta: (visto.append(venta), real(venta))[1])
    turno = e.datos["turno_con_sena"]
    assert completar(e, turno, medio_pago="efectivo").status_code == 200

    r = e.cliente.get(f"/appointments/{turno}/comprobante-no-fiscal")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    (venta,) = visto
    # `factura_pendiente` es lo que hace imprimir «NO VÁLIDO COMO FACTURA / La factura se emite al volver la conexión».
    assert venta["factura_pendiente"] is True
    assert venta["total"] == 1000.0 and venta["cliente_nombre"] == "Ana Gómez" and venta["cliente_cuit"] == "27111111113"
    assert venta["items"] == [{"nombre": "Corte", "cantidad": 1, "precio_unitario": 1000.0}]
    assert {p["medio"]: p["monto"] for p in venta["pagos"]} == {"transferencia": 400.0, "efectivo": 600.0}
    # El encabezado sale con la empresa del `config.json` de la PC, no vacío.
    assert encabezados and encabezados[0]["empresa_nombre"] == "Peluquería Ejemplo SRL"
    assert encabezados[0]["empresa_cuit"] == "30999999006"
    # Reimprimirlo da el mismo comprobante: sale de la foto del pedido, no de lo que valga hoy.
    assert e.cliente.get(f"/appointments/{turno}/comprobante-no-fiscal").status_code == 200


def test_un_turno_que_no_se_cobro_en_el_nodo_no_tiene_comprobante(escenario):
    e = escenario
    assert e.cliente.get(f"/appointments/{e.datos['turno']}/comprobante-no-fiscal").status_code == 404


# ── Con conexión y al volver ───────────────────────────────────────────────────────────────────────────────────────────


def test_con_conexion_la_factura_sale_en_el_acto_y_ata_los_cobros(escenario, monkeypatch):
    e = escenario
    arca = arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    e.en_linea(True)
    turno = e.datos["turno_con_sena"]
    r = completar(e, turno, medio_pago="efectivo")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["factura_en_cola"] is None and cuerpo["comprobante_no_fiscal"] is None
    assert cuerpo["factura"]["cae"] == "75123456789012" and cuerpo["factura"]["total"] == 1000.0
    assert cuerpo["factura"]["numero"] == 1 and cuerpo["factura"]["punto_venta"] == 3
    assert [p[0] for p in arca] == ["ultimo", "cae"]
    # Los dos cobros, atados a la factura; y la marca que la ata al turno.
    assert e.sql_nodo("SELECT referencia, factura_id FROM caja_movimientos ORDER BY referencia") == [
        (f"{turno}-saldo", cuerpo["factura"]["id"]), (f"{turno}-sena", cuerpo["factura"]["id"])]
    assert e.sql_nodo("SELECT observaciones FROM facturas") == [(f"Turno {turno}",)]
    assert e.sql_nodo("SELECT estado FROM cola_arca") == [("emitido",)]
    assert e.tipos_pendientes() == [
        "caja.movimiento", "caja.movimiento", "cola.pedido", "turno.atendido", "cola.pedido", "gestio.factura_turno"]


def test_al_volver_la_conexion_la_cola_emite_lo_que_quedo(escenario, monkeypatch):
    e = escenario
    arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    turno = e.datos["turno"]
    assert completar(e).status_code == 200
    assert e.sql_nodo("SELECT count(*) FROM facturas") == [(0,)]

    e.en_linea(True)
    salida = asyncio.run(procesar_cola(offline.cola()))
    assert [x["origen_id"] for x in salida["emitidos"]] == [turno]
    ((numero, cae, obs),) = e.sql_nodo("SELECT numero, cae, observaciones FROM facturas")
    assert (numero, cae, obs) == (1, "75123456789012", f"Turno {turno}")
    assert e.sql_nodo("SELECT factura_id IS NOT NULL FROM caja_movimientos") == [(True,)]
    # Y la factura sube junto con el estado del pedido.
    assert e.tipos_pendientes()[-2:] == ["cola.pedido", "gestio.factura_turno"]


def test_si_la_conexion_se_corta_a_mitad_el_pedido_sigue_esperando(escenario, monkeypatch):
    e = escenario
    arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch, falla=ConnectionError("el central no contesta"))
    e.en_linea(True)
    r = completar(e)
    assert r.status_code == 200, r.text
    assert r.json()["factura"] is None and r.json()["factura_en_cola"]["estado"] == "esperando"
    assert r.json()["comprobante_no_fiscal"]


def test_la_factura_emitida_es_idempotente_si_el_proceso_murio_a_mitad(escenario, monkeypatch):
    """Si ARCA emitió y el nodo no llegó a anotar el pedido como emitido, al reintentar el emisor encuentra la factura por
    su marca: no numera ni pide otro CAE (dos facturas por un solo servicio)."""
    e = escenario
    arca = arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    assert completar(e).status_code == 200
    e.en_linea(True)
    asyncio.run(procesar_cola(offline.cola()))
    assert [p[0] for p in arca] == ["ultimo", "cae"]
    # El proceso «murió» antes de marcar el pedido: vuelve a esperar.
    with core.get_connection() as conn:
        conn.execute("UPDATE cola_arca SET estado = 'esperando', resultado = ''")
        conn.commit()

    salida = asyncio.run(procesar_cola(offline.cola()))
    assert len(salida["emitidos"]) == 1
    assert e.sql_nodo("SELECT count(*) FROM facturas") == [(1,)]
    assert [p[0] for p in arca] == ["ultimo", "cae"], "no volvió a ir a ARCA"
    assert e.sql_nodo("SELECT estado FROM cola_arca") == [("emitido",)]
