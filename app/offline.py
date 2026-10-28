"""La costura de GestioLibra con LibraEdge: lo único del nodo sin conexión que es de este producto (ADR-036).

El nodo es la instancia de GestioLibra que corre en la PC del local y sincroniza con el central (el VPS) por LibraEdge.
Decisión del humano (2026-10-21, 2026-10-22 y 2026-10-25): **la agenda del nodo es de sólo consulta** —no se dan, mueven
ni cancelan turnos—, pero un turno ya dado se puede **atender y cobrar** sin internet; si en la web lo cancelaron o lo
movieron mientras tanto, la atención y lo cobrado valen y el turno queda «a revisar». Lo genérico es de los motores
(el aprovisionamiento y el transporte son de LibraEdge, la atención de un turno es de LibraGenda, la cola de ARCA y la
caja del nodo son de LibraCore); acá queda lo declarativo y las costuras.

| Pieza | Qué aporta este producto |
|---|---|
| `aprovisionamiento` | el reparto de autoridad (qué manda el central y qué espeja el nodo), las altas en el nodo y la sucursal |
| `configurar_atenciones()` | enchufa `libragenda.atencion_en_nodo` (`turno.atendido`) al outbox del nodo |
| `GANCHOS_DE_CAJA` | la caja del nodo (alta y anulación) sube como `caja.movimiento`, con lo propio en `extra` |
| `cola()` / `emisores` | la factura del turno cobrado sin red: la cola de ARCA, con el ticket prestado del central |
| `encolar_operacion` | las operaciones propias (`gestio.*`) y las de la cola |
| `solo_en_el_central` | la guarda del nodo: la agenda, el catálogo y la configuración los manda el central |

## 🔑 Dos casos que no se pueden confundir

- **Una instancia sin nodo** (la demo, el desarrollo, un cliente sin escritorio): `nodo()` es `None`. **Nada cambia**: la
  web opera como siempre, sin 409 y sin outbox. Lo fija `tests/test_nodo_fuera_de_un_nodo.py` y la suite entera.
- **El central de una instancia con nodo vinculado**: sigue operando como siempre (da, mueve y cancela turnos, cobra y
  factura con ARCA). A diferencia de LibraCargo, acá la web **no** pasa a ser de consulta: lo que no se puede hacer es en
  el *nodo*.

## Identidad: `LIBRAEDGE_NODE_ID` (y `GESTIOLIBRA_EDGE_NODE_ID`)

`nodo()` es `libraedge.identidad.nodo_actual("GESTIOLIBRA")`: la identidad del nodo, que escribe el instalador. LibraEdge
está incluido en todos los planes (libraedge ADR-014): no hay guarda comercial al registrar (`sin_guarda`). Hay un solo
nodo por sucursal (LibraEdge se niega a registrar un segundo nodo activo en la misma).

## Aprovisionar (en el central)

    LIBRAEDGE_APROVISIONAMIENTO=app.offline:aprovisionamiento libraedge-central nodo publicar
    libraedge-central nodo sucursales | registrar <node_id> --sucursal <id o nombre> | estado | dar-de-baja <id>
    LIBRAEDGE_DESPACHADOR=app.routers.sincronizacion_offline:despachador libraedge-central revision listar ...
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from libracore.cola_arca import ColaDeArca
from libracore.ganchos_de_caja import GanchosDeCaja
from libracore.nodo_offline import (
    VARIABLE_ESTADO,
    ConexionDelNodo,
    RechazoDelCentral,
    SinConexion,
    SoloEnElCentral,
    esta_en_linea,
    guarda_solo_en_el_central,
)
from libraedge.altas import AltaEnNodo
from libraedge.identidad import nodo_actual

_log = logging.getLogger(__name__)

#: El prefijo de las variables del producto (`GESTIOLIBRA_DATABASE_URL`, `GESTIOLIBRA_EDGE_NODE_ID`).
PREFIJO = "GESTIOLIBRA"

#: El `origen_producto` de la cola de comprobantes (libracore ADR-079) y del candado de cada pedido.
PRODUCTO = "gestiolibra"

#: La versión de las operaciones propias (`gestio.*`) y de la cola. Una forma nueva de un payload sube esta y registra un
#: manejador más en el `Despachador`; el central no entiende lo que no registró y lo manda a revisión manual.
SCHEMA_VERSION = 1

#: Las operaciones. `turno.atendido` es de LibraGenda (`libragenda.atencion_en_nodo`), la caja usa las del motor
#: (`caja.movimiento`, `caja.movimiento_anulado`) y la cola la suya (`cola.pedido`); lo propio de GestioLibra es
#: `gestio.*`.
TIPO_COLA_PEDIDO = "cola.pedido"
TIPO_CAJA_MOVIMIENTO = "caja.movimiento"
TIPO_CAJA_ANULADO = "caja.movimiento_anulado"
TIPO_FACTURA_DEL_TURNO = "gestio.factura_turno"
TIPO_CLIENTE_ALTA = "gestio.cliente_alta"

#: Las tablas de LibraGenda que el nodo espeja. **Todas las del dominio de la agenda**, salvo las que el nodo no usa
#: (`sent_reminders`: los recordatorios los manda el central). El nodo las lee; no las escribe (`TABLAS_SOLO_LECTURA`).
#: `agenda_applied_attendances` es la lista «a revisar» y lo ya aplicado de cada atención: la escribe el central y baja al
#: nodo de sólo lectura (libragenda ADR-019). **`agenda_node_attendances` NO está**: es la fila propia del nodo.
_TABLAS_DE_LA_AGENDA = (
    "branches", "branch_contacts", "branch_hours", "holidays", "resources", "services", "service_prices",
    "agenda_clients", "client_billing", "appointments", "appointment_resources", "appointment_transitions",
    "availability", "availability_exceptions", "time_blocks", "agenda_policies", "deposits", "business_settings",
    "agenda_applied_attendances",
)

#: El reparto de autoridad: qué tablas manda el central y el nodo sólo espeja. **Sólo los nombres**: la clave la lee
#: LibraEdge de la base. Lo que el **nodo** genera —la caja (`caja_movimientos`), las facturas (`facturas`), la cola de ARCA
#: (`cola_arca`), las atenciones (`agenda_node_attendances`) y la auditoría— **no se publica**: sube como operaciones.
#:
#: 🔴 NO están, a propósito:
#: - `arca_credenciales_servicio` ni ningún certificado o clave: **el ticket de ARCA lo presta el central** (libracore
#:   ADR-074 y ADR-079); la clave privada no sale del VPS. `arca_config` sí: lleva el CUIT, el punto de venta, el ambiente y
#:   las *rutas* de los archivos (que en el nodo no existen ni se usan), no los archivos.
#: - `secretos_instancia` (el almacén cifrado de claves de la instancia), `auth_log`, `envios_email`, `avisos_envios` (el registro de avisos: lleva teléfonos y textos de clientes, y los manda el central), `mp_*` (MercadoPago
#:   llega al central) y `sent_reminders`.
#: - Lo del motor que este producto no usa (`clients`, `productos`, `ventas`, `egresos`...).
TABLAS_DE_REFERENCIA = frozenset({
    # Quién entra y qué ve: los usuarios son los del central (libraauth ADR-027), con la aceptación de los Términos y el
    # gate de módulos (el del producto y el del motor); y las cajas del motor (la caja por defecto, a la que apuntan los
    # movimientos).
    "usuarios", "aceptaciones_terminos", "modulos", "gestiolibra_modulos", "cajas",
    # Con qué se emite: la configuración de ARCA (CUIT, punto de venta, ambiente).
    "arca_config",
    # La agenda, el catálogo y los clientes: los manda el central.
    *_TABLAS_DE_LA_AGENDA,
})

#: Los maestros que el nodo **no escribe**: LibraEdge les instala una guarda en la base del nodo y un intento de
#: escribirlos da un error claro en vez de pisarse con el espejo en el próximo ciclo. No están `usuarios` ni
#: `aceptaciones_terminos` (el arranque y la aceptación de los Términos hacen un upsert idempotente), `cajas` (el motor
#: asegura una por defecto) ni `client_billing` (cuit y condición de IVA de un cliente: el nodo escribe la fila de **su**
#: cliente provisorio, y la guarda de `agenda_clients` no la cubre; las ediciones las frena el 409 del producto).
#: `agenda_clients` sí está: con `AltaEnNodo` la guarda deja pasar las filas con id provisorio (`"-N"`) y rechaza el resto.
TABLAS_SOLO_LECTURA = frozenset({
    "arca_config", "modulos", "gestiolibra_modulos",
    *(t for t in _TABLAS_DE_LA_AGENDA if t != "client_billing"),
})

#: Las altas que el nodo da con un id provisorio y el central reescribe (libraedge ADR-021 y ADR-026): los **clientes**
#: (`agenda_clients`: quien llega al mostrador y no está cargado). Sus ids son **texto** (un uuid), así que su id
#: provisorio es el texto `"-N"` y el mapeo vive en `libraedge_mapeo_texto`. El central le asigna su id (deduplicando por
#: CUIT) y lo baja por el espejo; LibraEdge reapunta lo que lo referenciaba. Las claves foráneas hacia `agenda_clients`
#: (`appointments`, `client_billing`...) las encuentra solo en el catálogo de la base: no hay ninguna referencia sin FK
#: que declarar (`tests/test_nodo_aprovisionamiento.py` lo ata). Los turnos **no** se dan en el nodo, así que ninguno apunta
#: a un cliente provisorio todavía.
ALTAS_EN_EL_NODO = (AltaEnNodo("agenda_clients", id_de_texto=True),)


# ── La identidad y la conexión del nodo ───────────────────────────────────────────────────────────────────────────────


def nodo() -> str | None:
    """El id de este nodo, o `None` si la instancia no es un nodo (el central, o una instalación común).

    Se lee en cada llamada: activar el nodo no exige reiniciar nada y la suite no depende del orden de los tests."""
    return nodo_actual(PREFIJO)


def en_linea() -> bool:
    """Si el nodo ve al central: lo que dice el archivo de estado del proceso del nodo (`LIBRAEDGE_ESTADO`).

    Es la de libracore (ADR-074): el último ciclo sincronizó y la última sincronización buena es reciente. Sin archivo,
    viejo o ilegible, sin conexión. La ruta se lee en cada llamada."""
    return esta_en_linea((os.environ.get(VARIABLE_ESTADO) or "").strip() or None)


#: Lo que LibraCore pregunta antes de salir a ARCA. Fuera de un nodo, nada cambia. Las dos funciones se llaman por
#: nombre en cada pregunta (no se atan al construirla): así un test puede cambiarlas.
CONEXION = ConexionDelNodo(nodo=lambda: nodo(), en_linea=lambda: en_linea())


# ── Lo que el nodo no hace ────────────────────────────────────────────────────────────────────────────────────────────

#: La guarda del nodo: la agenda (dar, mover, confirmar y cancelar turnos), el catálogo y la configuración los manda el
#: central. 409 `solo_en_el_central` en un nodo; nada en el central ni en una instalación común.
solo_en_el_central = guarda_solo_en_el_central(nodo=lambda: nodo())

_LECTURAS = frozenset({"GET", "HEAD", "OPTIONS"})


def escritura_solo_en_el_central(request: Request) -> None:
    """Como `solo_en_el_central`, pero **sólo para lo que escribe**: las lecturas pasan. Es lo que se le pone a un router
    entero cuyos datos manda el central (sucursales, servicios, precios, usuarios, configuración): el nodo los lee del
    espejo y no los cambia."""
    if request.method not in _LECTURAS:
        solo_en_el_central()


MENSAJE_SIN_CONEXION = "Esto es del central: espera a que vuelva la conexión con el central."
MENSAJE_DEL_CENTRAL = (
    "Esto se hace desde la web, no desde el equipo del local: desde acá se atiende y se cobra, y se consulta el resto."
)


def exigir_central(mensaje: str = MENSAJE_DEL_CENTRAL) -> None:
    """En un nodo, lo que no se puede hacer ahí: `SoloEnElCentral` si está en línea y `SinConexion` si no. En el central
    y en una instalación común, no hace nada.

    Sirve para lo que el central podría hacer si el nodo lo viera (editar un cliente, consultar el padrón de ARCA):
    sin conexión se dice «esperá a que vuelva» y con conexión «hacelo desde la web»."""
    if nodo() is None:
        return
    if en_linea():
        raise SoloEnElCentral(mensaje)
    raise SinConexion(MENSAJE_SIN_CONEXION)


def consulta_al_central() -> None:
    """Una dependencia de FastAPI para lo que **lee** pero necesita lo que sólo tiene el central (el certificado de ARCA): en un
    nodo, `SinConexion` si no está en línea y `SoloEnElCentral` si lo está. `escritura_solo_en_el_central` no alcanza porque deja
    pasar los GET."""
    exigir_central("La consulta al padrón de ARCA se hace desde la web: el equipo del local no tiene el certificado.")


MENSAJE_SOLO_EN_EL_NODO_START = (
    "Marcar un turno «en curso» es del equipo del local sin conexión: en la web el turno se completa directamente."
)
MENSAJE_SOLO_EN_EL_NODO_NO_SHOW = (
    "Marcar «no vino» es del equipo del local sin conexión: en la web se cancela el turno."
)


def exigir_nodo(mensaje: str) -> None:
    """Lo que sólo existe en un nodo: 409 `solo_en_el_nodo` en el central y en una instalación común, para que la
    pantalla (que sólo lo ofrece en un nodo) y quien llame a mano sepan por qué."""
    if nodo() is None:
        from fastapi import HTTPException

        raise HTTPException(409, {"codigo": "solo_en_el_nodo", "mensaje": mensaje})


# ── Encolar una operación ─────────────────────────────────────────────────────────────────────────────────────────────


def _ahora_utc() -> str:
    return datetime.now(UTC).isoformat()


def conexion_de_la_sesion(sesion):
    """La conexión del motor (`?` como marcador, filas por posición) **sobre la misma transacción** de la sesión de
    SQLAlchemy. El outbox de LibraEdge, la caja y la cola de ARCA se escriben con esa interfaz, y tienen que entrar en la
    transacción de la atención: sin esto serían dos conexiones y una atención podría quedar sin su cobro, o al revés.

    No se cierra ni se commitea: es de la sesión."""
    from libracore.db._postgres import ConnectionWrapper

    return ConnectionWrapper(sesion.connection().connection.driver_connection)


def encolar_operacion(conn, tipo: str, agregado: str, id_local: Any, payload: Mapping[str, Any], *,
                      commit: bool = False) -> None:
    """Encola `tipo` en el outbox de este nodo, **en la transacción de `conn`** (sin confirmar, salvo `commit=True`).

    Es el contrato de ADR-025 de LibraEdge: `operation_id = <nodo>:<secuencia>`, `aggregate_id =
    <nodo>:<agregado>:<id local>`, y la secuencia es una sola por nodo: el central recibe las operaciones en el orden en
    que ocurrieron (libraedge ADR-020). Levanta `RuntimeError` fuera de un nodo: encolar en el central dejaría una
    operación que nadie sube.

    `conn` es una conexión DB-API de la familia (`libracore.db.core.get_connection()` o `conexion_de_la_sesion(...)`
    sobre la conexión de la sesión): con la de la sesión, la operación vive o muere con el cambio que la originó."""
    from libraedge.db.repository import NodeRepository
    from libraedge.domain.sync import OutboxOperation

    node_id = nodo()
    if node_id is None:
        raise RuntimeError("Encolar una operación es del nodo: esta instancia no es un nodo de LibraEdge.")
    repo = NodeRepository(conn)
    secuencia = repo.next_sequence(commit=False)
    repo.enqueue_operation(OutboxOperation(
        operation_id=f"{node_id}:{secuencia}", node_id=node_id, sequence=secuencia, operation_type=tipo,
        aggregate_type=agregado, aggregate_id=f"{node_id}:{agregado}:{id_local}", occurred_at=_ahora_utc(),
        schema_version=SCHEMA_VERSION, payload=dict(payload),
    ), commit=False)
    if commit:
        conn.commit()


def _encolar_de_caja(tipo: str):
    def gancho(conn, datos: dict) -> None:
        # Fuera de un nodo (el central, una instalación común) los ganchos no hacen nada: se arma siempre igual.
        if nodo() is not None:
            encolar_operacion(conn, tipo, "caja_movimiento", datos["movimiento_id"], datos)

    return gancho


#: Los ganchos de la caja para `libracore.db.caja` (`ganchos=`): en un nodo encolan cada movimiento que se anota (con lo
#: propio de este producto en `datos["extra"]`: el turno al que pertenece el cobro) y cada anulación; **fuera de un nodo**
#: no hacen nada, como `GanchosDeCaja()`. GestioLibra no abre turnos de caja ni cierra el día: sólo estos dos.
#:
#: 🔑 Los cobros de un turno (la seña y el saldo) suben **por acá**, como `caja.movimiento`, y no con el turno: la plata
#: no viaja en `turno.atendido.extra` más que como dato para el que revisa (si viajara en los dos lugares se duplicaría).
GANCHOS_DE_CAJA = GanchosDeCaja(
    al_registrar_movimiento=_encolar_de_caja(TIPO_CAJA_MOVIMIENTO),
    al_anular_movimiento=_encolar_de_caja(TIPO_CAJA_ANULADO),
)


# ── Atender un turno: la costura con LibraGenda ───────────────────────────────────────────────────────────────────────


def _encolar_atencion(sesion, tipo: str, agregado: str, id_local: str, datos: dict) -> None:
    encolar_operacion(conexion_de_la_sesion(sesion), tipo, agregado, id_local, datos)


def configurar_atenciones() -> None:
    """Enchufa `libragenda.atencion_en_nodo` al outbox de este nodo: `turno.atendido` se encola **en la transacción de la
    sesión** que atiende el turno, con el cobro. Se llama una vez al armar la app, **igual en el nodo y en el central**:
    fuera de un nodo `nodo()` es `None` y LibraGenda se niega a atender «en el nodo». El registro de `turno.atendido` en el
    despachador del central es `app/routers/sincronizacion_offline.py`."""
    from libragenda import atencion_en_nodo

    atencion_en_nodo.configurar(atencion_en_nodo.AtencionesEnNodo(nodo=lambda: nodo(), encolar=_encolar_atencion))


# ── Facturar sin red: la cola de ARCA ─────────────────────────────────────────────────────────────────────────────────

_cliente_de_ticket = None


def _version_esquema_del_nodo() -> str | None:
    """La misma versión de esquema que manda el proceso del nodo (`LIBRAEDGE_VERSION_ESQUEMA`, `alembic` por defecto),
    para que el central conteste 409 si no coinciden."""
    from libracore.db.core import get_connection
    from libraedge.cli import version_esquema_del_nodo

    with get_connection() as conn:
        return version_esquema_del_nodo(conn, os.environ.get("LIBRAEDGE_VERSION_ESQUEMA"))


def cliente_de_ticket():
    """El `ClienteDeTicket` de LibraEdge de este nodo (uno por proceso: guarda el ticket en memoria hasta que vence).
    Lo arma recién al primer uso: fuera de un nodo no hay a quién pedirle y `cliente_desde_entorno` levantaría."""
    global _cliente_de_ticket
    if _cliente_de_ticket is None:
        from libraedge.sync.ticket import cliente_desde_entorno

        version: list[str | None] = []

        def version_esquema() -> str | None:
            if not version:
                version.append(_version_esquema_del_nodo())
            return version[0]

        _cliente_de_ticket = cliente_desde_entorno(version_esquema=version_esquema)
    return _cliente_de_ticket


async def obtener_ta(arca: dict, servicio: str = "wsfe") -> dict:
    """El `obtener_ta(arca, servicio=)` de `ColaDeArca`, sobre el transporte de LibraEdge.

    Un corte (sin red, 5xx, esquema distinto) llega como `SinConexion` y el pedido queda `esperando`; un rechazo del
    central (nodo revocado, sin ARCA) como `RechazoDelCentral` con el mensaje del central: se informa en vez de
    reintentarse."""
    base = cliente_de_ticket().para_servicio(sin_conexion=SinConexion, rechazo=RechazoDelCentral)
    return await base(arca, servicio=servicio)


def subir_pedido(payload: dict) -> None:
    """El `al_cambiar` de la cola: encola el estado del pedido (`cola.pedido`) para que el central lo vea y, si el pedido
    de la factura de un turno quedó **emitido**, la factura misma (`gestio.factura_turno`), las dos en una sola
    transacción.

    Corre **después** de confirmar el cambio de la cola y no tiene transacción propia: abre la suya. Si falla, el motor lo
    registra y no deshace el comprobante (ya está emitido en ARCA); la `revision` del payload hace idempotente el reenvío
    al reconciliar."""
    from libracore.db.core import get_connection

    from app.services import factura_del_nodo

    with get_connection() as conn:
        encolar_operacion(conn, TIPO_COLA_PEDIDO, "cola_arca", payload["id_en_el_nodo"], payload)
        extra = factura_del_nodo.payload_de_la_factura_del_turno(payload, conn)
        if extra is not None:
            encolar_operacion(conn, TIPO_FACTURA_DEL_TURNO, "factura_turno", extra["turno_id"], extra)
        conn.commit()


def cola() -> ColaDeArca:
    """La cola de comprobantes de ARCA de este producto (libracore ADR-079). El mismo armado en el nodo y en el central:
    en el central no hace nada (`encolar` se rehúsa y `procesar_cola` no emite). Se arma en cada llamada (es barata) para
    que un test pueda cambiar la conexión o el numerador."""
    from app.services import factura_del_nodo

    return ColaDeArca(
        producto=PRODUCTO,
        emisores={"documento": factura_del_nodo.emitir_documento},
        conexion=CONEXION,
        obtener_ta=obtener_ta,
        al_cambiar=subir_pedido,
    )


def arrancar_cola() -> Any:
    """En un nodo, arranca el hilo que emite lo que quedó en la cola cuando vuelve la conexión (libracore ADR-079, punto
    7). Devuelve el `Event` que lo para, o `None` si la instancia no es un nodo."""
    from libracore.cola_arca import arrancar_cola_al_volver

    return arrancar_cola_al_volver(cola())


# ── El aprovisionamiento del central ──────────────────────────────────────────────────────────────────────────────────


def _conectar():
    """La base de la instancia, para el CLI de LibraEdge (que corre sin la app): la misma URL que arma `app/asgi.py`.
    Un nodo es de **una sola base** (ADR-035): el dominio y LibraCore son la misma."""
    from libracore.db.core import conectar
    from libracore.db.url_de_instancia import url_de_instancia

    return conectar(url_de_instancia("gestiolibra", requerida=True))


def nodos_del_central() -> list[dict]:
    """Los nodos registrados en esta instancia, para la barra de estado del pie (libracore ADR-075): la misma lista que
    «Sucursal sin internet». El motor usa sólo `activo` y `estado`."""
    from libracore.db.core import get_connection
    from libraedge.pantalla_del_central import nodos_de_la_instancia

    with get_connection() as conn:
        return nodos_de_la_instancia(conn, [])


def listar_sucursales(conn) -> list[dict]:
    """Las sucursales a las que se puede atar un nodo: las de la agenda (`branches`), de las que cuelgan los recursos, los
    turnos y los precios."""
    filas = conn.execute("SELECT id, name, active FROM branches ORDER BY name").fetchall()
    return [{"id": f[0], "nombre": f[1], "activa": bool(f[2])} for f in filas]


def _aprovisionamiento():
    from libraedge.aprovisionamiento import Aprovisionamiento, sin_guarda

    return Aprovisionamiento(
        prefijo=PREFIJO, tablas_de_referencia=TABLAS_DE_REFERENCIA, listar_sucursales=listar_sucursales,
        # Sin guarda comercial: LibraEdge está incluido en todos los planes (libraedge ADR-014).
        verificar_alta=sin_guarda, conectar=_conectar,
        tablas_solo_lectura=TABLAS_SOLO_LECTURA, altas_en_nodo=ALTAS_EN_EL_NODO,
    )


#: Lo que el central necesita para aprovisionar los nodos de este producto (`LIBRAEDGE_APROVISIONAMIENTO`).
aprovisionamiento = _aprovisionamiento()
