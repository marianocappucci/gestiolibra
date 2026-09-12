"""El captcha ALTCHA del login, cableado de verdad.

El resto de la suite corre con el captcha aprobado (fixture `_captcha_aprobado`
del conftest): el algoritmo lo prueba libraauth. Lo que es de ESTE producto, y
lo que fija este archivo, es el cableado:

1. Que `GET /auth/captcha` exista y devuelva un desafio con la forma que espera
   el widget de libra-ui (`parameters` + `signature`), sin cache.
2. 🔴 Que un login SIN captcha rebote con 400, aunque la contrasena sea buena.
   Si alguien sacara `captcha=True` de `app/routers/auth.py`, esto es lo que
   se pone rojo. Lo mismo para forgot-password.
3. Que con un desafio resuelto se entre.
"""
import pytest
from conftest import _CAPTCHA_DE_ORIGINAL, https_client
from libraauth.captcha import Captcha
from libraauth.session_auth import CAPTCHA_INVALIDO
from motor_de_test import fresh_database_url

from app.main import create_app

# El admin de arranque en ENV=development, el mismo que usa `admin_client`.
ADMIN_USER = "admin"
ADMIN_PASS = "admin"


@pytest.fixture
def client(monkeypatch):
    """App nueva SIN sesion, con la funcion real de libraauth y un `Captcha`
    barato en el state.

    No se usa `admin_client`: ese fixture ya se loguea, y con la funcion real
    puesta su propio login rebotaria antes de llegar al test. Barato para que
    resolver el desafio tarde milisegundos y no el segundo que cuesta en el
    navegador; el algoritmo es el mismo.
    """
    monkeypatch.setattr("libraauth.session_auth._captcha_de", _CAPTCHA_DE_ORIGINAL)
    app = create_app(fresh_database_url())
    app.state.captcha = Captcha("clave-de-prueba", costo=1, contador_min=1, contador_rango=5)
    with https_client(app) as cliente:
        try:
            yield cliente
        finally:
            # Mismo motivo que en `admin_client`: sin esto el pool del engine
            # de auth queda vivo y la corrida se come el `max_connections`.
            motor = getattr(app.state, "auth_engine", None)
            if motor is not None:
                motor.dispose()


def test_el_desafio_tiene_la_forma_del_widget_y_no_se_cachea(client):
    r = client.get("/auth/captcha")
    assert r.status_code == 200, r.text
    desafio = r.json()
    assert isinstance(desafio.get("parameters"), dict)
    assert isinstance(desafio.get("signature"), str)
    assert "no-store" in r.headers.get("cache-control", "")


def test_login_sin_captcha_rebota_aunque_la_clave_sea_buena(client):
    r = client.post("/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == CAPTCHA_INVALIDO
    # Y no quedo sesion abierta.
    assert client.get("/auth/me").status_code == 401


def test_forgot_password_sin_captcha_rebota(client):
    r = client.post("/auth/forgot-password", json={"identificador": ADMIN_USER})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == CAPTCHA_INVALIDO


def test_login_con_el_desafio_resuelto_entra(client):
    from altcha import Challenge, Payload, solve_challenge

    desafio = Challenge.from_dict(client.get("/auth/captcha").json())
    solucion = Payload(desafio, solve_challenge(desafio)).to_base64()
    r = client.post(
        "/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS, "captcha": solucion},
    )
    assert r.status_code == 200, r.text
    # Y la sesion quedo abierta: no alcanza con el 200 del login.
    assert client.get("/auth/me").status_code == 200


def test_el_login_del_seed_de_la_demo_resuelve_el_captcha(client):
    """🔴 `scripts/seed_demo.py` loguea por la API todas las noches (lo corre
    `reset_demo.sh`). Con el captcha prendido, un seed que no lo resuelva deja
    la demo vacia. Se prueba la misma funcion que corre el cron, con el mismo
    doble de `Api` que usa `test_seed_demo.py`."""
    from test_seed_demo import _ApiDeTest

    from scripts.seed_demo import login

    login(_ApiDeTest(client), ADMIN_USER, ADMIN_PASS)
    assert client.get("/auth/me").status_code == 200
