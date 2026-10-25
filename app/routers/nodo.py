"""La lista «Turnos a revisar»: las atenciones hechas sin conexión que en la web chocaron con un cambio (ADR-036).

Es el panel `TurnosARevisar` del kit (libra-ui ADR-095), servido por las dos puntas:

| Ruta | Dónde | Qué hace |
|---|---|---|
| `GET  /api/nodo/turnos-a-revisar` | central y nodo | las atenciones que esperan, de la más vieja a la más nueva (`turnos_a_revisar`) |
| `POST /api/nodo/turnos-a-revisar/revisar` | **sólo el central** | `{"atenciones": [id, ...]}`: las saca de la lista (`marcar_revisada`) |

La lista la arma el central al aplicar `turno.atendido` (`agenda_applied_attendances`) y **baja al nodo por el espejo**, de
sólo lectura: el nodo la ve y no la resuelve (409 `solo_en_el_central`). «Ya lo revisé» **no cambia el turno ni la
atención**: acomodar el turno —moverlo, cancelarlo, ver si se cobró dos veces— se hace en la agenda, a mano.

Las filas salen con los nombres de `AtencionAplicada` de LibraGenda, que es lo que espera el kit (`AtencionARevisar`), más
quién y qué era el turno (`cliente`, `servicio`, `starts_at`): la tarjeta dice «Ana Gómez · Corte» y no un uuid.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from libragenda import atencion_en_nodo as atencion
from libragenda.sqlalchemy_repository import AppointmentRow, ClientRow, ServiceRow
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import offline
from ..auth import get_current_user
from ..dependencies import get_sessions

router = APIRouter(prefix="/api/nodo", tags=["nodo"])


class Revisadas(BaseModel):
    atenciones: list[str] = Field(min_length=1, max_length=200)


def _fila(a: atencion.AtencionAplicada, turno: dict | None = None) -> dict:
    return {
        **(turno or {"cliente": None, "servicio": None, "starts_at": None}),
        "atencion_id": a.atencion_id,
        "appointment_id": a.appointment_id,
        "estado": a.estado.value,
        "at": a.at.isoformat(),
        "actor": a.actor,
        "motivo": a.motivo,
        "estado_despues": a.estado_despues.value if a.estado_despues else None,
        "resultado": a.resultado,
        "revisada_at": a.revisada_at.isoformat() if a.revisada_at else None,
    }


def _turnos(sesion: Session, ids: set[str]) -> dict[str, dict]:
    """`{turno_id: {"cliente", "servicio", "starts_at"}}` de los que todavía existen (uno borrado en la web no figura)."""
    salida = {}
    for turno in sesion.scalars(select(AppointmentRow).where(AppointmentRow.id.in_(ids))) if ids else []:
        cliente = sesion.get(ClientRow, turno.client_id)
        servicio = sesion.get(ServiceRow, turno.service_id)
        salida[turno.id] = {
            "cliente": cliente.name if cliente else None, "servicio": servicio.name if servicio else None,
            "starts_at": turno.starts_at.isoformat(),
        }
    return salida


@router.get("/turnos-a-revisar")
def turnos_a_revisar(sessions: sessionmaker[Session] = Depends(get_sessions)):
    """Las atenciones que esperan a que alguien acomode el turno. Vacía si no hay ninguna (y siempre en una instalación que
    nunca tuvo un nodo)."""
    with sessions() as sesion:
        filas = atencion.turnos_a_revisar(sesion)
        turnos = _turnos(sesion, {a.appointment_id for a in filas})
        return [_fila(a, turnos.get(a.appointment_id)) for a in filas]


@router.post("/turnos-a-revisar/revisar", dependencies=[Depends(offline.solo_en_el_central)])
def marcar_revisadas(
    datos: Revisadas, sessions: sessionmaker[Session] = Depends(get_sessions), user: dict = Depends(get_current_user),
):
    """Saca de la lista las atenciones indicadas, con quién las revisó y cuándo. Marcar dos veces no pisa la primera."""
    quien = user.get("name") or user.get("username")
    try:
        with sessions.begin() as sesion:
            return [_fila(atencion.marcar_revisada(sesion, id_, por=quien)) for id_ in datos.atenciones]
    except atencion.AtencionNotFound as exc:
        raise HTTPException(404, f"No hay una atención {exc}.")
