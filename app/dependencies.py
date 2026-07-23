"""FastAPI dependency providers reading shared state off the app instance."""

from fastapi import Request

from libragenda import DepositManager, ReminderDispatcher
from libragenda.availability_repository import SqlAlchemyAvailabilityRepository
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.repositories import DepositRepository

from .services.appointments import AppointmentService
from .services.branch_hours import BranchHoursRepository
from .services.branches import BranchRepository
from .services.business_settings import BusinessSettingsRepository
from .services.clients import ClientRepository
from .services.dashboard import DashboardService
from .services.service_prices import ServicePriceRepository
from .services.users import UserRepository


def get_catalog_repository(request: Request) -> SqlAlchemyCatalogRepository:
    return request.app.state.catalog


def get_client_repository(request: Request) -> ClientRepository:
    return request.app.state.clients


def get_availability_repository(request: Request) -> SqlAlchemyAvailabilityRepository:
    return request.app.state.availability


def get_appointment_service(request: Request) -> AppointmentService:
    return request.app.state.appointment_service


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.users


def get_branch_repository(request: Request) -> BranchRepository:
    return request.app.state.branches


def get_branch_hours_repository(request: Request) -> BranchHoursRepository:
    return request.app.state.branch_hours


def get_service_price_repository(request: Request) -> ServicePriceRepository:
    return request.app.state.service_prices


def get_business_settings_repository(request: Request) -> BusinessSettingsRepository:
    return request.app.state.business_settings


def get_reminder_dispatcher(request: Request) -> ReminderDispatcher:
    return request.app.state.reminder_dispatcher


def get_deposit_manager(request: Request) -> DepositManager:
    return request.app.state.deposit_manager


def get_deposit_repository(request: Request) -> DepositRepository:
    return request.app.state.deposits


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard
