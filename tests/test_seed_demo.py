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

def _estados(api, hoy):
    """⚠️ La ventana se arma con la fecha que devolvió `sembrar()`, no con
    `date.today()`. Ver `test_hay_turnos_pasados_y_futuros`."""
    from datetime import timedelta

    desde, hasta = hoy - timedelta(days=2), hoy + timedelta(days=5)
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
    hoy = sembrar(api)

    estados = _estados(api, hoy)
    assert len(estados) >= 8, f"pocos turnos: {len(estados)}"
    assert len(set(estados)) >= 3, f"un solo estado o dos: {set(estados)}"


def test_hay_turnos_pasados_y_futuros(api):
    """El dashboard mira lo de hoy y la agenda lo que viene. Con todo en el
    mismo día, una de las dos queda vacía."""
    from datetime import date, timedelta

    # ⚠️ **Se pregunta por la fecha que devolvió `sembrar()`, no por
    # `date.today()`.** El mismo test en Restolibra se puso rojo el 2026-08-29 a
    # las 00:04 de Argentina con el código que había pasado en verde una hora
    # antes: `HOY` se resolvía al importar el seed y la suite cruzó la
    # medianoche. Volver a preguntarle a `date.today()` acá reproduce el defecto
    # con una ventana más chica -- entre que `sembrar()` devuelve y el assert
    # corre, el día puede cambiar igual.
    hoy = sembrar(api)

    # 🔑 Control de que la fecha devuelta es realmente «hoy» y no cualquier
    # cosa: sin esto, un `sembrar()` que devolviera una fecha inventada --y
    # sembrara en esa-- pasaría los asserts de abajo sin que la agenda tenga
    # nada el día que el operador la abre. Se admite un día de juego, que es
    # justo el cruce de medianoche que este test dejó de mirar mal.
    assert abs((hoy - date.today()).days) <= 1, (
        f"sembrar() dijo haber sembrado para {hoy}, y hoy es {date.today()}"
    )

    manana = hoy + timedelta(days=1)

    def cuantos(desde, hasta):
        return sum(
            len(api.get(f"/resources/{r['id']}/agenda"
                        f"?date_from={desde}&date_to={hasta}") or [])
            for r in api.get("/resources")
        )

    # 🔴 El turno pasado NO cae en el día calendario anterior: el seed cuenta
    # días HÁBILES, justamente porque un turno corrido a un domingo lo rechaza
    # LibraGenda. Preguntar por "ayer" a secas pasa seis días de cada siete y
    # falla los lunes -- que es como se descubrió, un lunes, con el CI en rojo
    # por un cambio que no tenía nada que ver.
    #
    # Se pregunta por la semana pasada en vez de replicar acá la tabla de
    # horarios del seed: acoplar el test a esa tabla es acoplarlo a lo que
    # justamente está probando. Y sigue fallando si el seed pone todo hoy, que
    # es lo que este test cuida.
    assert cuantos(hoy - timedelta(days=7), hoy - timedelta(days=1)) >= 1
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
    hoy = sembrar(api)
    antes = len(_estados(api, hoy))

    sembrar(api)

    assert len(_estados(api, hoy)) == antes


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


def test_LA_FECHA_NO_SE_RESUELVE_AL_IMPORTAR(monkeypatch):
    """🔴 La guarda del defecto que puso en rojo el CI de Restolibra el 2026-08-29.

    `HOY` era un `date.today()` a nivel de módulo: quedaba congelado en el
    instante del import. Un proceso que importa antes de medianoche y siembra
    después —la suite tarda minutos, y el cron de la demo corre sobre procesos
    que viven días— siembra para AYER, y después la agenda se ve vacía el día
    que alguien la abre.

    No se prueba llamando a `sembrar()`: eso es una corrida entera contra la
    base. Se prueba la pieza que decide la fecha, que es donde vivía el defecto.
    """
    import datetime

    import scripts.seed_demo as seed

    # Se mueve el reloj DESPUÉS de que el módulo ya está importado, que es
    # exactamente el cruce de medianoche a mitad de corrida.
    otro_dia = datetime.date(2031, 7, 4)

    class RelojMovido(datetime.date):
        @classmethod
        def today(cls):
            return otro_dia

    monkeypatch.setattr(seed, "date", RelojMovido)

    assert seed._fijar_hoy() == otro_dia, (
        "la fecha sigue viniendo del import: mover el reloj no la cambió"
    )
    # Y deja el módulo consistente: `_sembrar_turnos` lee `seed.HOY`, no el
    # valor devuelto.
    assert seed.HOY == otro_dia, (
        "`_fijar_hoy` devolvió la fecha nueva pero no actualizó `HOY`, que es "
        "la que usan los sembradores"
    )
