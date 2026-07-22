"""Placeholder NotificationPort: logs instead of actually sending.

LibraGenda's ReminderDispatcher needs a real channel (email/SMS/WhatsApp)
to deliver reminders -- Gestiolibra doesn't have a provider configured
yet (no credentials for any channel). This keeps the reminder pipeline
(due-reminder rule, sent-reminder ledger, dispatch endpoint) fully wired
and testable now; swapping in a real channel later means only replacing
this one class, nothing else changes (see TASKS.md).
"""
import logging
from datetime import timedelta

from libragenda import ReminderNotification, ReminderPolicy

logger = logging.getLogger("gestiolibra.reminders")

# Fixed for now -- not configurable per branch/service, nobody asked for
# that yet. Change here if the lead times need adjusting.
DEFAULT_REMINDER_POLICIES = [
    ReminderPolicy("24h", timedelta(hours=24)),
    ReminderPolicy("2h", timedelta(hours=2)),
]


class LoggingNotificationPort:
    """Implements libragenda.NotificationPort (structurally -- the Protocol
    isn't @runtime_checkable, so this isn't isinstance-verified, just
    matched by the `send(notification)` signature)."""

    def send(self, notification: ReminderNotification) -> None:
        logger.info(
            "reminder due: appointment=%s policy=%s client=%s starts_at=%s",
            notification.appointment_id, notification.policy_id,
            notification.client_id, notification.starts_at,
        )
