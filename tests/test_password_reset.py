"""Recuperación de contraseña: el cableado de Gestiolibra sobre libraauth.

La lógica está probada en el motor (libraauth, 25 tests). Lo que se prueba
acá es lo que el motor NO puede probar: que este producto la tenga
efectivamente montada, apuntando a la base donde vive `usuarios`, y que el
flujo entero funcione contra la app real.
"""
from datetime import UTC, datetime, timedelta, timezone

import pytest
from conftest import https_client
from libraauth.models import PasswordResetToken
from libraauth.password_reset import _hash_token
from motor_de_test import fresh_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import create_app


def test_los_endpoints_estan_montados():
    client = https_client(create_app(fresh_database_url()))
    # Sin SMTP configurado responde 503, que es justamente la prueba de que
    # el endpoint existe y llega al servicio (un 404 sería "no montado").
    r = client.post("/auth/forgot-password", json={"identificador": "admin"})
    assert r.status_code == 503


def test_forgot_password_responde_igual_exista_o_no(monkeypatch):
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    app = create_app(fresh_database_url())
    enviados = []
    app.state.password_reset._send_email = lambda **kw: enviados.append(kw)
    client = https_client(app)

    real = client.post("/auth/forgot-password", json={"identificador": "admin"})
    fantasma = client.post("/auth/forgot-password", json={"identificador": "nadie"})

    assert real.status_code == fantasma.status_code == 200
    assert real.json() == fantasma.json()
    # El admin del bootstrap no tiene email cargado, así que tampoco sale un
    # mail para él: la respuesta es igual por diseño, no porque haya
    # coincidido el caso.
    assert enviados == []


def test_flujo_completo_con_un_usuario_con_email(monkeypatch):
    """Punta a punta contra la app real: alta de usuario con email, pedido
    del reset, y login con la contraseña nueva."""
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    app = create_app(fresh_database_url())
    enviados = []
    app.state.password_reset._send_email = lambda **kw: enviados.append(kw)
    app.state.users.create(username="ana", name="Ana", password="vieja123",
                           role="staff", email="ana@empresa.com")
    client = https_client(app)

    assert client.post("/auth/forgot-password",
                       json={"identificador": "ana@empresa.com"}).status_code == 200
    assert len(enviados) == 1
    token = enviados[0]["cuerpo"].split("?token=")[1].split("\n")[0].strip()
    # El link apunta a la pantalla de este producto, no a una genérica.
    assert "/reset-password?token=" in enviados[0]["cuerpo"]

    r = client.post("/auth/reset-password",
                    json={"token": token, "new_password": "nueva-clave-1"})
    assert r.status_code == 200

    assert client.post("/auth/login",
                       json={"username": "ana", "password": "nueva-clave-1"}).status_code == 200
    assert client.post("/auth/login",
                       json={"username": "ana", "password": "vieja123"}).status_code == 401


def test_token_invalido_da_400():
    client = https_client(create_app(fresh_database_url()))
    r = client.post("/auth/reset-password",
                    json={"token": "inventado", "new_password": "nueva-clave-1"})
    assert r.status_code == 400


def test_la_tabla_de_tokens_declara_su_FK_contra_usuarios(admin_client):
    """El invariante que el motor **si** puede chequear.

    `usuarios` vive en la base de LibraCore (no en la del dominio) porque 11
    tablas del motor le declaran FK; si `password_reset_tokens` cayera en la
    otra base, su FK apuntaria a una tabla que ahi no existe.

    🔴 Hasta el 2026-08-25 esto se comprobaba abriendo el ARCHIVO de libracore
    con un engine propio y corriendo `PRAGMA foreign_key_check` --- las dos
    cosas de SQLite, asi que el test se salteaba entero contra PostgreSQL. Con
    SQLite retirado se habria quedado sin correr nunca.

    Reescrito con el mismo proposito y sin depender del motor: se le pregunta al
    catalogo si la FK existe y a que tabla apunta. Sobre PostgreSQL la respuesta
    ademas es fuerte, porque una FK que no resuelve **no se puede crear**: si la
    tabla hubiera caido en otra base, el DDL habria fallado al arrancar la app.
    """
    from sqlalchemy import inspect

    sesiones = admin_client.app.state.smtp_settings.session_factory
    with sesiones() as s:
        fks = inspect(s.get_bind()).get_foreign_keys("password_reset_tokens")

    apuntadas = {fk["referred_table"] for fk in fks}
    assert "usuarios" in apuntadas, (
        f"`password_reset_tokens` no declara FK contra `usuarios`: apunta a "
        f"{apuntadas or 'nada'}. Si la tabla quedo en la base del dominio, su "
        "FK no tiene contra que resolver."
    )


def test_token_vencido_no_sirve(monkeypatch):
    """Un token de recuperacion vencido no deja cambiar la clave.

    Se fuerza el vencimiento escribiendo `expires_at` en el pasado en vez de
    esperar una hora --- el reloj real no participa.

    🔴 Hasta el 2026-08-25 este test se salteaba contra PostgreSQL, y el motivo
    era **incidental**: se armaba su propio engine contra un ARCHIVO para llegar
    a la fila del token. Lo que se dejaba de probar no es incidental --- que un
    token vencido no sirva es de seguridad. Con SQLite retirado se habria
    quedado sin correr nunca.

    Ahora llega a la fila por la sesion de la app, que va al motor que sea, y
    arma la app con el mismo molde que el resto del archivo.
    """
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    app = create_app(fresh_database_url())
    enviados = []
    app.state.password_reset._send_email = lambda **kw: enviados.append(kw)
    app.state.users.create(username="ana", name="Ana", password="vieja123",
                           role="staff", email="ana@empresa.com")
    cliente = https_client(app)
    cliente.post("/auth/forgot-password", json={"identificador": "ana"})
    assert enviados, "no salio ningun mail: sin token no hay nada que vencer"
    token = enviados[0]["cuerpo"].split("?token=")[1].splitlines()[0].strip()

    sesiones = app.state.smtp_settings.session_factory
    with sesiones() as s:
        fila = s.query(PasswordResetToken).filter_by(token_hash=_hash_token(token)).one()
        fila.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
        s.commit()

    assert cliente.post("/auth/reset-password",
                        json={"token": token, "new_password": "nueva-clave-1"}).status_code == 400
    # 🔑 El control de que ese 400 significa algo: la clave vieja sigue valiendo.
    assert cliente.post("/auth/login",
                        json={"username": "ana", "password": "vieja123"}).status_code == 200
