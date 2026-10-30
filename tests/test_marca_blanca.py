"""La marca blanca esta cableada: la instancia puede tener nombre, color y logo del revendedor (libracore ADR-092).

Lo que se mide aca es el **cableado** del producto, no el motor: que las rutas esten montadas, que escribir las gatee el rol del
producto y que el mail de recuperacion salga con el nombre de la marca. El comportamiento lo prueba `libracore`.
"""
import pytest
from conftest import https_client
from motor_de_test import fresh_database_url

from app.main import create_app
from app.spa import montar_spa

MARCA = {"nombre": "Consultorio Modelo", "nombre_corto": "Modelo", "color": "#c0392b"}


@pytest.fixture
def sin_sesion():
    with https_client(create_app(fresh_database_url())) as client:
        yield client


def test_sin_marca_la_instancia_es_la_del_producto(sin_sesion):
    r = sin_sesion.get("/api/marca")
    assert r.status_code == 200
    assert r.json()["propia"] is False
    assert r.json()["terminos_propios"] is False


def test_el_admin_carga_la_marca_y_cualquiera_la_lee(admin_client):
    assert admin_client.put("/api/marca", json=MARCA).status_code == 200
    leida = https_client(admin_client.app).get("/api/marca").json()  # sin sesion: el login tambien lleva la marca
    assert leida["propia"] is True
    assert leida["nombre"] == "Consultorio Modelo"
    assert leida["color"] == "#c0392b"


@pytest.mark.parametrize("metodo", ["put", "delete"])
def test_sin_sesion_no_se_escribe_la_marca(sin_sesion, metodo):
    r = sin_sesion.request(metodo, "/api/marca", json=MARCA if metodo == "put" else None)
    assert r.status_code in (401, 403)


def test_el_staff_no_escribe_la_marca(staff_client):
    assert staff_client.put("/api/marca", json=MARCA).status_code == 403


def test_sin_sesion_no_se_escriben_los_terminos_propios(sin_sesion):
    r = sin_sesion.put("/api/marca/terminos", json={"version": "r-1.0", "vigente_desde": "01-01-2026", "texto": "x"})
    assert r.status_code in (401, 403)


def test_el_manifest_es_el_de_la_marca_y_no_el_index_de_la_spa(admin_client):
    admin_client.put("/api/marca", json=MARCA)
    r = https_client(admin_client.app).get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["name"] == "Consultorio Modelo"


def test_el_mail_de_recuperacion_sale_con_el_nombre_de_la_marca(admin_client):
    reset = admin_client.app.state.password_reset
    assert reset.product_name == "Gestiolibra"
    admin_client.put("/api/marca", json=MARCA)
    assert reset.product_name == "Consultorio Modelo"
    admin_client.delete("/api/marca")
    assert reset.product_name == "Gestiolibra"


def test_el_manifest_le_gana_al_catch_all_de_la_spa(monkeypatch, tmp_path):
    """🔴 Con un build, la SPA contesta `index.html` a cualquier ruta que no conozca. Si la marca se montara despues, el navegador
    leeria HTML como manifest. Se arma como `app/asgi.py`: la app primero, la SPA encima, con un build de juguete."""
    from app import main as principal

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa-de-prueba</html>", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name": "Gestiolibra", "icons": []}', encoding="utf-8")
    monkeypatch.setattr(principal, "frontend_dist", lambda: dist)
    app = create_app(fresh_database_url())
    montar_spa(app, dist)
    cliente = https_client(app)
    r = cliente.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.json()["name"] == "Gestiolibra", r.text
    assert "manifest" in r.headers["content-type"], r.headers
    assert cliente.get("/api/marca").json()["propia"] is False
    app.state.auth_engine.dispose()
