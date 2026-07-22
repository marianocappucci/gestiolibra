"""Placeholder PaymentPort: no automatic charge/refund.

LibraGenda's DepositManager needs a real payment provider to move money --
Gestiolibra doesn't have one wired yet (MercadoPago via libracore.mp_api
is available but requires per-business credentials, tied to the still-open
"facturación/caja" decision, see TASKS.md). Until then, an admin confirms
payment manually (cash, transfer, an MP link sent by hand) via
POST /deposits/{id}/mark-paid -- this port just logs the intent so the
deposit lifecycle (request/paid/failed/refunded) stays fully wired now.
"""
import logging

from libragenda import Deposit

logger = logging.getLogger("gestiolibra.payments")


class ManualPaymentPort:
    def request_charge(self, deposit: Deposit) -> None:
        logger.info("deposit charge requested (manual): %s amount=%s", deposit.id, deposit.amount)

    def request_refund(self, deposit: Deposit) -> None:
        logger.info("deposit refund requested (manual): %s amount=%s", deposit.id, deposit.amount)
