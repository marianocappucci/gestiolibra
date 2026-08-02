"""
Token de servicio en el router de usuarios (2026-08-02).

`/users` es lo único que el backoffice de la suite
(`admin.gestiolibra.com.ar`) necesita y que no puede salir del motor: el router
de usuarios es propio de cada producto. Se le agregó
`json_api_require_admin_o_servicio`, que **amplía un permiso**, así que lo que
importa fijar acá es el borde:

1. Sin `LIBRA_SERVICE_TOKEN` en el entorno, nada cambia.
2. Con la variable puesta, un token equivocado tampoco entra.
3. El ensanchamiento es sólo de `/users`: el resto de los routers admin-only
   siguen exigiendo una sesión de usuario del producto.
"""
import pytest
from fastapi.testclient import TestClient
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER

from app.main import create_app
from conftest import https_client

TOKEN = "un-token-de-servicio-de-prueba"


@pytest.fixture
def sin_sesion():
    """Cliente sin loguear: es como llega el backoffice, que no es usuario."""
    with https_client(create_app("sqlite:///:memory:")) as client:
        yield client


def test_sin_la_variable_el_header_no_sirve(sin_sesion, monkeypatch):
    """La garantía de adopción: una instancia que actualiza y no toca su
    compose se comporta exactamente como antes."""
    monkeypatch.delenv(SERVICE_TOKEN_ENV, raising=False)
    r = sin_sesion.get("/users", headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 401


def test_con_la_variable_el_token_correcto_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.get("/users", headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 200


def test_token_incorrecto_no_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.get("/users", headers={SERVICE_TOKEN_HEADER: "otro"})
    assert r.status_code == 401


def test_sin_header_no_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.get("/users").status_code == 401


def test_el_token_puede_dar_de_alta_un_usuario(sin_sesion, monkeypatch):
    """El caso de uso real del backoffice."""
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.post(
        "/users",
        headers={SERVICE_TOKEN_HEADER: TOKEN},
        json={"username": "ana", "name": "Ana", "password": "clave-inicial", "role": "staff"},
    )
    assert r.status_code == 201
    assert r.json()["username"] == "ana"


# Rutas REALES de otros routers admin-only. Que existan importa: una ruta
# inventada devuelve 404 y el test pasaría sin haber probado nada — pasó
# escribiendo esto, con `/business-settings` y `/availability`, que no existen
# (los prefijos reales son `/business` y `/resources/{id}/availability`).
OTRAS_ADMIN = ["/branches", "/services", "/business"]


def test_las_rutas_de_control_existen(sin_sesion):
    """Guarda contra el falso verde del test de abajo."""
    esquema = sin_sesion.app.openapi()["paths"]
    for ruta in OTRAS_ADMIN:
        assert ruta in esquema, f"{ruta} ya no existe: el test de abajo no mide nada"


@pytest.mark.parametrize("ruta", OTRAS_ADMIN)
def test_el_token_NO_abre_el_resto_de_los_routers_admin(sin_sesion, monkeypatch, ruta):
    """El ensanchamiento es sólo de `/users`, y esto lo fija.

    Si mañana alguien mueve la dependencia a `admin_only` para "simplificar",
    estos casos se ponen rojos — que es exactamente lo que tienen que hacer.
    """
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.get(ruta, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 401, f"{ruta} quedó abierta al token de servicio"


def test_el_admin_de_siempre_sigue_entrando(admin_client: TestClient, monkeypatch):
    """El token se suma, no reemplaza."""
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert admin_client.get("/users").status_code == 200
