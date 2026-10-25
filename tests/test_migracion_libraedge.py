"""La migración `0010_libraedge`: las tablas del nodo offline en la cadena del producto (ADR-036).

Se mide sobre PostgreSQL real y con la cadena real, en el orden del deploy. Lo que se ata:

1. **Se crean en toda instancia**, sea nodo o no: un central sin nodos igual las necesita (`node_identity` para autenticar,
   `sync_inbox` para deduplicar). La revisión no consulta la identidad del nodo.
2. **Incluye el mapeo de texto** (`libraedge_mapeo_texto`, libraedge v0.23): el de los ids provisorios de la agenda.
3. **Idempotente** y aditiva: no toca ninguna tabla existente.
4. **Reversible, pero sólo con las tablas vacías**: bajar con operaciones sin sincronizar las tira, y se niega.
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

PREVIA = "0009_gestiolibra_modulos"
NUEVA = "0010_libraedge"

TABLAS_DE_LIBRAEDGE = {
    "node_identity", "local_sequences", "sync_outbox", "sync_inbox", "sync_changelog", "libraedge_mapeo",
    "libraedge_mapeo_texto",
}


def _cruda(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def base_limpia(monkeypatch):
    """Un `schema public` vacío, y alembic (el de este producto) apuntado a él por el entorno (ver
    `test_modulos_renombrados.py`)."""
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


def _cadena_del_deploy(cfg, hasta: str = "head") -> None:
    libragenda_migrar.upgrade(TEST_DATABASE_URL)
    libraauth_migrar.upgrade(TEST_DATABASE_URL)
    libracore_migrar.upgrade(TEST_DATABASE_URL)
    command.upgrade(cfg, hasta)


def test_una_base_nueva_trae_las_tablas_del_nodo_incluido_el_mapeo_de_texto(base_limpia):
    _cadena_del_deploy(base_limpia)
    assert TABLAS_DE_LIBRAEDGE <= _tablas()
    assert _sql("SELECT version_num FROM alembic_version_gestiolibra") == [(NUEVA,)]
    columnas = dict(_sql("SELECT column_name, data_type FROM information_schema.columns "
                         "WHERE table_name = 'libraedge_mapeo_texto'"))
    assert columnas["id_nodo"] == "text" and columnas["id_central"] == "text", "el mapeo de los ids de texto es de texto"


def test_una_instancia_de_antes_la_suma_sin_tocar_nada_de_lo_que_tenia(base_limpia):
    _cadena_del_deploy(base_limpia, PREVIA)
    assert not TABLAS_DE_LIBRAEDGE & _tablas(), "hasta la 0009 no hay nada del nodo"
    _sql("INSERT INTO agenda_clients (id, name, active) VALUES ('ana', 'Ana', true)")
    antes = _tablas() - TABLAS_DE_LIBRAEDGE

    command.upgrade(base_limpia, "head")

    assert TABLAS_DE_LIBRAEDGE <= _tablas()
    assert antes <= _tablas()
    assert _sql("SELECT id, name FROM agenda_clients") == [("ana", "Ana")]


def test_correrla_dos_veces_no_falla(base_limpia):
    _cadena_del_deploy(base_limpia)
    command.downgrade(base_limpia, PREVIA)
    command.upgrade(base_limpia, "head")
    assert TABLAS_DE_LIBRAEDGE <= _tablas()


def test_bajar_con_las_tablas_vacias_las_saca_y_con_datos_se_niega(base_limpia):
    _cadena_del_deploy(base_limpia)
    _sql("INSERT INTO libraedge_mapeo_texto (node_id, tabla, id_nodo, id_central, creado_at) "
         "VALUES ('local-1', 'agenda_clients', '-1', 'ana', now()::text)")
    with pytest.raises(NotImplementedError, match="libraedge_mapeo_texto tiene filas"):
        command.downgrade(base_limpia, PREVIA)
    assert TABLAS_DE_LIBRAEDGE <= _tablas(), "no se tiró nada"

    _sql("DELETE FROM libraedge_mapeo_texto")
    command.downgrade(base_limpia, PREVIA)
    assert not TABLAS_DE_LIBRAEDGE & _tablas()
    assert _sql("SELECT version_num FROM alembic_version_gestiolibra") == [(PREVIA,)]
