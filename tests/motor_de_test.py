"""Contra que motor corre la suite.

Por defecto SQLite en memoria, que es como corrio siempre. Con
`GESTIOLIBRA_TEST_DATABASE_URL` puesta, la suite entera va a ese motor.

🔴 **Por que hizo falta.** Hasta el 2026-08-09 los siete archivos de test
llamaban a `create_app()` con la cadena `sqlite:///:memory:` **escrita a mano**
(19 veces). Apuntar una variable de entorno a un PostgreSQL real y correr la
suite no cambiaba nada: no la leia nadie. O sea que la suite **no podia** correr
contra otro motor, y su verde no decia nada sobre PostgreSQL.

Es el mismo modulo que [[medlibra]] estreno el 2026-08-09 (su PR #25), con el
mismo nombre y la misma forma a proposito: son dos productos con la misma
arquitectura y no tiene sentido que diverjan en como eligen el motor de test.

Va en un modulo y no en `conftest.py` porque los tests lo llaman como funcion:
un `conftest` se carga solo para las fixtures, no se importa por nombre.
"""
import os

#: Vacia salvo que el entorno la ponga. Se lee UNA vez, al importar: si un test
#: la cambiara a mitad de corrida, la mitad de la suite iria a un motor y la
#: mitad al otro, que es peor que cualquiera de los dos.
TEST_DATABASE_URL = os.environ.get("GESTIOLIBRA_TEST_DATABASE_URL", "").strip()

# 🔴 **PostgreSQL y nada mas.** Hasta el 2026-08-25 la suite caia a SQLite
# cuando la variable no estaba, y el CI corria las dos pasadas. El modo SQLite
# se retiro el 2026-08-12 para toda la familia: no chequea las FK, tipa
# dinamicamente y acepta cadenas donde la base pide enteros, asi que una corrida
# verde sobre el no dice nada del motor real.
#
# El guard va ACA porque este es el unico lugar donde se elegia el motor. Con el
# puesto, el predicado que preguntaba por el motor seria siempre True, asi que
# se saco junto con las tres ramas SQLite que colgaban de el.
if not TEST_DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        "La suite de Gestiolibra necesita PostgreSQL: defini "
        "GESTIOLIBRA_TEST_DATABASE_URL (ej. "
        "postgresql+psycopg://gestiolibra:gestiolibra-ci@localhost:5432/gestiolibra). "
        "Sin esa variable la suite correria sobre SQLite, que es lo que se "
        "retiro el 2026-08-12: una suite verde sobre SQLite no dice nada "
        "sobre el motor real."
    )


# --- Una base por worker y plantillas restauradas con CREATE DATABASE ... TEMPLATE ---
# Cada test arranca de bases **nuevas** y rearmarlas es lo que mas cuesta. Medido
# sobre PostgreSQL 16 y libracore v1.118.0, por test: ~0,25 s en el schema de auth
# de la base de LibraCore (`crear_schema_de_auth`, la cadena de Alembic de
# libraauth), ~0,9 s en `create_app()` (las tablas de LibraGenda, el schema del
# core, los modulos, el admin) y ~0,03 s en vaciar el schema del dominio. Con
# `CREATE DATABASE ... TEMPLATE` la base sale de una copia ya armada, ~0,2 s cada
# una (son dos por test) y `create_app()` posterior, ya sobre bases armadas, baja a
# ~0,3 s.
#
# Ojo con el disco: crear y borrar bases fuerza checkpoints, y con 4 workers a la vez
# lo que manda es el `fsync` del servidor, no la CPU. Medido en una maquina cargada, la
# suite entera tardo 335 s con `fsync` y 120 s sin el. Ver `reglas/ci.md` del wiki.
#
# El mecanismo (una base por worker de xdist, plantillas, `FORCE` para echar las
# conexiones del test anterior) vive en `libracore.testing.pg_por_worker`; aca
# queda lo propio de Gestiolibra: que hay en cada plantilla.
#
# 🔴 **Este producto tiene DOS bases** (dominio y LibraCore, ver `url_libracore`),
# asi que cada una tiene su propia `BasePorWorker` y sus propias plantillas:
#
# | plantilla | dominio                  | LibraCore (`_core`)                    |
# |-----------|--------------------------|----------------------------------------|
# | `vacia`   | nada (schema public)     | solo el schema de auth                 |
# | `armada`  | lo que deja `create_app` | auth + lo que `create_app` le agrega   |
#
# - **vacia** es EXACTAMENTE lo que dejaban antes `fresh_database_url()` (vaciar
#   `public`) y `_preparar_libracore()` (vaciar `public` + `crear_schema_de_auth`),
#   asi que los tests que arman su propia app, prueban el arranque sin la cadena
#   de auth o corren migraciones desde cero ven lo mismo que siempre.
# - **armada** es lo que `admin_client` le hacia a esas dos bases (`create_app()`).
#   Solo la piden los tests que usan `admin_client`; su `create_app` posterior es
#   idempotente sobre ella, que es lo que el producto hace en cada arranque. La
#   arma una funcion `(url_dominio, url_core) -> None` que pasa el conftest
#   (`construir_armada`), porque `create_app` vive en el producto y no aca.
#
# `from motor_de_test import TEST_DATABASE_URL` es como lo leen los tests, asi que
# reasignarla aca alcanza: ninguno compone la URL por su cuenta.
#
# 🔴 Una base por worker **tambien para LibraCore**: la de antes era una sola
# (`gestiolibra_core`) y dos workers se la vaciaban por debajo.
#
# 🔴 Si un test importara `tests.motor_de_test` y otro `motor_de_test` serian DOS
# modulos y este codigo correria dos veces por proceso. `base_por_worker` es
# idempotente a proposito, asi que no recrea la base la segunda vez. Hoy todos
# importan `motor_de_test`.
from libracore.respaldo_postgres import con_base  # noqa: E402
from libracore.testing.pg_por_worker import base_por_worker  # noqa: E402

