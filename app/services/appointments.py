"""Application service for the appointment booking use case.

Wraps LibraGenda's InMemoryScheduler with the one piece of app-specific
validation the engine can't do on its own (does this service exist at
all) — everything else is delegated straight to LibraGenda's own use
cases and domain exceptions, per CONVENTIONS.md ("no duplicar reglas de
LibraGenda").
"""

from datetime import datetime, time
from uuid import uuid4

from libragenda import Appointment, Availability, InMemoryScheduler
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.repositories import AppointmentRepository


class ServiceNotFound(Exception):
    """Raised when booking references a service that was never registered."""


class AppointmentService:
    def __init__(
        self, catalog: SqlAlchemyCatalogRepository, appointments: AppointmentRepository
    ) -> None:
        self.catalog = catalog
        self.appointments = appointments

    def create(
        self, resource_id: str, service_id: str, client_id: str, starts_at: datetime
    ) -> Appointment:
        services = {item.id: item for item in self.catalog.list_services()}
        service = services.get(service_id)
        if service is None:
            raise ServiceNotFound(service_id)
        scheduler = InMemoryScheduler(
            [Availability(resource_id, starts_at.weekday(), time(9), time(18))],
            repository=self.appointments,
        )
        appointment = Appointment(
            str(uuid4()), resource_id, service_id, client_id, starts_at, service.duration,
        )
        scheduler.create(appointment)
        return appointment

    def confirm(self, appointment_id: str) -> Appointment:
        scheduler = InMemoryScheduler(repository=self.appointments)
        return scheduler.confirm(appointment_id)
