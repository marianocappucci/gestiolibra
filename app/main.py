"""Gestiolibra app factory: wires LibraGenda and mounts the routers."""

import os

from libracore.db.url_de_instancia import url_de_instancia

from fastapi import Depends, FastAPI

from libraauth.auditoria import (
    AuditoriaBase, AuditoriaRepository, agregar_middleware_de_usuario, build_logs_router,
    configurar_auditoria,
)
from libraauth.auth_events import AuthEventRepository
from libraauth.demo_codigos import DemoCodigoRepository
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.session_auth import (
    build_demo_codigos_router, build_smtp_settings_router, demo_username,
)
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from libraauth.terminos import TerminosRepository, build_terminos_router
from libracore import config_manager
from libracore.arca_router import build_arca_router
from libracore.config_router import (
    build_backup_router, build_empresa_admin_router, build_empresa_router,
)
from libracore.respaldo import Instancia
from libracore.smtp_router import build_smtp_probe_router
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
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
    agenda, appointments, availability, branch_hours, branches,
    business_settings, clients, dashboard as dashboard_router, deposits, health, holidays,
    medios_pago as medios_pago_router,
    reminders,
    resources, service_prices, services, users as users_router,
)
from .routers import auth as auth_router
from . import mercadopago
from .services import billing
from .services.appointments import AppointmentService
from .services.branch_hours import BranchHoursRepository
from .services.branches import BranchRepository
from .services.business_settings import BusinessSettingsRepository
from .services.clients import ClientRepository
from .services.dashboard import DashboardService
from .services.modules import ModuleRepository
from .services.service_prices import ServicePriceRepository
from libraauth.bootstrap import ensure_demo_user
from .services.users import UserRepository, ensure_default_admin


def _carpeta_de_backups(libracore_db_path: str) -> str:
    """Donde se guardan los ZIP de backup.

    🔴 **Salia de `os.path.dirname(libracore_db_path)`, y con la base en
    PostgreSQL eso no es una carpeta.** `dirname()` de
    `postgresql://usuario:clave@host:5432/base` devuelve
    `postgresql://usuario:clave@host:5432`, y ahi se creaba `backups/`: una
    carpeta **con la contrasena en el nombre**, colgando del directorio de
    trabajo. Es el mismo defecto que `billing.configure()` tenia, en otro lugar
    del mismo arranque.

    Con la base en PostgreSQL no hay "al lado de la base": se usa `DATA_DIR`,
    que es donde viven los logos de esta instancia.
    """
    if str(libracore_db_path).startswith(("postgresql://", "postgresql+psycopg://")):
        return os.path.join(os.environ.get("DATA_DIR", "./data"), "backups")
    return os.path.join(os.path.dirname(libracore_db_path), "backups")


