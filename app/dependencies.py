"""FastAPI dependency providers reading shared state off the app instance."""

from fastapi import Request

from libragenda.availability_repository import SqlAlchemyAvailabilityRepository
from libragenda.catalog_repository import SqlAlchemyCatalogRepository

from .services.appointments import AppointmentService
from .services.users import UserRepository


def get_catalog_repository(request: Request) -> SqlAlchemyCatalogRepository:
    return request.app.state.catalog


def get_availability_repository(request: Request) -> SqlAlchemyAvailabilityRepository:
    return request.app.state.availability


def get_appointment_service(request: Request) -> AppointmentService:
    return request.app.state.appointment_service


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.users
