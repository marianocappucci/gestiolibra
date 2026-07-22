"""Gestiolibra app factory: wires LibraGenda and mounts the routers."""

from fastapi import Depends, FastAPI

from libragenda.availability_repository import SqlAlchemyAvailabilityRepository
from libragenda.database import configure, get_engine, get_session_factory
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.sqlalchemy_repository import Base, SqlAlchemyAppointmentRepository

from .auth import build_session_auth, require_admin, require_staff
from .routers import (
    agenda, appointments, availability, branches, clients, health, resources,
    services, users as users_router,
)
from .routers import auth as auth_router
from .services.appointments import AppointmentService
from .services.users import UserRepository, ensure_default_admin


def create_app(database_url: str) -> FastAPI:
    """Build the vertical app after configuring LibraGenda's PostgreSQL port."""
    configure(database_url)
    Base.metadata.create_all(get_engine())  # demo only; deploy uses Alembic
    sessions = get_session_factory()
    catalog = SqlAlchemyCatalogRepository(sessions)
    appointment_repository = SqlAlchemyAppointmentRepository(sessions)
    availability_repository = SqlAlchemyAvailabilityRepository(sessions)
    user_repository = UserRepository(sessions)
    ensure_default_admin(user_repository)

    app = FastAPI(title="Gestiolibra")
    app.state.catalog = catalog
    app.state.availability = availability_repository
    app.state.appointment_service = AppointmentService(
        catalog, appointment_repository, availability_repository,
    )
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    # Catalog/admin surface: only admins manage branches, resources, services,
    # clients, availability and other users -- staff only touches turnos.
    admin_only = [Depends(require_admin)]
    app.include_router(branches.router, dependencies=admin_only)
    app.include_router(resources.router, dependencies=admin_only)
    app.include_router(services.router, dependencies=admin_only)
    app.include_router(clients.router, dependencies=admin_only)
    app.include_router(availability.router, dependencies=admin_only)
    app.include_router(users_router.router, dependencies=admin_only)
    # Agenda surface: staff manages their own turnos too.
    staff_or_admin = [Depends(require_staff)]
    app.include_router(appointments.router, dependencies=staff_or_admin)
    app.include_router(agenda.router, dependencies=staff_or_admin)

    return app
