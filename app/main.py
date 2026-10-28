"""Gestiolibra app factory: wires LibraGenda and mounts the routers."""

import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from libraauth.auditoria import (
    AuditoriaBase,
    AuditoriaRepository,
    agregar_middleware_de_usuario,
    build_logs_router,
    configurar_auditoria,
)
from libraauth.auth_events import AuthEventRepository, ip_del_request
from libraauth.bootstrap import ensure_demo_user
from libraauth.captcha import Captcha, UsadosEnBase
from libraauth.demo_codigos import DemoCodigoRepository
from libraauth.migrar import exigir_schema_al_dia
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.secretos import SecretosRepository
from libraauth.session_auth import (
    build_demo_codigos_router,
    build_smtp_settings_router,
    demo_username,
)
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from libraauth.terminos import TerminosRepository, build_terminos_router
from libracore import config_manager
from libracore.arca_router import build_arca_router
from libracore.avisos_router import build_avisos_router
from libracore.candados import una_vez_al_arrancar
from libracore.cola_arca import pedidos_a_emitir
from libracore.cola_arca_router import build_cola_del_nodo_router
from libracore.config_router import (
    build_backup_router,
    build_empresa_admin_router,
    build_empresa_router,
)
from libracore.consultar_cuit_router import build_consultar_cuit_router
from libracore.db.core import get_connection as lc_get_connection
from libracore.docs_api import cerrar_docs_de_la_api
from libracore.errores import instalar_registro_de_errores
from libracore.estado_del_sistema import build_estado_del_sistema_router
from libracore.facturas_router import build_comprobantes_pdf_router
from libracore.nodo_conexion_router import build_conexion_del_nodo_router
from libracore.nodo_offline import SinConexion, SoloEnElCentral
from libracore.resguardo_enlace import build_resguardo_enlace_router
from libracore.respaldo import Instancia
from libracore.security_headers import CSP_SPA, SecurityHeadersMiddleware
from libracore.smtp_router import build_smtp_probe_router
from libracore.tema_router import build_tema_admin_router, build_tema_router
from libraedge.pantalla_del_central import create_canje_router, create_nodos_router
from libragenda import (
    DepositManager,
    ReminderDispatcher,
    SqlAlchemyDepositRepository,
    SqlAlchemyReminderRepository,
    crear_esquema,
)
from libragenda.availability_repository import SqlAlchemyAvailabilityRepository
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.database import configure, get_engine, get_session_factory
from libragenda.sqlalchemy_repository import Base, SqlAlchemyAppointmentRepository
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from . import empresa_demo, mercadopago, offline
from .auditoria import AUDITABLES, ENTIDADES_A_MANO
from .auth import build_session_auth, get_current_user, require_admin, require_admin_o_servicio, require_staff
from .config import misma_base, url_de_libracore
from .modules_gate import require_module
from .notifications import DEFAULT_REMINDER_POLICIES, crear_puerto_de_avisos, reintentar_avisos
from .payments import ManualPaymentPort
from .routers import (
    agenda,
    appointments,
    availability,
    branch_hours,
    branches,
    business_settings,
    clients,
    deposits,
    factura_del_turno,
    health,
    holidays,
    reminders,
    resources,
    service_prices,
    services,
    sincronizacion_offline,
)
from .routers import auth as auth_router
from .routers import (
    dashboard as dashboard_router,
)
from .routers import (
    medios_pago as medios_pago_router,
)
from .routers import (
    nodo as nodo_router,
)
from .routers import (
    users as users_router,
)
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

_log = logging.getLogger(__name__)


