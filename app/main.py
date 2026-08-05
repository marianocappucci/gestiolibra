"""Gestiolibra app factory: wires LibraGenda and mounts the routers."""

import os

from fastapi import Depends, FastAPI

from libraauth.auditoria import (
    AuditoriaBase, AuditoriaRepository, agregar_middleware_de_usuario, build_logs_router,
    configurar_auditoria,
)
from libraauth.auth_events import AuthEventRepository
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.session_auth import build_smtp_settings_router
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libragenda import DepositManager, ReminderDispatcher, SqlAlchemyDepositRepository, SqlAlchemyReminderRepository
from libragenda.availability_repository import SqlAlchemyAvailabilityRepository
from libragenda.database import configure, get_engine, get_session_factory
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.sqlalchemy_repository import Base, SqlAlchemyAppointmentRepository

from .auditoria import AUDITABLES
from .auth import build_session_auth, require_admin, require_admin_o_servicio, require_staff
from .modules_gate import require_module
from .notifications import DEFAULT_REMINDER_POLICIES, LoggingNotificationPort
from .payments import ManualPaymentPort
from .routers import (
    agenda, appointments, availability, billing as billing_router, branch_hours, branches,
    business_settings, clients, dashboard as dashboard_router, deposits, health, reminders,
    resources, service_prices, services, users as users_router,
)
from .routers import auth as auth_router
from .services import billing
from .services.appointments import AppointmentService
from .services.branch_hours import BranchHoursRepository
from .services.branches import BranchRepository
from .services.business_settings import BusinessSettingsRepository
from .services.clients import ClientRepository
from .services.dashboard import DashboardService
from .services.modules import ModuleRepository
from .services.service_prices import ServicePriceRepository
from .services.users import UserRepository, ensure_default_admin


