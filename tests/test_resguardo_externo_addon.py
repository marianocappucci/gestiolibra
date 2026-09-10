"""El add-on `resguardo_externo` y el enlace de la copia externa.

El router es de LibraCore (`libracore.resguardo_enlace`, v1.93.0) y tiene sus
propios tests ahí. Lo que se prueba acá es lo que sólo este producto decide:

1. 🔴 Que el add-on arranque **apagado**. `ModuleRepository.is_enabled`
   devolvía `True` para todo lo que no estuviera en `TODOS_LOS_MODULOS`, y un
   add-on queda afuera de ese set a propósito: sin su rama propia,
   `require_module("resguardo_externo")` no daba 403 nunca y el add-on quedaba
   prendido en todas las instancias.
2. Que los módulos de plan sigan exactamente como antes.
3. Que el backoffice pueda prenderlo y leerlo por `app.database`, contra la
   misma base que mira la app.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from motor_de_test import TEST_DATABASE_URL
from sqlalchemy import delete

import plans
from app.services.modules import ModuleRow

ADDON = "resguardo_externo"
RUTA = "/api/config/resguardo-externo/enlace"
RAIZ = Path(__file__).resolve().parent.parent


def _addon(client: TestClient, habilitado: bool) -> None:
    client.app.state.modules.set_enabled(ADDON, habilitado)


# ── El gate del add-on ────────────────────────────────────────────────────

def test_sin_fila_el_addon_esta_apagado(admin_client):
    modules = admin_client.app.state.modules
    # Control: la fila de verdad no está, ni después de otro seed. Si el seed
    # sembrara el add-on, este test mediría otra cosa.
    modules.ensure_seeded()
    assert ADDON not in modules.get_all()

    assert modules.is_enabled(ADDON) is False
    assert admin_client.get(RUTA).status_code == 403


def test_con_la_fila_apagada_da_403(admin_client):
    _addon(admin_client, False)
    assert admin_client.app.state.modules.get_all()[ADDON] is False

    assert admin_client.get(RUTA).status_code == 403


def test_prendido_el_enlace_responde(admin_client):
    _addon(admin_client, True)

    r = admin_client.get(RUTA)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert "proveedores" in datos
    assert "enlace" in datos


@pytest.mark.parametrize(("metodo", "sufijo"), [
    ("GET", ""), ("POST", "/drive"), ("GET", "/callback"), ("DELETE", ""),
])
def test_sin_el_addon_ninguna_ruta_del_enlace_responde(admin_client, metodo, sufijo):
    """Las cuatro rutas, no sólo la de lectura: el `DELETE` y el callback
    escriben en `.resguardo/`. Un 403 (y no un 404) dice además que la ruta
    está montada: el gate corre sólo sobre una ruta que matcheó."""
    assert admin_client.request(metodo, RUTA + sufijo).status_code == 403


# ── El rol ────────────────────────────────────────────────────────────────

def test_el_staff_no_entra_aunque_el_addon_este_prendido(admin_client, staff_client):
    _addon(admin_client, True)
    assert admin_client.get(RUTA).status_code == 200  # control: el add-on sí abre

    assert staff_client.get(RUTA).status_code in (401, 403)


def test_sin_sesion_no_entra(admin_client):
    _addon(admin_client, True)
    with TestClient(admin_client.app, base_url="https://gestiolibra.test") as anonimo:
        assert anonimo.get(RUTA).status_code in (401, 403)


# ── Los módulos de plan no cambian ────────────────────────────────────────

def test_un_modulo_de_plan_sin_fila_sigue_prendido(admin_client):
    """Regresión: la rama de los add-ons no puede arrastrar a los módulos de
    plan. Sin fila, un módulo de plan sigue prendido (el default de una
    instancia sin plan asignado), y el core no gateable también."""
    modules = admin_client.app.state.modules
    with modules.session_factory.begin() as session:
        session.execute(delete(ModuleRow).where(ModuleRow.modulo == "facturacion"))
    assert "facturacion" not in modules.get_all()

    assert modules.is_enabled("facturacion") is True
    assert modules.is_enabled("turnos") is True


def test_resguardo_externo_es_addon_y_no_de_plan():
    assert ADDON in plans.ADDONS
    assert ADDON not in plans.TODOS_LOS_MODULOS
    for plan in plans.PLANES:
        assert ADDON not in plans.modulos_de_plan(plan), plan
    assert not (plans.ADDONS & plans.TODOS_LOS_MODULOS)


def test_aplicar_un_plan_no_apaga_el_addon(admin_client):
    """Un add-on se paga aparte: bajar de plan no puede apagarlo."""
    _addon(admin_client, True)

    plans.aplicar_plan_en_db(TEST_DATABASE_URL, "basico")

    modulos = admin_client.app.state.modules.get_all()
    # Control: el plan se aplicó de verdad sobre esta base. Sin esto, un
    # `aplicar_plan_en_db` que escribiera en otro lado dejaba el test verde.
    assert modulos["facturacion"] is False
    assert modulos[ADDON] is True
    assert admin_client.get(RUTA).status_code == 200


# ── El contrato del backoffice ────────────────────────────────────────────

def test_app_database_exporta_el_contrato_del_backoffice():
    """El import textual del snippet de `libracore.admin.services`."""
    from app.database import get_modulos, set_addon

    assert callable(get_modulos)
    assert callable(set_addon)


def _como_el_backoffice(codigo: str) -> str:
    """Corre `codigo` como lo corre el backoffice: un `python3 -c` en un
    proceso NUEVO, donde no hubo `create_app()`, con la URL de la instancia en
    el entorno. Es la única forma honesta de probar el shim: dentro de la suite
    `libracore.db.core` ya está configurado contra la base de LibraCore."""
    entorno = {**os.environ, "GESTIOLIBRA_DATABASE_URL": TEST_DATABASE_URL}
    r = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(RAIZ)!r}); {codigo}"],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_el_backoffice_prende_el_addon_y_la_app_lo_ve(admin_client):
    assert admin_client.get(RUTA).status_code == 403

    _como_el_backoffice(f"from app.database import set_addon; set_addon({ADDON!r}, True)")
    assert admin_client.get(RUTA).status_code == 200

    leido = json.loads(_como_el_backoffice(
        "import json; from app.database import get_modulos; print(json.dumps(get_modulos()))"
    ))
    assert leido[ADDON] is True
    # Control: el shim leyó la tabla del DOMINIO. La de `gestiolibra_core`
    # existe pero está vacía, así que ahí no habría ningún módulo de plan.
    assert leido["facturacion"] is True

    _como_el_backoffice(f"from app.database import set_addon; set_addon({ADDON!r}, False)")
    assert admin_client.get(RUTA).status_code == 403


def test_dentro_de_la_app_el_shim_no_lee_la_base_de_libracore(admin_client):
    """Con la app armada, `libracore.db.core` apunta a `gestiolibra_core`, no a
    la base del dominio. El shim tiene que negarse en vez de leer esa tabla
    `modulos` —vacía— y contestar `{}` como si fuera la verdad."""
    from app.database import get_modulos

    with pytest.raises(RuntimeError, match="base de LibraCore"):
        get_modulos()
