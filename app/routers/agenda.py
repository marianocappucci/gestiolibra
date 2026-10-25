from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from libragenda import atencion_en_nodo as atencion
from libragenda.sqlalchemy_repository import AppliedAttendanceRow
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import mensajes_agenda as mensajes
from .. import offline
from ..dependencies import get_appointment_service, get_sessions
from ..services.appointments import AppointmentService
from ._instantes import InstanteUTC

router = APIRouter(tags=["agenda"])


class AppointmentOut(BaseModel):
    id: str
    resource_id: str
    service_id: str
    client_id: str
    starts_at: InstanteUTC
    ends_at: InstanteUTC
    status: str
    # Lo que la agenda cuenta de un turno atendido en un nodo sin conexión (ADR-036, libra-ui ADR-095). Sin nodo, y sin
    # turnos atendidos así, son siempre `False` / `None`: la respuesta es la de siempre con tres campos de más.
    atendido_sin_conexion: bool = False
    a_revisar: bool = False
    motivo: str | None = None


def _marcas_del_nodo(sessions: sessionmaker[Session], ids: list[str]) -> tuple[dict, set[str], dict]:
    """`(propias, subidas, a_revisar)` de los turnos `ids`: la última atención hecha **en este nodo** de cada uno, cuáles de
    esas atenciones ya subieron al central, y los turnos que están en la lista «a revisar» (con su motivo)."""
    if not ids:
        return {}, set(), {}
    with sessions() as sesion:
        propias = atencion.atenciones_del_nodo(sesion, ids) if offline.nodo() is not None else {}
        subidas = set()
        if propias:
            subidas = set(sesion.scalars(
                select(AppliedAttendanceRow.atencion_id).where(
                    AppliedAttendanceRow.atencion_id.in_([a.id for a in propias.values()]))
            ))
        a_revisar = {}
        conjunto = set(ids)
        for fila in atencion.turnos_a_revisar(sesion):
            if fila.appointment_id in conjunto:
                a_revisar[fila.appointment_id] = fila.motivo
    return propias, subidas, a_revisar


@router.get("/resources/{resource_id}/agenda", response_model=list[AppointmentOut])
def get_agenda(
    resource_id: str,
    date_from: date,
    date_to: date,
    service: AppointmentService = Depends(get_appointment_service),
    sessions: sessionmaker[Session] = Depends(get_sessions),
):
    """La agenda del recurso entre dos días.

    En un nodo (ADR-036) un turno que se atendió **en esta PC** y todavía no subió se muestra con el estado de esa
    atención (`atendido_sin_conexion`): la fila del espejo no se escribe, y sin esto el mostrador vería «confirmado» un
    turno que ya cobró. Cuando la atención sube, el central la aplica y el estado baja por el espejo. Un turno que subió y
    en la web cambió está «a revisar» (con su motivo) en las dos puntas."""
    if date_to < date_from:
        raise HTTPException(422, mensajes.RANGO_INVERTIDO)
    turnos = service.agenda(resource_id, date_from, date_to)
    propias, subidas, a_revisar = _marcas_del_nodo(sessions, [t.id for t in turnos])
    salida = []
    for item in turnos:
        propia = propias.get(item.id)
        sin_subir = propia is not None and propia.id not in subidas
        salida.append(AppointmentOut(
            id=item.id, resource_id=item.resource_id, service_id=item.service_id,
            client_id=item.client_id, starts_at=item.starts_at, ends_at=item.ends_at,
            status=propia.estado.value if sin_subir else item.status.value,
            atendido_sin_conexion=sin_subir,
            a_revisar=item.id in a_revisar, motivo=a_revisar.get(item.id),
        ))
    return salida
