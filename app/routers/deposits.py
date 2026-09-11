from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from libragenda import (
    Deposit,
    DepositManager,
    DepositNotFound,
    DepositStatus,
    InvalidDepositTransition,
)
from libragenda.repositories import DepositRepository
from pydantic import BaseModel

from ..dependencies import get_appointment_service, get_deposit_manager, get_deposit_repository
from ..services.appointments import AppointmentService
from ._instantes import InstanteUTC, a_utc

# Requesting/reading a deposit is part of the booking flow -- same access
# as appointments (admin or staff). Confirming money actually moved
# (paid/failed/refunded) is a separate, admin-only router below.
request_router = APIRouter(prefix="/appointments/{appointment_id}/deposit", tags=["deposits"])
admin_router = APIRouter(prefix="/deposits", tags=["deposits"])


class DepositRequest(BaseModel):
    amount: Decimal


class MarkPaidRequest(BaseModel):
    medio_pago: str | None = None


class DepositOut(BaseModel):
    id: str
    appointment_id: str
    amount: Decimal
    status: str
    medio_pago: str | None = None


class DepositListItem(DepositOut):
    """Una seña con el turno al que pertenece pegado encima.

    🔴 **Por qué el turno viaja adentro.** Una seña sola es un monto y un
    estado: `1000.00, pending`. Para cobrarla hay que saber **de quién es y de
    cuándo** — es lo que se le pregunta al cliente que llama o que está en el
    mostrador. Sin esto la pantalla tendría que pedir cada turno por separado,
    y no hay endpoint para eso: la agenda es por recurso y por rango de días.

    Los campos del turno son opcionales sólo por prudencia: la FK de
    `deposits.appointment_id` hace que hoy no pueda faltar, pero una seña es
    plata y no se esconde de la lista porque su turno no aparezca.
    """

    appointment_starts_at: InstanteUTC | None = None
    appointment_status: str | None = None
    client_id: str | None = None
    service_id: str | None = None
    resource_id: str | None = None


def _to_out(deposit: Deposit) -> DepositOut:
    return DepositOut(
        id=deposit.id, appointment_id=deposit.appointment_id,
        amount=deposit.amount, status=deposit.status.value, medio_pago=deposit.medio_pago,
    )


@request_router.post("", status_code=201, response_model=DepositOut)
def request_deposit(
    appointment_id: str, data: DepositRequest,
    manager: DepositManager = Depends(get_deposit_manager),
):
    try:
        return _to_out(manager.request(str(uuid4()), appointment_id, data.amount))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@request_router.get("", response_model=DepositOut)
def get_deposit(appointment_id: str, deposits: DepositRepository = Depends(get_deposit_repository)):
    deposit = deposits.get_by_appointment(appointment_id)
    if deposit is None:
        raise HTTPException(404, "deposit not found")
    return _to_out(deposit)


#: Dónde van las señas cuyo turno no aparece: al final, no mezcladas.
_SIN_TURNO = datetime.max.replace(tzinfo=UTC)


@admin_router.get("", response_model=list[DepositListItem])
def list_deposits(
    status: DepositStatus | None = None,
    deposits: DepositRepository = Depends(get_deposit_repository),
    service: AppointmentService = Depends(get_appointment_service),
):
    """Las señas, todas o las de un estado.

    Hasta el 2026-09-11 la única forma de ver una seña era conocer su turno
    (`GET /appointments/{id}/deposit`): el Dashboard contaba las pendientes
    pero no había dónde verlas. Admin-only y gateado por el módulo `senas`,
    como el resto de este router: es la lista de plata a cobrar y a devolver.

    El repositorio del motor sólo sabe listar **por estado**, así que "todas"
    son las cuatro listas juntas. Y los turnos se leen **una sola vez**, no uno
    por seña: con el `get` por fila, la pantalla haría tantas consultas como
    señas haya.

    Ordenadas por el inicio del turno, el más próximo primero: la seña que hay
    que cobrar antes es la del turno que viene antes.
    """
    estados = [status] if status is not None else list(DepositStatus)
    todas = [d for estado in estados for d in deposits.list_by_status(estado)]
    if not todas:
        return []
    turnos = {t.id: t for t in service.appointments.list()}

    items: list[DepositListItem] = []
    for deposit in todas:
        turno = turnos.get(deposit.appointment_id)
        items.append(DepositListItem(
            **_to_out(deposit).model_dump(),
            appointment_starts_at=turno.starts_at if turno else None,
            appointment_status=turno.status.value if turno else None,
            client_id=turno.client_id if turno else None,
            service_id=turno.service_id if turno else None,
            resource_id=turno.resource_id if turno else None,
        ))
    # `a_utc` antes de comparar: según el motor, el mismo instante vuelve con
    # `tzinfo` (PostgreSQL) o sin él (SQLite), y Python no compara uno con otro.
    items.sort(key=lambda d: (
        a_utc(d.appointment_starts_at) if d.appointment_starts_at else _SIN_TURNO, d.id,
    ))
    return items


@admin_router.post("/{deposit_id}/mark-paid", response_model=DepositOut)
def mark_paid(
    deposit_id: str, data: MarkPaidRequest = MarkPaidRequest(),
    manager: DepositManager = Depends(get_deposit_manager),
):
    try:
        return _to_out(manager.mark_paid(deposit_id, medio_pago=data.medio_pago))
    except DepositNotFound:
        raise HTTPException(404, "deposit not found")
    except InvalidDepositTransition as exc:
        raise HTTPException(409, str(exc))


@admin_router.post("/{deposit_id}/mark-failed", response_model=DepositOut)
def mark_failed(deposit_id: str, manager: DepositManager = Depends(get_deposit_manager)):
    try:
        return _to_out(manager.mark_failed(deposit_id))
    except DepositNotFound:
        raise HTTPException(404, "deposit not found")
    except InvalidDepositTransition as exc:
        raise HTTPException(409, str(exc))


@admin_router.post("/{deposit_id}/refund", response_model=DepositOut)
def refund(deposit_id: str, manager: DepositManager = Depends(get_deposit_manager)):
    try:
        return _to_out(manager.request_refund(deposit_id))
    except DepositNotFound:
        raise HTTPException(404, "deposit not found")
    except InvalidDepositTransition as exc:
        raise HTTPException(409, str(exc))
