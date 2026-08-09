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


def corre_contra_postgres() -> bool:
    return TEST_DATABASE_URL.startswith("postgresql")


def fresh_database_url() -> str:
    """La URL para un `create_app()` nuevo, con la base vacia.

    Cada test arma su propia app y espera una base limpia. Con
    `sqlite:///:memory:` eso sale gratis: cada conexion nueva ES una base
    nueva. Un PostgreSQL, en cambio, es **uno solo y compartido** por toda la
    corrida, asi que hay que vaciarlo entre test y test o el segundo ve las
    filas del primero.

    Se borra el SCHEMA y no la base: `DROP DATABASE` exige que no quede ninguna
    conexion abierta, y el engine de la app del test anterior todavia puede
    tener una.

    🔴 **Y hay que soltar el engine anterior, no solo vaciar el schema.**
    `libragenda.database.configure()` reemplaza el engine del proceso **sin
    hacerle `dispose()`**, asi que cada `create_app()` deja vivo un pool
    entero. Con `sqlite:///:memory:` da igual -- es un `StaticPool` de una
    conexion que se recolecta sola -- pero contra PostgreSQL son conexiones TCP
    que se acumulan hasta `max_connections`, y el sintoma (errores de conexion
    lejos del test que los causo) no se parece en nada a la causa. Lo pago
    medlibra antes que nosotros.
    """
    if not corre_contra_postgres():
        return "sqlite:///:memory:"

    import psycopg

    try:
        from libragenda.database import reset as soltar_engine_anterior

        soltar_engine_anterior()
    except ImportError:  # pragma: no cover - depende de la version pineada
        pass

    with psycopg.connect(
        TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1),
        autocommit=True,
    ) as conexion:
        conexion.execute("DROP SCHEMA public CASCADE")
        conexion.execute("CREATE SCHEMA public")
    return TEST_DATABASE_URL


def url_para_archivo(ruta) -> str:
    """La URL de una base **en archivo**, para los tests que necesitan que la
    base sobreviva a la app (backup, restore, migraciones).

    Contra PostgreSQL no hay archivo: se devuelve el mismo destino compartido,
    vaciado. El test que de verdad necesite un archivo aparte tiene que
    saltearse solo, no simularlo.
    """
    if not corre_contra_postgres():
        return f"sqlite:///{ruta}"
    return fresh_database_url()