def _instancia_a_respaldar(database_url: str, libracore_db_path: str,
                           directorios: list) -> Instancia:
    """Que se lleva el backup, segun el motor de cada mitad.

    🔴 **Las dos mitades o ninguna.** El dominio y LibraCore son dos bases
    separadas -- dos archivos en SQLite, dos bases PostgreSQL despues del corte,
    porque no pueden compartir schema: las dos declaran una tabla `clients` con
    `id` de tipos incompatibles. Un backup con una sola no se puede restaurar:
    o volves el dominio y te quedan usuarios de otro momento, o al reves. Y no
    falla -- da un ZIP que se descarga y pesa poco.

    `bases=` sirve para rutas de archivo: con la base en PostgreSQL la URL
    entraba como si fuera una ruta, el archivo no existia y `_copiar_base` se lo
    salteaba **en silencio**. Lo encontro la suite de [[medlibra]], donde ese
    test no se saltea contra PostgreSQL; aca los skips lo tapaban.
    """
    dominio = make_url(database_url)
    if dominio.drivername.startswith("postgresql"):
        extra = []
        if str(libracore_db_path).startswith(("postgresql://", "postgresql+psycopg://")):
            extra.append(str(libracore_db_path))
        return Instancia(
            nombre="gestiolibra",
            postgres_url=database_url,
            postgres_extra=extra,
            directorios=directorios,
        )
    return Instancia(
        nombre="gestiolibra",
        bases=[dominio.database, libracore_db_path],
        directorios=directorios,
    )


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
    libracore_db_path = url_de_instancia(
        "gestiolibra", core=True, default="./data/gestiolibra_libracore.db"
    )
    billing.configure(libracore_db_path)
    # La URL de SQLAlchemy salia siempre como `sqlite:///...`, aunque el destino
    # fuera una URL PostgreSQL: la interpolacion la convertia en una ruta
    # relativa sin sentido (`sqlite:///postgresql://...`) y el engine moria con
    # *unable to open database file*. `postgresql://` se pasa tal cual, con el
    # driver psycopg que es el de la familia, y `connect_args` es de SQLite.
    # Mismo arreglo que [[ventalibra]], que llego a esto primero.
    if libracore_db_path.startswith(("postgresql://", "postgresql+psycopg://")):
        auth_engine = create_engine(
            libracore_db_path.replace("postgresql://", "postgresql+psycopg://", 1)
        )
    else:
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
    # Crea al visitante de la demo, **solo si esta instancia es una demo**: se
    # guia por `DEMO_MODE` + `DEMO_USERNAME`, las mismas dos variables que
    # registran `POST /auth/demo`. En la instancia de un cliente devuelve None
    # y no toca la base.
    #
    # 🔴 Sin esta llamada la ruta existe y no tiene a quien loguear: contesta
    # `503 demo user not provisioned`. Cablear `incluir_demo=True` en el router
    # no alcanza — la ruta y la siembra las conecta el producto, cada una por
    # su lado.
    ensure_demo_user(user_repository)

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
    # Terminos y Condiciones del Servicio: la prueba de la aceptacion y lo que
    # enciende el gate. MISMA fabrica de sesiones que el SMTP y los usuarios --
    # la tabla tiene FK a `usuarios`, que no siempre vive en la base del dominio.
    #
    # 🔴 Sin esta linea el gate NO corta y la instancia no falla: se queda sin
    # gate, en silencio. Por eso cada producto tiene un test que lo prueba.
    app.state.terminos = TerminosRepository(auth_sessions)
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
    # `POST /admin/smtp/probar`, del motor: abre la conexion, negocia TLS y
    # hace login.
    #
    # 🔑 Resuelve por el MISMO camino que los envios, y por eso el boton
    # significa algo: un endpoint que probara otra config diria "Conectado"
    # contra un servidor mientras los mails salen por otro. El gate va afuera
    # porque el router del motor no trae ninguno propio, y esto abre una
    # sesion SMTP con las credenciales del cliente.
    app.include_router(
        build_smtp_probe_router(lambda: resolver_smtp_config(auth_sessions)),
        dependencies=[Depends(require_admin)],
    )
    # `GET /terminos`, `POST /terminos/aceptar`, `GET /terminos/historial`.
    # NO se gatea desde afuera: es el unico camino para salir del gate.
    app.include_router(build_terminos_router())
    # `GET`/`POST`/`DELETE /admin/demo-codigos`, **solo en la demo**: es por
    # donde el backoffice emite los codigos que se le pasan a un interesado.
    # Exige rol admin o token de servicio por dentro, igual que el de SMTP.
    #
    # 🔴 El repositorio va contra `auth_sessions`, NO contra `sessions`: la
    # tabla de codigos vive en el mismo engine que `usuarios`, que en este
    # producto no es la base del dominio. Con el factory del dominio, la tabla
    # se crearia en el lugar equivocado y `POST /auth/demo` no encontraria
    # ningun codigo valido.
    #
    # 🔴 Y una instancia demo que llegue aca SIN el repositorio deja de dejar
    # entrar: el endpoint falla cerrado a proposito. Si un dia la demo devuelve
    # `503 demo access codes not configured`, lo que falta es esta linea.
    if demo_username():
        app.state.demo_codigos = DemoCodigoRepository(auth_sessions)
        app.include_router(build_demo_codigos_router())
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
    app.include_router(holidays.router, dependencies=admin_only)
    app.include_router(resources.router, dependencies=staff_or_admin_catalog)
    app.include_router(services.router, dependencies=staff_or_admin_catalog)
    app.include_router(service_prices.router, dependencies=admin_only)
    app.include_router(clients.router, dependencies=staff_or_admin_catalog)
    app.include_router(availability.router, dependencies=admin_only)
    app.include_router(business_settings.router, dependencies=admin_only)
    # 🔴 Con que medios se puede cobrar. **NO va con **: lo consume
    # el selector del mostrador al completar un turno, y ahi no hay un admin.
    # Es una lista de constantes del motor, sin datos de la instancia.
    app.include_router(medios_pago_router.router)
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
    # ARCA, del motor. Reemplaza al `routers/billing.py` propio, que sobre el
    # MISMO prefijo `/config/arca` solo tenia GET y PUT, y pedia el certificado
    # como un PATH DEL FILESYSTEM del servidor en un campo de texto.
    #
    # 🔴 Eso tenia dos problemas y ninguno se veia en pantalla: el alta no se
    # podia hacer desde el navegador --alguien tenia que dejar el .crt y el .key
    # dentro del volumen del contenedor a mano-- y era una ruta que el admin
    # escribe y el servidor abre.
    #
    # Lo que gana la pantalla con el router del motor: sube el par y lo VALIDA
    # antes de escribirlo --subir el .csr en vez del .crt, o dos mitades que no
    # son pareja, se rechazan al subir con el motivo escrito--, dice cuando
    # vence el certificado, y autentica de verdad contra WSAA.
    #
    # 🔑 El vencimiento es el dato que evita la falla silenciosa: duran dos anos
    # y el dia que vencen la facturacion deja de andar sin que nadie haya tocado
    # nada.
    #
    # El prefijo y las dependencias son los mismos, asi que el gate del modulo
    # "facturacion" sigue igual.
    app.include_router(
        # 🔴 `empresa_por_defecto` es el slug con el que `services/billing.py`
        # lee la configuracion de facturacion (`EMPRESA = "negocio"`). En una
        # instancia que todavia no facturo no hay fila, y el primer guardado la
        # crea: sin esto la crearia como `default`, donde ese servicio no mira
        # nunca. El PUT contesta 200, la pantalla dice "Guardado", y el primer
        # comprobante falla con "ARCA no esta configurado".
        #
        # La pantalla compartida ya manda el slug desde libra-ui v0.48.0, pero
        # un script, el backoffice o un curl no tienen por que saberlo. Ver
        # LibraCore v1.63.0.
        build_arca_router(prefix="/config/arca", empresa_por_defecto=billing.EMPRESA),
        dependencies=admin_only + [Depends(require_module("facturacion"))],
    )
    # MercadoPago: las tres pantallas y el webhook, todas del motor. Lo unico
    # de este producto es de donde salen los clientes -- ver app/mercadopago.py.
    mercadopago.montar(
        app, client_repository,
        gates=admin_only + [Depends(require_module("facturacion"))],
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

    # Datos de empresa, logo y Datos / Backup (LibraCore v1.11.0).
    #
    # Los tres routers son del motor: este producto no reimplementa nada, solo
    # les pone su dependencia de rol. Todo admin — hasta hoy este producto no
    # tenia NINGUNA pantalla de configuracion, asi que no hay ningun consumidor
    # de la lectura que haya que dejar abierto.
    app.include_router(build_empresa_router(), dependencies=admin_only)
    app.include_router(build_empresa_admin_router(), dependencies=admin_only)

    # 🔴 DOS bases, y las dos tienen que entrar al backup: `usuarios` vive en
    # la de LibraCore, separada de la del dominio. Un backup de una sola no se
    # puede restaurar —o volves el dominio y te quedan usuarios de otro
    # momento, o al reves— y no falla: da un ZIP que se descarga y pesa poco.
    engine = get_engine()
    app.include_router(
        build_backup_router(
            _instancia_a_respaldar(
                database_url, libracore_db_path,
                directorios=[config_manager.LOGO_DIR],
            ),
            _carpeta_de_backups(libracore_db_path),
            # Sin estos dos el restore devuelve `ok` y no tiene efecto hasta
            # que alguien reinicie el contenedor: el pool sigue con el archivo
            # viejo abierto. `dispose()` sirve para los dos momentos.
            cerrar_conexiones=engine.dispose,
            reabrir_conexiones=engine.dispose,
        ),
        dependencies=admin_only,
    )

    return app
