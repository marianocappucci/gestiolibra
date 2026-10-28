from collections.abc import Callable

from fastapi import APIRouter, Depends
from libragenda import ReminderDispatcher
from pydantic import BaseModel

from ..dependencies import get_reintentar_avisos, get_reminder_dispatcher
from ..notifications import despachar_recordatorios
from ._instantes import InstanteUTC

router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderOut(BaseModel):
    appointment_id: str
    policy_id: str
    resource_id: str
    service_id: str
    client_id: str
    starts_at: InstanteUTC


@router.post("/dispatch", response_model=list[ReminderOut])
def dispatch_reminders(
    dispatcher: ReminderDispatcher = Depends(get_reminder_dispatcher),
    reintentar: Callable = Depends(get_reintentar_avisos),
):
    """Send every reminder that's currently due and hasn't been sent yet.

    Salen por WhatsApp y por mail (`app/notifications.py`); antes se vuelve
    a intentar lo que quedó `fallido` en una pasada anterior. Meant to be called periodically
    by a cron/scheduler (`scripts/despachar_recordatorios.py` es el mismo
    trabajo sin pasar por HTTP); idempotent, safe to call as often as needed:
    el motor no manda dos veces el mismo aviso.
    """
    return despachar_recordatorios(dispatcher, reintentar)
