# --- Zona horaria de la suite ---------------------------------------------
# Argentina, UTC-3 fijo, sin horario de verano. Se fija ACA y no se hereda de
# la maquina: el CI y WSL corren en UTC, asi que un test que compare una
# fecha da distinto segun donde se corra, y a las 21:00 de Argentina el
# `date.today()` del proceso ya devuelve manana. Antes de cualquier import
# del producto, porque `tzset()` no alcanza a lo ya importado.
import os as _os
import time as _time

_os.environ["TZ"] = "America/Argentina/Buenos_Aires"
_time.tzset()

import pytest
from fastapi.testclient import TestClient
from libraauth import session_auth as _session_auth
from motor_de_test import TEST_DATABASE_URL, destino_libracore, fresh_database_url, url_libracore

from app.main import create_app

#: La variable que le diria a la app y al motor "LibraCore esta en OTRA base". La suite es de una sola
#: base (ADR-035): ningun test arranca con ella puesta, ni siquiera si quien corre la suite la tiene en
#: su entorno. Los tests de la forma de dos bases (tolerada, ya sin instancias así) la ponen ellos, a
#: mano, con una base propia.
_VARIABLES_DEL_CORE = ("GESTIOLIBRA_LIBRACORE_DATABASE_URL",)


@pytest.fixture(autouse=True)
def _sin_almacen_de_secretos_colgado():
    """El almacen de secretos de `config_manager` no se filtra entre tests.

    `create_app()` llama a `config_manager.usar_almacen_de_secretos(...)`
    (libracore v1.108.0) con un repositorio atado a la base de ESE test, y es un
    global del proceso. Como la base de LibraCore se restaura entre tests (se la
    borra con `FORCE`, ver `motor_de_test.py`), el almacen queda apuntando a
    conexiones que el servidor ya cerro, y el primer test posterior que llame a
    `config_manager.load()` sin levantar su propia app muere con `AdminShutdown`,
    lejisimos de su causa. Lo midio VentaLibra al adoptar las plantillas.

    Antes y despues: antes por si un test anterior lo dejo puesto, despues para
    no ensuciar al que viene. Sin almacen, `config_manager` lee el JSON.
    """
    from libracore import config_manager

    config_manager.usar_almacen_de_secretos(None)
    yield
    config_manager.usar_almacen_de_secretos(None)


#: Las cuatro cadenas del deploy, en el orden de `scripts/panel_admin.py` (lo ata `test_migraciones_en_el_deploy.py`).
_CADENAS_DEL_DEPLOY = (
    ("libragenda-migrar", "upgrade"),
    ("libraauth-migrar", "upgrade", "--prefijo", "gestiolibra", "--base", "dominio"),
    ("libracore-migrar", "upgrade", "--prefijo", "gestiolibra"),
    ("alembic", "upgrade", "head"),
)


