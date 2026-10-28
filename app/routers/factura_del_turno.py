"""La factura de un turno y su nota de crédito (ADR-039).

| Ruta | Quién | Qué hace |
|---|---|---|
| `GET /appointments/{id}/factura` | admin y staff | la factura del turno con sus notas de crédito y lo que falta acreditar |
| `GET /appointments/{id}/nota-credito/destino?importe=` | admin | qué hay que preguntar sobre la plata (el del motor, ADR-065) |
| `POST /appointments/{id}/nota-credito` | admin | emite la nota de crédito, total o parcial, con su **motivo** |

El PDF de la factura y de la nota, y su envío por mail, son el `build_comprobantes_pdf_router` del motor
(`/api/facturas/{id}/pdf`), montado en `app/main.py`.

## La nota la emite el motor, no esta ruta

`POST` **no repite** ninguna regla: llama a la misma función que atiende `POST /api/facturas/{id}/nota-credito` del motor
(`libracore.facturas_router.build_nota_de_credito_router`), con sus guardas (una factura no se acredita dos veces, el
tope acumulado de las parciales, un pedido a la vez), su comprobante asociado, su CAE y el destino de la plata
(`devolver` / `a_favor`, ADR-065). Lo único que agrega esta ruta es lo del producto:

- llegar desde el **turno** y no desde el id de la factura (el turno es lo que la pantalla conoce);
- el **motivo**, obligatorio, que queda en el log de actividad junto con quién la emitió. El motor todavía no lo recibe
  en ese endpoint (ADR-039): cuando lo reciba, esta ruta se va y se monta la del motor tal cual.

En un nodo de LibraEdge (ADR-036) la nota es **del central**: 409 `solo_en_el_central`, igual que cualquier otra escritura
que el nodo no hace. Emitirla necesita el certificado de ARCA y el nodo no lo tiene.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from libracore import reintegro_de_nota
from libracore.facturas_router import NotaCreditoIn, build_nota_de_credito_router
from pydantic import field_validator
from sqlalchemy.orm import Session, sessionmaker

from ..auth import get_current_user, require_admin
from ..dependencies import get_sessions
from ..services import factura_del_turno as servicio

router = APIRouter(tags=["facturas"])

MOTIVO_MINIMO = 5
MOTIVO_MAXIMO = 200


class NotaDelTurnoIn(NotaCreditoIn):
    """El cuerpo del `POST`: el del motor (`importe`, `destino`, `medio_pago`) más el motivo.

    Hereda `extra="forbid"` y el rechazo de booleanos del motor: un campo de más es un 422, no se ignora."""

    motivo: str

    @field_validator("motivo")
    @classmethod
    def _motivo_con_sentido(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if len(valor) < MOTIVO_MINIMO:
            raise ValueError(f"Escribí el motivo de la nota de crédito (al menos {MOTIVO_MINIMO} letras).")
        if len(valor) > MOTIVO_MAXIMO:
            raise ValueError(f"El motivo no puede pasar de {MOTIVO_MAXIMO} caracteres.")
        return valor


def _emitir_del_motor():
    """La función que atiende `POST …/nota-credito` en el motor. Se arma una vez, al importar.

    El motor la define dentro de su `APIRouter` (es una ruta, no una función suelta), así que se busca por su ruta. Si el
    motor la mueve o la renombra, esto levanta al importar y `tests/test_nota_de_credito.py` se pone rojo: no queda una nota
    de crédito que no se puede emitir y nadie se enteró."""
    del_motor = build_nota_de_credito_router(usuario_actual=get_current_user, solo_admin=require_admin)
    for ruta in del_motor.routes:
        if getattr(ruta, "path", "").endswith("/{factura_id}/nota-credito") and "POST" in getattr(ruta, "methods", ()):
            return ruta.endpoint
    raise RuntimeError("libracore ya no publica POST /{factura_id}/nota-credito: revisar el pin y el ADR-039.")


_emitir_nota = _emitir_del_motor()


def _factura_o_404(turno_id: str) -> dict:
    factura = servicio.factura_del_turno(turno_id)
    if factura is None:
        raise HTTPException(404, "Este turno no tiene una factura.")
    return factura


@router.get("/appointments/{appointment_id}/factura")
def factura_del_turno(appointment_id: str):
    """La factura del turno con sus notas de crédito. 404 si el turno no se facturó."""
    return servicio.detalle(_factura_o_404(appointment_id))


@router.get("/appointments/{appointment_id}/nota-credito/destino", dependencies=[Depends(require_admin)])
def destino_de_la_plata(appointment_id: str, importe: Decimal | None = Query(None, gt=0)):
    """Lo que hay que preguntar antes de emitir la nota: si hay plata cobrada de más, cuánta y con qué medios. Es la
    respuesta del motor tal cual (`GET /api/facturas/{id}/nota-credito/destino`); no escribe nada."""
    factura = _factura_o_404(appointment_id)
    return reintegro_de_nota.ofrecer(factura, importe if importe is not None else factura["total"])


@router.post("/appointments/{appointment_id}/nota-credito", dependencies=[Depends(require_admin)])
def emitir_nota_de_credito(
    appointment_id: str, datos: NotaDelTurnoIn,
    sessions: sessionmaker[Session] = Depends(get_sessions), usuario: dict = Depends(get_current_user),
):
    """Emite la nota de crédito de la factura del turno: total (sin `importe`) o parcial (`importe`, con IVA).

    `def` y no `async def`, como la factura: el motor corre ARCA con `asyncio.run` en el hilo de la request."""
    factura = _factura_o_404(appointment_id)
    # 🔑 Sin elegir qué pasa con la plata, el motor no mueve nada (su default, para los productos que no mandan el campo). Acá
    # no hay nada que mantener compatible: si hay plata cobrada de más, la caja no se puede quedar sin explicar, y la
    # decisión de devolverla es de quien emite (ADR-039). Se dice antes de pedirle nada a ARCA.
    if datos.destino is None:
        oferta = reintegro_de_nota.ofrecer(factura, datos.importe if datos.importe is not None else factura["total"])
        if oferta["aplica"]:
            raise HTTPException(
                422, "La factura ya está cobrada: elegí qué pasa con la plata (devolverla, con el medio de pago) antes "
                     "de emitir la nota.")
    del_motor = NotaCreditoIn(importe=datos.importe, destino=datos.destino, medio_pago=datos.medio_pago)
    nota = _emitir_nota(factura["id"], del_motor, usuario)
    servicio.dejar_rastro(
        sessions, usuario=usuario.get("username") or usuario.get("name") or "", nota=nota, factura=factura,
        turno_id=appointment_id, motivo=datos.motivo)
    return nota
