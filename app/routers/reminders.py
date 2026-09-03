from datetime import UTC, datetime, timezone

from fastapi import APIRouter, Depends
from libragenda import ReminderDispatcher
from pydantic import BaseModel

from ..dependencies import get_reminder_dispatcher
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
def dispatch_reminders(dispatcher: ReminderDispatcher = Depends(get_reminder_dispatcher)):
    """Send every reminder that's currently due and hasn't been sent yet.

    Meant to be called periodically by a cron/scheduler (not wired here --
    see TASKS.md); idempotent, safe to call as often as needed.
    """
    return dispatcher.dispatch(datetime.now(UTC))
