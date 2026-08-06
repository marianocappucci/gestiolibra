"""El seed de la demo pública, corrido contra una base limpia.

**Por qué un test y no una corrida a mano contra una instancia.** El cron de
reset borra la base y vuelve a sembrar, así que lo que hay que garantizar es
que el seed funcione *desde cero* — que cada paso encuentre creado lo que
necesita. Probarlo contra una instancia ya sembrada no verifica eso: la mitad
de los pasos cae en la rama "ya estaba".

Y hacerlo acá, contra el `TestClient`, en vez de borrarle la base a una
instancia del VPS: es reproducible, corre en CI, y no deja a nadie sin su
entorno.

Lo que fijan estos tests, en orden de lo que se rompe sin que se note:

1. 🔴 **Que el seed corra entero sobre una base vacía.** El orden importa: los
   precios necesitan el servicio y la sucursal, los turnos necesitan el
   recurso, su disponibilidad **y** el horario de la sucursal. Un paso fuera de
   orden falla sólo la primera vez, o sea justo en el reset.
2. 🔴 **Que deje turnos en más de un estado.** Si todos quedaran pendientes, la
   agenda de la demo mostraría una sola de sus vistas.
3. Que correrlo dos veces no duplique nada — el cron lo va a correr siempre.
4. Que la guarda no deje sembrar la instancia de un cliente.
"""
import pytest

from scripts.seed_demo import Api, sembrar, url_no_productiva


class _ApiDeTest(Api):
    """Habla con el `TestClient` en vez de por red, con la misma interfaz que
    usa `sembrar()`. Así el seed que se prueba es el mismo que corre en
    producción, no una copia."""

    def __init__(self, client):
        self.client = client

    def _pedir(self, metodo, ruta, cuerpo=None):
        # ⚠️ Serializa con `default=str`, **igual que el `Api` real**, y no con
        # el `json=` de httpx. El seed manda objetos `time` y `datetime`, que
        # httpx no sabe serializar: con `json=` el doble fallaba donde el
        # cliente de verdad anda, o sea probaba otra cosa.
        import json as _json

        datos = _json.dumps(cuerpo, default=str) if cuerpo is not None else None
        respuesta = self.client.request(
            metodo, ruta, content=datos,
            headers={"Content-Type": "application/json"} if datos else None,
        )
        if respuesta.status_code >= 400:
            raise RuntimeError(f"{metodo} {ruta} -> {respuesta.status_code}: "
                               f"{respuesta.text[:300]}")
        return respuesta.json() if respuesta.content else None


@pytest.fixture
def api(admin_client):
    return _ApiDeTest(admin_client)


# ── 🔴 Desde cero ─────────────────────────────────────────────────────────

def test_el_seed_corre_entero_sobre_una_base_vacia(api, capsys):
    """El escenario del cron de reset. Si algún paso depende de algo que otro
    crea después, falla acá y no en la madrugada."""
    sembrar(api)

    salida = capsys.readouterr().out
    assert "sucursales   2 creados" in salida
    assert "servicios    5 creados" in salida
    assert "recursos     4 creados" in salida


def test_deja_el_catalogo_completo(api):
    sembrar(api)

    assert len(api.get("/branches")) == 2
    assert len(api.get("/services")) == 5
    assert len(api.get("/resources")) == 4
    assert len(api.get("/clients")) == 6


def test_los_precios_difieren_entre_sucursales(api):
    """Es la razón de que este producto tenga precios por sucursal. Con un
    precio único esa pantalla no dice nada."""
    sembrar(api)

    precios = {p["branch_id"]: p["price"] for p in api.get("/services/corte/prices")}
    assert len(precios) == 2
    assert len(set(precios.values())) == 2, "los dos precios son iguales"


def test_deja_catalogo_activo_e_inactivo(api):
    """Las pantallas distinguen activos de inactivos. Con todo activo, esa
    mitad no se ve."""
    sembrar(api)

    assert any(not s["active"] for s in api.get("/services"))
    assert any(not r["active"] for r in api.get("/resources"))
    assert any(not c["active"] for c in api.get("/clients"))


# ── 🔴 Los turnos, en varios estados ──────────────────────────────────────

def _estados(api):
    from datetime import date, timedelta

    desde, hasta = date.today() - timedelta(days=2), date.today() + timedelta(days=5)
    estados = []
    for r in api.get("/resources"):
        agenda = api.get(f"/resources/{r['id']}/agenda"
                         f"?date_from={desde}&date_to={hasta}") or []
        estados += [t["status"] for t in agenda]
    return estados


def test_deja_turnos_en_mas_de_un_estado(api):
    """🔴 Si todos quedaran pendientes, la agenda mostraría una sola vista. Y
    completar un turno **no es un campo**: hay que confirmarlo primero, así que
    este test también prueba que la cadena de transiciones se hizo bien."""
    sembrar(api)

    estados = _estados(api)
    assert len(estados) >= 8, f"pocos turnos: {len(estados)}"
    assert len(set(estados)) >= 3, f"un solo estado o dos: {set(estados)}"


def test_hay_turnos_pasados_y_futuros(api):
    """El dashboard mira lo de hoy y la agenda lo que viene. Con todo en el
    mismo día, una de las dos queda vacía."""
    from datetime import date, timedelta

    sembrar(api)
    ayer = date.today() - timedelta(days=1)
    manana = date.today() + timedelta(days=1)

    def cuantos(desde, hasta):
        return sum(
            len(api.get(f"/resources/{r['id']}/agenda"
                        f"?date_from={desde}&date_to={hasta}") or [])
            for r in api.get("/resources")
        )

    assert cuantos(ayer, ayer) >= 1
    assert cuantos(manana, manana + timedelta(days=3)) >= 1


# ── Idempotencia ──────────────────────────────────────────────────────────

def test_correrlo_dos_veces_no_duplica(api, capsys):
    """El cron lo va a correr todos los días. Y alguien lo va a correr a mano
    alguna vez sobre una demo ya sembrada."""
    sembrar(api)
    capsys.readouterr()

    sembrar(api)

    salida = capsys.readouterr().out
    assert "sucursales   0 creados, 2 ya estaban" in salida
    assert "servicios    0 creados, 5 ya estaban" in salida
    assert len(api.get("/clients")) == 6


def test_la_segunda_corrida_no_agrega_turnos(api):
    sembrar(api)
    antes = len(_estados(api))

    sembrar(api)

    assert len(_estados(api)) == antes


# ── La guarda ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://demo.gestiolibra.com.ar",
    "https://dev.gestiolibra.com.ar",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
])
def test_donde_si_se_puede_sembrar(url):
    assert url_no_productiva(url) is True


@pytest.mark.parametrize("url", [
    "https://gestiolibra.com.ar",
    "https://cliente.gestiolibra.com.ar",
    # 🔴 Empieza con "demo" pero es un cliente. Con comparación por substring
    # habría pasado.
    "https://demoliciones.gestiolibra.com.ar",
])
def test_donde_NO(url):
    assert url_no_productiva(url) is False
