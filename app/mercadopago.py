"""MercadoPago en Gestiolibra: qué se monta y con qué registro de clientes.

Todo el mecanismo —firma del webhook, idempotencia, bandeja, ingesta única
compartida con el cron— vive en `libracore`. Acá queda **de dónde salen los
clientes**, que es lo único de este producto.

🔑 **No se factura solo, y es a propósito.** En un negocio de turnos la factura
sale del turno completado (`services.billing.invoice_appointment`), no de un
cobro suelto: un comprobante emitido desde un pago de MercadoPago no
correspondería a ningún turno y quedaría colgado de nada. Los cobros entran a la
bandeja y una persona decide con el botón *Facturar*.

No hace falta una regla especial para eso: el registro de este producto no
expone `auto_facturar` —la agenda no tiene esa bandera por cliente— así que la
condición por omisión del motor nunca da verdadero. Si algún día se quiere
auto-facturar, se le pasa un `debe_auto_facturar` propio y queda escrito acá.
"""

from fastapi import FastAPI

from app.registro_de_clientes import RegistroDeGestiolibra
from app.services.clients import ClientRepository
from libracore.mp_bandeja_router import build_mp_bandeja_router
from libracore.mp_config_router import build_mp_config_router
from libracore.mp_webhook import build_mp_webhook_router


def montar(app: FastAPI, clientes: ClientRepository, *, gates: list) -> None:
    """Monta las tres pantallas y el webhook.

    `gates` son las dependencias del producto —admin + el módulo de
    facturación—; el paquete no las conoce.

    ⚠️ **El webhook va sin gate**: lo llama MercadoPago desde internet, no un
    usuario logueado. Lo que lo protege es la firma HMAC, no una cookie.
    """
    registro = RegistroDeGestiolibra(clientes)
    #: Lo guarda la app para que el cron use ESTE registro y no arme otro con
    #: sus propios criterios. Es la divergencia que en Contalibra dejó al cron
    #: afuera del cambio de los alias.
    app.state.registro_mp = registro

    app.include_router(build_mp_config_router(), dependencies=gates)
    app.include_router(build_mp_bandeja_router(registro=registro), dependencies=gates)
    app.include_router(build_mp_webhook_router(registro=registro))