_PG = base_por_worker("gestiolibra", TEST_DATABASE_URL)
TEST_DATABASE_URL = _PG.url
# 🔴 La variable se pisa con la URL de ESTE worker. No es adorno: el restore de un backup
# (`test_config_backup.py`) se niega si "ninguna variable de entorno apunta" a la base
# que va a restaurar, porque las migraciones se la encuentran por el entorno (ver
# `libracore.respaldo_postgres.bases_sin_variable`). Con la variable en la base original
# esos dos tests morian con un 422 que no se parece en nada a la causa.
os.environ["GESTIOLIBRA_TEST_DATABASE_URL"] = TEST_DATABASE_URL


def _url_cruda(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _asegurar_base(nombre: str) -> None:
    """Crea `nombre` en el servidor si no esta. La necesita `base_por_worker`: administra
    conectada a la base ORIGINAL, que tiene que existir.

    Tolera la carrera de dos procesos que la crean a la vez; en la practica la crea el
    proceso que lanza a los workers (importa este modulo antes de que ellos arranquen).
    """
    import psycopg
    from psycopg import sql

    with psycopg.connect(_url_cruda(_PG.url_original), autocommit=True) as conexion:
        existe = conexion.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone()
        if not existe:
            try:
                conexion.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
            except psycopg.errors.DuplicateDatabase:  # pragma: no cover - carrera entre procesos
                pass


# LibraCore va a OTRA base del mismo servidor (`<base>_core`); su base por worker sale de ahi.
_NOMBRE_CORE = _url_cruda(_PG.url_original).rsplit("/", 1)[1].split("?")[0] + "_core"
_asegurar_base(_NOMBRE_CORE)
_PG_CORE = base_por_worker("gestiolibra_core", con_base(_PG.url_original, _NOMBRE_CORE))


def _no_hacer_nada(url: str) -> None:
    """La plantilla `vacia` del dominio: una base recien creada, sin tablas."""


def _construir_core_vacia(url: str) -> None:
    # Las seis tablas de auth viven en la base de LibraCore (`--base core`) y desde
    # libraauth v0.45.0 el arranque exige su cadena en vez de crearlas. Es el mismo
    # orden que el deploy, donde `libraauth-migrar` va antes de `libracore-migrar`.
    from libraauth.testing import crear_schema_de_auth

    crear_schema_de_auth(_url_cruda(url))


def fresh_database_url(construir_armada=None) -> str:
    """La URL para un `create_app()` nuevo, con la base del dominio **de este worker** restaurada.

    Cada test arma su propia app y espera una base limpia. Con
    `sqlite:///:memory:` eso sale gratis: cada conexion nueva ES una base
    nueva. Un PostgreSQL, en cambio, es **uno solo y compartido** por toda la
    corrida, asi que hay que restaurarlo entre test y test o el segundo ve las
    filas del primero.

    Sin argumentos: la plantilla **vacia** (lo que dejaba el `DROP SCHEMA` de
    antes). Con `construir_armada` (una funcion `(url_dominio, url_core) -> None`
    que deja las dos bases como las deja `create_app()`): la plantilla **armada**,
    que se construye la primera vez en cada worker.

    🔴 **Se borra la base con `FORCE` y no se hace un `DROP SCHEMA`**: la app del test
    anterior puede seguir conectada y `DROP DATABASE` sin `FORCE` fallaria. Y hay
    que soltar tambien su engine: `libragenda.database.configure()` reemplaza el
    engine del proceso **sin hacerle `dispose()`**, asi que cada `create_app()`
    deja vivo un pool entero. Contra PostgreSQL son conexiones TCP que se acumulan
    hasta `max_connections`, y el sintoma (errores de conexion lejos del test que
    los causo) no se parece en nada a la causa. Lo pago medlibra antes que nosotros.
    """
    try:
        from libragenda.database import reset as soltar_engine_anterior

        soltar_engine_anterior()
    except ImportError:  # pragma: no cover - depende de la version pineada
        pass

    if construir_armada is None:
        _PG.restaurar("vacia", _no_hacer_nada)
    else:
        # La base de LibraCore ya esta restaurada (la fixture autouse la dejo ANTES): `create_app`
        # le agrega lo suyo, que es idempotente sobre una base que ya lo tiene.
        _PG.restaurar("armada", lambda url: construir_armada(url, url_libracore()))
    return TEST_DATABASE_URL


def url_libracore() -> str:
    """La URL de la base de LibraCore **de este worker**: **otra base**, en el mismo servidor.

    🔴 **No puede ser el mismo schema que el dominio, y esto no es preferencia.**
    LibraCore y LibraGenda declaran los dos una tabla `clients`, con formas
    incompatibles:

        LibraCore   clients.id  INTEGER PRIMARY KEY AUTOINCREMENT
        LibraGenda  clients.id  VARCHAR(100) PRIMARY KEY

    En SQLite vivian en dos ARCHIVOS distintos y nunca se cruzaban. En un solo
    schema hay una sola tabla: el segundo `CREATE TABLE IF NOT EXISTS` no hace
    nada y no avisa, y despues PostgreSQL rechaza el DDL de LibraCore con
    *"foreign key constraint cannot be implemented: Key columns are of
    incompatible types: integer and character varying"*. Son las nueve FK del
    core que apuntan a `clients(id)`.

    Dos bases en el mismo servidor es la traduccion fiel de los dos archivos, y
    es la topologia que va a necesitar tambien la instancia de produccion.
    """
    return _url_cruda(_PG_CORE.url)


def destino_libracore(ruta_sqlite, construir_armada=None) -> str:  # noqa: ARG001
    """El destino de la base de LIBRACORE (facturacion, caja, ARCA), restaurada de una plantilla.

    Sin `construir_armada`: la plantilla **vacia**, solo el schema de auth (lo que
    dejaba `_preparar_libracore()`). Con ella: la plantilla **armada**.

    🔴 **Esta era la mitad que la suite no ejercitaba.** El conftest le daba un
    archivo SQLite temporal aunque el resto de la corrida fuera a PostgreSQL, asi
    que el verde de este repo no decia nada sobre las ~340 consultas crudas de
    LibraCore. Se vio al cablear [[ventalibra]], que tiene la misma estructura de
    dos bases y las apunto a las dos.
    """
    if construir_armada is None:
        _PG_CORE.restaurar("vacia", _construir_core_vacia)
    else:

        def construir(url: str) -> None:
            _construir_core_vacia(url)
            # `create_app` tambien arma el dominio: se le da el de este worker, limpio. El
            # test lo restaura enseguida (`fresh_database_url`), asi que no queda nada de esto.
            _PG.restaurar("vacia", _no_hacer_nada)
            construir_armada(_PG.url, _url_cruda(url))

        _PG_CORE.restaurar("armada", construir)
    return url_libracore()


def url_para_archivo(ruta) -> str:
    """La URL de una base **en archivo**, para los tests que necesitan que la
    base sobreviva a la app (backup, restore, migraciones).

    Contra PostgreSQL no hay archivo: se devuelve el mismo destino compartido,
    restaurado. El test que de verdad necesite un archivo aparte tiene que
    saltearse solo, no simularlo.
    """
    return fresh_database_url()
