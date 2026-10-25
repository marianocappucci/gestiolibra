"""`modulos` pasa a `gestiolibra_modulos` (ADR-034): la migración `0009`, la `0005` y la forma de la tabla del motor.

LibraCore tiene una `modulos` propia (`id` serial, `modulo` UNIQUE, `habilitado` INTEGER) y la de este
producto (`modulo` PRIMARY KEY, `habilitado` BOOLEAN) se llamaba igual. Con una sola base por producto las dos no
pueden convivir y `libracore-unir-bases` corta con cualquier nombre repetido (ADR-078 de libracore).

Se mide sobre PostgreSQL real y con la cadena real, en el orden del deploy (`scripts/panel_admin.py`):
LibraGenda, LibraAuth, LibraCore y la propia. Lo que se ata:

1. **Base nueva**: la `0005` crea `gestiolibra_modulos` directamente, y no hay ninguna `modulos` del producto.
2. **Una sola base nueva**: `libracore-migrar` corre ANTES que la cadena propia y `modulos` ya existe (es la del motor).
   Con el nombre viejo, la `0005` moría con «already exists». Con el nuevo conviven, y la del motor queda como estaba.
3. **Instancia de antes** (la tabla se llamaba `modulos`, con filas): la `0009` la renombra sin perder una fila, y la
   clave primaria cambia de nombre (un `RENAME` de tabla no la mueve y el `modulos_pkey` del motor chocaría).
4. **Reversible**, salvo en una base donde `modulos` ya es la del motor: ahí aborta y dice por qué.
5. **El paso de filas a la del motor** (punto 3 del ADR) es posible: las dos formas son compatibles.

No se levanta la app: la app contra una y dos bases está en `test_una_sola_base.py`.
"""
from __future__ import annotations

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from libraauth import migrar as libraauth_migrar
from libracore import migrar as libracore_migrar
from libragenda import migrar as libragenda_migrar
from motor_de_test import TEST_DATABASE_URL

PREVIA = "0008_sin_users"
NUEVA = "0009_gestiolibra_modulos"


