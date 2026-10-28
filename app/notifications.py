"""Los recordatorios de turno salen de verdad, por WhatsApp y por mail (ADR-090 de libracore, ADR-040 de este producto).

`libragenda` es dueña de una sola cosa: la regla «¿toca recordar?» (`ReminderDispatcher.dispatch`) y un puerto, `send(notificacion)`,
que el producto implementa. La notificación trae ids y nada más: ni a quién, ni por qué canal, ni con qué texto. Esos tres son de acá:

- **A quién**: el teléfono y el mail del cliente del turno (`contacto_del_cliente`).
- **Con qué texto**: `RedactorDeRecordatorios`, en criollo y sin datos de más.
- **Cómo sale y que no salga dos veces**: el motor (`libracore.avisos`). El puerto es `NotificacionPorAvisos`, que pone la clave
  `agenda:{turno}:{política}` y deja un registro por canal en `avisos_envios`.

Antes esto era un `LoggingNotificationPort` que escribía una línea al log y daba el recordatorio por enviado. Con el canal apagado o sin
configurar sigue pasando lo mismo (el motor no escribe nada y `libragenda` lo da por visto), así que **una instancia sin WhatsApp ni SMTP
se comporta como siempre**. Lo que cambia es lo que pasa cuando hay un canal: el recordatorio sale.

🔴 `dispatch` marca el recordatorio como enviado apenas `send` vuelve, salga o no. Un fallo del proveedor no corta la tanda (el adaptador
no levanta) y queda `fallido` en el registro: lo vuelve a mandar `reintentar_avisos`, que corre **en la misma llamada pero ANTES de
`dispatch`** (`despachar_recordatorios`: la usan la ruta `POST /reminders/dispatch` y `scripts/despachar_recordatorios.py`). El orden
importa: después de `dispatch`, un fallo de esta misma pasada se reintentaría al instante y gastaría 2 de los 3 intentos en el mismo
segundo (con Evolution caído, los dos fallarían igual); antes, cada reintento espera a la pasada siguiente del cron.
"""
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from libracore import config_manager
from libracore.avisos import Mensaje, Resumen, proveedores, reintentar_fallidos
from libracore.avisos.agenda import NotificacionPorAvisos
from libragenda import ReminderDispatcher, ReminderNotification, ReminderPolicy
from libragenda.timezones import to_branch_local

logger = logging.getLogger("gestiolibra.reminders")

# Fixed for now -- not configurable per branch/service, nobody asked for
# that yet. Change here if the lead times need adjusting.
DEFAULT_REMINDER_POLICIES = [
    ReminderPolicy("24h", timedelta(hours=24)),
    ReminderPolicy("2h", timedelta(hours=2)),
]

#: El huso con el que se escribe la hora cuando el recurso no cuelga de ninguna sucursal. Argentina y no UTC (`SIN_SUCURSAL` de
#: `services/husos.py` es UTC porque ahí sólo importa que el instante no se corra; acá la lee una persona).
HUSO_DEL_MENSAJE = "America/Argentina/Buenos_Aires"

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def contacto_del_cliente(clients) -> Callable[[str], Mapping[str, str]]:
    """`contacto(client_id)` para `NotificacionPorAvisos`: el teléfono y el mail del cliente. Un cliente que ya no existe no tiene
    contacto (el motor deja el aviso `omitido`, no levanta)."""

    def contacto(client_id: str) -> Mapping[str, str]:
        cliente = clients.get(client_id)
        if cliente is None:
            return {}
        return {"telefono": cliente.get("phone") or "", "email": cliente.get("email") or ""}

    return contacto


