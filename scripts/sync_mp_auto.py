#!/usr/bin/env python3
"""Sincronización nocturna de MercadoPago.

    docker exec gestiolibra python3 /app/scripts/sync_mp_auto.py [--dias N]

Trae a la bandeja los cobros que no llegaron por webhook. El trabajo lo hace
`libracore.mp_sync`, que comparte la ingesta con el botón *Sincronizar* de la
bandeja — tenerlas separadas es lo que en Contalibra dejó al cron afuera del
cambio de los alias y costó dos comprobantes al CUIT equivocado.

🔑 **Importa `app.asgi` en vez de rearmar la configuración.** Ese módulo es el
que levanta el contenedor: resuelve la URL del dominio y la de LibraCore con los
mismos criterios, y deja el registro de clientes en `app.state`. Un cron que
reconstruye el cableado por su cuenta es una segunda copia con sus propios
criterios, que es exactamente la clase de divergencia que este trabajo está
cerrando.

🔑 **Acá el cron NO factura solo.** En un negocio de turnos la factura sale del
turno completado, no de un cobro suelto. Los cobros entran a la bandeja y una
persona decide — ver `app/mercadopago.py`.
"""
import asyncio
import logging
import os
import sys

# Este script corre POR RUTA desde cron, asi que sys.path[0] es /app/scripts y
# no /app: sin esto no encuentra el paquete `app`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libracore.mp_sync import sincronizar_y_facturar  # noqa: E402

from app.asgi import app  # noqa: E402  -- configura dominio y libracore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main(argv=None) -> dict:
    import argparse

    parser = argparse.ArgumentParser(description="Sync automatico de MercadoPago")
    parser.add_argument("--dias", type=int, default=2,
                        help="Dias hacia atras a sincronizar (default: 2)")
    args = parser.parse_args(argv)
    return asyncio.run(sincronizar_y_facturar(
        dias=args.dias, registro=app.state.registro_mp,
    ))


if __name__ == "__main__":
    main()
