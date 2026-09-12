"""Las rutas que tocan algo sincrónico no frenan el loop de uvicorn.

🔴 Gestiolibra corre uvicorn con **un solo proceso**. Una ruta `async def` que
llama sincrónico a la base —un repositorio de LibraGenda, la caja de
LibraCore— o a `openssl` por subproceso frena el loop entero mientras dura:
ningún otro request avanza, `/health` incluido. En un test común no se ve,
porque la ruta contesta bien: lo que hace mal es retener a los demás. Acá se
mide eso y nada más.

Cómo: una llamada de la ruta se reemplaza por una que duerme con `time.sleep`
—bloquea el hilo donde corre, como la consulta real— y, mientras duerme, se
pide `/health` por el **mismo loop**. Si la ruta corre fuera del loop,
`/health` termina antes de que la llamada lenta se despierte; si lo bloquea,
`/health` no puede ni empezar hasta entonces. Se compara contra el instante en
que la llamada lenta **se despertó**, no contra un umbral de tiempo, así que el
resultado no depende de lo rápida que sea la máquina.

🔑 Completar un turno con precio llama a `invoice_appointment`, que es
corrutina pero **mezcla**: la numeración y el CAE van por red, y entre medio
escribe la factura y la caja con el acceso crudo de LibraCore —y en
producción el numerador firma el TRA con `openssl`—. Por eso uno de los dos
casos pone lo lento **adentro** de esa corrutina: pasar la ruta a `def` sin
sacar la corrutina del loop de uvicorn dejaría ese caso en rojo igual.

Es la misma medición que `tests/test_rutas_no_bloquean_el_loop.py` de
Contalibra, Restolibra y LibraCore. Cada caso se probó contra la ruta como
estaba en `origin/develop`: se ponen rojos.
"""
import asyncio
import threading
import time

import httpx
import pytest
from libracore import arca_facturacion

from tests.test_billing import _seeded_appointment

#: Lo que duerme la llamada reemplazada. Alcanza con que sea mucho más que lo
#: que tarda un `/health` sin carga.
LENTO = 0.5

#: El mismo host que `conftest.https_client`: la cookie de sesión es `Secure`
#: y el jar de httpx no la devuelve por http ni a un host de una sola etiqueta.
BASE_URL = "https://gestiolibra.test"


class _Lento:
    """Una llamada sincrónica que tarda.

    `time.sleep` y no `asyncio.sleep` es el punto entero: una consulta a la
    base o `openssl` por subproceso no le ceden el control a nadie.
    """

    def __init__(self):
        self.entro = threading.Event()
        self.desperto_en: float | None = None

    def dormir(self):
        self.entro.set()
        time.sleep(LENTO)
        if self.desperto_en is None:
            self.desperto_en = time.monotonic()


def _mientras_duerme(app, lento: _Lento, pedir, cookies=None):
    """Corre `pedir(cliente)` y, con la llamada lenta ya adentro, un `/health`
    anónimo por el MISMO loop. Devuelve la respuesta del pedido, la de
    `/health` y el instante en que `/health` terminó."""

    async def _correr():
        transporte = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transporte, base_url=BASE_URL,
                              cookies=cookies) as quien_pide,
            httpx.AsyncClient(transport=transporte, base_url=BASE_URL) as anonimo,
        ):
            tarea = asyncio.create_task(pedir(quien_pide))
            # La espera va a un hilo para no ocupar el loop con la espera misma.
            assert await asyncio.to_thread(lento.entro.wait, 10), (
                "la llamada lenta nunca empezó: el parche no intercepta la ruta")
            health = await anonimo.get("/health")
            health_termino = time.monotonic()
            respuesta = await asyncio.wait_for(tarea, 30)
        return respuesta, health, health_termino

    return asyncio.run(_correr())


def _no_bloqueo(lento: _Lento, health, health_termino: float):
    assert health.status_code == 200, health.text
    # Sin esto el test pasaría si el parche no interceptara nada: sin llamada
    # lenta, no hay nada que bloquee.
    assert lento.desperto_en is not None, "la parte lenta no llegó a correr"
    assert health_termino < lento.desperto_en, (
        f"/health terminó {health_termino - lento.desperto_en:.2f}s DESPUÉS de "
        "que se despertara la llamada lenta: la ruta bloqueó el loop mientras dormía"
    )


# ── POST /appointments/{id}/complete ─────────────────────────────────────


def _lectura_del_turno_lenta(app, lento: _Lento, monkeypatch):
    """Lo lento es la primera lectura de la ruta: el turno, de la base del
    dominio por el repositorio sincrónico de LibraGenda."""
    repositorio = app.state.appointment_service.appointments
    real = repositorio.get

    def leer_lento(appointment_id):
        lento.dormir()
        return real(appointment_id)

    monkeypatch.setattr(repositorio, "get", leer_lento)


def _numerador_lento(app, lento: _Lento, monkeypatch):
    """🔑 Lo lento va ADENTRO de `invoice_appointment`: el numerador, que en
    producción autentica contra el WSAA firmando el TRA con `openssl`. Es el
    caso que un `await` desde el loop no resuelve aunque la ruta fuera `def`."""
    real = arca_facturacion.get_next_numero_with_arca

    async def numerar_con_openssl(punto_venta, tipo):
        lento.dormir()
        return await real(punto_venta, tipo)

    monkeypatch.setattr(arca_facturacion, "get_next_numero_with_arca", numerar_con_openssl)


@pytest.mark.parametrize(
    "hacer_lento", [_lectura_del_turno_lenta, _numerador_lento],
    ids=["la-lectura-del-turno", "el-numerador-de-arca"],
)
def test_completar_un_turno_con_factura_no_frena_el_loop(admin_client, monkeypatch, hacer_lento):
    appointment_id = _seeded_appointment(admin_client)
    lento = _Lento()
    hacer_lento(admin_client.app, lento, monkeypatch)

    respuesta, health, fin = _mientras_duerme(
        admin_client.app, lento,
        lambda c: c.post(f"/appointments/{appointment_id}/complete",
                         json={"medio_pago": "efectivo"}),
        cookies=admin_client.cookies,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "completed"
    assert respuesta.json()["factura"] is not None, "el turno tenía que facturarse"
    _no_bloqueo(lento, health, fin)
