"""La factura de un turno y su nota de crédito (ADR-039).

La nota de crédito **no es de este producto**: sale del motor y es la misma para toda la familia (ADR-014 de
`libracore`). Este módulo no repite ninguna guarda ni arma ningún comprobante; sólo aporta lo que depende del modelo de
acá:

| Pieza | Qué hace |
|---|---|
| `factura_del_turno(turno_id)` | la factura que se emitió al completar el turno (o `None`) |
| `detalle(factura)` | la factura con sus notas de crédito y lo que todavía se puede acreditar |
| `dejar_rastro(...)` | el renglón de la nota en el log de actividad, con **quién** la emitió y **por qué** |

## Cómo se encuentra la factura de un turno

`invoice_appointment` no marca la factura con el turno: la ata a los **movimientos de caja** de la seña y del saldo
(`referencia = <turno>-sena` / `<turno>-saldo`, con `factura_id`). Es la única marca que tienen las facturas ya emitidas,
así que se busca por ella. En un nodo (ADR-036) la factura nace con `observaciones = "Turno <id>"`: es el segundo camino.
Una factura que no se emitió (turno sin precio, plan sin facturación) no tiene ninguna de las dos marcas: `None`.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from libraauth.auditoria import CREAR, ActividadLog, fila_de_auditoria
from libracore import notas_de_credito as motor
from libracore.db import facturas as db_facturas
from libracore.db.core import get_connection
from sqlalchemy.orm import Session, sessionmaker

from app.services.factura_del_nodo import SUFIJO_SALDO, SUFIJO_SENA, factura_del_nodo_de, referencia_de_cobro

logger = logging.getLogger(__name__)

#: El nombre con el que la nota de crédito aparece en el log de actividad. No es un modelo del ORM (no está en
#: `AUDITABLES`): se escribe a mano al emitirla, ver `dejar_rastro`.
ENTIDAD_DEL_LOG = "nota_de_credito"


def factura_del_turno(turno_id: str) -> dict | None:
    """La factura que se emitió al completar el turno, o `None` si no hay."""
    referencias = (referencia_de_cobro(turno_id, SUFIJO_SENA), referencia_de_cobro(turno_id, SUFIJO_SALDO))
    with get_connection() as conn:
        fila = conn.execute(
            "SELECT factura_id FROM caja_movimientos WHERE referencia IN (?, ?) AND factura_id IS NOT NULL "
            "ORDER BY id LIMIT 1",
            referencias,
        ).fetchone()
        if fila is not None:
            return db_facturas.get_factura(int(fila[0]), conn=conn)
        return factura_del_nodo_de(turno_id, conn=conn)


def _tiene_cae(comprobante: dict) -> bool:
    return motor._es_cae(comprobante.get("cae"))


def _resumen(comprobante: dict) -> dict:
    """Lo que la pantalla necesita de un comprobante: no se manda la fila entera (rutas de archivos, ids internos)."""
    return {
        "id": comprobante["id"], "tipo": comprobante["tipo"], "punto_venta": comprobante["punto_venta"],
        "numero": comprobante["numero"], "fecha": comprobante["fecha"], "total": comprobante["total"],
        "cliente_razon": comprobante.get("cliente_razon") or "", "cae": comprobante.get("cae") or "",
        "cae_vto": comprobante.get("cae_vto") or "", "observaciones": comprobante.get("observaciones") or "",
    }


def notas_de(factura: dict) -> list[dict]:
    """Las notas de crédito que cuelgan de la factura (del mismo emisor y ambiente), las más viejas primero."""
    return db_facturas.get_nc_de_factura(
        factura["tipo"], factura["punto_venta"], factura["numero"],
        emisor_id=factura.get("emisor_id"), ambiente=factura.get("ambiente"))


def detalle(factura: dict) -> dict:
    """La factura con sus notas y lo que queda por acreditar. `puede_acreditar` es una pista para la pantalla: la
    decisión es del motor, que vuelve a mirar todo al emitir (y contesta 409 si no corresponde)."""
    notas = notas_de(factura)
    previas = [{"cae": n.get("cae"), "total": n["total"]} for n in notas]
    acreditado = motor.acreditado(factura, previas)
    saldo = motor.saldo_acreditable(factura, previas)
    # Una nota sin CAE (ARCA la rechazó) frena la siguiente hasta que se autorice o se borre (`nota_sin_cae`).
    hay_nota_sin_cae = any(not _tiene_cae(n) for n in notas)
    puede = _tiene_cae(factura) and not factura.get("anulada_en") and saldo > Decimal("0") and not hay_nota_sin_cae
    return {
        "factura": _resumen(factura),
        "notas_credito": [_resumen(n) for n in notas],
        "acreditado": float(acreditado),
        "saldo_acreditable": float(saldo),
        "puede_acreditar": puede,
    }


def dejar_rastro(
    sessions: sessionmaker[Session], *, usuario: str, nota: dict, factura: dict, turno_id: str, motivo: str,
) -> None:
    """Deja en el log de actividad quién emitió la nota de crédito, sobre qué factura y por qué.

    La nota ya guarda en `facturas.usuario_id` quién la emitió, pero **no el motivo**: el motor todavía no lo recibe en el
    endpoint (ver ADR-039). El log es el único lugar donde queda, y lo ve el administrador en Logs.

    🔑 **No puede tumbar la request**: la nota ya está autorizada por ARCA y eso no se deshace. Si el log falla, se
    registra el error y se sigue. El formato de la fila es el de `libraauth` (`fila_de_auditoria`), no una copia.
    """
    try:
        etiqueta = f"{motor.etiqueta(nota)} sobre {motor.etiqueta(factura)} (turno {turno_id}) — {motivo}"
        fila = fila_de_auditoria(
            entidad=ENTIDAD_DEL_LOG, accion=CREAR, entidad_id=nota["id"], etiqueta=etiqueta, usuario=usuario)
        with sessions() as sesion:
            sesion.add(ActividadLog(**fila))
            sesion.commit()
    except Exception:
        logger.exception(
            "La nota de crédito %s se emitió pero no quedó en el log de actividad (motivo: %s).", nota.get("id"), motivo)