def migrar_secretos(secretos: SecretosRepository) -> dict:
    """Saca de `config.json` los secretos que quedaron en claro. Idempotente.

    Corre en cada `create_app()` -- este producto no tiene un hook `startup`
    separado, `create_app()` ES el arranque (lo llama `app/asgi.py` una vez
    por proceso, y cada test que arma su propia app lo dispara igual) -- asi
    que la migracion de una instancia viva **es su deploy**. Loguea NOMBRES de
    claves, nunca valores: un log con el secreto lo muda del archivo a una
    superficie peor, porque los logs se copian y se mandan.

    Si cifrar falla, el `config.json` **no se toca** -- la instancia sigue
    cobrando con la credencial que tiene -- y se loguea como error, que es lo
    que despues ve la sonda `auditar_secretos.py`.
    """
    informe = config_manager.migrar_secretos_al_almacen()
    if informe["migradas"]:
        _log.warning(
            "secretos movidos de config.json al almacen cifrado: %s",
            ", ".join(informe["migradas"]),
        )
    if informe["ya_estaban"]:
        _log.warning(
            "config.json tenia una copia vieja de %s; se vacio (el almacen manda)",
            ", ".join(informe["ya_estaban"]),
        )
    if informe["fallaron"]:
        _log.error(
            "no se pudieron cifrar y QUEDAN EN CLARO en config.json: %s",
            ", ".join(f"{k} ({v})" for k, v in informe["fallaron"].items()),
        )
    return informe


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

    Con **una sola base** (ADR-034: `libracore_db_path` ES `database_url`) se lleva esa, una vez.
    Lo que sigue vale para la forma de dos bases, que ya no tiene ninguna instancia (dev y demo se unieron el 2026-10-25) pero el código tolera.

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
        # Una sola base (ADR-034): la de LibraCore ES la del dominio, y el dump de la misma base dos veces
        # no se puede restaurar (el segundo `pg_restore` pisaria al primero).
        if (str(libracore_db_path).startswith(("postgresql://", "postgresql+psycopg://"))
                and not misma_base(database_url, str(libracore_db_path))):
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


async def _contestar_409_de_nodo(request: Request, exc: SinConexion | SoloEnElCentral) -> JSONResponse:
    """Lo que un nodo de LibraEdge contesta con un 409 y no con un 500: una guarda que levanta desde un servicio al que no
    llega ninguna traducción por ruta (editar un cliente). El mismo cuerpo que los routers del motor:
    `{"detail": {"codigo", "mensaje"}}`."""
    return JSONResponse({"detail": exc.detalle()}, status_code=409)


#: Los routers cuyos datos manda el central: en un nodo se leen del espejo y se escriben sólo en el central (409
#: `solo_en_el_central`). Lo mismo en el central o en una instalación común: no hace nada. Ver `app/offline.py`.
_DEL_CENTRAL = [Depends(offline.escritura_solo_en_el_central)]