class RedactorDeRecordatorios:
    """El texto del recordatorio de un turno, para WhatsApp y para mail.

    Dice el negocio, el día y la hora **en la zona de la sede del recurso**, el servicio y con quién. Nada más: ni el precio, ni el
    teléfono del cliente, ni su CUIT. La hora de la notificación es un instante UTC; contarla en UTC le diría al cliente un turno
    tres horas corrido.
    """

    def __init__(self, catalog, business_settings) -> None:
        self._catalog = catalog
        self._business_settings = business_settings

    def __call__(self, notificacion: ReminderNotification, canal: str) -> Mensaje:
        recurso = self._catalog.get_resource(notificacion.resource_id)
        servicio = self._catalog.get_service(notificacion.service_id)
        negocio = self._nombre_del_negocio()
        lineas = [self._cuando(notificacion, recurso, negocio)]
        if servicio is not None:
            lineas.append(f"Servicio: {servicio.name}")
        if recurso is not None:
            lineas.append(f"Con: {recurso.name}")
            sede = self._sede_si_hay_mas_de_una(recurso.branch_id)
            if sede:
                lineas.append(f"Sede: {sede}")
        lineas.append("Si no podés venir, avisanos con tiempo.")
        cuerpo = "\n".join(lineas)
        titulo = "Recordatorio de turno"
        if canal == "whatsapp":
            # En WhatsApp la primera línea, entre asteriscos, hace de título.
            return Mensaje("", cuerpo=f"*{titulo}*\n{cuerpo}")
        return Mensaje("", asunto=f"{titulo} - {negocio}" if negocio else titulo, cuerpo=cuerpo)

    def _nombre_del_negocio(self) -> str:
        """El nombre comercial que carga el administrador; si no, el de la empresa (Configuración > Datos de empresa)."""
        comercial = (self._business_settings.get().get("business_name") or "").strip()
        return comercial or (config_manager.load().get("empresa_nombre") or "").strip()

    def _cuando(self, notificacion: ReminderNotification, recurso, negocio: str) -> str:
        sede = self._catalog.get_branch(recurso.branch_id) if recurso is not None and recurso.branch_id else None
        local = to_branch_local(notificacion.starts_at, sede.timezone if sede is not None else HUSO_DEL_MENSAJE)
        cuando = f"el {_DIAS[local.weekday()]} {local:%d/%m} a las {local:%H:%M} hs"
        return f"{negocio}: tu turno es {cuando}." if negocio else f"Tu turno es {cuando}."

    def _sede_si_hay_mas_de_una(self, branch_id: str | None) -> str:
        """El nombre de la sede, sólo si el negocio tiene más de una: con una sola, decirla es ruido."""
        if not branch_id:
            return ""
        if sum(1 for b in self._catalog.list_branches() if b.active) < 2:
            return ""
        sede = self._catalog.get_branch(branch_id)
        return sede.name if sede is not None else ""


def crear_puerto_de_avisos(*, clients, catalog, business_settings, smtp_config: Callable,
                           nodo: Callable[[], str | None] | None = None) -> NotificacionPorAvisos:
    """El `NotificationPort` de verdad. Los proveedores se resuelven **en cada envío**: prender WhatsApp o cargar el SMTP por pantalla
    tiene efecto sin reiniciar. `nodo` es la identidad del nodo de LibraEdge: un nodo no manda avisos, los manda el central."""
    return NotificacionPorAvisos(
        lambda: proveedores(smtp_config),
        contacto=contacto_del_cliente(clients),
        redactar=RedactorDeRecordatorios(catalog, business_settings),
        nodo=nodo,
    )


def reintentar_avisos(smtp_config: Callable, nodo: Callable[[], str | None] | None = None) -> Callable[[], dict[str, Resumen]]:
    """Lo que corre **antes** de `dispatch`: vuelve a mandar, por cada canal, lo que quedó `fallido` en una pasada anterior (con su tope de intentos)."""

    def reintentar() -> dict[str, Resumen]:
        return {canal: reintentar_fallidos(proveedor, nodo=nodo) for canal, proveedor in proveedores(smtp_config).items()}

    return reintentar


def despachar_recordatorios(dispatcher: ReminderDispatcher, reintentar: Callable[[], dict[str, Resumen]],
                            ahora: datetime | None = None) -> list[ReminderNotification]:
    """Reintenta lo que falló en pasadas anteriores y, a continuación, `dispatch`. Devuelve lo que `dispatch` encontró vencido (la forma
    de siempre de la ruta).

    Los reintentos van **primero** (ver el docstring del módulo) y **no pueden romper** esta llamada: un 500 acá dejaría sin despachar los
    recordatorios nuevos por culpa de un proveedor viejo. Si fallan se loguea la clase del error (nunca su texto: puede traer una URL o
    una clave)."""
    try:
        for canal, resumen in reintentar().items():
            logger.info("avisos %s, reintentos: %s", canal, resumen)
    except Exception as exc:  # noqa: BLE001 - un proveedor mal configurado no puede tumbar el despacho
        logger.error("no se pudieron reintentar los avisos fallidos: %s", type(exc).__name__)
    return dispatcher.dispatch(ahora or datetime.now(UTC))
