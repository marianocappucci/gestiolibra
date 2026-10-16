"""`GET /api/consultar-cuit/{cuit}`: el router del motor, montado en este producto.

Completa el alta de un cliente (nombre y condición de IVA) con el padrón de ARCA. Es el mismo router que usan
Contalibra, Restolibra y VentaLibra; acá se fija lo que le toca a Gestiolibra:

- **Lee la config de ARCA que escribe la pantalla de Configuración** (`/config/arca`, tabla `arca_config` del motor).
- **Mismo gate que el alta de un cliente** (`require_admin`) y que la configuración de ARCA (módulo `facturacion`):
  sin sesión es 401, un operador (`staff`) es 403 y con el módulo apagado también, antes de tocar ARCA.
- El cliente de ARCA vive en el motor, así que se simula `libracore.arca_wsaa` y `libracore.arca_wspadron`.
"""

import pytest
from fastapi.testclient import TestClient
from libracore.config_manager import ARCHIVOS_POR_AMBIENTE

from tests.conftest import https_client

CERT, CLAVE = ARCHIVOS_POR_AMBIENTE["homologacion"]
URL = "/api/consultar-cuit/"


@pytest.fixture
def arca_cargada(admin_client, tmp_path, monkeypatch):
    """La config de ARCA cargada por la pantalla (`PUT /config/arca`) y el par de homologación en disco."""
    from libracore import config_manager
    from libracore.db import arca_config

    d = tmp_path / "arca_certs"
    d.mkdir()
    for nombre in (CERT, CLAVE):
        (d / nombre).write_text(nombre)
    monkeypatch.setattr(config_manager, "CERTS_DIR", str(d))

    r = admin_client.put("/config/arca", json={"cuit": "30712345679", "punto_venta": 3, "ambiente": "homologacion"})
    assert r.status_code == 200, r.text
    arca_config.actualizar_arca_config(
        r.json()["empresa"], certificado_path_homologacion=str(d / CERT), clave_path_homologacion=str(d / CLAVE),
    )


PERSONA = {
    "nombre": "ACME SA",
    "domicilio": "Ruta 8 km 5, Pilar, Buenos Aires",
    "iva_condition": "Responsable Inscripto",
    "estado": "ACTIVO",
}


def _padron(monkeypatch, *, persona=None, falla=None, pedidos=None, usados=None):
    """Simula WSAA y WSPadron; `pedidos` junta los CUIT consultados y `usados` lo que se le pasó al WSAA."""
    from libracore import arca_wsaa, arca_wspadron

    async def _autenticar(cert, clave, ambiente, servicio=""):
        if usados is not None:
            usados.update(cert=cert, clave=clave, ambiente=ambiente, servicio=servicio)
        return {"token": "t", "sign": "s"}

    async def _consultar(cuit_emisor, cuit_consultado, *a, **k):
        if pedidos is not None:
            pedidos.append(cuit_consultado)
        if falla is not None:
            raise falla
        return persona

    monkeypatch.setattr(arca_wsaa, "autenticar", _autenticar)
    monkeypatch.setattr(arca_wspadron, "consultar_persona", _consultar)


@pytest.mark.parametrize("cuit", ["123", "abc", "2011111111912"])
def test_cuit_que_no_tiene_11_digitos_da_400(admin_client, arca_cargada, cuit):
    r = admin_client.get(URL + cuit)
    assert r.status_code == 400
    assert r.json() == {"error": "CUIT inválido. Debe tener 11 dígitos."}


def test_sin_config_de_arca_da_503(admin_client):
    r = admin_client.get(URL + "30711111114")
    assert r.status_code == 503
    assert r.json() == {
        "error": "Configurá los certificados ARCA en Configuración para habilitar la consulta de CUIT."
    }


def test_con_el_padron_simulado_da_200_con_los_campos_del_padron(admin_client, arca_cargada, monkeypatch):
    usados = {}
    _padron(monkeypatch, persona=PERSONA, usados=usados)
    r = admin_client.get(URL + "30711111114")
    assert r.status_code == 200, r.text
    assert r.json() == PERSONA
    # Lo que se cargó por la pantalla de ARCA es lo que usa el padrón: el par de ese ambiente, en su servicio.
    assert usados["ambiente"] == "homologacion"
    assert usados["servicio"] == "ws_sr_padron_a13"
    assert usados["cert"].endswith(CERT)


def test_el_cuit_se_limpia_antes_de_consultar(admin_client, arca_cargada, monkeypatch):
    pedidos = []
    _padron(monkeypatch, persona=PERSONA, pedidos=pedidos)
    assert admin_client.get(URL + "30-71111111-4").status_code == 200
    assert pedidos == ["30711111114"]


@pytest.mark.parametrize("falla, estado, mensaje", [
    (RuntimeError("CUIT no encontrado en el padrón de ARCA."), 404, "CUIT no encontrado en el padrón de ARCA."),
    (RuntimeError("Computador no autorizado a acceder al servicio"), 403, "Consulta a Padrón Alcance 13"),
    (RuntimeError("alguna otra cosa de ARCA"), 502, "alguna otra cosa de ARCA"),
    (ValueError("boom"), 500, "Error al consultar ARCA: boom"),
])
def test_los_errores_del_padron_conservan_estado_y_mensaje(admin_client, arca_cargada, monkeypatch, falla, estado, mensaje):
    _padron(monkeypatch, falla=falla)
    r = admin_client.get(URL + "30711111114")
    assert r.status_code == estado, r.text
    assert mensaje in r.json()["error"]


def test_un_operador_no_puede_consultar_igual_que_no_puede_dar_de_alta(admin_client, staff_client, arca_cargada, monkeypatch):
    pedidos = []
    _padron(monkeypatch, persona=PERSONA, pedidos=pedidos)
    # Control: el alta de un cliente también es de admin, así que el gate es el mismo.
    assert staff_client.post("/clients", json={"id": "c-1", "name": "Ana"}).status_code == 403
    assert staff_client.get(URL + "30711111114").status_code == 403
    assert pedidos == []


def test_con_el_modulo_facturacion_apagado_no_se_consulta(admin_client, arca_cargada, monkeypatch):
    pedidos = []
    _padron(monkeypatch, persona=PERSONA, pedidos=pedidos)
    admin_client.app.state.modules.set_enabled("facturacion", False)
    r = admin_client.get(URL + "30711111114")
    assert r.status_code == 403
    assert "error" not in r.json(), "el 403 del módulo no es el de «el certificado no tiene acceso a Padrón»"
    assert pedidos == []


def test_sin_sesion_es_401_y_no_se_toca_arca(admin_client, arca_cargada, monkeypatch):
    pedidos = []
    _padron(monkeypatch, persona=PERSONA, pedidos=pedidos)
    with https_client(admin_client.app) as anonimo:
        assert anonimo.get(URL + "30711111114").status_code == 401
    assert pedidos == []