def _migrar_como_el_deploy(url: str) -> None:
    """Corre las cuatro cadenas del deploy sobre `url`, en subprocesos y sin variable del core.

    La plantilla "armada" tiene que ser una instancia **migrada**, como la deja el deploy, y no solo lo que crea
    `create_app()` (`create_all`, que no deja ninguna tabla de version). El restore de un backup
    (`POST /api/config/restore`) vuelve a correr las cuatro cadenas contra el backup restaurado: sobre una base sin
    versiones, `libragenda-migrar` muere con `relation "resources" already exists`. Hasta que la suite pasó a una
    sola base eso no se veia: `libragenda-migrar` y `alembic` leen `DATABASE_URL`, que en el CI apunta a un SQLite
    y en una corrida local a la base original, o sea que migraban *otra* base y solo `libracore-migrar` (por la
    variable del core) tocaba la restaurada."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GESTIOLIBRA_LIBRACORE_")}
    entorno.update(DATABASE_URL=url, GESTIOLIBRA_DATABASE_URL=url)
    for comando in _CADENAS_DEL_DEPLOY:
        r = subprocess.run([str(Path(sys.executable).parent / comando[0]), *comando[1:]], env=entorno, cwd=raiz,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, f"{' '.join(comando)}: {(r.stderr or r.stdout)[-2000:]}"


def _armar_app(url: str) -> None:
    """Deja la base como la deja `create_app()`: es lo que contiene la plantilla "armada".

    Se corre una vez por worker (ver `motor_de_test.py`), con el mismo entorno que `_dev_env`
    le pone a cada test, sobre una base que ya tiene la cadena de auth, y no deja nada vivo: ni el
    pool del engine de auth, ni el de LibraGenda, ni el almacen de secretos, ni la ruta de
    `libracore.db.core` apuntando a una plantilla (una escritura posterior caeria ahi y la copia
    dejaria de ser la que se restaura).
    """
    import shutil
    import tempfile

    from libracore import config_manager
    from libracore.db import core as libracore_core

    carpeta = tempfile.mkdtemp(prefix="gestiolibra-plantilla-")
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("ENV", "development")
        # Una sola base (ADR-035): ninguna variable del core, como en dev unida y en un alta nueva.
        for nombre in _VARIABLES_DEL_CORE:
            mp.delenv(nombre, raising=False)
        mp.setattr(config_manager, "CONFIG_PATH", f"{carpeta}/config.json")
        mp.setattr(config_manager, "LOGO_DIR", f"{carpeta}/logos")
        mp.setattr(config_manager, "MARCA_DIR", f"{carpeta}/marca")
        _migrar_como_el_deploy(url)
        app = create_app(url)
        app.state.auth_engine.dispose()
    finally:
        mp.undo()
        from libragenda.database import reset as soltar_engine_de_libragenda

        soltar_engine_de_libragenda()
        config_manager.usar_almacen_de_secretos(None)
        libracore_core.configure(url_libracore())
        shutil.rmtree(carpeta, ignore_errors=True)


@pytest.fixture(autouse=True)
def _dev_env(request, monkeypatch, tmp_path):
    # La base (UNA sola, ADR-035) se restaura UNA VEZ POR TEST de una plantilla (ver
    # `motor_de_test.py`): la ARMADA para los tests que usan `admin_client`
    # (`staff_client` lo arrastra en `fixturenames`), la VACIA (solo auth) para el
    # resto, que arma su app o prueba el arranque y las migraciones desde cero.
    usa_admin_client = "admin_client" in request.fixturenames
    # Sin variable del core, aunque este en el entorno de quien corre.
    for nombre in _VARIABLES_DEL_CORE:
        monkeypatch.delenv(nombre, raising=False)
    destino_libracore(tmp_path / "gestiolibra_libracore.db", _armar_app if usa_admin_client else None)
    # 🔴 Y `DATABASE_URL` apuntada a la base de este worker, como en una instancia real (donde ES la base del
    # dominio). Con una sola base ya no hay variable del core, y el restore de un backup corre las cuatro cadenas en
    # subprocesos con el entorno del proceso (`libracore.respaldo_postgres.correr_migraciones`): `libracore-migrar` y
    # `libraauth-migrar` caen a la base del dominio, y `libragenda-migrar` y `alembic` la leen de `DATABASE_URL`. El job
    # del CI define `DATABASE_URL=sqlite:///...ci.db`; sin esto el restore migraba ese archivo (`unable to open
    # database file`) o, peor, migraba SQLite en vez de la base restaurada y el test pasaba sin probar nada.
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    # SessionAuth's SECRET_KEY resolution and the admin bootstrap both
    # fail closed unless ENV=development -- see app/auth.py and
    # app/services/users.py::ensure_default_admin.
    monkeypatch.setenv("ENV", "development")
    # `libracore.config_manager` resuelve sus rutas AL IMPORTARSE, desde
    # DATA_DIR o -- si no esta -- el cwd, que corriendo pytest es la raiz del
    # repo. Setear la variable de entorno aca ya llega tarde, por eso se
    # parchean los atributos del modulo y no el entorno.
    #
    # Sin esto, `test_config_backup.py` escribe `config.json` y `logos/logo.png`
    # EN EL ARBOL DE TRABAJO: guardar los datos de la empresa deja el nombre y
    # el CUIT del test commiteados, y subir el logo graba en `logo_path` la
    # ruta absoluta de la maquina que corrio la suite -- un valor que no puede
    # ser correcto para ninguna otra. El que corre los tests se lleva un ` M
    # config.json` que es facil que se cuele en un commit o un PR.
    #
    # Es el mismo bug que VentaLibra encontro el 2026-07-28 al agregar la
    # config del ticket (ver su tests/conftest.py); aca llego con la pantalla
    # de Configuracion y quedo sin arreglar hasta el 2026-08-16.
    #
    # `CERTS_DIR` no se parchea a proposito: los certificados ARCA de este
    # producto salen de la config de facturacion en la base
    # (`app/routers/billing.py`), no de `config_manager`.
    from libracore import config_manager
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_manager, "LOGO_DIR", str(tmp_path / "logos"))
    # La marca de la instancia (logo y Terminos propios, ADR-092/093) tambien vive en disco.
    monkeypatch.setattr(config_manager, "MARCA_DIR", str(tmp_path / "marca"))


def https_client(app) -> TestClient:
    """SessionAuth's cookie is Secure-flagged (see libracore.auth); httpx's
    cookie jar won't send a Secure cookie back over plain http, and
    TestClient defaults to http://testserver. A dotted hostname is required
    too: httpx's cookie jar domain-matching is unreliable for single-label
    hosts like the default "testserver". This part is real and stays.

    CORRECTION (2026-07-25, investigated in VentaLibra/DECISIONS.md
    ADR-006): the intermittent 401 documented here before as fixed by this
    dotted hostname ("0 failures in 300 iterations") was misdiagnosed. Re-run
    30 clean iterations of this suite after that investigation: 30/30 had at
    least one failure, spread across unrelated test files -- the dotted
    hostname does NOT fix it. The real cause is this machine's WSL2 clock
    jumping ~15s forward/backward recurrently during a test run (confirmed
    with a standalone `time.time()` monitor), which intermittently makes
    itsdangerous's signature/expiry check on SessionAuth's cookie fail even
    though the cookie is valid and was issued moments earlier -- not a
    cookie-jar or domain-matching problem. No code fix exists for this: it's
    an environment issue (see the ADR for what was tried and ruled out:
    thread-limiter, locks, converting everything to `async def`)."""
    return TestClient(app, base_url="https://gestiolibra.test")


@pytest.fixture
def admin_client():
    """Fresh app + logged in as the dev bootstrap admin (admin/admin).

    Entered as a context manager and kept open for the whole test: outside
    a `with` block, TestClient spins up a brand new anyio portal thread per
    request instead of reusing one (see starlette.testclient.TestClient).

    CORRECTION (2026-07-25): this used to blame an "anyio portal thread /
    SQLite StaticPool race" for the intermittent 401 seen mid-test -- see
    the corrected note on `https_client()` above. That theory was never
    confirmed and the real cause (WSL2 clock jumps) has nothing to do with
    threading or connection pooling.
    """
    # La plantilla armada ya la restauro la fixture autouse (`_dev_env`): `fresh_database_url()` no la repite.
    with https_client(create_app(fresh_database_url())) as client:
        response = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200, response.text
        try:
            yield client
        finally:
            # 🔴 Sin esto, cada test deja vivo el pool del engine de auth y la
            # corrida entera se come el `max_connections` del servidor. El
            # sintoma aparece lejos: mueren tests del medio con "too many
            # clients" y el que los causo paso en verde. `fresh_database_url()`
            # ya suelta el engine de LibraGenda; este es el otro.
            motor = getattr(client.app.state, "auth_engine", None)
            if motor is not None:
                motor.dispose()


@pytest.fixture
def staff_client(admin_client: TestClient):
    """A second client logged in as a staff user that admin_client just
    created -- same app/database, separate session/cookie."""
    created = admin_client.post("/users", json={
        "username": "staff-1", "name": "Empleada",
        "password": "staff-pass", "role": "staff",
    })
    assert created.status_code == 201, created.text
    with https_client(admin_client.app) as client:
        response = client.post("/auth/login", json={"username": "staff-1", "password": "staff-pass"})
        assert response.status_code == 200, response.text
        yield client


# ── Términos y Condiciones: aceptados para el resto de la suite ─────────────
#
# Desde libraauth v0.31.0 el motor corta con 403 **cualquier** llamada gateada
# por rol mientras la instancia no haya aceptado la versión vigente del
# contrato. Sin esta excepción, la suite entera se pone roja de golpe: cada
# test que loguea y pide datos recibe el 403 del gate en vez de lo que iba a
# medir, y el rojo no dice nada sobre el dominio.
#
# 🔴 **Esto NO apaga el gate donde importa.** Lo que la suite no puede es medir
# el dominio a través de un corte que no está probando; el corte tiene su propio
# archivo, `test_terminos_gate.py`, que se marca con `sin_aceptar_terminos` y
# queda afuera de esta excepción. Si alguien borrara el cableado de
# `app.state.terminos`, esa marca es lo único que se pondría rojo — el resto de
# la suite seguiría verde, porque no lo mira.


@pytest.fixture(autouse=True)
def _terminos_ya_aceptados(request):
    if request.node.get_closest_marker("sin_aceptar_terminos"):
        yield
        return

    from libraauth.terminos import TerminosRepository

    # 🔴 **`MonkeyPatch()` propio y no el fixture `monkeypatch`.** El fixture es
    # uno solo por test y lo comparten todas las fixtures que lo pidan, asi que
    # un `monkeypatch.undo()` en el cuerpo de un test —que existe, y es
    # legitimo— deshace TAMBIEN este parche y le prende el gate a la mitad del
    # test. El sintoma no se parece a la causa: la llamada siguiente devuelve
    # 403 y el test explota con un `KeyError` sobre la clave que esperaba en el
    # JSON. Lo encontro `test_despues_de_un_fallo_el_boton_puede_emitirlo` de
    # VentaLibra, que era el unico de las seis suites que llama `undo()`.
    mp = pytest.MonkeyPatch()
    mp.setattr(TerminosRepository, "esta_aceptada", lambda self: True)
    yield
    mp.undo()


# ── Captcha ALTCHA: aprobado para el resto de la suite ─────────────────────
#
# Desde libraauth v0.40.0 este producto monta el router con `captcha=True`
# (app/routers/auth.py): el login y el forgot-password exigen la solucion de un
# desafio. La suite postea a `/auth/login` en muchos lugares (los fixtures
# `admin_client` y `staff_client`, los tests de usuarios, de logs, del reset de
# contrasena...) y resolver un desafio en cada uno no prueba nada de este
# producto.
#
# 🔴 **El captcha lo prueba libraauth; aca solo se cablea.** Lo que es de este
# producto —que la ruta exista, que un login sin captcha rebote— lo fija
# `test_captcha_login.py`, que restaura la funcion real con
# `_CAPTCHA_DE_ORIGINAL`. Si alguien sacara `captcha=True` del router, ese
# archivo es lo que se pondria rojo.

#: La funcion real, para que un test pueda volver a ponerla.
_CAPTCHA_DE_ORIGINAL = _session_auth._captcha_de


class _CaptchaQueAprueba:
    """Doble del `Captcha` de libraauth: aprueba cualquier payload.

    `emitir()` delega en un `Captcha` real y barato, para que `GET
    /auth/captcha` siga devolviendo un desafio con la forma de siempre.
    """

    def __init__(self):
        from libraauth.captcha import Captcha

        self._real = Captcha("clave-de-prueba", costo=1, contador_min=1, contador_rango=5)

    def emitir(self) -> dict:
        return self._real.emitir()

    def verificar(self, payload) -> bool:
        return True


_CAPTCHA_DE_PRUEBA = _CaptchaQueAprueba()


@pytest.fixture(autouse=True)
def _captcha_aprobado(monkeypatch):
    """Todo login y forgot-password de la suite pasa el captcha.

    Por que: la suite postea al login en muchos lugares y el captcha lo prueba
    libraauth; aca solo se cablea (ver el bloque de arriba).

    Se parchea la funcion de modulo `libraauth.session_auth._captcha_de`
    porque el router la resuelve por nombre en cada request: parchear
    `app.state.captcha` no alcanzaria a los tests que arman su propia app con
    `create_app(...)`.
    """
    # Desde libraauth v0.50.0 el router la llama con `(request, captcha_usados)`.
    monkeypatch.setattr(
        "libraauth.session_auth._captcha_de", lambda request, usados=None: _CAPTCHA_DE_PRUEBA
    )


# ── Un nodo y su central (ADR-036) ──────────────────────────────────────────

#: Lo que la referencia del escenario deja cargado, para que los tests no repitan los ids.
CUIT_EMISOR = "20111222339"


@pytest.fixture
def escenario(admin_client, monkeypatch, tmp_path):
    """Un nodo y su central, con dos bases (ver `tests/nodo_apoyo.py`).

    La referencia (la sucursal, el recurso, el servicio con su precio, un cliente, dos turnos confirmados y la configuración
    de ARCA) se carga **antes** de copiar la base al central: es lo que el espejo de LibraEdge deja en el nodo. Después la
    instancia pasa a ser el nodo del local, **sin conexión**, y el central tiene registrado ese nodo. `escenario.datos` trae
    los ids de la referencia."""
    from nodo_apoyo import Escenario

    c = admin_client
    assert c.post("/branches", json={"id": "sucursal-1", "name": "Sucursal Centro"}).status_code == 201
    assert c.post("/resources", json={"id": "box-1", "name": "Box 1", "branch_id": "sucursal-1"}).status_code == 201
    assert c.post("/services", json={"id": "corte", "name": "Corte", "duration_minutes": 30}).status_code == 201
    for dia in range(7):
        r = c.post("/resources/box-1/availability", json={"weekday": dia, "starts_at": "00:00:00", "ends_at": "23:59:00"})
        assert r.status_code == 201, r.text
    assert c.put("/services/corte/prices", json={"branch_id": "sucursal-1", "price": "1000.00"}).status_code == 200
    r = c.post("/clients", json={"id": "ana", "name": "Ana Gómez", "cuit": "27111111113",
                                 "condicion_iva": "Consumidor Final"})
    assert r.status_code == 201, r.text
    turnos = []
    for hora in ("10:00", "11:00", "12:00"):
        r = c.post("/appointments", json={"resource_id": "box-1", "service_id": "corte", "client_id": "ana",
                                          "starts_at": f"2099-01-01T{hora}:00"})
        assert r.status_code == 201, r.text
        turno = r.json()["id"]
        assert c.post(f"/appointments/{turno}/confirm").status_code == 200
        turnos.append(turno)
    # El tercer turno tiene una seña de 400 ya cobrada por transferencia: el saldo es de 600.
    sena = c.post(f"/appointments/{turnos[2]}/deposit", json={"amount": "400.00"})
    assert sena.status_code == 201, sena.text
    r = c.post(f"/deposits/{sena.json()['id']}/mark-paid", json={"medio_pago": "transferencia"})
    assert r.status_code == 200, r.text
    r = c.put("/config/arca", json={"empresa": "negocio", "cuit": CUIT_EMISOR, "punto_venta": 3,
                                    "ambiente": "produccion"})
    assert r.status_code == 200, r.text

    e = Escenario(c, monkeypatch, tmp_path)
    e.datos = {"sucursal": "sucursal-1", "recurso": "box-1", "servicio": "corte", "cliente": "ana",
               "turno": turnos[0], "otro_turno": turnos[1], "turno_con_sena": turnos[2], "precio": "1000.00"}
    e.clonar_el_central()
    e.registrar_el_nodo()
    e.ser_nodo()
    try:
        yield e
    finally:
        e.soltar()
