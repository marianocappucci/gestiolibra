"""La factura de un turno cobrado en un nodo sin conexión: el emisor de la cola de ARCA y lo que el central hace con lo que
sube (ADR-036).

En el central, completar un turno factura en el momento (`billing.invoice_appointment`, con `get_next_numero_with_arca`).
En un nodo **no puede**: sin red, esa función cae a la numeración local, y un número local choca con el de ARCA y con el del
central (libracore ADR-074). Por eso en un nodo completar un turno **no emite**: deja el pedido en la cola
(`libracore.cola_arca`, ADR-079) y, si hay conexión, lo emite en el momento; si no, sale solo cuando vuelve.

| Pieza | Dónde corre | Qué hace |
|---|---|---|
| `emitir_documento(pedido, ctx)` | nodo | el emisor `documento` de la cola: numera con el ticket prestado y emite |
| `vincular_cobros_a_factura(...)` | nodo y central | ata a la factura los cobros del turno que quedaron sin ella |
| `payload_de_la_factura_del_turno(...)` | nodo | la operación `gestio.factura_turno` que sube la factura emitida |
| `aplicar_factura_del_turno(conn, op)` | central | escribe la factura con su número y CAE y la ata a los cobros del turno |
| `aplicar_movimiento_de_caja(conn, op)` | central | `caja.movimiento` del nodo, y si la factura del turno ya subió, lo ata a ella |

## El emisor es idempotente por la marca de la factura

`facturas.observaciones = "Turno <id>"` (`observacion_del_turno`). Si el proceso murió entre «ARCA emitió» y «el nodo
anotó», la factura ya está creada: el emisor la encuentra por la marca y no emite otra. Si está **sin CAE**, vuelve a
pedirlo con un ticket nuevo (no numera ni crea otra).

## Los cobros salen sin factura y se atan después

En el central la seña y el saldo se anotan **con** la factura (`factura_id`). En el nodo se anotan al atender, antes de que
exista, y llevan la marca `extra["turno_id"]` y la referencia `<turno>-sena` / `<turno>-saldo`. Cuando la factura sale,
el nodo los ata (`vincular_cobros_a_factura`) y el central los ata al aplicar `gestio.factura_turno`: sus ids son otros
(`factura_id` y `cc_pago_id` no se copian, libracore ADR-080), así que se atan por la referencia.

## La fecha y el importe salen de la foto del pedido

`cola_arca.datos` lleva lo que **no se puede releer después**: el precio que se cobró, el cliente tal como estaba (nombre,
CUIT, condición de IVA) y cómo se pagó. Si mañana cambia el precio del servicio, o el cliente provisorio recibe su id
definitivo, la factura sale por lo que se cobró.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from libracore.arca_facturacion import ambiente_de, solicitar_cae
from libracore.db import cola_arca as db_cola
from libracore.db import facturas as db_facturas
from libracore.db.core import get_connection
from libracore.facturas_del_nodo import VERSION as VERSION_FACTURA
from libracore.facturas_del_nodo import aplicar_factura_del_nodo, payload_factura

from app import offline
from app.services.billing import IVA_CODES, _split_iva, _tipo_comprobante, get_arca_config

logger = logging.getLogger(__name__)

#: La forma del payload de `gestio.factura_turno`. Si cambia, sube: el central rechaza lo que no entiende.
VERSION = 1

#: La forma del `datos` del pedido de la cola (`cola_arca.datos`). Si cambia, sube.
VERSION_DEL_PEDIDO = 1

SUFIJO_SENA = "sena"
SUFIJO_SALDO = "saldo"


class FacturaDelTurnoError(ValueError):
    """La factura de un turno del nodo no se puede aplicar en el central. Es un `ValueError` a propósito: el receptor de
    LibraEdge la manda a revisión manual y el nodo no traba la cola detrás de ella (ADR-020 de libraedge)."""


def observacion_del_turno(turno_id: str) -> str:
    """La marca que lleva la factura de un turno (`facturas.observaciones`): es lo que la ata al turno."""
    return f"Turno {turno_id}"


def referencia_de_cobro(turno_id: str, parte: str) -> str:
    """La referencia con la que se anota un cobro del turno en la caja (`<turno>-sena` o `<turno>-saldo`), igual que
    `billing.invoice_appointment`."""
    return f"{turno_id}-{parte}"


def _referencias(turno_id: str) -> tuple[str, str]:
    return referencia_de_cobro(turno_id, SUFIJO_SENA), referencia_de_cobro(turno_id, SUFIJO_SALDO)


# ── La foto del pedido ─────────────────────────────────────────────────────────────────────────────────────────────────


def datos_del_pedido(*, turno_id: str, precio: Decimal, cliente: dict, servicio: str, sena: Decimal,
                     sena_medio_pago: str | None, saldo: Decimal, saldo_medio_pago: str | None) -> dict:
    """Lo que la cola guarda del cobro (`cola_arca.datos`, JSON): la plata, como texto."""
    return {
        "version": VERSION_DEL_PEDIDO,
        "turno_id": turno_id,
        "servicio": servicio,
        "precio": str(precio),
        "sena": str(sena),
        "sena_medio_pago": sena_medio_pago or "",
        "saldo": str(saldo),
        "saldo_medio_pago": saldo_medio_pago or "",
        "cliente": {
            "id": cliente.get("id") or "",
            "nombre": cliente.get("name") or "",
            "cuit": cliente.get("cuit") or "",
            "condicion_iva": cliente.get("condicion_iva") or "",
        },
    }


# ── En el nodo: el emisor de la cola ──────────────────────────────────────────────────────────────────────────────────


def factura_del_nodo_de(turno_id: str, *, conn=None) -> dict | None:
    """La factura que ya existe para este turno (por su marca), o `None`."""
    if conn is None:
        with get_connection() as propia:
            return factura_del_nodo_de(turno_id, conn=propia)
    fila = conn.execute(
        "SELECT id FROM facturas WHERE observaciones = ? ORDER BY id LIMIT 1", (observacion_del_turno(turno_id),)
    ).fetchone()
    return None if fila is None else db_facturas.get_factura(fila[0], conn=conn)


def vincular_cobros_a_factura(turno_id: str, factura_id: int, *, conn=None) -> int:
    """Ata a `factura_id` los cobros del turno que todavía no tienen factura. Devuelve cuántos ató. Idempotente.

    En el nodo, justo después de emitir; en el central, al aplicar la factura (y al aplicar un cobro que llegó después)."""
    if conn is None:
        with get_connection() as propia:
            hechos = vincular_cobros_a_factura(turno_id, factura_id, conn=propia)
            propia.commit()
            return hechos
    sena, saldo = _referencias(turno_id)
    cursor = conn.execute(
        "UPDATE caja_movimientos SET factura_id = ? WHERE factura_id IS NULL AND referencia IN (?, ?)",
        (factura_id, sena, saldo),
    )
    return max(cursor.rowcount or 0, 0)


async def emitir_documento(pedido: dict, ctx) -> dict:
    """El emisor `documento` de la cola de ARCA: emite la factura del turno `pedido["origen_id"]`.

    Numera con `ctx.numerar` (el ticket que presta el central; **nunca local**), toma la fecha de
    `ctx.fecha_de_la_factura` (la del hecho si ARCA todavía la admite) y pide el CAE. Devuelve `{"factura_id", "cae"}`; sin
    CAE el motor deja el pedido `a_revisar`. Es idempotente (ver el docstring del módulo). Los errores de red y de rechazo
    del central los clasifica el motor: este emisor no los atrapa.

    La factura sale como la del central (`billing.invoice_appointment`): la misma letra, el mismo desglose de IVA, sin
    renglones."""
    turno_id = str(pedido["origen_id"])
    previa = factura_del_nodo_de(turno_id)
    if previa is not None:
        if not previa.get("cae"):
            ta, arca = await ctx.ticket()
            previa = await solicitar_cae(previa["id"], previa, ta, arca)
        return _resultado(previa)

    datos = pedido["datos"]
    cliente = datos.get("cliente") or {}
    precio = Decimal(datos["precio"])
    arca_cfg = get_arca_config()
    punto_venta = arca_cfg["punto_venta"] if arca_cfg else 1
    condicion_iva = cliente.get("condicion_iva") or None
    tipo = _tipo_comprobante(condicion_iva)
    subtotal, iva = _split_iva(precio)

    numero, ta, arca = await ctx.numerar(punto_venta, tipo)
    ambiente = ambiente_de(arca)
    fecha = ctx.fecha_de_la_factura(punto_venta, tipo, ambiente)
    factura_id = db_facturas.create_factura(
        tipo, punto_venta, numero, fecha.isoformat(),
        cliente.get("cuit") or "", cliente.get("nombre") or "",
        IVA_CODES.get(condicion_iva, IVA_CODES["Consumidor Final"]),
        [], float(subtotal), float(iva), float(precio),
        observaciones=observacion_del_turno(turno_id),
        # Del MISMO `arca` con el que se acaba de pedir el número, como en `billing.invoice_appointment`.
        ambiente=ambiente,
    )
    factura = await solicitar_cae(factura_id, db_facturas.get_factura(factura_id), ta, arca)
    # Los cobros que ya estaban en la caja del nodo, atados a esta factura (el central ata los suyos al aplicarla).
    vincular_cobros_a_factura(turno_id, factura_id)
    return _resultado(factura)


def _resultado(factura: dict) -> dict:
    resultado = {"factura_id": int(factura["id"]), "cae": factura.get("cae") or ""}
    if factura.get("cae_error"):
        resultado["cae_error"] = str(factura["cae_error"])
    return resultado


# ── En el nodo: la operación que sube la factura ──────────────────────────────────────────────────────────────────────


def payload_de_la_factura_del_turno(pedido: dict, conn) -> dict | None:
    """El payload de `gestio.factura_turno` para un `cola.pedido` que quedó **emitido**, o `None` si no corresponde (otro
    estado, otro tipo, o una factura que el nodo no tiene). Lo arma `offline.subir_pedido`, en la transacción de `conn`."""
    if pedido.get("estado") != db_cola.ESTADO_EMITIDO or pedido.get("origen_tipo") != db_cola.ORIGEN_DOCUMENTO:
        return None
    factura_id = (pedido.get("resultado") or {}).get("factura_id")
    if factura_id is None:
        return None
    factura = db_facturas.get_factura(int(factura_id), conn=conn)
    if factura is None:
        logger.error(
            "Nodo: el pedido %s de la cola salió con la factura %s y la factura no está",
            pedido.get("id_en_el_nodo"), factura_id,
        )
        return None
    return {
        "version": VERSION,
        "turno_id": str(pedido["origen_id"]),
        "factura": payload_factura(factura),
    }


# ── En el central: lo que sube del nodo ───────────────────────────────────────────────────────────────────────────────


def aplicar_factura_del_turno(conn, operacion) -> None:
    """Aplica `gestio.factura_turno`: escribe la factura del nodo con su número y CAE y la ata a los cobros del turno.

    Todo en la transacción del receptor. Idempotente: la factura por la clave ante ARCA, el vínculo porque si los cobros ya
    tienen factura no se tocan. Los errores son `ValueError` (revisión manual): el central ya tiene **otra** factura para el
    mismo turno (dos comprobantes por un solo servicio), o ya tiene ese comprobante con otro total u otro CAE
    (`FacturaEnConflicto`)."""
    if operacion.operation_type != offline.TIPO_FACTURA_DEL_TURNO:
        raise FacturaDelTurnoError(f"se esperaba {offline.TIPO_FACTURA_DEL_TURNO}, llegó {operacion.operation_type!r}")
    if operacion.schema_version != offline.SCHEMA_VERSION:
        raise FacturaDelTurnoError(f"schema {operacion.schema_version} de {offline.TIPO_FACTURA_DEL_TURNO} desconocido")
    datos = operacion.payload
    if datos.get("version") != VERSION:
        raise FacturaDelTurnoError(f"versión {datos.get('version')!r} de {offline.TIPO_FACTURA_DEL_TURNO} desconocida")
    if (datos.get("factura") or {}).get("version") != VERSION_FACTURA:
        raise FacturaDelTurnoError("versión de la factura del nodo desconocida")
    turno_id = datos.get("turno_id")
    if not isinstance(turno_id, str) or not turno_id.strip():
        raise FacturaDelTurnoError("la factura del nodo no dice de qué turno es")

    factura = dict(datos["factura"])
    marca = observacion_del_turno(turno_id)
    # La marca es la del turno: el turno nunca es provisorio (el nodo no los da), así que no hay nada que traducir.
    factura["observaciones"] = marca
    factura_id, _creada = aplicar_factura_del_nodo(factura, conn=conn)

    otra = conn.execute(
        "SELECT id FROM facturas WHERE observaciones = ? AND id <> ? ORDER BY id LIMIT 1", (marca, factura_id)
    ).fetchone()
    if otra is not None:
        raise FacturaDelTurnoError(
            f"el turno {turno_id} ya tiene la factura {otra[0]} en el central y el nodo {operacion.node_id} le emitió "
            f"la {factura_id}: dos comprobantes por el mismo turno. Revisar a mano"
        )
    vincular_cobros_a_factura(turno_id, factura_id, conn=conn)


def aplicar_movimiento_de_caja(conn, operacion) -> None:
    """`caja.movimiento` del nodo (libracore `caja_del_nodo`, ADR-080), más lo propio de GestioLibra: si el movimiento es
    un cobro de un turno (`extra["turno_id"]`) y la factura de ese turno **ya subió**, lo ata a ella.

    El orden normal es el inverso (los cobros se anotan al atender y la factura sale después), pero el nodo puede emitir
    antes de que el central haya aplicado los cobros: la operación de la factura los vincularía a ninguno."""
    from libracore.caja_del_nodo import aplicar_movimiento_del_nodo

    def atar(conn_, mov_id: int, datos: dict) -> None:
        turno_id = (datos.get("extra") or {}).get("turno_id")
        if not turno_id:
            return
        fila = conn_.execute(
            "SELECT id FROM facturas WHERE observaciones = ? ORDER BY id LIMIT 1", (observacion_del_turno(turno_id),)
        ).fetchone()
        if fila is not None:
            conn_.execute("UPDATE caja_movimientos SET factura_id = ? WHERE id = ? AND factura_id IS NULL",
                          (fila[0], mov_id))

    aplicar_movimiento_del_nodo(conn, operacion.node_id, operacion.payload, al_aplicar=atar)
