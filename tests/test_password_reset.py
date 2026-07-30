"""Recuperación de contraseña: el cableado de Gestiolibra sobre libraauth.

La lógica está probada en el motor (libraauth, 25 tests). Lo que se prueba
acá es lo que el motor NO puede probar: que este producto la tenga
efectivamente montada, apuntando a la base donde vive `usuarios`, y que el
flujo entero funcione contra la app real.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libraauth.models import PasswordResetToken
from libraauth.password_reset import _hash_token

from app.main import create_app
from conftest import https_client


def test_los_endpoints_estan_montados():
    client = https_client(create_app("sqlite:///:memory:"))
    # Sin SMTP configurado responde 503, que es justamente la prueba de que
    # el endpoint existe y llega al servicio (un 404 sería "no montado").
    r = client.post("/auth/forgot-password", json={"identificador": "admin"})
    assert r.status_code == 503


def test_forgot_password_responde_igual_exista_o_no(monkeypatch):
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    app = create_app("sqlite:///:memory:")
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
    app = create_app("sqlite:///:memory:")
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
    client = https_client(create_app("sqlite:///:memory:"))
    r = client.post("/auth/reset-password",
                    json={"token": "inventado", "new_password": "nueva-clave-1"})
    assert r.status_code == 400


def test_la_tabla_de_tokens_queda_en_la_base_de_libracore(tmp_path, monkeypatch):
    """El chequeo que el motor no puede hacer: que la tabla nueva haya
    quedado en el MISMO archivo que `usuarios`.

    `usuarios` vive en la base de LibraCore (no en la del dominio) porque 11
    tablas del motor le declaran FK; si `password_reset_tokens` cayera en la
    otra base, su FK apuntaría a una tabla que ahí no existe.
    """
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    libracore_db = tmp_path / "gestiolibra_libracore.db"
    monkeypatch.setenv("GESTIOLIBRA_LIBRACORE_DB_PATH", str(libracore_db))
    app = create_app(f"sqlite:///{tmp_path}/dominio.db")
    app.state.password_reset._send_email = lambda **kw: None
    app.state.users.create(username="ana", name="Ana", password="vieja123",
                           role="staff", email="ana@empresa.com")
    https_client(app).post("/auth/forgot-password", json={"identificador": "ana"})

    sessions = sessionmaker(bind=create_engine(f"sqlite:///{libracore_db}"))
    with sessions() as s:
        filas = s.query(PasswordResetToken).all()
        assert len(filas) == 1
        # Y la FK resuelve de verdad contra `usuarios` del mismo archivo.
        assert s.execute(
            __import__("sqlalchemy").text("PRAGMA foreign_key_check")
        ).fetchall() == []


def test_token_vencido_no_sirve(tmp_path, monkeypatch):
    """Se fuerza el vencimiento escribiendo `expires_at` en el pasado en vez
    de esperar una hora — el reloj real no participa."""
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    libracore_db = tmp_path / "gestiolibra_libracore.db"
    monkeypatch.setenv("GESTIOLIBRA_LIBRACORE_DB_PATH", str(libracore_db))
    app = create_app(f"sqlite:///{tmp_path}/dominio.db")
    enviados = []
    app.state.password_reset._send_email = lambda **kw: enviados.append(kw)
    app.state.users.create(username="ana", name="Ana", password="vieja123",
                           role="staff", email="ana@empresa.com")
    client = https_client(app)
    client.post("/auth/forgot-password", json={"identificador": "ana"})
    token = enviados[0]["cuerpo"].split("?token=")[1].split("\n")[0].strip()

    sessions = sessionmaker(bind=create_engine(f"sqlite:///{libracore_db}"))
    with sessions() as s:
        fila = s.query(PasswordResetToken).filter_by(token_hash=_hash_token(token)).one()
        fila.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        s.commit()

    assert client.post("/auth/reset-password",
                       json={"token": token, "new_password": "nueva-clave-1"}).status_code == 400
    assert client.post("/auth/login",
                       json={"username": "ana", "password": "vieja123"}).status_code == 200
