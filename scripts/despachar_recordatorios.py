#!/usr/bin/env python3
"""Manda los recordatorios de turno que ya tocan, por WhatsApp y por mail.

    docker exec gestiolibra python3 /app/scripts/despachar_recordatorios.py

Es lo mismo que `POST /reminders/dispatch` sin pasar por HTTP ni por una sesión de administrador, para un cron cada 10 o 15 minutos:
el reintento de lo que quedó `fallido` en la pasada anterior y `ReminderDispatcher.dispatch` (los recordatorios vencidos, 24 h y 2 h
antes), en ese orden (ADR-040). El trabajo lo hace `app.notifications.despachar_recordatorios`, que comparten el script y la ruta: tenerlos separados
es lo que deja a un cron afuera del cambio de una regla.

Es idempotente: el motor no manda dos veces el mismo aviso (clave `agenda:{turno}:{política}`), así que correrlo seguido, o a la vez que
la ruta, no duplica nada.

🔑 **Importa `app.asgi` en vez de rearmar la configuración**, como `sync_mp_auto.py`: ese módulo es el que levanta el contenedor y `create_app()`
enchufa el almacén de secretos (`config_manager.usar_almacen_de_secretos`) y configura `libracore.db.core`. Sin el almacén, Evolution no
tiene la `apikey` y el canal queda sin configurar en silencio.

Termina con código 0 aunque no haya nada que mandar, y con 1 si el despacho mismo levantó (que el cron lo vea).
"""
import logging
import os
import sys

# Este script corre POR RUTA desde cron, asi que sys.path[0] es /app/scripts y
# no /app: sin esto no encuentra el paquete `app`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import offline  # noqa: E402
from app.asgi import app  # noqa: E402  -- configura dominio y libracore
from app.notifications import despachar_recordatorios  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gestiolibra.reminders")


def main() -> int:
    # Un nodo de LibraEdge no manda avisos (los manda el central), y despachar ahí marcaría los recordatorios como vistos sin que salga
    # ninguno. La ruta lo frena con 409; el script, acá.
    if offline.nodo() is not None:
        log.info("este equipo es un nodo de LibraEdge: los recordatorios los despacha el central")
        return 0
    # El módulo `recordatorios` apagado por plan: la ruta da 403 y el script no hace nada.
    if not app.state.modules.is_enabled("recordatorios"):
        log.info("el módulo de recordatorios está apagado en esta instancia")
        return 0
    vencidos = despachar_recordatorios(app.state.reminder_dispatcher, app.state.reintentar_avisos)
    log.info("recordatorios vencidos: %d", len(vencidos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
