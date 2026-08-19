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
    "DepositRow": "seña",
    # Dominio propio de Gestiolibra
    "BranchHoursRow": "horario",
    "BranchContactRow": "contacto",
    "BusinessSettingsRow": "configuracion",
    "ServicePriceRow": "precio",
    "ClientBillingRow": "facturacion",
}

# 🔴 Aca vivia `"AgendaPolicyRow": "politica"`, y estuvo MUERTA desde el dia
# que se escribio. Las dos fechas cuentan la historia sola:
#
#   2026-08-05  nace `AgendaPolicyRow` en libragenda (commit `1935d8e`)
#   2026-08-05  se escribe esta lista, nombrandola (commit `64a2dd6`)
#   ...pero este producto pinea `libragenda@v0.9.0` desde su scaffold, y esa
#   clase **no salio en ningun tag**: no existe en la version instalada.
#
# O sea que quien escribio la lista estaba leyendo el `develop` del motor
# mientras el producto consume un tag anterior. No rompio nada --la lista se
# indexa por nombre de clase, asi que un nombre inexistente no matchea nunca--,
# pero el filtro "politica" se ofrecia en la pantalla de Logs y no podia
# devolver nada, indistinguible de "todavia no se uso".
#
# **Vuelve el dia que libragenda saque un tag con `AgendaPolicyRow` y este
# producto suba el pin**, no antes. Lo cuida `tests/test_auditables.py`, que
# cruza cada clave contra los modelos realmente mapeados: si se la agrega sin
# bumpear, el test se pone rojo.

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
