"""Atender y cobrar un turno en un nodo de LibraEdge sin conexión, y lo que el nodo le entrega a quien paga (ADR-036).

Un local sin internet también atiende (decisión del humano, 2026-10-21 y 2026-10-25): la agenda del nodo es de **sólo
consulta**, pero un turno ya dado se puede marcar **en curso**, **atendido** o **«no vino»**, y lo cobrado en el mostrador
cuenta. Este módulo es el caso de uso del nodo; las partes genéricas son de los motores:

| Qué | De quién |
|---|---|
| la atención (la fila propia, `turno.atendido`, las reglas de estado) | `libragenda.atencion_en_nodo` |
| los cobros (seña y saldo) | `libracore.db.caja`, con `offline.GANCHOS_DE_CAJA` (`caja.movimiento`) |
| la factura | `libracore.cola_arca` (`documento`), que sale al volver la conexión (`services/factura_del_nodo`) |
| el comprobante que se lleva el cliente en el momento | `libracore.ticket_generator.generar_ticket_venta`, no fiscal |

## Todo en una transacción

Atender, cobrar y dejar el pedido de la factura en la cola son **una sola transacción** de la sesión de LibraGenda: o queda
el turno atendido con su plata y su factura en cola, o no queda nada. Las operaciones que suben (`caja.movimiento`,
`cola.pedido`, `turno.atendido`) se encolan en esa misma transacción, así que el outbox nunca tiene un cobro sin su
atención ni al revés. Si el turno no se puede atender (ya estaba cancelado, ya estaba atendido) la transacción entera se
deshace, incluidos los cobros.

## Qué se le da al cliente en el momento

Una **factura no se numera sin ARCA** (libracore ADR-074): el cobro sin red sale con un **comprobante no fiscal** con la
leyenda «La factura se emite al volver la conexión» (decisión del humano, 2026-10-25), y la factura sale sola cuando
vuelve (`cola_arca`). Con conexión, la cola se intenta en el acto y el cliente se lleva la factura de siempre.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

from libracore import fechas
from libracore.cola_arca import (
    EmisionEnCurso,
    emitir_pedido,
    encolar,
    payload_de_pedido,
)
from libracore.db import caja as db_caja
from libracore.db import cola_arca as db_cola
from libracore.nodo_offline import NodoSinArca, SinConexion
from libragenda import AppointmentStatus
from libragenda import atencion_en_nodo as atencion
from sqlalchemy.orm import Session, sessionmaker

from app import offline
from app.services import factura_del_nodo

logger = logging.getLogger(__name__)

PARTE_SENA = factura_del_nodo.SUFIJO_SENA
PARTE_SALDO = factura_del_nodo.SUFIJO_SALDO

#: La leyenda del comprobante que se lleva el cliente cuando la factura queda para después. La imprime el motor
#: (`generar_ticket_venta(..., factura_pendiente=True)`); acá queda el texto de la API.
LEYENDA_NO_FISCAL = "La factura se emite al volver la conexión."
MENSAJE_FACTURA_EN_COLA = "Sin conexión: la factura queda en la cola y se emite sola cuando vuelva la conexión."


@dataclass(frozen=True)
class CobroDelTurno:
    """Lo que se cobra al completar un turno: el precio del servicio, la seña ya cobrada y el saldo.

    Es la misma cuenta que hace `billing.invoice_appointment`: el saldo es el precio menos la seña **pagada**. `cliente` es
    el dict del cliente (`id`, `name`, `cuit`, `condicion_iva`) tal como está ahora."""

    precio: Decimal
    sena: Decimal
    sena_medio_pago: str | None
    saldo: Decimal
    saldo_medio_pago: str | None
    cliente: dict
    servicio: str

    def para_la_atencion(self, referencia: str) -> dict:
        """El `extra` de `turno.atendido`: lo que se cobró, **para quien revisa** (libragenda lo guarda y lo devuelve, no
        lo mira). La plata viaja por `caja.movimiento`; acá es información."""
        return {
            "cobro": {
                "referencia": referencia,
                "precio": str(self.precio),
                "sena": str(self.sena),
                "sena_medio_pago": self.sena_medio_pago or "",
                "saldo": str(self.saldo),
                "saldo_medio_pago": self.saldo_medio_pago or "",
                "cliente": self.cliente.get("name") or "",
                "factura": "en_cola",
            }
        }


def _anotar_cobros(conn, turno_id: str, cobro: CobroDelTurno) -> None:
    """La seña y el saldo, como dos movimientos de caja **sin factura** (se atan cuando salga), con los ganchos del nodo:
    cada uno encola su `caja.movimiento` en la transacción de `conn`."""
    hoy = fechas.hoy().isoformat()
    partes = (
        (PARTE_SENA, "Seña del turno", cobro.sena, cobro.sena_medio_pago),
        (PARTE_SALDO, "Saldo del turno", cobro.saldo, cobro.saldo_medio_pago),
    )
    for parte, concepto, monto, medio in partes:
        if monto <= 0:
            continue
        db_caja.create_caja_movimiento(
            hoy, "ingreso", concepto, monto, referencia=factura_del_nodo.referencia_de_cobro(turno_id, parte),
            medio_pago=medio or "", conn=conn, ganchos=offline.GANCHOS_DE_CAJA,
            extra={"turno_id": turno_id, "parte": parte},
        )


def _dejar_en_la_cola(conn, turno_id: str, cobro: CobroDelTurno) -> dict:
    """El pedido de la factura del turno, en la transacción de `conn`, más su `cola.pedido` para el central.

    `encolar(conn=)` no avisa a `al_cambiar` (no está confirmado todavía): el aviso lo hace esta función en la misma
    transacción, con el pedido que devuelve."""
    datos = factura_del_nodo.datos_del_pedido(
        turno_id=turno_id, precio=cobro.precio, cliente=cobro.cliente, servicio=cobro.servicio, sena=cobro.sena,
        sena_medio_pago=cobro.sena_medio_pago, saldo=cobro.saldo, saldo_medio_pago=cobro.saldo_medio_pago,
    )
    pedido, _creado = encolar(
        offline.cola(), "documento", turno_id, datos=datos, fecha_ref=fechas.hoy().isoformat(), concepto=1, conn=conn,
    )
    offline.encolar_operacion(conn, offline.TIPO_COLA_PEDIDO, "cola_arca", pedido["id"], payload_de_pedido(pedido))
    return pedido


def atender(
    sessions: sessionmaker[Session], turno_id: str, estado: AppointmentStatus, *, actor: str | None,
    cobro: CobroDelTurno | None = None,
) -> dict | None:
    """Atiende el turno en el nodo (en curso, completado o «no vino») y, si hay `cobro`, lo anota y deja la factura en la
    cola, **todo en una transacción**. Devuelve el pedido de la cola (o `None` si no hubo cobro).

    Levanta lo de `atencion.atender_en_nodo` (`AppointmentNotFound`, `InvalidTransition`, `EstadoNoAtendible`,
    `NoEsUnNodo`) y, si algo falla, no queda nada: ni la atención, ni los movimientos de caja, ni el pedido, ni lo que se
    haya encolado para subir."""
    with sessions.begin() as sesion:
        pedido = None
        extra = None
        if cobro is not None:
            conn = offline.conexion_de_la_sesion(sesion)
            _anotar_cobros(conn, turno_id, cobro)
            pedido = _dejar_en_la_cola(conn, turno_id, cobro)
            extra = cobro.para_la_atencion(turno_id)
        atencion.atender_en_nodo(sesion, turno_id, estado, actor=actor, extra=extra)
    return pedido


def emitir_si_hay_conexion(pedido: dict, *, usuario_id: int | None = None) -> dict:
    """Con conexión, intenta emitir el pedido en el acto; sin ella (o si se corta) lo deja `esperando` para cuando vuelva.
    Devuelve el pedido como quedó. Corre en el hilo del request, con un loop propio (`asyncio.run`), como la factura del
    central (`routers/appointments.complete_appointment`)."""
    cola = offline.cola()
    if cola.conexion.sin_conexion():
        return pedido
    try:
        return asyncio.run(emitir_pedido(cola, pedido["id"], usuario_id=usuario_id))
    except (SinConexion, NodoSinArca, EmisionEnCurso):
        return db_cola.get_pedido(pedido["id"])


def mensaje_del_pedido(pedido: dict) -> str:
    """Qué decirle a quien cobró cuando la factura no salió en el acto."""
    estado = pedido["estado"]
    if estado == db_cola.ESTADO_ESPERANDO:
        return pedido.get("ultimo_error") or MENSAJE_FACTURA_EN_COLA
    if estado in db_cola.ESTADOS_DE_REVISION:
        return pedido.get("ultimo_error") or "La factura necesita que alguien la revise."
    return f"La factura está {estado}."


# ── El comprobante no fiscal ───────────────────────────────────────────────────────────────────────────────────────────


class SinComprobanteNoFiscal(LookupError):
    """El turno no tiene pedido de factura en la cola de este nodo (no se cobró en el nodo, o no se cobró)."""


class YaFacturado(ValueError):
    """La factura del turno ya salió: el comprobante que corresponde es la factura, no el no fiscal."""


def comprobante_no_fiscal(turno_id: str) -> bytes:
    """El PDF del comprobante no fiscal del turno, armado con la foto del pedido de la cola (lo que se cobró, no lo que
    vale hoy). Lleva la leyenda «NO VÁLIDO COMO FACTURA — La factura se emite al volver la conexión» (el motor, con
    `factura_pendiente`). Se puede reimprimir las veces que haga falta: la misma foto da el mismo archivo.

    `SinComprobanteNoFiscal` si el turno no tiene pedido en este nodo, `YaFacturado` si la factura ya salió."""
    from libracore.ticket_generator import generar_ticket_venta

    pedido = _pedido_del_turno(turno_id)
    if pedido is None:
        raise SinComprobanteNoFiscal(f"El turno {turno_id} no tiene una factura en la cola de este equipo.")
    if pedido["estado"] == db_cola.ESTADO_EMITIDO:
        raise YaFacturado(f"La factura del turno {turno_id} ya se emitió: el comprobante es la factura.")
    datos = pedido["datos"]
    cliente = datos.get("cliente") or {}
    pagos = []
    if Decimal(datos["sena"]) > 0:
        pagos.append({"medio": datos["sena_medio_pago"], "monto": float(Decimal(datos["sena"]))})
    if Decimal(datos["saldo"]) > 0:
        pagos.append({"medio": datos["saldo_medio_pago"], "monto": float(Decimal(datos["saldo"]))})
    precio = float(Decimal(datos["precio"]))
    return generar_ticket_venta({
        # El número es el del turno (corto), no uno fiscal: el comprobante no tiene numeración propia.
        "id": turno_id[:8],
        "fecha": pedido.get("created_at") or "",
        "cliente_nombre": cliente.get("nombre") or "Consumidor final",
        "cliente_cuit": cliente.get("cuit") or "",
        "items": [{"nombre": datos.get("servicio") or "Servicio", "cantidad": 1, "precio_unitario": precio}],
        "total": precio,
        "pagos": pagos,
        "factura_pendiente": True,
    })


def _pedido_del_turno(turno_id: str) -> dict | None:
    cola = offline.cola()
    return db_cola.get_por_origen(cola.producto, cola.instancia(), db_cola.ORIGEN_DOCUMENTO, turno_id)