def _cruda(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def base_limpia(monkeypatch):
    """Un `schema public` vacío, y alembic (el de este producto) apuntado a él por el entorno.

    Mismo cuidado que `test_migracion_sin_users.py`: el `env.py` prefiere el entorno a `sqlalchemy.url`, así que
    se pone el nombre normalizado, que `url_de_instancia` prueba antes que `DATABASE_URL` (variable del job de CI,
    que apunta a un SQLite)."""
    monkeypatch.setenv("GESTIOLIBRA_DATABASE_URL", TEST_DATABASE_URL)
    with psycopg.connect(_cruda(TEST_DATABASE_URL), autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def _sql(sentencia: str, *parametros):
    with psycopg.connect(_cruda(TEST_DATABASE_URL), autocommit=True) as c:
        cur = c.execute(sentencia, parametros)
        return cur.fetchall() if cur.description else []


def _tablas() -> set[str]:
    return {f[0] for f in _sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


def _columnas(tabla: str) -> dict[str, str]:
    return dict(_sql(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s", tabla,
    ))


def _clave_primaria(tabla: str) -> str:
    return _sql(
        "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'", tabla,
    )[0][0]


def _filas(tabla: str) -> list[tuple]:
    return _sql(f"SELECT modulo, habilitado, plan FROM {tabla} ORDER BY modulo")


def _libragenda() -> None:
    libragenda_migrar.upgrade(TEST_DATABASE_URL)


def _cadena_del_deploy(cfg, hasta: str = "head") -> None:
    """Las cuatro cadenas en el orden de `scripts/panel_admin.py` (todas contra la misma base)."""
    _libragenda()
    libraauth_migrar.upgrade(TEST_DATABASE_URL)
    libracore_migrar.upgrade(TEST_DATABASE_URL)
    command.upgrade(cfg, hasta)


def _dejar_como_estaba_antes(filas: list[tuple]) -> None:
    """Deja la tabla del producto como la dejaba la `0005` ANTES de ADR-034: se llamaba `modulos`."""
    _sql("ALTER TABLE gestiolibra_modulos RENAME TO modulos")
    _sql("ALTER TABLE modulos RENAME CONSTRAINT gestiolibra_modulos_pkey TO modulos_pkey")
    for modulo, habilitado, plan in filas:
        _sql("INSERT INTO modulos (modulo, habilitado, plan) VALUES (%s, %s, %s)", modulo, habilitado, plan)


FILAS_DE_UNA_INSTANCIA = [
    ("dashboard", False, "basico"),
    ("facturacion", False, "basico"),
    ("recordatorios", True, "estandar"),
    ("resguardo_externo", True, "addon"),
    ("senas", True, "estandar"),
]


# ── 1. Base nueva ────────────────────────────────────────────────────────────

def test_base_nueva_crea_gestiolibra_modulos_y_ninguna_modulos_del_producto(base_limpia):
    _libragenda()
    command.upgrade(base_limpia, "head")

    tablas = _tablas()
    assert "gestiolibra_modulos" in tablas
    assert "modulos" not in tablas
    assert _clave_primaria("gestiolibra_modulos") == "gestiolibra_modulos_pkey"
    assert _columnas("gestiolibra_modulos") == {"modulo": "character varying", "habilitado": "boolean", "plan": "character varying"}


def test_client_billing_apunta_a_agenda_clients_en_una_base_nueva(base_limpia):
    """La `0003` tiene la FK a `agenda_clients` (LibraGenda v0.14.0): en una base nueva `clients` no existe."""
    _libragenda()
    command.upgrade(base_limpia, "head")

    assert "clients" not in _tablas()
    destino = _sql(
        "SELECT confrelid::regclass::text FROM pg_constraint WHERE conrelid = 'client_billing'::regclass AND contype = 'f'"
    )
    assert destino == [("agenda_clients",)]


# ── 2. Una sola base nueva: conviven con la `modulos` del motor ──────────────

def test_en_una_sola_base_nueva_la_modulos_del_motor_y_la_del_producto_conviven(base_limpia):
    """🔴 El que decide. `libracore-migrar` corre antes que la cadena propia y crea SU `modulos` y SU `clients`.

    Con el nombre viejo la `0005` moría con *relation "modulos" already exists*."""
    _libragenda()
    libraauth_migrar.upgrade(TEST_DATABASE_URL)
    libracore_migrar.upgrade(TEST_DATABASE_URL)
    # Control: la `modulos` que hay ahora es la del motor (con `id`), y está en la misma base que `agenda_clients`.
    assert "id" in _columnas("modulos")
    _sql("INSERT INTO modulos (modulo, habilitado, plan) VALUES ('del_motor', 1, 'estandar')")

    command.upgrade(base_limpia, "head")

    assert "id" in _columnas("modulos"), "la `modulos` del motor no se toca"
    assert _sql("SELECT modulo, habilitado, plan FROM modulos") == [("del_motor", 1, "estandar")]
    assert "id" not in _columnas("gestiolibra_modulos")
    # Y las dos `clients` también conviven: la del motor (id entero) y la de LibraGenda (id de texto).
    assert _columnas("clients")["id"] in ("integer", "bigint")
    assert _columnas("agenda_clients")["id"] == "character varying"
    # Cada cadena con su tabla de versión: ninguna pisa a otra.
    versiones = {t for t in _tablas() if t.startswith("alembic_version")}
    assert {"alembic_version", "alembic_version_libragenda", "alembic_version_gestiolibra"} <= versiones


# ── 3. Instancia de antes ────────────────────────────────────────────────────

def test_una_instancia_de_antes_se_renombra_sin_perder_filas(base_limpia):
    _libragenda()
    command.upgrade(base_limpia, PREVIA)
    _dejar_como_estaba_antes(FILAS_DE_UNA_INSTANCIA)
    assert "gestiolibra_modulos" not in _tablas()
    assert _clave_primaria("modulos") == "modulos_pkey"

    command.upgrade(base_limpia, "head")

    tablas = _tablas()
    assert "modulos" not in tablas and "gestiolibra_modulos" in tablas
    assert _filas("gestiolibra_modulos") == FILAS_DE_UNA_INSTANCIA
    assert _clave_primaria("gestiolibra_modulos") == "gestiolibra_modulos_pkey"
    assert _sql("SELECT version_num FROM alembic_version_gestiolibra") == [(NUEVA,)]


def test_el_renombre_libera_el_nombre_de_la_clave_para_el_motor(base_limpia):
    """Sin renombrar la clave, el `modulos_pkey` quedaba en el schema y el de la `modulos` del motor chocaba."""
    _libragenda()
    command.upgrade(base_limpia, PREVIA)
    _dejar_como_estaba_antes(FILAS_DE_UNA_INSTANCIA)
    command.upgrade(base_limpia, "head")

    nombres = {f[0] for f in _sql("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace")}
    assert "modulos_pkey" not in nombres
    # Control: la `modulos` del motor se puede crear ahora, en esta misma base.
    libraauth_migrar.upgrade(TEST_DATABASE_URL)
    libracore_migrar.upgrade(TEST_DATABASE_URL)
    assert "id" in _columnas("modulos")
    assert _filas("gestiolibra_modulos") == FILAS_DE_UNA_INSTANCIA


def test_una_gestiolibra_modulos_vacia_que_creo_el_arranque_se_descarta(base_limpia):
    """Alguien arrancó la app nueva antes de migrar: `create_all` dejó una `gestiolibra_modulos` vacía."""
    _libragenda()
    command.upgrade(base_limpia, PREVIA)
    _dejar_como_estaba_antes(FILAS_DE_UNA_INSTANCIA)
    _sql("CREATE TABLE gestiolibra_modulos (modulo VARCHAR(50) PRIMARY KEY, habilitado BOOLEAN NOT NULL, plan VARCHAR(20) NOT NULL)")

    command.upgrade(base_limpia, "head")

    assert "modulos" not in _tablas()
    assert _filas("gestiolibra_modulos") == FILAS_DE_UNA_INSTANCIA


def test_con_filas_en_las_dos_aborta_sin_tocar_nada(base_limpia):
    _libragenda()
    command.upgrade(base_limpia, PREVIA)
    _dejar_como_estaba_antes(FILAS_DE_UNA_INSTANCIA)
    _sql("CREATE TABLE gestiolibra_modulos (modulo VARCHAR(50) PRIMARY KEY, habilitado BOOLEAN NOT NULL, plan VARCHAR(20) NOT NULL)")
    _sql("INSERT INTO gestiolibra_modulos VALUES ('otro', true, 'premium')")

    with pytest.raises(RuntimeError, match="no se sabe cual es la buena"):
        command.upgrade(base_limpia, "head")

    assert _filas("modulos") == FILAS_DE_UNA_INSTANCIA
    assert _filas("gestiolibra_modulos") == [("otro", True, "premium")]
    assert _sql("SELECT version_num FROM alembic_version_gestiolibra") == [(PREVIA,)]


def test_repetir_el_upgrade_no_hace_nada(base_limpia):
    _libragenda()
    command.upgrade(base_limpia, PREVIA)
    _dejar_como_estaba_antes(FILAS_DE_UNA_INSTANCIA)
    command.upgrade(base_limpia, "head")

    command.upgrade(base_limpia, "head")
    command.downgrade(base_limpia, PREVIA)
    command.upgrade(base_limpia, "head")

    assert _filas("gestiolibra_modulos") == FILAS_DE_UNA_INSTANCIA


# ── 4. Reversible, salvo en una base donde `modulos` ya es la del motor ──────

def test_el_downgrade_devuelve_el_nombre_viejo_con_sus_filas(base_limpia):
    _libragenda()
    command.upgrade(base_limpia, PREVIA)
    _dejar_como_estaba_antes(FILAS_DE_UNA_INSTANCIA)
    command.upgrade(base_limpia, "head")

    command.downgrade(base_limpia, PREVIA)

    tablas = _tablas()
    assert "modulos" in tablas and "gestiolibra_modulos" not in tablas
    assert _filas("modulos") == FILAS_DE_UNA_INSTANCIA
    assert _clave_primaria("modulos") == "modulos_pkey"


def test_el_downgrade_de_la_0005_borra_la_del_producto_y_nunca_la_del_motor(base_limpia):
    """Cadena entera hacia atrás sobre una base SIN la `modulos` del motor: no queda ninguna."""
    _libragenda()
    command.upgrade(base_limpia, "head")

    command.downgrade(base_limpia, "0004_client_created_at")

    assert not ({"modulos", "gestiolibra_modulos"} & _tablas())


def test_en_una_base_unida_el_downgrade_aborta_y_no_toca_la_modulos_del_motor(base_limpia):
    _cadena_del_deploy(base_limpia)
    _sql("INSERT INTO modulos (modulo, habilitado, plan) VALUES ('del_motor', 1, 'estandar')")

    with pytest.raises(RuntimeError, match="ya existe una `modulos`"):
        command.downgrade(base_limpia, PREVIA)

    assert _sql("SELECT modulo, habilitado, plan FROM modulos") == [("del_motor", 1, "estandar")]
    assert "gestiolibra_modulos" in _tablas()
    assert _sql("SELECT version_num FROM alembic_version_gestiolibra") == [(NUEVA,)]


# ── 5. El paso de las filas a la del motor es posible ────────────────────────

#: El paso de ADR-034, punto 3. **No lo corre ninguna revisión de este PR**: una revisión que ya se aplicó antes de
#: unir no volvería a correr, y copiar al azar dejaría dos fuentes. Lo corre quien cambie la lectura a la del motor.
PASAR_FILAS = """
INSERT INTO modulos (modulo, habilitado, plan)
SELECT modulo, CASE WHEN habilitado THEN 1 ELSE 0 END, plan FROM gestiolibra_modulos
ON CONFLICT (modulo) DO UPDATE SET habilitado = EXCLUDED.habilitado, plan = EXCLUDED.plan
"""


def test_las_dos_formas_de_modulos_son_compatibles_y_el_motor_lee_las_filas_pasadas(base_limpia):
    """Verificado contra el esquema real del motor (no contra una copia a mano): las columnas que importan
    (`modulo`, `habilitado`, `plan`) están en las dos, `modulo` es único en la del motor (el `ON CONFLICT` del paso lo
    necesita), `id` lo pone el motor solo y la diferencia de tipo de `habilitado` (boolean contra integer) se cubre
    con un `CASE`. Y `libracore.db.modulos.get_modulos()` devuelve lo mismo que `ModuleRepository.get_all()`."""
    from libracore.db import core as libracore_core
    from libracore.db import modulos as modulos_del_motor

    _cadena_del_deploy(base_limpia)
    del_producto, del_motor = _columnas("gestiolibra_modulos"), _columnas("modulos")
    assert del_producto["habilitado"] == "boolean" and del_motor["habilitado"] == "integer"
    assert {"modulo", "habilitado", "plan"} <= set(del_motor) and "id" in del_motor
    for modulo, habilitado, plan in FILAS_DE_UNA_INSTANCIA:
        _sql("INSERT INTO gestiolibra_modulos (modulo, habilitado, plan) VALUES (%s, %s, %s)", modulo, habilitado, plan)
    _sql("INSERT INTO modulos (modulo, habilitado, plan) VALUES ('facturacion', 1, 'estandar')")  # ya estaba, distinta

    _sql(PASAR_FILAS)
    _sql(PASAR_FILAS)  # idempotente

    esperadas = {m: h for m, h, _ in FILAS_DE_UNA_INSTANCIA}
    assert _sql("SELECT count(*), count(DISTINCT id) FROM modulos") == [(5, 5)]
    assert _sql("SELECT modulo, habilitado != 0, plan FROM modulos ORDER BY modulo") == sorted(FILAS_DE_UNA_INSTANCIA)
    previo = (libracore_core._db_path, libracore_core._database_url)
    try:
        libracore_core.configure(TEST_DATABASE_URL)
        assert modulos_del_motor.get_modulos() == esperadas
    finally:
        libracore_core._db_path, libracore_core._database_url = previo
