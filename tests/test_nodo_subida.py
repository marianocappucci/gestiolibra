"""Lo que atiende y cobra el nodo sube al central, y el central lo aplica con sus ids y sus reglas (ADR-036).

Un nodo y su central con **dos bases** (`escenario`, ver `tests/nodo_apoyo.py`): lo que el nodo hace por la API de siempre queda
en su outbox como operaciones (`turno.atendido`, `caja.movimiento`, `cola.pedido`, `gestio.factura_turno`), y el receptor de
LibraEdge del central las aplica con el despachador real del producto. Cada test mira las dos puntas.

🔑 **La atención y lo cobrado valen siempre.** Si en la web el turno cambió mientras tanto (se canceló, se movió), la atención
queda registrada, el cobro sube igual y el turno queda «a revisar» (decisión del humano, 2026-10-25).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from libracore.cola_arca import procesar_cola
from nodo_apoyo import NODO, arca_responde, ticket_de_prueba

from app import offline


def completar(e, turno=None, **cuerpo):
    cuerpo = cuerpo or {"medio_pago": "efectivo"}
    r = e.cliente.post(f"/appointments/{turno or e.datos['turno']}/complete", json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


def atenciones_aplicadas(e):
    return e.sql_central(
        "SELECT appointment_id, status, resultado, motivo, status_before, status_after FROM agenda_applied_attendances"
        " ORDER BY at")


# ── La atención ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_central_aplica_la_atencion_con_la_hora_del_nodo_y_el_turno_queda_completado(escenario):
    e = escenario
    turno = e.datos["turno"]
    completar(e)
    e.subir_todo_y_exigir()

    assert e.sql_central("SELECT status FROM appointments WHERE id = ?", turno) == [("completed",)]
    assert atenciones_aplicadas(e) == [(turno, "completed", "aplicada", None, "confirmed", "completed")]
    # El historial del turno dice de dónde vino.
    assert e.sql_central("SELECT from_status, to_status, reason FROM appointment_transitions WHERE appointment_id = ? "
                         "AND to_status = 'completed'", turno) == [
        ("confirmed", "completed", f"atendido sin conexión en el nodo {NODO}")]


def test_el_cobro_sube_como_caja_del_central_con_su_origen(escenario):
    e = escenario
    turno = e.datos["turno_con_sena"]
    completar(e, turno, medio_pago="efectivo")
    e.subir_todo_y_exigir()

    filas = e.sql_central(
        "SELECT referencia, monto, medio_pago, origen, factura_id FROM caja_movimientos ORDER BY referencia")
    assert filas == [(f"{turno}-saldo", Decimal("600.00"), "efectivo", NODO, None),
                     (f"{turno}-sena", Decimal("400.00"), "transferencia", NODO, None)]
    # El pedido de la factura se ve en el central (la web consulta): `esperando`, con el nodo al que pertenece.
    assert e.sql_central("SELECT origen_instancia, origen_id, estado FROM cola_arca") == [(NODO, turno, "esperando")]


def test_en_curso_y_despues_completado_se_aplican_en_orden_y_las_dos_valen(escenario):
    e = escenario
    turno = e.datos["turno"]
    assert e.cliente.post(f"/appointments/{turno}/start").status_code == 200
    completar(e)
    e.subir_todo_y_exigir()
    assert e.sql_central("SELECT status FROM appointments WHERE id = ?", turno) == [("completed",)]
    assert [(f[1], f[2]) for f in atenciones_aplicadas(e)] == [("in_progress", "aplicada"), ("completed", "aplicada")]
    assert e.sql_central("SELECT from_status, to_status FROM appointment_transitions WHERE appointment_id = ? "
                         "AND reason LIKE 'atendido sin conexión%' ORDER BY at", turno) == [
        ("confirmed", "in_progress"), ("in_progress", "completed")]


def test_un_no_vino_sube_sin_cobro_y_el_turno_queda_ausente(escenario):
    e = escenario
    turno = e.datos["otro_turno"]
    assert e.cliente.post(f"/appointments/{turno}/no-show").status_code == 200
    e.subir_todo_y_exigir()
    assert e.sql_central("SELECT status FROM appointments WHERE id = ?", turno) == [("no_show",)]
    assert e.sql_central("SELECT count(*) FROM caja_movimientos") == [(0,)]


def test_subir_lo_mismo_dos_veces_es_un_solo_efecto(escenario):
    e = escenario
    completar(e)
    operaciones = e.pendientes()
    primera = e.subir(operaciones)
    assert {r.result for _op, r in primera} == {"accepted"}
    segunda = e.subir(operaciones)
    assert {r.result for _op, r in segunda} == {"duplicate"}
    assert e.sql_central("SELECT count(*) FROM caja_movimientos") == [(1,)]
    assert len(atenciones_aplicadas(e)) == 1


def test_la_misma_atencion_aplicada_a_mano_otra_vez_no_repite_nada(escenario):
    """Aunque el receptor no la deduplicara (otra entrega, otro proceso), LibraGenda es idempotente por `atencion_id`."""
    e = escenario
    completar(e)
    (atencion,) = [op for op in e.pendientes() if op.operation_type == "turno.atendido"]
    from libragenda import atencion_en_nodo

    e.subir_todo_y_exigir()
    with e.en_el_central():
        from libragenda.database import get_session_factory

        with get_session_factory().begin() as sesion:
            repetida = atencion_en_nodo.aplicar_turno_atendido(sesion, atencion)
    assert repetida.repetida is True
    assert len(atenciones_aplicadas(e)) == 1


# ── Lo que cambió en la web mientras tanto ────────────────────────────────────────────────────────────────────────────


def test_un_turno_cancelado_en_la_web_queda_a_revisar_pero_lo_cobrado_vale(escenario):
    e = escenario
    turno = e.datos["turno"]
    completar(e)
    # Mientras el local estaba sin internet, alguien canceló el turno en la web.
    e.ejecutar_en_el_central("UPDATE appointments SET status = 'cancelled' WHERE id = ?", turno)
    resultados = e.subir_todo_y_exigir()
    assert all(r.result == "accepted" for _op, r in resultados)

    # El turno cancelado no se toca (cancelado es terminal) y la atención queda a revisar, con su motivo.
    assert e.sql_central("SELECT status FROM appointments WHERE id = ?", turno) == [("cancelled",)]
    assert atenciones_aplicadas(e) == [(turno, "completed", "a_revisar", "cancelado", "cancelled", "cancelled")]
    # Lo cobrado se conserva: la plata entró en el mostrador.
    assert e.sql_central("SELECT monto FROM caja_movimientos") == [(Decimal("1000.00"),)]


def test_un_turno_movido_en_la_web_se_atiende_sobre_el_turno_movido_y_queda_a_revisar(escenario):
    e = escenario
    turno = e.datos["turno"]
    completar(e)
    e.ejecutar_en_el_central("UPDATE appointments SET starts_at = starts_at + interval '1 day' WHERE id = ?", turno)
    e.subir_todo_y_exigir()
    assert e.sql_central("SELECT status FROM appointments WHERE id = ?", turno) == [("completed",)]
    assert atenciones_aplicadas(e)[0][2:4] == ("a_revisar", "movido")


def test_un_turno_que_la_web_ya_completo_queda_a_revisar_y_el_cobro_repetido_va_a_revision_manual(escenario):
    """La web completó y cobró el mismo turno: puede haberse cobrado dos veces. La atención queda a revisar; el cobro del nodo
    tiene la misma referencia que el de la web y el central **no lo duplica**: va a la revisión manual de LibraEdge."""
    e = escenario
    turno = e.datos["turno"]
    completar(e)
    e.ejecutar_en_el_central("UPDATE appointments SET status = 'completed' WHERE id = ?", turno)
    e.ejecutar_en_el_central(
        "INSERT INTO caja_movimientos (fecha, tipo, concepto, monto, referencia, medio_pago) "
        "VALUES ('2026-10-25', 'ingreso', 'Saldo factura 1', 1000, ?, 'efectivo')", f"{turno}-saldo")
    resultados = e.subir()
    por_tipo = {op.operation_type: r for op, r in resultados}
    assert por_tipo["turno.atendido"].result == "accepted"
    assert atenciones_aplicadas(e)[0][2:4] == ("a_revisar", "ya_atendido")
    assert por_tipo["caja.movimiento"].result == "rejected"
    assert "no se duplica" in por_tipo["caja.movimiento"].error
    assert e.sql_central("SELECT count(*) FROM caja_movimientos") == [(1,)]


def test_un_turno_que_ya_no_existe_en_el_central_no_pierde_la_atencion(escenario):
    e = escenario
    turno = e.datos["otro_turno"]
    completar(e, turno)
    e.ejecutar_en_el_central("DELETE FROM appointments WHERE id = ?", turno)
    e.subir_todo_y_exigir()
    assert atenciones_aplicadas(e) == [(turno, "completed", "a_revisar", "turno_inexistente", None, None)]


# ── La factura ────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_la_factura_emitida_al_volver_la_conexion_llega_al_central_con_su_numero_y_ata_los_cobros(escenario, monkeypatch):
    e = escenario
    arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    turno = e.datos["turno_con_sena"]
    completar(e, turno, medio_pago="efectivo")
    e.en_linea(True)
    asyncio.run(procesar_cola(offline.cola()))
    resultados = e.subir_todo_y_exigir()
    assert "gestio.factura_turno" in [op.operation_type for op, _r in resultados]

    ((factura_id, numero, cae, total, obs),) = e.sql_central("SELECT id, numero, cae, total, observaciones FROM facturas")
    assert (numero, cae, Decimal(str(total)), obs) == (1, "75123456789012", Decimal("1000.00"), f"Turno {turno}")
    # Los dos cobros del central quedaron atados a la factura del central (no a la del nodo).
    assert e.sql_central("SELECT referencia, factura_id FROM caja_movimientos ORDER BY referencia") == [
        (f"{turno}-saldo", factura_id), (f"{turno}-sena", factura_id)]
    assert e.sql_central("SELECT estado FROM cola_arca") == [("emitido",)]


def test_la_factura_que_llega_antes_que_el_cobro_lo_ata_cuando_este_llega(escenario, monkeypatch):
    e = escenario
    arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    turno = e.datos["turno"]
    completar(e)
    e.en_linea(True)
    asyncio.run(procesar_cola(offline.cola()))
    operaciones = e.pendientes()
    factura = [op for op in operaciones if op.operation_type == "gestio.factura_turno"]
    resto = [op for op in operaciones if op.operation_type != "gestio.factura_turno"]
    # Orden invertido a propósito (el outbox lo entrega en orden, pero la unicidad no puede depender de eso).
    e.subir(factura)
    assert e.sql_central("SELECT count(*) FROM caja_movimientos") == [(0,)]
    e.subir(resto)
    ((factura_id,),) = e.sql_central("SELECT id FROM facturas")
    assert e.sql_central("SELECT referencia, factura_id FROM caja_movimientos") == [(f"{turno}-saldo", factura_id)]


def test_la_factura_se_aplica_una_sola_vez(escenario, monkeypatch):
    e = escenario
    arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    completar(e)
    e.en_linea(True)
    asyncio.run(procesar_cola(offline.cola()))
    operaciones = e.pendientes()
    e.subir(operaciones)
    e.subir(operaciones)
    assert e.sql_central("SELECT count(*) FROM facturas") == [(1,)]


def test_dos_comprobantes_por_el_mismo_turno_van_a_revision_manual(escenario, monkeypatch):
    """La web ya había facturado el turno (con la marca): la del nodo no se aplica a ciegas."""
    e = escenario
    arca_responde(monkeypatch)
    ticket_de_prueba(monkeypatch)
    turno = e.datos["turno"]
    completar(e)
    e.en_linea(True)
    asyncio.run(procesar_cola(offline.cola()))
    e.ejecutar_en_el_central(
        "INSERT INTO facturas (tipo, punto_venta, numero, fecha, cliente_cuit, cliente_razon, cliente_iva_cond, items, "
        "subtotal, iva_amount, total, cae, observaciones, ambiente) VALUES (6, 3, 99, '2026-10-25', '', 'Ana', 5, '[]', "
        "826.45, 173.55, 1000, '12345678901234', ?, 'produccion')", f"Turno {turno}")
    resultados = e.subir()
    factura = [r for op, r in resultados if op.operation_type == "gestio.factura_turno"][0]
    assert factura.result == "rejected" and "dos comprobantes por el mismo turno" in factura.error


# ── Lo que ve la lista «a revisar» en el nodo ─────────────────────────────────────────────────────────────────────────


def test_una_atencion_que_ya_subio_deja_de_ser_atendida_sin_conexion(escenario):
    """El nodo sabe que subió porque la tabla de lo aplicado baja por el espejo: acá se simula copiándola."""
    e = escenario
    turno = e.datos["turno"]
    completar(e)

    def agenda():
        r = e.cliente.get("/resources/box-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-01"})
        return {t["id"]: t for t in r.json()}[turno]

    assert agenda()["atendido_sin_conexion"] is True
    e.ejecutar_en_el_central("UPDATE appointments SET status = 'cancelled' WHERE id = ?", turno)
    e.subir_todo_y_exigir()

    # El espejo baja al nodo lo que el central decidió: el turno cancelado y la atención «a revisar».
    from libracore.db import core

    with core.get_connection() as conn:
        conn.execute("SET LOCAL libraedge.aplicando = '1'")
        conn.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (turno,))
        (fila,) = e.sql_central(
            "SELECT atencion_id, node_id, appointment_id, status, at, actor, resultado, motivo, status_before, "
            "status_after, applied_at FROM agenda_applied_attendances")
        conn.execute(
            "INSERT INTO agenda_applied_attendances (atencion_id, node_id, appointment_id, status, at, actor, resultado, "
            "motivo, status_before, status_after, applied_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", fila)
        conn.commit()
    visto = agenda()
    assert (visto["status"], visto["atendido_sin_conexion"], visto["a_revisar"], visto["motivo"]) == (
        "cancelled", False, True, "cancelado")
