"""Los secretos de `config.json` viven cifrados, no en el archivo (2026-09-17).

**Estos tests miran el `config.json` CRUDO y la tabla en la base**, no lo que
devuelve `config_manager.load()`. Es a proposito: `load()` devuelve el secreto
en claro por diseño -- para que los ~12 consumidores no cambien -- asi que un
assert sobre `load()` da verde igual con la implementacion vieja, la que
escribia el token en el archivo. Lo unico que distingue una de otra es que
quedo en el disco.

Y se mide a traves del enganche REAL del producto (`app.main.create_app`), no
armando un almacen a mano: lo que este archivo fija es que Gestiolibra lo haya
enchufado, que es la mitad que LibraCore no puede garantizar.

🔴 Gestiolibra no tiene un hook `startup` separado -- `create_app()` ES el
arranque, lo mismo que fija `tests/test_arranque_exige_cadena_libraauth.py`.
Por eso cada test arma su propia app con `create_app(fresh_database_url())` en
vez de pedir un fixture `client`: es el equivalente exacto de ese disparo.
"""
import json
import os

import pytest
from libracore import config_manager as lc_config_manager
from motor_de_test import fresh_database_url
from sqlalchemy import text

from app.main import create_app, migrar_secretos

TOKEN = "APP_USR-1234567890123456-091712-abcdef0123456789-3392230021"


def _crudo():
    with open(lc_config_manager.CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _escribir_crudo(datos):
    """Escribe el archivo como lo dejaba la version vieja, sin pasar por
    `save()` -- que ya enruta al almacen y no dejaria el secreto en el
    archivo--."""
    with open(lc_config_manager.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def _filas_de_secretos(app):
    with app.state.auth_engine.connect() as c:
        return dict(c.execute(text("select clave, valor_cifrado from secretos_instancia")).all())


@pytest.fixture
def app():
    """Una app nueva, contra una base de LibraCore limpia -- mismo disparo que
    `test_arranque_exige_cadena_libraauth.py`: `create_app()` corre
    `exigir_schema_al_dia()` y, ahora, `migrar_secretos()`, en el mismo lugar
    que un arranque real."""
    return create_app(fresh_database_url())


@pytest.fixture(autouse=True)
def _limpio():
    """Sin secretos en el archivo antes y despues. La tabla vive en una base
    que `fresh_database_url()`/`_preparar_libracore()` ya dejan vacia en cada
    test, asi que no hace falta limpiarla aca."""
    if os.path.exists(lc_config_manager.CONFIG_PATH):
        os.unlink(lc_config_manager.CONFIG_PATH)
    yield
    if os.path.exists(lc_config_manager.CONFIG_PATH):
        os.unlink(lc_config_manager.CONFIG_PATH)


def test_el_producto_enchufo_el_almacen(app):
    """Sin esto, todo lo demas es la implementacion vieja: `config_manager`
    sin almacen escribe el secreto en el JSON, exactamente como antes."""
    assert lc_config_manager.almacen_de_secretos() is app.state.secretos_repository


def test_guardar_el_token_no_lo_deja_en_el_archivo(app):
    cfg = lc_config_manager.load()
    cfg["mp_access_token"] = TOKEN
    cfg["empresa_nombre"] = "Compulibra SRL"
    lc_config_manager.save(cfg)

    crudo = _crudo()
    assert crudo["mp_access_token"] == ""
    # Control positivo del mismo barrido: lo que no es secreto si quedo escrito.
    assert crudo["empresa_nombre"] == "Compulibra SRL"
    # Y para los consumidores no cambio nada.
    assert lc_config_manager.load()["mp_access_token"] == TOKEN


def test_en_la_base_tampoco_esta_en_claro(app):
    cfg = lc_config_manager.load()
    cfg["mp_access_token"] = TOKEN
    lc_config_manager.save(cfg)

    filas = _filas_de_secretos(app)
    assert "mp_access_token" in filas
    assert TOKEN not in filas["mp_access_token"]
    assert filas["mp_access_token"].startswith("v1:")


def test_el_arranque_migra_lo_que_la_version_vieja_dejo_en_el_archivo(app):
    """🔑 El caso de las instancias vivas: el archivo tiene los secretos en
    claro, se despliega esta version, y el arranque los mueve solo."""
    _escribir_crudo({
        "empresa_nombre": "Compulibra SRL",
        "mp_access_token": TOKEN,
        "mp_webhook_secret": "firma-del-webhook",
        "email_smtp_password": "la-contrasena",
    })
    assert _crudo()["mp_access_token"] == TOKEN          # el punto de partida

    informe = migrar_secretos(app.state.secretos_repository)

    assert sorted(informe["migradas"]) == [
        "email_smtp_password", "mp_access_token", "mp_webhook_secret",
    ]
    crudo = _crudo()
    for clave in lc_config_manager.CLAVES_SECRETAS:
        assert crudo[clave] == "", f"{clave} sigue en el archivo"
    assert crudo["empresa_nombre"] == "Compulibra SRL"
    assert lc_config_manager.load()["mp_access_token"] == TOKEN
    assert lc_config_manager.load()["mp_webhook_secret"] == "firma-del-webhook"


def test_la_migracion_es_idempotente(app):
    _escribir_crudo({"mp_access_token": TOKEN})
    migrar_secretos(app.state.secretos_repository)
    antes = _filas_de_secretos(app)["mp_access_token"]

    informe = migrar_secretos(app.state.secretos_repository)

    assert informe == {"migradas": [], "ya_estaban": [], "fallaron": {}}
    # No se reescribio: el blob es el mismo, con el mismo nonce.
    assert _filas_de_secretos(app)["mp_access_token"] == antes


def test_el_arranque_de_la_app_corre_la_migracion():
    """El enganche adentro de `create_app()` y no solo la funcion: sin la
    llamada, la migracion existe y nadie la corre."""
    _escribir_crudo({"mp_access_token": TOKEN})
    create_app(fresh_database_url())
    assert _crudo()["mp_access_token"] == ""
    assert lc_config_manager.load()["mp_access_token"] == TOKEN