def create_app(database_url: str) -> FastAPI:
    """Build the vertical app after configuring LibraGenda's PostgreSQL port."""
    # `pool_pre_ping` en el engine del dominio tambien (`libragenda.configure` se lo pasa a `create_engine`): mismo motivo
    # que el de auth mas abajo.
    configure(database_url, pool_pre_ping=True)
    # De a un proceso por vez (libragenda v0.12.0, ADR-015): con `uvicorn --workers N` el arranque corre N veces y dos
    # `create_all` a la vez chocan con «already exists».
    crear_esquema(get_engine())  # demo only; deploy uses Alembic

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
    #
    # **Esa "base de LibraCore" puede ser la del dominio** (ADR-034): sin la variable del core, o con la
    # misma base, `usuarios` y todo LibraCore viven junto a las tablas de LibraGenda. Dos formas, un solo
    # valor (`app.config.url_de_libracore`). Con dos bases sigue valiendo todo lo de arriba.
    libracore_db_path = url_de_libracore(database_url)
    billing.configure(libracore_db_path)
    # La URL de SQLAlchemy salia siempre como `sqlite:///...`, aunque el destino
    # fuera una URL PostgreSQL: la interpolacion la convertia en una ruta
    # relativa sin sentido (`sqlite:///postgresql://...`) y el engine moria con
    # *unable to open database file*. `postgresql://` se pasa tal cual, con el
    # driver psycopg que es el de la familia, y `connect_args` es de SQLite.
    # Mismo arreglo que [[ventalibra]], que llego a esto primero.
    if libracore_db_path.startswith(("postgresql://", "postgresql+psycopg://")):
        # `pool_pre_ping`: tras un restore en caliente con varios workers, el que no atendio el restore se recupera
        # solo en vez de dar 500 hasta el reinicio (docs/varios-procesos.md de libracore).
        auth_engine = create_engine(
            libracore_db_path.replace("postgresql://", "postgresql+psycopg://", 1), pool_pre_ping=True
        )
    else:
        auth_engine = create_engine(
            f"sqlite:///{libracore_db_path}", connect_args={"check_same_thread": False}
        )
    # 🔴 Las tablas de auth las crea la cadena de LibraAuth (`libraauth-migrar
    # upgrade --prefijo gestiolibra --base dominio`, declarada en `scripts/panel_admin.py`),
    # no el arranque. Desde libraauth v0.45.0 (2026-09-17) el arranque la EXIGE: si
    # no corrió, la app no levanta y el error dice el comando. Hasta ese día acá
    # había un `AuthBase.metadata.create_all(auth_engine)` que tapaba cualquier
    # camino que se olvidara de migrar.
    # `--base` del comando que dice el error: `dominio` con una sola base (la forma de todo el mundo desde el
    # 2026-10-25, ADR-037) y `core` sólo si alguien todavía declara la variable del core con OTRA base.
    exigir_schema_al_dia(
        auth_engine, prefijo="gestiolibra",
        base="dominio" if misma_base(database_url, str(libracore_db_path)) else "core",
    )
    auth_sessions = sessionmaker(bind=auth_engine)

    # 🔴 Los secretos de terceros de `config.json` -- el access token y la
    # firma de webhook de MercadoPago, y la contrasena SMTP -- dejan de vivir
    # en texto plano (libracore v1.108.0 + libraauth v0.46.0, 2026-09-17). Se
    # enchufa ACA porque es donde nace `auth_sessions`, que apunta a la base
    # de LibraCore -- ahi viven las tablas de libraauth (`usuarios` y, desde
    # la revision `0002`, `secretos_instancia`), NO la base del dominio de
    # LibraGenda. `exigir_schema_al_dia()` de arriba ya garantiza que esa
    # revision esta aplicada, asi que migrar aca -- despues de esa linea --
    # no puede pisar un schema viejo.
    #
    # LibraCore no importa libraauth: recibe el almacen inyectado. Por eso el
    # enganche es del producto, que es el unico que tiene los dos paquetes.
    secretos_repository = SecretosRepository(auth_sessions)
    config_manager.usar_almacen_de_secretos(secretos_repository)
    # La empresa ficticia de la demo (ADR-038 y ADR-061 de libracore): con `DEMO_MODE=1` el emisor de un comprobante es
    # esta y no la de la base. Sin esta línea la demo dice «Empresa Demo SRL», la genérica del motor. Fuera de una demo
    # no cambia nada.
    empresa_demo.registrar()
    with una_vez_al_arrancar("gestiolibra-arranque", destino=libracore_db_path):
        migrar_secretos(secretos_repository)

    sessions = get_session_factory()

    # Log de actividad (libraauth v0.9.0). Va contra el engine del DOMINIO
    # —el de LibraGenda— y no contra `auth_engine`: es donde ocurren las
    # escrituras que audita y donde vive su transacción. La tabla de accesos,
    # en cambio, sí va del lado de auth, que es donde LibraCore ya la creó.
    # DDL: con dos workers sobre una base nueva, dos `CREATE TABLE` a la vez se pisan (`pg_type_typname_nsp_index`).
    with una_vez_al_arrancar("gestiolibra-arranque", destino=libracore_db_path):
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
    # 🔴 De a un proceso por vez (ADR-044 de libracore). `create_app()` ES el arranque y con `uvicorn --workers N` lo corre
    # cada worker: un «si no existe, crear» (los modulos, el admin, el usuario de la demo) se contestaba «no existe» en
    # todos antes de que ninguno creara. El candado hace que el segundo espere al primero y vea lo que dejo; cada paso
    # sigue preguntando adentro, asi que sigue siendo idempotente. `destino` es la base de LibraCore: cualquiera sirve
    # mientras sea la misma para todos los workers (el candado es de esa base, no de lo que se siembra).
    with una_vez_al_arrancar("gestiolibra-arranque", destino=libracore_db_path):
        # En un nodo los módulos son los del central (`gestiolibra_modulos` se espeja de sólo lectura, ADR-036): sembrarlos
        # acá chocaría con la guarda de LibraEdge, y los que falten se leen como siempre (sin fila, habilitado).
        if offline.nodo() is None:
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
    cerrar_docs_de_la_api(app)
    for excepcion in (SinConexion, SoloEnElCentral):
        app.add_exception_handler(excepcion, _contestar_409_de_nodo)
    # Atender un turno en un nodo (`turno.atendido`, ADR-036) se enchufa al outbox. Fuera de un nodo no hace nada.
    offline.configurar_atenciones()
    # Un nodo es de UNA sola base (ADR-035): el dominio y LibraCore son la misma, y es donde LibraEdge crea sus tablas
    # (`node_identity`, `sync_outbox`...). Con dos bases (ya no hay ninguna instancia así) no se monta nada de lo del nodo.
    una_base = misma_base(database_url, str(libracore_db_path))

    # 🔴 Colgado de la app para poder SOLTARLO. En produccion la app es una y
    # vive lo que vive el proceso, asi que da igual; en la suite cada test arma
    # una app nueva y este engine deja un pool vivo por test. Contra SQLite no
    # se notaba --un `StaticPool` de una conexion que se recolecta sola--, pero
    # contra PostgreSQL son conexiones TCP que se acumulan hasta
    # `max_connections`, y el sintoma son errores de conexion en tests que no
    # tienen nada que ver con el que los causo. Ver `fresh_database_url()`.
    app.state.auth_engine = auth_engine
    # Para que la suite pueda verificar el enganche (`config_manager.
    # almacen_de_secretos() is app.state.secretos_repository`) y correr la
    # migracion a mano, sin reconstruir el repositorio por su cuenta.
    app.state.secretos_repository = secretos_repository
    app.state.catalog = catalog
    # La fábrica de sesiones del dominio, para lo que escribe varias tablas en una transacción (atender y cobrar un turno
    # en un nodo, el alta provisoria de un cliente).
    app.state.sessions = sessions
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
    # Los desafios del captcha ya resueltos se anotan en la base de `usuarios` (libraauth v0.50.0, ADR-023) y no en la
    # memoria del proceso: con `uvicorn --workers N` un desafio resuelto servia una vez POR WORKER. Es el mismo `Captcha`
    # que el router armaria solo (misma clave que la sesion), pero con `usados=`. La tabla la crea la revision `0003`
    # de la cadena de `libraauth-migrar`.
    app.state.captcha = Captcha(app.state.session_auth.secret_key, usados=UsadosEnBase(auth_sessions))
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
    # Los recordatorios salen de verdad (ADR-040, avisos del motor): WhatsApp por Evolution y mail por el SMTP de la instancia, con el
    # canal que haya configurado. El SMTP se resuelve en cada envío, igual que en el reset de contraseña y en las facturas. Un nodo de
    # LibraEdge no manda avisos: los manda el central (`offline.nodo()` es la identidad que lee el producto, y se lee en cada llamada).
    def smtp_config():
        return resolver_smtp_config(auth_sessions)

    app.state.reminder_dispatcher = ReminderDispatcher(
        appointment_repository, reminder_repository,
        crear_puerto_de_avisos(
            clients=client_repository, catalog=catalog, business_settings=app.state.business_settings,
            smtp_config=smtp_config, nodo=lambda: offline.nodo(),
        ),
        DEFAULT_REMINDER_POLICIES,
    )
    # Lo que corre junto con `dispatch`: volver a mandar lo que quedó `fallido` en una pasada anterior. Lo usan la ruta y el script del cron.
    app.state.reintentar_avisos = reintentar_avisos(smtp_config, lambda: offline.nodo())
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

    # 🔴 Los headers de seguridad. Se agrega **al final** a proposito: en
    # Starlette el ultimo middleware agregado es el mas externo, asi que asi
    # envuelve a todas las respuestas, incluidas las de error que devuelven los
    # de adentro.
    #
    # `CSP_SPA` y no la CSP por defecto: esa habilita `cdn.jsdelivr.net` para las
    # apps Jinja2, y este producto no carga nada externo. Ver libracore.
    app.add_middleware(SecurityHeadersMiddleware, csp=CSP_SPA)
    # El registro de errores de la familia (ADR-045 de libracore): un 500 deja una linea en `DATA_DIR/errores/` con un
    # `ref` que el usuario puede dictar, y monta `POST /api/errores-cliente` para los errores del navegador (publico a
    # proposito).
    instalar_registro_de_errores(app, "gestiolibra")

    app.include_router(health.router)
    if una_base:
        # La sincronización del nodo offline (LibraEdge, ADR-036): `/sync/v1/push`, `/pull` y `/ticket-arca`. Se monta
        # siempre: sin un nodo registrado no hay ningún secreto válido y todo contesta 401. La autenticación es el
        # secreto del nodo, no la sesión: por eso no lleva guarda de rol.
        app.include_router(sincronizacion_offline.router)
        # «Sucursal sin internet» (libraedge ADR-011 y ADR-014): el admin da de alta el nodo del local, se lleva la
        # dirección y un código de vinculación, ve el nodo y lo da de baja. Toda la lógica es de LibraEdge; acá sólo la
        # guarda (cambia la estructura de la instancia: sólo admin) y el aprovisionamiento de `app/offline.py`.
        app.include_router(
            create_nodos_router(offline.aprovisionamiento, lc_get_connection), dependencies=[Depends(require_admin)],
        )
        # El canje del código (libraedge ADR-014): `POST /sync/v1/vinculacion`. **Sin guarda a propósito**: lo llama el
        # instalador del nodo, que no tiene sesión; lo protegen el código (un solo uso, 15 minutos) y el límite de
        # intentos del motor. La IP real detrás del proxy es la de libraauth.
        app.include_router(
            create_canje_router(offline.aprovisionamiento, lc_get_connection, ip_del_request=ip_del_request)
        )
        # La cola de comprobantes de ARCA del nodo (libracore ADR-079): lo que quedó esperando sin conexión, para avisarlo
        # y para resolverlo. Reintentar, descartar y marcar emitido deciden sobre un documento fiscal: sólo admin. Fuera
        # de un nodo contesta `es_nodo: false` y no hace nada.
        app.include_router(
            build_cola_del_nodo_router(cola=offline.cola(), usuario_actual=get_current_user, resolver_con=require_admin)
        )
        # `GET /api/nodo/conexion` (libracore ADR-084): lo que el cartel «Sin conexión» de libra-ui lee (`es_nodo`, `en_linea`,
        # `node_id`). Este producto no tiene punto de venta, así que no monta el router de las ventas; cualquier usuario de la
        # instancia, porque la pantalla lo pregunta al cargar la sesión. Antes preguntaba a la cola (`/api/nodo/cola?limite=1`).
        app.include_router(
            build_conexion_del_nodo_router(conexion=offline.CONEXION, usuario_actual=get_current_user)
        )
    # Los turnos que se atendieron sin conexión y en la web cambiaron (libra-ui ADR-095). Las dos puntas la leen.
    app.include_router(nodo_router.router, dependencies=[Depends(require_staff)])
    app.include_router(auth_router.router)
    # `GET`/`PUT`/`DELETE /admin/smtp`. El router ya exige rol admin por dentro
    # (quien pueda escribir ahí puede redirigir a dónde salen los enlaces de
    # recuperación de contraseña de todos los usuarios).
    app.include_router(build_smtp_settings_router(), dependencies=_DEL_CENTRAL)
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
        dependencies=[Depends(require_admin)] + _DEL_CENTRAL,
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
    # puestas en cada endpoint mutante de esos routers. **Excepción: el alta de un
    # cliente (`POST /clients`) es de staff+admin** (ADR-033): quien atiende da de
    # alta al cliente desde el selector de «Nuevo turno»; editarlo y borrarlo
    # siguen siendo de admin.
    #
    # 🔑 **En un nodo de LibraEdge el catálogo se lee y no se escribe** (ADR-036): sucursales, horarios, feriados,
    # recursos, servicios, precios, disponibilidad y datos del negocio los manda el central por el espejo (`_DEL_CENTRAL`).
    # Los clientes sí admiten el alta (provisoria): su guarda está en el router (`routers/clients.py`).
    app.include_router(branches.router, dependencies=staff_or_admin_catalog + _DEL_CENTRAL)
    app.include_router(branch_hours.router, dependencies=admin_only + _DEL_CENTRAL)
    app.include_router(holidays.router, dependencies=admin_only + _DEL_CENTRAL)
    app.include_router(resources.router, dependencies=staff_or_admin_catalog + _DEL_CENTRAL)
    app.include_router(services.router, dependencies=staff_or_admin_catalog + _DEL_CENTRAL)
    app.include_router(service_prices.router, dependencies=admin_only + _DEL_CENTRAL)
    app.include_router(clients.router, dependencies=staff_or_admin_catalog)
    app.include_router(availability.router, dependencies=admin_only + _DEL_CENTRAL)
    app.include_router(business_settings.router, dependencies=admin_only + _DEL_CENTRAL)
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
    #
    # El guard ya NO se pasa acá (ADR-018, libraauth v0.43.0): vive dentro
    # del router que arma `build_users_router()` en `app/routers/users.py`.
    app.include_router(users_router.router, dependencies=_DEL_CENTRAL)
    # Recordatorios, señas, facturación y dashboard son módulos gateables
    # por plan (ver plans.py) -- catálogo/turnos nunca se gatean.
    app.include_router(
        reminders.router, dependencies=admin_only + [Depends(require_module("recordatorios"))] + _DEL_CENTRAL,
    )
    # La configuración de los avisos (WhatsApp por Evolution, mail) y el registro de lo que salió: `/api/avisos`, del motor (ADR-090).
    # Sólo admin: la configuración dice con qué cuenta de WhatsApp habla el negocio y el registro lleva los teléfonos y los textos de los
    # clientes. El gate lo pone `build_avisos_router` (no tiene default). En un nodo, guardar y probar dan 409 `solo_en_el_central`
    # (la apikey vive en el central); ver la configuración y el registro, no. Sin `require_module`: la sección vive en Configuración y no
    # es una función vendible aparte.
    app.include_router(build_avisos_router(require_admin=require_admin, smtp_config=smtp_config, nodo=lambda: offline.nodo()))
    app.include_router(
        deposits.admin_router, dependencies=admin_only + [Depends(require_module("senas"))] + _DEL_CENTRAL,
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
        # El certificado y la clave no existen en el nodo (ADR-036): se cargan en el central.
        dependencies=admin_only + [Depends(require_module("facturacion"))] + _DEL_CENTRAL,
    )
    # Consulta de CUIT en el padrón de ARCA (`GET /api/consultar-cuit/{cuit}`): el router del motor, el que usan
    # Contalibra, Restolibra y VentaLibra. Completa nombre y condición de IVA del alta de un cliente a partir del
    # CUIT. Lee la fila activa de `arca_config` (la que escribe el router de arriba) y autentica contra
    # `ws_sr_padron_a13` con el par de la facturación: sin certificados contesta 503, y si ARCA no delegó ese
    # servicio al certificado, 403 con el paso a seguir.
    #
    # Gate de admin, como la configuración de ARCA (módulo `facturacion`) y la edición de un cliente
    # (`routers/clients.py`; el alta es de staff desde ADR-033, pero consultar el padrón no): sin ese módulo no hay
    # dónde cargar los certificados, así que el módulo lo corta antes.
    app.include_router(
        build_consultar_cuit_router(usuario_actual=get_current_user),
        # La consulta al padrón de ARCA usa el certificado, que sólo está en el central (es un GET: `_DEL_CENTRAL` no lo frena).
        dependencies=admin_only + [Depends(require_module("facturacion")), Depends(offline.consulta_al_central)],
    )
    # MercadoPago: las tres pantallas y el webhook, todas del motor. Lo unico
    # de este producto es de donde salen los clientes -- ver app/mercadopago.py.
    mercadopago.montar(
        app, client_repository,
        gates=admin_only + [Depends(require_module("facturacion"))] + _DEL_CENTRAL,
    )
    app.include_router(
        dashboard_router.router, dependencies=admin_only + [Depends(require_module("dashboard"))],
    )
    # Agenda surface: staff manages their own turnos too.
    staff_or_admin = [Depends(require_staff)]
    app.include_router(appointments.router, dependencies=staff_or_admin)
    # La factura de un turno y su nota de crédito (ADR-039). Ver y pedir el destino de la plata es de admin y staff / admin;
    # emitir la nota es de admin (lo dice cada ruta). Sin el módulo `facturacion` no hay facturas que acreditar. En un nodo la
    # nota es del central (409 `solo_en_el_central`: el nodo no tiene el certificado de ARCA); ver la factura, no.
    app.include_router(
        factura_del_turno.router,
        dependencies=staff_or_admin + [Depends(require_module("facturacion"))] + _DEL_CENTRAL,
    )
    # El PDF de la factura y de la nota (`GET /api/facturas/{id}/pdf`) y su envío por mail, del motor (libracore ADR-031): el
    # mismo archivo que se ve es el que se manda. El SMTP se resuelve en cada envío, así que guardarlo por pantalla tiene
    # efecto sin reiniciar. Enviar es escribir: en un nodo, del central.
    app.include_router(
        build_comprobantes_pdf_router(
            usuario_actual=get_current_user, smtp_config=lambda: resolver_smtp_config(auth_sessions),
        ),
        dependencies=staff_or_admin + [Depends(require_module("facturacion"))] + _DEL_CENTRAL,
    )
    app.include_router(agenda.router, dependencies=staff_or_admin)
    app.include_router(
        deposits.request_router, dependencies=staff_or_admin + [Depends(require_module("senas"))] + _DEL_CENTRAL,
    )
    # Logs: admin y nada más. Es la pantalla que dice quién borró qué y desde
    # qué IP entró cada uno; el staff no tiene por qué ver la actividad de sus
    # compañeros. **No** se gatea por plan: un log de auditoría no es una
    # feature vendible, es cómo se averigua qué pasó.
    #
    # El router lo arma el motor (libraauth v0.10.0) pero el gate lo pone el
    # producto: el vocabulario de roles es de acá, no del paquete.
    app.include_router(build_logs_router({**AUDITABLES, **ENTIDADES_A_MANO}), dependencies=admin_only)

    # Datos de empresa, logo y Datos / Backup (LibraCore v1.11.0).
    #
    # Los tres routers son del motor: este producto no reimplementa nada, solo
    # les pone su dependencia de rol. Todo admin — hasta hoy este producto no
    # tenia NINGUNA pantalla de configuracion, asi que no hay ningun consumidor
    # de la lectura que haya que dejar abierto.
    app.include_router(build_empresa_router(), dependencies=admin_only + _DEL_CENTRAL)
    app.include_router(build_empresa_admin_router(), dependencies=admin_only + _DEL_CENTRAL)

    # El tema de la suite (libracore ADR-012, libra-ui ADR-007/008): los colores que el backoffice de la suite empuja a esta instancia. La
    # lectura es PÚBLICA a propósito (el login también va con los colores de la suite y no expone nada sensible). La escritura es del admin O
    # del token de servicio del backoffice: 🔴 con `require_admin` a secas el backoffice NO entraría (esa guarda no conoce el token).
    app.include_router(build_tema_router())
    app.include_router(build_tema_admin_router(), dependencies=[Depends(require_admin_o_servicio)])

    # 🔴 DOS bases, y las dos tienen que entrar al backup: `usuarios` vive en
    # la de LibraCore, separada de la del dominio. Un backup de una sola no se
    # puede restaurar —o volves el dominio y te quedan usuarios de otro
    # momento, o al reves— y no falla: da un ZIP que se descarga y pesa poco.
    engine = get_engine()
    # Una sola carpeta para los dos routers de abajo: el enlace deja su
    # `rclone.conf` en `<backups_dir>/.resguardo/`, y el subidor del host lo
    # busca AL LADO de los ZIP. Calcularla dos veces es invitar a que diverjan.
    backups_dir = _carpeta_de_backups(libracore_db_path)
    app.include_router(
        build_backup_router(
            _instancia_a_respaldar(
                database_url, libracore_db_path,
                directorios=[config_manager.LOGO_DIR],
            ),
            backups_dir,
            # Sin estos dos el restore devuelve `ok` y no tiene efecto hasta
            # que alguien reinicie el contenedor: el pool sigue con el archivo
            # viejo abierto. `dispose()` sirve para los dos momentos.
            cerrar_conexiones=engine.dispose,
            reabrir_conexiones=engine.dispose,
        ),
        # Restaurar un backup en el nodo le cambiaría la base por debajo a LibraEdge: se hace en el central (ADR-036).
        dependencies=admin_only + _DEL_CENTRAL,
    )
    # La barra de estado del pie (libracore ADR-075, libra-ui ADR-083): usuario, versión, el certificado de ARCA y el
    # último respaldo, en una consulta. La abre cualquier rol de la instancia; lo que ve cada uno lo decide el motor
    # (ARCA y respaldo, sólo admin).
    app.include_router(
        build_estado_del_sistema_router(
            usuario_actual=get_current_user, backups_dir=backups_dir, conexion=offline.CONEXION,
            # La barra del pie: el nodo con lo que espera su conexión (las facturas en cola), o los nodos del central.
            # Las dos leen las tablas de LibraEdge, que están en la base de LibraCore sólo con una base (ADR-035).
            a_facturar=(lambda: pedidos_a_emitir(offline.cola())) if una_base else None,
            nodos_del_central=offline.nodos_del_central if una_base else None,
        ),
        dependencies=[Depends(require_staff)],
    )
    # El enlace de la copia externa con la nube del cliente (LibraCore
    # v1.93.0): la pantalla de Datos / Backup conecta Drive o Dropbox desde
    # acá. Admin y, además, el add-on `resguardo_externo` — que viene apagado y
    # se prende por instancia desde el backoffice. Sin el add-on las cuatro
    # rutas dan 403, y la pantalla (libra-ui v0.68.0) lo lee como "sin plan".
    #
    # El callback de OAuth queda detrás del mismo gate a propósito: la cookie
    # de sesión es `SameSite=Lax` y viaja en la redirección del proveedor.
    app.include_router(
        build_resguardo_enlace_router(backups_dir, carpeta="Resguardo Gestiolibra"),
        dependencies=admin_only + [Depends(require_module("resguardo_externo"))] + _DEL_CENTRAL,
    )

    # En un nodo, un hilo emite lo que quedó en la cola de ARCA cuando vuelve la conexión (libracore ADR-079). Fuera de un
    # nodo no arranca nada. Con varios workers cada uno arranca el suyo: el candado por pedido evita la doble emisión.
    def _arrancar_la_cola() -> None:
        app.state.parar_la_cola = offline.arrancar_cola() if una_base else None

    def _parar_la_cola() -> None:
        parar = getattr(app.state, "parar_la_cola", None)
        if parar is not None:
            parar.set()

    app.router.add_event_handler("startup", _arrancar_la_cola)
    app.router.add_event_handler("shutdown", _parar_la_cola)

    return app
