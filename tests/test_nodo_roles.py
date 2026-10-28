"""La matriz de roles del nodo: quién puede entrar a cada ruta de LibraEdge y de la cola (ADR-036).

Una segunda declaración, escrita a mano y **no derivada del código**, de quién tiene que poder entrar a las rutas que suma el
nodo. Si saliera del código, un cambio de guarda movería el código y el test juntos y no se pondría rojo nunca.

- **`NODO`**: las que autentica el secreto del nodo (`carga-inicial` incluida: GestioLibra no declara carga inicial porque la
  autoridad del nodo nace vacía, así que contesta 501 al nodo autenticado). No las decide el rol: una sesión de administrador **no** alcanza (401),
  y sin el secreto tampoco.
- **`CODIGO`**: `POST /sync/v1/vinculacion`, el canje del código. Lo llama el instalador del nodo, sin sesión; lo protegen el
  código (un solo uso, 15 minutos) y el límite de intentos del motor. Anónimo llega al motor (no es 401 ni 403).
- **`SALUD`**: las dos de uptime-kuma, con su propio token: sin la variable, 404.
- **`ADMIN`**: la pantalla «Sucursal sin internet» (`/api/nodos-offline*`), lo que decide sobre un documento fiscal de la
  cola (reintentar, descartar y marcar emitido) y la configuración y el registro de los avisos (`/api/avisos*`). Un operador
  (`staff`) recibe 403.
- **`STAFF`**: ver la cola, pedir que se emita, la barra de estado y la lista «Turnos a revisar». Cualquier usuario.

**Cobertura.** Una ruta nueva de estos prefijos que la tabla no conoce hace fallar `test_toda_ruta_tiene_fila`: un router que
alguien monta sin decidir quién entra se nota acá. Las filas que ya no existen también fallan.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

NODO, CODIGO, SALUD, ADMIN, STAFF = "NODO", "CODIGO", "SALUD", "ADMIN", "STAFF"

TABLA = {
    ("POST", "/sync/v1/push"): NODO,
    ("GET", "/sync/v1/pull"): NODO,
    ("POST", "/sync/v1/ticket-arca"): NODO,
    ("GET", "/sync/v1/carga-inicial"): NODO,
    ("POST", "/sync/v1/estado-operaciones"): NODO,
    ("POST", "/sync/v1/vinculacion"): CODIGO,
    ("GET", "/sync/v1/salud"): SALUD,
    ("GET", "/sync/v1/salud/{node_id}"): SALUD,
    ("GET", "/api/nodos-offline"): ADMIN,
    ("GET", "/api/nodos-offline/menu"): ADMIN,
    ("POST", "/api/nodos-offline"): ADMIN,
    ("POST", "/api/nodos-offline/vinculacion"): ADMIN,
    ("POST", "/api/nodos-offline/{node_id}/carga"): ADMIN,
    ("POST", "/api/nodos-offline/{node_id}/vinculacion"): ADMIN,
    ("DELETE", "/api/nodos-offline/{node_id}/vinculacion"): ADMIN,
    ("DELETE", "/api/nodos-offline/{node_id}"): ADMIN,
    ("GET", "/api/nodo/conexion"): STAFF,
    ("GET", "/api/nodo/cola"): STAFF,
    ("POST", "/api/nodo/cola/emitir"): STAFF,
    ("POST", "/api/nodo/cola/{pedido_id}/reintentar"): ADMIN,
    ("POST", "/api/nodo/cola/{pedido_id}/descartar"): ADMIN,
    ("POST", "/api/nodo/cola/{pedido_id}/emitido"): ADMIN,
    ("GET", "/api/nodo/turnos-a-revisar"): STAFF,
    ("POST", "/api/nodo/turnos-a-revisar/revisar"): STAFF,
    ("GET", "/api/estado-del-sistema"): STAFF,
    # Los avisos por WhatsApp y mail (ADR-040): la configuración dice con qué cuenta habla el negocio y el registro lleva los teléfonos y los
    # textos de los clientes. Las cuatro son de administrador, también la lectura.
    ("GET", "/api/avisos/config"): ADMIN,
    ("PUT", "/api/avisos/config"): ADMIN,
    ("POST", "/api/avisos/probar"): ADMIN,
    ("GET", "/api/avisos/envios"): ADMIN,
    ("GET", "/appointments/{appointment_id}/comprobante-no-fiscal"): STAFF,
    ("POST", "/appointments/{appointment_id}/start"): STAFF,
    ("POST", "/appointments/{appointment_id}/no-show"): STAFF,
}
PREFIJOS = ("/sync/", "/api/nodos-offline", "/api/nodo/", "/api/estado-del-sistema", "/api/avisos")
#: Las rutas de los turnos que son del nodo (no tienen prefijo propio).
RUTAS_DE_TURNO_DEL_NODO = ("/comprobante-no-fiscal", "/start", "/no-show")


def _rutas_reales(app) -> set[tuple[str, str]]:
    """Las operaciones que publica `openapi.json` bajo los prefijos del nodo. (FastAPI arma las rutas de un router incluido
    de forma perezosa: `app.routes` no las lista, el esquema sí.)"""
    reales = set()
    for camino, operaciones in app.openapi()["paths"].items():
        if camino.startswith(PREFIJOS) or camino.endswith(RUTAS_DE_TURNO_DEL_NODO):
            reales.update((m.upper(), camino) for m in operaciones if m.upper() not in ("HEAD", "OPTIONS"))
    return reales


#: Las rutas del nodo autentican **adentro** del handler, después de leer el cuerpo: con uno mal formado contestan 422 antes
#: de llegar al 401. Se les manda uno bien formado (e inofensivo: el nodo «x» no existe).
CUERPOS = {
    ("POST", "/sync/v1/push"): {
        "operation_id": "x:1", "node_id": "x", "sequence": 1, "operation_type": "turno.atendido",
        "aggregate_type": "turno", "aggregate_id": "x:turno:1", "occurred_at": "2026-10-24T00:00:00+00:00",
        "schema_version": 1, "payload": {}},
    ("POST", "/sync/v1/ticket-arca"): {"node_id": "x", "emisor_id": None, "servicio": "wsfe"},
    ("POST", "/sync/v1/estado-operaciones"): {"node_id": "x", "operation_ids": ["x:1"]},
    ("POST", "/api/nodo/turnos-a-revisar/revisar"): {"atenciones": ["no-existe"]},
}


def _sondeo(cliente, metodo: str, camino: str):
    """Pega con ids que no existen y un cuerpo que no es un objeto: el rol se chequea antes de validar el cuerpo, así que
    quien no debe recibe 401/403 y quien debe recibe otra cosa (422, 404...) sin que se ejecute nada."""
    url = re.sub(r"\{[^}]+\}", "999999", camino)
    if metodo == "GET":
        return cliente.get(url, params={"node_id": "x"})
    return cliente.request(metodo, url, json=CUERPOS.get((metodo, camino), []))


@pytest.fixture
def anonimo(admin_client):
    return TestClient(admin_client.app, base_url="https://gestiolibra.test")


def test_toda_ruta_tiene_fila(admin_client):
    reales = _rutas_reales(admin_client.app)
    assert not reales - set(TABLA), f"rutas del nodo sin fila en la matriz: {sorted(reales - set(TABLA))}"
    assert not set(TABLA) - reales, f"filas de la matriz que ya no existen: {sorted(set(TABLA) - reales)}"


@pytest.mark.parametrize("ruta", [r for r, quien in TABLA.items() if quien == NODO])
def test_las_rutas_del_nodo_las_autentica_el_secreto_y_no_la_sesion(admin_client, anonimo, ruta):
    metodo, camino = ruta
    assert _sondeo(anonimo, metodo, camino).status_code == 401
    # Una sesión de administrador no es el secreto del nodo.
    assert _sondeo(admin_client, metodo, camino).status_code == 401


def test_el_canje_del_codigo_no_pide_sesion(admin_client, anonimo):
    for quien in (anonimo, admin_client):
        r = _sondeo(quien, "POST", "/sync/v1/vinculacion")
        assert r.status_code not in (401, 403), r.text


@pytest.mark.parametrize("ruta", [r for r, quien in TABLA.items() if quien == SALUD])
def test_la_salud_sin_token_de_monitoreo_no_existe(admin_client, anonimo, ruta):
    metodo, camino = ruta
    assert _sondeo(anonimo, metodo, camino).status_code == 404


@pytest.mark.parametrize("ruta", [r for r, quien in TABLA.items() if quien == ADMIN])
def test_las_de_administrador_rechazan_al_anonimo_y_al_operador(admin_client, staff_client, anonimo, ruta):
    metodo, camino = ruta
    assert _sondeo(anonimo, metodo, camino).status_code == 401
    assert _sondeo(staff_client, metodo, camino).status_code == 403
    assert _sondeo(admin_client, metodo, camino).status_code not in (401, 403)


@pytest.mark.parametrize("ruta", [r for r, quien in TABLA.items() if quien == STAFF])
def test_las_de_staff_las_abre_cualquier_usuario_de_la_instancia(admin_client, staff_client, anonimo, ruta):
    metodo, camino = ruta
    assert _sondeo(anonimo, metodo, camino).status_code == 401
    for quien in (staff_client, admin_client):
        assert _sondeo(quien, metodo, camino).status_code not in (401, 403)
