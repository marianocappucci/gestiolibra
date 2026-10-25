"""La base de LibraCore: la propia o, si no hay, la del dominio (ADR-034 y ADR-035).

GestioLibra llevaba dos bases (`gestiolibra` y `gestiolibra_core`) porque LibraCore y LibraGenda declaraban las dos una
tabla `clients` con `id` de tipos incompatibles. Con LibraGenda v0.14.0 la suya es `agenda_clients` y la `modulos` de este
producto es `gestiolibra_modulos`: ya no hay nombre repetido y el código anda con **una base o con dos** (igual que
LibraClub, ADR-020). **Una sola es la forma de la suite y de todo alta nueva** (ADR-035); dev y demo se unieron el
2026-10-25 (ADR-037) y ya no queda ninguna instancia de dos bases, pero el código las tolera y esa forma se sigue midiendo, con
una base propia y descartable.

Lo que se ata:

1. `url_de_libracore` / `misma_base`: sin variable, o con la misma base (aunque cambie el driver o los parámetros), es la URL
   del dominio TAL CUAL; con otra base, esa; las dos variables (la vigente y la histórica).
2. **La app arranca y anda con una sola base**: auth, LibraGenda y LibraCore en la misma base, y no vuelca la base dos veces
   al respaldar.
3. **Con dos bases (tolerado, ya sin instancias así)** el respaldo lleva las dos y la app usa la del core para `usuarios`.
4. **Una base nueva sin `GESTIOLIBRA_LIBRACORE_*`** migra con las cuatro cadenas del deploy, en su orden, y las tablas de
   auth quedan en la del dominio (`tests/test_cadena_de_una_sola_base.py` mide la cadena entera).
"""
from __future__ import annotations

import contextlib

import psycopg
from libracore.db import caja as db_caja
from motor_de_test import fresh_database_url, url_libracore

from app.config import misma_base, url_de_libracore
from app.main import _instancia_a_respaldar, create_app

DOMINIO = "postgresql+psycopg://u:clave@servidor:5432/gestiolibra"


