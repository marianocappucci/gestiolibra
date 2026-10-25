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
# Cada test arranca de una base **nueva** y rearmarla es lo que mas cuesta. Medido sobre
# PostgreSQL 16 y libracore v1.118.0, por test: ~0,25 s en el schema de auth
# (`crear_schema_de_auth`, la cadena de Alembic de libraauth), ~0,9 s en `create_app()` (las
# tablas de LibraGenda, el schema del core, los modulos, el admin) y ~0,03 s en vaciar el
# schema. Con `CREATE DATABASE ... TEMPLATE` la base sale de una copia ya armada, ~0,2 s, y
# `create_app()` posterior, ya sobre una base armada, baja a ~0,3 s.
#
# Ojo con el disco: crear y borrar bases fuerza checkpoints, y con 4 workers a la vez
# lo que manda es el `fsync` del servidor, no la CPU. Medido en una maquina cargada, la
# suite entera tardo 335 s con `fsync` y 120 s sin el. Ver `reglas/ci.md` del wiki.
#
# El mecanismo (una base por worker de xdist, plantillas, `FORCE` para echar las
# conexiones del test anterior) vive en `libracore.testing.pg_por_worker`; aca
# queda lo propio de Gestiolibra: que hay en cada plantilla.
#
# 🔑 **UNA sola base por worker** (ADR-035). Hasta el 2026-10-25 eran dos --el dominio y la de
# LibraCore (`gestiolibra_core_gw0`)-- porque LibraCore y LibraGenda declaraban las dos una tabla
# `clients`; desde LibraGenda v0.14.0 la suya es `agenda_clients` y el dominio, LibraAuth y
# LibraCore comparten la base, que es la forma de dev (unida), de un alta nueva y de un nodo de
# LibraEdge. La suite no define ninguna variable del core.
#
# | plantilla | contenido                                                             |
# |-----------|-----------------------------------------------------------------------|
# | `vacia`   | solo el schema de auth (`crear_schema_de_auth`): una instancia recien |
# |           | migrada con `libraauth-migrar`, sin el dominio ni el core             |
# | `armada`  | auth + lo que deja `create_app()` (LibraGenda, LibraCore, modulos)    |
#
# - **vacia** es lo que ven los tests que arman su propia app, prueban el arranque sin la cadena de
#   auth o corren migraciones desde cero. Es lo que antes eran el dominio sin tablas mas el core
#   con solo auth, juntos.
# - **armada** es lo que `admin_client` le hacia a las bases (`create_app()`). Solo la piden los
#   tests que usan `admin_client`; su `create_app` posterior es idempotente sobre ella, que es lo
#   que el producto hace en cada arranque. La arma una funcion `(url) -> None` que pasa el conftest
#   (`construir_armada`), porque `create_app` vive en el producto y no aca.
#
# 🔴 **La base se restaura UNA VEZ POR TEST**, en la fixture autouse (`destino_libracore`), y
# `fresh_database_url()` NO la restaura otra vez (salvo que se le pase `construir_armada`, para el
# test que pide la plantilla a mano). Con dos bases eran dos restauraciones independientes; con una,
# una segunda pisaria lo que el test dejo a proposito (`test_arranque_exige_cadena_libraauth` le borra
# la tabla de version de auth y espera que la app no arranque).
#
# `from motor_de_test import TEST_DATABASE_URL` es como lo leen los tests, asi que
# reasignarla aca alcanza: ninguno compone la URL por su cuenta.
#
# 🔴 Si un test importara `tests.motor_de_test` y otro `motor_de_test` serian DOS
# modulos y este codigo correria dos veces por proceso. `base_por_worker` es
# idempotente a proposito, asi que no recrea la base la segunda vez. Hoy todos
# importan `motor_de_test`.
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


def _construir_auth(url: str) -> None:
    # Las tablas de auth viven en la misma base que el dominio y desde libraauth v0.45.0 el
    # arranque exige su cadena en vez de crearlas. Es el mismo orden que el deploy, donde
    # `libraauth-migrar` va antes de `libracore-migrar`.
    from libraauth.testing import crear_schema_de_auth

    crear_schema_de_auth(_url_cruda(url))


def fresh_database_url(construir_armada=None) -> str:
    """La URL de la base de **este worker**, para un `create_app()` nuevo.

    Sin argumentos devuelve la base tal como la dejo la fixture autouse (`destino_libracore`): no
    restaura nada, y de paso suelta el engine de LibraGenda del test anterior. Con
    `construir_armada` (una funcion `(url) -> None` que deja la base como la deja `create_app()`)
    la restaura de la plantilla **armada**, que se construye la primera vez en cada worker.

    🔴 **Hay que soltar el engine anterior**: `libragenda.database.configure()` reemplaza el engine
    del proceso **sin hacerle `dispose()`**, asi que cada `create_app()` deja vivo un pool entero.
    Contra PostgreSQL son conexiones TCP que se acumulan hasta `max_connections`, y el sintoma
    (errores de conexion lejos del test que los causo) no se parece en nada a la causa. Lo pago
    medlibra antes que nosotros.
    """
    try:
        from libragenda.database import reset as soltar_engine_anterior

        soltar_engine_anterior()
    except ImportError:  # pragma: no cover - depende de la version pineada
        pass

    if construir_armada is not None:
        _restaurar_armada(construir_armada)
    return TEST_DATABASE_URL


def _restaurar_armada(construir_armada) -> None:
    def construir(url: str) -> None:
        _construir_auth(url)
        construir_armada(url)

    _PG.restaurar("armada", construir)


def url_libracore() -> str:
    """La URL de la base de LibraCore: **la misma que la del dominio** (una sola base, ADR-035).

    Sigue existiendo con este nombre porque la leen los tests que miden el arranque y la
    ubicacion de las tablas de auth (`usuarios`, `alembic_version_libraauth`), que desde el
    ADR-035 estan en la base del dominio. Devuelve la forma `postgresql://` de psycopg.

    La forma de DOS bases (ya no la tiene ninguna instancia desde el 2026-10-25; el código la tolera) la miden `tests/test_una_sola_base.py` con
    una base propia y descartable: no es la forma de la suite.
    """
    return _url_cruda(_PG.url)


def destino_libracore(ruta_sqlite, construir_armada=None) -> str:  # noqa: ARG001
    """Deja la base de este worker como nueva, restaurada de una plantilla, y devuelve su URL.

    Es la restauracion UNICA de cada test (la llama la fixture autouse). Sin `construir_armada`:
    la plantilla **vacia**, solo el schema de auth. Con ella: la plantilla **armada**.

    🔴 **Esta era la mitad que la suite no ejercitaba.** El conftest le daba un
    archivo SQLite temporal aunque el resto de la corrida fuera a PostgreSQL, asi
    que el verde de este repo no decia nada sobre las ~340 consultas crudas de
    LibraCore. Se vio al cablear [[ventalibra]].
    """
    if construir_armada is None:
        _PG.restaurar("vacia", _construir_auth)
    else:
        _restaurar_armada(construir_armada)
    return url_libracore()


def url_para_archivo(ruta) -> str:
    """La URL de una base **en archivo**, para los tests que necesitan que la
    base sobreviva a la app (backup, restore, migraciones).

    Contra PostgreSQL no hay archivo: se devuelve la base de este worker, tal como la dejo la
    fixture. El test que de verdad necesite un archivo aparte tiene que saltearse solo, no
    simularlo.
    """
    return fresh_database_url()
