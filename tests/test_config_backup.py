"""Datos de empresa, logo y Datos / Backup — ítems 1, 4 y 5.

Hasta hoy este producto **no tenía ninguna pantalla de configuración**: los
datos de la empresa no se podían cargar, el logo no se podía subir y el backup
era exclusivamente por CLI.

El mecanismo es de `libracore` y tiene sus propios tests ahí. Lo que se prueba
acá es lo que sólo este producto puede verificar:

1. 🔴 Que el backup traiga **las dos bases**. `usuarios` vive en la de
   LibraCore, separada de la del dominio: un backup de una sola no se puede
   restaurar, y **no falla** — da un ZIP que se descarga y pesa poco.
2. Que después de restaurar la app sirva los datos nuevos.
3. Que todo sea admin-only.
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def https_client(app) -> TestClient:
    """Igual que el de `conftest.py`: la cookie de sesión es Secure y httpx no
    la reenvía sobre http plano ni con un host de un solo label. No se importa
    de allá porque `tests/` no es un paquete."""
    return TestClient(app, base_url="https://gestiolibra.test")


@pytest.fixture
def admin_client(tmp_path):
    """⚠️ Fixture propia, con la base del dominio **en un archivo real**.

    La de `conftest.py` usa `sqlite:///:memory:`, y para estos tests no sirve
    por dos motivos, los dos artefactos del entorno y no del producto:

    1. No hay archivo que respaldar, así que el ZIP saldría con una sola base
       y el test de las dos bases fallaría por el motivo equivocado.
    2. `engine.dispose()` sobre una base en memoria **la borra**: la base vive
       en la conexión. En producción siempre es un archivo.
    """
    app = create_app(f"sqlite:///{tmp_path / 'gestiolibra.db'}")
    with https_client(app) as client:
        r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200, r.text
        yield client


@pytest.fixture
def staff_client(admin_client: TestClient):
    creado = admin_client.post("/users", json={
        "username": "staff-1", "name": "Empleada",
        "password": "staff-pass", "role": "staff",
    })
    assert creado.status_code == 201, creado.text
    with https_client(admin_client.app) as client:
        r = client.post("/auth/login", json={"username": "staff-1", "password": "staff-pass"})
        assert r.status_code == 200, r.text
        yield client


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * 40


def _cliente(client, nombre="Ana Pérez"):
    r = client.post("/clients", json={"name": nombre, "email": "ana@ejemplo.com"})
    assert r.status_code == 201, r.text
    return r.json()


# ── 🔴 Las dos bases ──────────────────────────────────────────────────────

def test_el_backup_trae_las_dos_bases(admin_client):
    _cliente(admin_client)

    r = admin_client.get("/api/config/backup-ahora")
    assert r.status_code == 200, r.text

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        bases = sorted(n for n in z.namelist() if n.startswith("bases/"))

    assert len(bases) == 2, f"esperaba dos bases, vinieron {bases}"
    assert any("libracore" in b for b in bases), f"falta la base de usuarios: {bases}"


def test_el_backup_trae_el_logo(admin_client):
    admin_client.post("/api/config/empresa/logo", files={"logo": ("l.png", _png(), "image/png")})

    r = admin_client.get("/api/config/backup-ahora")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert any(n.startswith("datos/logos/") for n in z.namelist()), z.namelist()


# ── El restore tiene efecto ───────────────────────────────────────────────

def test_despues_de_restaurar_la_app_sirve_los_datos_nuevos(admin_client):
    """Sin cerrar y reabrir el pool, el restore devuelve `ok` y el proceso
    sigue leyendo el archivo viejo, sin ninguna señal de error."""
    _cliente(admin_client, "Antes del backup")
    copia = admin_client.get("/api/config/backup-ahora").content

    _cliente(admin_client, "Después del backup")

    r = admin_client.post("/api/config/restore",
                          files={"backup_file": ("b.zip", copia, "application/zip")})
    assert r.status_code == 200, r.text

    nombres = [c["name"] for c in admin_client.get("/clients").json()]
    assert "Antes del backup" in nombres
    assert "Después del backup" not in nombres


def test_la_sesion_sobrevive_al_restore(admin_client):
    """`usuarios` viaja en el backup, así que restaurar reemplaza también la
    base de la sesión. Con el mismo usuario en las dos puntas la cookie sigue
    siendo válida — si no, el admin queda afuera justo después de restaurar."""
    copia = admin_client.get("/api/config/backup-ahora").content
    admin_client.post("/api/config/restore",
                      files={"backup_file": ("b.zip", copia, "application/zip")})

    assert admin_client.get("/auth/me").status_code == 200


def test_se_puede_seguir_escribiendo_despues_de_un_restore(admin_client):
    copia = admin_client.get("/api/config/backup-ahora").content
    admin_client.post("/api/config/restore",
                      files={"backup_file": ("b.zip", copia, "application/zip")})

    assert _cliente(admin_client, "Cliente de después del restore")["id"]


# ── Empresa, logo y gates ─────────────────────────────────────────────────

def test_guardar_y_leer_los_datos_de_empresa(admin_client):
    r = admin_client.put("/api/config/empresa", json={
        "empresa_nombre": "Barbería Suipacha", "empresa_cuit": "20-11111111-9",
    })
    assert r.status_code == 200, r.text
    assert admin_client.get("/api/config/empresa").json()["empresa_nombre"] == "Barbería Suipacha"


def test_subir_y_bajar_el_logo(admin_client):
    r = admin_client.post("/api/config/empresa/logo",
                          files={"logo": ("l.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    assert admin_client.get("/api/config/empresa/logo").content == _png()


def test_el_staff_no_ve_nada_de_configuracion(staff_client):
    for ruta in ("/api/config/empresa", "/api/config/backups", "/api/config/backup-ahora"):
        assert staff_client.get(ruta).status_code == 403, ruta


def test_el_staff_no_restaura(staff_client):
    r = staff_client.post("/api/config/restore",
                          files={"backup_file": ("b.zip", b"x", "application/zip")})
    assert r.status_code == 403