def create_app(database_url: str) -> FastAPI:
    """Build the vertical app after configuring LibraGenda's PostgreSQL port."""
    configure(database_url)
    Base.metadata.create_all(get_engine())  # demo only; deploy uses Alembic

    # `usuarios` (libraauth) vive en la base de LIBRACORE, no en la del dominio.
    #
    # Es deliberado y se pago aprendiendolo: 11 tablas de libracore
    # (facturas, ventas, caja_movimientos, turnos_caja, egresos, egresos_pagos,
    # movimientos_stock, movimientos_tesoreria, cc_pagos, remitos, presupuestos)
    # declaran `usuario_id REFERENCES usuarios(id)`, y esas FK resuelven contra
    # la tabla que este en SU MISMO archivo. Mover `usuarios` a la base del
    # dominio (como se hizo el 2026-07-30 y se revirtio el mismo dia) dejaba dos
    # copias con ids distintos: un usuario nuevo entraba solo en la de auth, y
    # al facturar libracore escribia un usuario_id que ahi no existia -> o
    # violacion de FK, o el registro atribuido a OTRA persona. Ver
    # wiki/entities/libraauth.md.
    #
    # libraauth lee sin problema la tabla que escribio el sqlite3 crudo de
    # libracore (mismo schema, mismo hashing) y `create_all` no la altera.
    libracore_db_path = os.environ.get(
        "GESTIOLIBRA_LIBRACORE_DB_PATH", "./data/gestiolibra_libracore.db"
    )
    billing.configure(libracore_db_path)
    auth_engine = create_engine(
        f"sqlite:///{libracore_db_path}", connect_args={"check_same_thread": False}
    )
    AuthBase.metadata.create_all(auth_engine)
    auth_sessions = sessionmaker(bind=auth_engine)

    sessions = get_session_factory()

    # Log de actividad (libraauth v0.9.0). Va contra el engine del DOMINIO
    # —el de LibraGenda— y no contra `auth_engine`: es donde ocurren las
    # escrituras que audita y donde vive su transacción. La tabla de accesos,
    # en cambio, sí va del lado de auth, que es donde LibraCore ya la creó.
    AuditoriaBase.metadata.create_all(get_engine())
    configurar_auditoria(sessions, AUDITABLES)

    catalog = SqlAlchemyCatalogRepository(sessions)
    appointment_repository = SqlAlchemyAppointmentRepository(sessions)
    availability_repository = SqlAlchemyAvailabilityRepository(sessions)
    # Sin `roles=`: el default ("admin","staff") es el vocabulario de Gestiolibra.
    user_repository = UserRepository(auth_sessions)
    branch_hours_repository = BranchHoursRepository(sessions)
    deposit_repository = SqlAlchemyDepositRepository(sessions)
    reminder_repository = SqlAlchemyReminderRepository(sessions)
    client_repository = ClientRepository(catalog, sessions)
    module_repository = ModuleRepository(sessions)
    module_repository.ensure_seeded()
    ensure_default_admin(user_repository)

    app = FastAPI(title="Gestiolibra")
    app.state.catalog = catalog
    app.state.availability = availability_repository
    app.state.branches = BranchRepository(catalog, sessions)
    app.state.branch_hours = branch_hours_repository
    app.state.service_prices = ServicePriceRepository(sessions)
    app.state.business_settings = BusinessSettingsRepository(sessions)
    app.state.clients = client_repository
    app.state.appointment_service = AppointmentService(
        catalog, appointment_repository, availability_repository, branch_hours_repository,
    )
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)
    # Recuperación de contraseña por correo (libraauth v0.5.0). Usa
    # `auth_sessions` —el mismo session_factory que el UserRepository— porque
    # la tabla de tokens tiene FK a `usuarios`, que vive en la base de
    # LibraCore y no en la del dominio.
    #
    # Sin SMTP configurado la app **levanta igual**: el que avisa es el
    # endpoint, con un 503, recién cuando alguien pide un reset.
    # Config SMTP editable por backoffice (libraauth v0.6.0), con la contraseña
    # cifrada en reposo. Mismo `auth_sessions` que el resto del motor.
    app.state.smtp_settings = SmtpSettingsRepository(auth_sessions)
    app.state.password_reset = PasswordResetService(
        auth_sessions,
        product_name="Gestiolibra",
        reset_url_base=os.environ.get(
            "GESTIOLIBRA_RESET_URL_BASE", "https://dev.gestiolibra.com.ar/reset-password"
        ),
        # CALLABLE, no un valor: se resuelve en cada envío. Con un valor fijo,
        # guardar el SMTP por pantalla no tendría efecto hasta recrear el
        # contenedor. Si no hay nada guardado cae a las variables de entorno,
        # así que esta instancia se comporta igual que antes hasta que alguien
        # cargue algo.
        smtp_config=lambda: resolver_smtp_config(auth_sessions),
    )
    app.state.reminder_dispatcher = ReminderDispatcher(
        appointment_repository, reminder_repository,
        LoggingNotificationPort(), DEFAULT_REMINDER_POLICIES,
    )
    app.state.deposits = deposit_repository
    app.state.deposit_manager = DepositManager(deposit_repository, ManualPaymentPort())
    app.state.dashboard = DashboardService(
        appointment_repository, client_repository, reminder_repository, deposit_repository,
    )
    app.state.modules = module_repository
    app.state.auditoria = AuditoriaRepository(sessions)
    # Accesos: `auth_sessions`, que apunta a la base de LibraCore. Ahí la tabla
    # `auth_log` **ya existe** —la crea el schema de LibraCore— así que esto no
    # agrega ninguna tabla; sólo empieza a escribirla, que hasta ahora no hacía
    # nadie en este producto.
    app.state.auth_events = AuthEventRepository(auth_sessions)
    # Sella el usuario de la cookie para que la auditoría sepa quién escribió.
    agregar_middleware_de_usuario(app)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    # `GET`/`PUT`/`DELETE /admin/smtp`. El router ya exige rol admin por dentro
    # (quien pueda escribir ahí puede redirigir a dónde salen los enlaces de
    # recuperación de contraseña de todos los usuarios).
    app.include_router(build_smtp_settings_router())
    # Catalog/admin surface: only admins manage branches, resources, services,
    # clients, availability, hours, prices, business settings and other users
    # -- staff only touches turnos.
    admin_only = [Depends(require_admin)]
    staff_or_admin_catalog = [Depends(require_staff)]
    # branches/resources/services/clients: lectura abierta a staff+admin
    # (necesaria para que el frontend arme selectores de turno sin ser
    # admin), escritura (create/update/delete) admin-only via dependencies
    # puestas en cada endpoint mutante de esos routers.
    app.include_router(branches.router, dependencies=staff_or_admin_catalog)
    app.include_router(branch_hours.router, dependencies=admin_only)
    app.include_router(resources.router, dependencies=staff_or_admin_catalog)
    app.include_router(services.router, dependencies=staff_or_admin_catalog)
    app.include_router(service_prices.router, dependencies=admin_only)
    app.include_router(clients.router, dependencies=staff_or_admin_catalog)
    app.include_router(availability.router, dependencies=admin_only)
    app.include_router(business_settings.router, dependencies=admin_only)
    # Usuarios acepta ADEMÁS el token de servicio (libraauth v0.7.0): es lo
    # único que el backoffice de la suite necesita y que no puede salir del
    # motor, porque el router de usuarios es propio de cada producto.
    #
    # Deliberadamente sólo este: el resto de los routers admin-only siguen
    # exigiendo sesión de un usuario del producto. El backoffice no tiene por
    # qué poder tocar sucursales, precios ni disponibilidad, y darle el token
    # acceso a todo `admin_only` sería ampliar el permiso sin necesidad.
    app.include_router(
        users_router.router, dependencies=[Depends(require_admin_o_servicio)]
    )
    # Recordatorios, señas, facturación y dashboard son módulos gateables
    # por plan (ver plans.py) -- catálogo/turnos nunca se gatean.
    app.include_router(
        reminders.router, dependencies=admin_only + [Depends(require_module("recordatorios"))],
    )
    app.include_router(
        deposits.admin_router, dependencies=admin_only + [Depends(require_module("senas"))],
    )
    app.include_router(
        billing_router.router, dependencies=admin_only + [Depends(require_module("facturacion"))],
    )
    app.include_router(
        dashboard_router.router, dependencies=admin_only + [Depends(require_module("dashboard"))],
    )
    # Agenda surface: staff manages their own turnos too.
    staff_or_admin = [Depends(require_staff)]
    app.include_router(appointments.router, dependencies=staff_or_admin)
    app.include_router(agenda.router, dependencies=staff_or_admin)
    app.include_router(
        deposits.request_router, dependencies=staff_or_admin + [Depends(require_module("senas"))],
    )
    # Logs: admin y nada más. Es la pantalla que dice quién borró qué y desde
    # qué IP entró cada uno; el staff no tiene por qué ver la actividad de sus
    # compañeros. **No** se gatea por plan: un log de auditoría no es una
    # feature vendible, es cómo se averigua qué pasó.
    #
    # El router lo arma el motor (libraauth v0.10.0) pero el gate lo pone el
    # producto: el vocabulario de roles es de acá, no del paquete.
    app.include_router(build_logs_router(AUDITABLES), dependencies=admin_only)

    return app
