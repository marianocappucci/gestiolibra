"""Que audita Gestiolibra — la lista blanca y nada mas.

El mecanismo (los listeners del `flush`, el diff, el ContextVar del usuario, el
repositorio de lectura) vive en `libraauth.auditoria` desde su v0.9.0. Lo unico
que queda en el producto es lo unico que el producto sabe: **cuales de sus
modelos vale la pena auditar**.

Ojo con una particularidad de este producto: **la mayoria de los modelos son de
LibraGenda**, no propios. Se los nombra igual por el nombre de la clase
(`ClientRow`, `AppointmentRow`, …), que es lo que el motor compara.
"""
from libraauth.auditoria import (  # noqa: F401 — re-export para el router y los tests
    BORRAR,
    CREAR,
    EDITAR,
    AuditoriaRepository,
)

# {nombre de la clase del modelo: nombre logico}. El nombre logico es el que ve
# el usuario en el filtro de la pantalla, asi que va en castellano y con el
# vocabulario del producto ("turno", no "appointment").
AUDITABLES: dict[str, str] = {
    # Dominio de LibraGenda
    "ClientRow": "cliente",
    "AppointmentRow": "turno",
    "ServiceRow": "servicio",
    "ResourceRow": "recurso",
    "BranchRow": "sucursal",
    "AvailabilityRow": "disponibilidad",
    "AvailabilityExceptionRow": "excepcion",
    "TimeBlockRow": "bloqueo",
    "HolidayRow": "feriado",
    "AgendaPolicyRow": "politica",
    "DepositRow": "seña",
    # Dominio propio de Gestiolibra
    "BranchHoursRow": "horario",
    "BranchContactRow": "contacto",
    "BusinessSettingsRow": "configuracion",
    "ServicePriceRow": "precio",
    "ClientBillingRow": "facturacion",
}

# Afuera a proposito:
#
# - `AppointmentTransitionRow` y `SentReminderRow` **ya son historial**: la
#   ficha del turno muestra sus transiciones y los recordatorios enviados.
#   Auditarlos pondria el mismo hecho dos veces en la misma pantalla.
# - `AppointmentResourceRow` es la tabla puente turno↔recurso: lo que se ve es
#   el turno, y su alta ya queda registrada.
# - `ModuleRow` la reescribe `ensure_seeded()` en **cada arranque** del
#   contenedor y la cambia el backoffice al aplicar un plan, no una persona
#   usando el sistema. Cada deploy habria dejado filas de "editar modulo" que
#   no le sirven a nadie.