def _cruda(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


# ── 1. Config ────────────────────────────────────────────────────────────────

def test_misma_base_ignora_driver_parametros_y_barra():
    assert misma_base(DOMINIO, "postgresql://u:clave@servidor:5432/gestiolibra")
    assert misma_base(DOMINIO, DOMINIO + "?sslmode=disable")
    assert misma_base(DOMINIO + "/", DOMINIO)


def test_misma_base_distingue_servidor_usuario_y_nombre():
    assert not misma_base(DOMINIO, DOMINIO + "_core")
    assert not misma_base(DOMINIO, DOMINIO.replace("servidor", "otro"))
    assert not misma_base(DOMINIO, DOMINIO.replace("u:clave", "v:clave"))


def test_sin_variable_del_core_es_la_base_del_dominio_tal_cual():
    assert url_de_libracore(DOMINIO, entorno={}) == DOMINIO


def test_una_variable_vacia_cuenta_como_no_puesta():
    assert url_de_libracore(DOMINIO, entorno={"GESTIOLIBRA_LIBRACORE_DATABASE_URL": "  "}) == DOMINIO


def test_con_la_misma_base_es_la_url_del_dominio_y_no_la_de_la_variable():
    """Un solo valor: quien pregunta no compara cadenas. La variable dice `postgresql://` y el dominio `+psycopg`."""
    entorno = {"GESTIOLIBRA_LIBRACORE_DATABASE_URL": "postgresql://u:clave@servidor:5432/gestiolibra?sslmode=disable"}
    assert url_de_libracore(DOMINIO, entorno=entorno) == DOMINIO


def test_con_otra_base_es_esa():
    core = "postgresql://u:clave@servidor:5432/gestiolibra_core"
    assert url_de_libracore(DOMINIO, entorno={"GESTIOLIBRA_LIBRACORE_DATABASE_URL": core}) == core


def test_el_nombre_historico_de_la_variable_sigue_valiendo():
    """Dev y demo la llevan así en su compose (`GESTIOLIBRA_LIBRACORE_DB_PATH`, que guarda una URL)."""
    core = "postgresql://u:clave@servidor:5432/gestiolibra_core"
    assert url_de_libracore(DOMINIO, entorno={"GESTIOLIBRA_LIBRACORE_DB_PATH": core}) == core
    assert url_de_libracore(DOMINIO, entorno={"GESTIOLIBRA_LIBRACORE_DB_PATH": DOMINIO}) == DOMINIO


def test_el_nombre_vigente_le_gana_al_historico():
    vigente = "postgresql://u:clave@servidor:5432/vigente"
    entorno = {"GESTIOLIBRA_LIBRACORE_DATABASE_URL": vigente, "GESTIOLIBRA_LIBRACORE_DB_PATH": "postgresql://u:clave@servidor:5432/viejo"}
    assert url_de_libracore(DOMINIO, entorno=entorno) == vigente


# ── 2. La app anda con una sola base ─────────────────────────────────────────

def _app_con_una_sola_base(monkeypatch):
    """La base de la suite (auth ya migrada, que deja la fixture autouse) y SIN variable del core: todo en la misma base."""
    monkeypatch.delenv("GESTIOLIBRA_LIBRACORE_DB_PATH", raising=False)
    monkeypatch.delenv("GESTIOLIBRA_LIBRACORE_DATABASE_URL", raising=False)
    url = fresh_database_url()
    return url, create_app(url)


def test_la_app_arranca_y_anda_con_una_sola_base(monkeypatch):
    from conftest import https_client

    url, app = _app_con_una_sola_base(monkeypatch)
    try:
        with https_client(app) as client:
            r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
            assert r.status_code == 200, r.text
            alta = client.post("/clients", json={"name": "Cliente de prueba", "phone": None, "email": None})
            assert alta.status_code == 201, alta.text
            assert [c["name"] for c in client.get("/clients").json()] == ["Cliente de prueba"]
            assert db_caja.get_default_caja_id() is not None  # LibraCore armó su schema en esta base
            assert app.state.modules.is_enabled("facturacion") is True
        with psycopg.connect(_cruda(url)) as c:
            tablas = {f[0] for f in c.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()}
            admins = c.execute("SELECT count(*) FROM usuarios WHERE role = 'admin'").fetchone()[0]
            agenda = c.execute("SELECT count(*) FROM agenda_clients").fetchone()[0]
            core = c.execute("SELECT count(*) FROM clients").fetchone()[0]
            modulos = c.execute("SELECT count(*) FROM gestiolibra_modulos").fetchone()[0]
        # Todo en UNA base: la de auth, la de LibraGenda, la de LibraCore y la tabla de módulos propia.
        assert {"usuarios", "agenda_clients", "clients", "cajas", "modulos", "gestiolibra_modulos"} <= tablas
        assert (admins, agenda, core) == (1, 1, 0)  # el cliente de la agenda no se mezcla con `clients` de LibraCore
        assert modulos > 0
    finally:
        app.state.auth_engine.dispose()


def test_con_una_sola_base_el_respaldo_no_vuelca_la_misma_base_dos_veces(monkeypatch):
    url, app = _app_con_una_sola_base(monkeypatch)
    try:
        instancia = _instancia_a_respaldar(url, url_de_libracore(url), directorios=[])
        assert instancia.postgres_url == url
        assert instancia.postgres_extra == []
    finally:
        app.state.auth_engine.dispose()


# ── 3. Con dos bases (tolerado: ya no lo tiene ninguna instancia) ─────────────────

@contextlib.contextmanager
def _core_aparte(monkeypatch):
    """Una base de LibraCore PROPIA y descartable, con la cadena de auth, y la variable del core apuntada a ella.

    La suite es de una sola base (ADR-035); esta es la forma que tenía la demo hasta el 2026-10-25 y que el código
    sigue tolerando. Se crea en el mismo servidor, con un nombre único por proceso, y se borra al salir (`FORCE`: la app deja su pool vivo)."""
    import uuid
    from urllib.parse import urlsplit, urlunsplit

    from libraauth.testing import crear_schema_de_auth
    from psycopg import sql

    dominio = _cruda(fresh_database_url())
    nombre = f"gestiolibra_core_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(dominio, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
    partes = urlsplit(dominio)
    core = urlunsplit(partes._replace(path=f"/{nombre}"))
    try:
        crear_schema_de_auth(core)
        monkeypatch.setenv("GESTIOLIBRA_LIBRACORE_DATABASE_URL", core)
        yield core
    finally:
        monkeypatch.delenv("GESTIOLIBRA_LIBRACORE_DATABASE_URL", raising=False)
        from libracore.db import core as libracore_core

        libracore_core.configure(url_libracore())
        with psycopg.connect(dominio, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nombre)))


def test_con_dos_bases_el_respaldo_lleva_las_dos(monkeypatch):
    dominio = fresh_database_url()
    with _core_aparte(monkeypatch) as core:
        assert not misma_base(dominio, core)
        instancia = _instancia_a_respaldar(dominio, core, directorios=[])
        assert instancia.postgres_url == dominio
        assert instancia.postgres_extra == [core]


def test_con_dos_bases_la_app_pone_auth_y_libracore_en_la_del_core(monkeypatch):
    """La forma de dos bases (la que tenía la demo) sigue andando: `usuarios` está en la base del core, no en la del dominio."""
    from conftest import https_client

    with _core_aparte(monkeypatch) as core:
        url = fresh_database_url()
        app = create_app(url)
        try:
            with https_client(app) as client:
                r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
                assert r.status_code == 200, r.text
            dominio_del_motor = app.state.auth_engine.url.render_as_string(hide_password=False)
            assert misma_base(dominio_del_motor, core)
            assert not misma_base(dominio_del_motor, url)
            with psycopg.connect(core) as c:
                assert c.execute("SELECT count(*) FROM usuarios WHERE role = 'admin'").fetchone()[0] == 1
                assert c.execute("SELECT count(*) FROM cajas").fetchone()[0] >= 1  # LibraCore armó su schema acá
            with psycopg.connect(_cruda(url)) as c:
                assert c.execute("SELECT count(*) FROM gestiolibra_modulos").fetchone()[0] > 0  # el dominio, el suyo
        finally:
            app.state.auth_engine.dispose()
