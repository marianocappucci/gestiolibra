"""Dashboard: turnos, clientes, recordatorios/señas y facturación/caja --
resumen de lectura pura sobre repositorios ya existentes (LibraGenda +
ClientRepository propio) y sobre libracore.db (facturación/caja, misma
conexión global que ya configura app/services/billing.py -- sin estado
ni tabla propia de este módulo). Facturación/caja quedó afuera del primer
corte (decisión explícita del usuario, ver DECISIONS.md ADR-012) y se
sumó después, ver ADR-015.
"""
from datetime import UTC, date, datetime, time, timedelta, timezone

from libracore.db import caja as db_caja
from libracore.db import facturas as db_facturas
from libragenda import AppointmentStatus, DepositStatus
from libragenda.repositories import AppointmentRepository, DepositRepository, SentReminderRepository

from .clients import ClientRepository

#: Zona del negocio. Argentina es UTC-3 fijo, sin horario de verano, así que el
#: desfasaje es una constante y no hace falta una base de husos para resolverlo.
_ZONA = timezone(timedelta(hours=-3))


def _day_range_utc(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Los días **locales** del rango, expresados como instantes UTC.

    🔴 Acá los días se armaban con `tzinfo=timezone.utc`, o sea que el rango
    significaba *"del 00:00 UTC al 23:59 UTC"*. Y en el mismo `summary()` la
    mitad de facturación compara ese rango contra fechas **locales** —las
    facturas se estampan con `date.today()`—, así que **la misma función usaba
    dos relojes**: entre las 21:00 y las 24:00 de Argentina, los turnos y los
    clientes se contaban de un día y las facturas de otro.

    Se vio el 2026-08-25 a las 02:02 UTC (23:02 ART): pedir el dashboard de
    "hoy" devolvía las facturas del día y **cero clientes nuevos**, o al revés
    según qué fecha se mandara. Ninguna de las dos respuestas era la del día que
    el negocio llama hoy.

    Ahora el rango significa una sola cosa —**días del negocio**— y las dos
    mitades responden por el mismo período. `time.max` mantiene el cierre
    inclusivo que ya tenía: 23:59:59.999999 local.
    """
    return (
        datetime.combine(date_from, time.min, tzinfo=_ZONA).astimezone(UTC),
        datetime.combine(date_to, time.max, tzinfo=_ZONA).astimezone(UTC),
    )


class DashboardService:
    def __init__(
        self,
        appointments: AppointmentRepository,
        clients: ClientRepository,
        reminders: SentReminderRepository,
        deposits: DepositRepository,
    ) -> None:
        self.appointments = appointments
        self.clients = clients
        self.reminders = reminders
        self.deposits = deposits

    def summary(self, date_from: date, date_to: date) -> dict:
        range_start, range_end = _day_range_utc(date_from, date_to)
        all_appointments = list(self.appointments.list())
        in_range = [
            item for item in all_appointments if range_start <= item.starts_at <= range_end
        ]
        por_estado = {status.value: 0 for status in AppointmentStatus}
        for item in in_range:
            por_estado[item.status.value] += 1
        today = datetime.now(UTC).date()
        turnos_hoy = sum(1 for item in all_appointments if item.starts_at.date() == today)

        desde, hasta = date_from.isoformat(), date_to.isoformat()
        facturas_en_periodo = db_facturas.get_facturas_filtradas(desde, hasta, limit=0)["total"]
        caja_resumen = db_caja.get_caja_resumen(desde, hasta)

        return {
            "date_from": date_from,
            "date_to": date_to,
            "turnos": {
                "total_en_periodo": len(in_range),
                "por_estado": por_estado,
                "hoy": turnos_hoy,
            },
            "clientes": {
                "total_activos": self.clients.count_active(),
                "nuevos_en_periodo": self.clients.count_created_between(range_start, range_end),
            },
            "recordatorios_enviados_en_periodo": len(
                self.reminders.list_sent(range_start, range_end)
            ),
            "senas_pendientes": len(self.deposits.list_by_status(DepositStatus.PENDING)),
            "facturacion": {
                "facturas_emitidas_en_periodo": facturas_en_periodo,
                "caja": {
                    "ingresos_en_periodo": caja_resumen["ingresos"],
                    "egresos_en_periodo": caja_resumen["egresos"],
                    "saldo_periodo": caja_resumen["saldo_periodo"],
                    "saldo_total": caja_resumen["saldo_total"],
                },
            },
        }
