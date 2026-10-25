"""Los clientes que se dan de alta en un nodo de LibraEdge sin conexión, y su vuelta en el central (ADR-036).

Un local sin internet también recibe gente nueva: quien llega al mostrador **no está en la lista** y hay que darlo de alta
ahí mismo. Su id no puede ser el de la secuencia del nodo (chocaría con uno del central, o lo pisaría el espejo), así que
el nodo le pone un **id provisorio** y el central le asigna el definitivo (decisión del humano, 2026-10-25: *«número
provisorio con cartel»*, libraedge ADR-021).

> ⚠️ **Los ids de la agenda son de texto** (un uuid): `agenda_clients.id` es `VARCHAR`. Su id provisorio es el texto
> `"-N"` (`"-1"`, `"-2"`...) y su mapeo es `libraedge_mapeo_texto` (libraedge v0.23, ADR-026), no `libraedge_mapeo`. Por eso
> la tabla se declara `AltaEnNodo("agenda_clients", id_de_texto=True)` (`offline.ALTAS_EN_EL_NODO`).

## Dos tablas, una operación

Un cliente de GestioLibra son **dos filas**: `agenda_clients` (LibraGenda: nombre, teléfono, correo) y `client_billing`
(este producto: CUIT y condición de IVA, con clave foránea a la primera). El alta del nodo escribe las dos y encola **una**
operación, `gestio.cliente_alta`, en la misma transacción; el central crea las dos con el id definitivo.

Cuando el central anota el mapeo y baja la fila definitiva, el espejo reapunta lo que referenciaba al provisorio por las
claves foráneas del catálogo y borra la fila provisoria (libraedge `reconciliacion`). `client_billing` es una tabla
espejada: su fila provisoria se **borra** (la definitiva baja con el cuerpo que escribió el central), no se reapunta.

## La operación

- `operation_type`: `gestio.cliente_alta`. `aggregate_type = "cliente"`, `aggregate_id = "<nodo>:cliente:<id>"`.
- `schema_version = 1`. Payload `version 1`: `cliente_id` (`"-N"`), `nombre`, `telefono`, `email`, `cuit`,
  `condicion_iva`, `activo`, `creada_at` (ISO con zona).

## Qué hace el central (`aplicar_cliente_alta`, idempotente por `libraedge_mapeo_texto`)

1. Si el mapeo `(nodo, 'agenda_clients', id provisorio)` ya está, no crea nada **siempre que el cliente mapeado sea la
   misma persona** (si no, el nodo reusó un id provisorio, una PC reemplazada con el mismo `node_id`:
   `ClienteDelNodoError`, revisión manual).
2. Si no, **busca a la persona** entre los clientes activos del central: por **CUIT** (sin puntos ni guiones) y, después,
   por **correo**. Si la encuentra, usa **ésa** y no toca sus datos: el central es la autoridad del maestro.
3. Si no existe, la crea con un uuid.
4. Anota el mapeo.

**No se deduplica por nombre ni por teléfono**: dos «Juan Pérez» son dos clientes (fusionar por el nombre es peor que
duplicar: un duplicado se junta a mano, un turno atado a otra persona no se nota). Una coincidencia por correo se descarta
si los dos tienen CUIT y son distintos.

## En el nodo: las guardas

`agenda_clients` es una tabla que el nodo espeja y, con `AltaEnNodo`, sólo deja escribir las filas con id provisorio
(LibraEdge ADR-019: cualquier otra da SQLSTATE `LE001`). Lo que la base rechazaría con un 500 se contesta antes con un
409 claro: editar o borrar un cliente es **`sin_conexion`** si el nodo no está en línea y **`solo_en_el_central`** si lo
está; y uno **provisorio** tampoco se edita (la operación que ya se encoló llevaría los datos viejos y el cambio se
perdería cuando baje el definitivo).
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from libracore.nodo_offline import SoloEnElCentral
from libragenda import Client
from libragenda.sqlalchemy_repository import ClientRow
from sqlalchemy.orm import Session, sessionmaker

from app import offline
from app.services.clients import ClientBillingRow

logger = logging.getLogger(__name__)

#: La forma de los `datos` de la operación. Si cambia, sube: el central rechaza lo que no entiende.
VERSION = 1

#: La tabla del mapeo: la de los clientes de la agenda (no la `clients` de LibraCore).
TABLA_CLIENTES = "agenda_clients"
AGREGADO_CLIENTE = "cliente"

#: Largos de las columnas (el central valida antes de escribir: un `DataError` ajeno no es un `ValueError`).
_LARGOS = {"nombre": 200, "telefono": 50, "email": 254, "cuit": 20, "condicion_iva": 50}

MENSAJE_PROVISORIO = (
    "Este cliente se dio de alta sin conexión y todavía no subió a la web: corregilo desde la web cuando suba."
)


class ClienteDelNodoError(ValueError):
    """Un alta de cliente del nodo que el central no puede aplicar. Es un `ValueError` a propósito: el receptor de
    LibraEdge la manda a revisión manual y el nodo no traba la cola (ADR-020 de libraedge)."""


class AltaDeClienteInvalida(ClienteDelNodoError):
    """El payload de `gestio.cliente_alta` no se entiende o trae algo que el central no puede escribir."""


def es_provisorio(cliente_id: str | None) -> bool:
    """Si el cliente se dio de alta en este nodo y todavía no tiene su id definitivo: el texto `"-N"`."""
    from libraedge.mapeo import es_provisorio_de_texto

    return es_provisorio_de_texto(cliente_id)


# ── En el nodo: el alta ──────────────────────────────────────────────────────


def alta_en_el_nodo(
    sessions: sessionmaker[Session], *, nombre: str, telefono: str | None, email: str | None, cuit: str | None,
    condicion_iva: str | None,
) -> dict:
    """Da de alta un cliente en el nodo: le pone un id provisorio, guarda las dos filas y encola `gestio.cliente_alta`,
    **todo en una transacción**. Si algo falla no queda ni el cliente ni la operación.

    Devuelve el cliente como lo devuelve la API (`ClientRepository._to_out`). `ValueError` si el nombre o el correo no
    sirven (la misma validación del dominio que usa el alta del central)."""
    from libraedge.mapeo import siguiente_id_provisorio

    if offline.nodo() is None:
        raise RuntimeError("El alta provisoria es del nodo: esta instancia no es un nodo de LibraEdge.")
    with sessions.begin() as sesion:
        conn = offline.conexion_de_la_sesion(sesion)
        id_provisorio = siguiente_id_provisorio(conn, texto=True)
        # El mismo `Client` del dominio que construye el alta del central: valida el nombre y el correo.
        cliente = Client(id_provisorio, nombre, telefono, email, True)
        creada = datetime.now(UTC)
        sesion.add(ClientRow(
            id=cliente.id, name=cliente.name, phone=cliente.phone, email=cliente.email, active=True,
        ))
        # Las dos filas en orden: `client_billing.id` apunta a `agenda_clients.id`.
        sesion.flush()
        sesion.add(ClientBillingRow(id=cliente.id, cuit=cuit, condicion_iva=condicion_iva, created_at=creada))
        sesion.flush()
        offline.encolar_operacion(conn, offline.TIPO_CLIENTE_ALTA, AGREGADO_CLIENTE, cliente.id, {
            "version": VERSION,
            "cliente_id": cliente.id,
            "nombre": cliente.name,
            "telefono": cliente.phone,
            "email": cliente.email,
            "cuit": cuit,
            "condicion_iva": condicion_iva,
            "activo": True,
            "creada_at": creada.isoformat(),
        })
    return {
        "id": cliente.id, "name": cliente.name, "phone": cliente.phone, "email": cliente.email, "active": True,
        "cuit": cuit, "condicion_iva": condicion_iva,
    }


# ── En el nodo: las guardas ──────────────────────────────────────────────────


def exigir_cliente_modificable(cliente_id: str) -> None:
    """En un nodo, editar o borrar un cliente no se puede (el del central es de sólo lectura, el provisorio ya subió con
    sus datos). Fuera de un nodo no hace nada.

    Levanta `SinConexion` (409 `sin_conexion`) si el nodo no está en línea, y `SoloEnElCentral` (409 `solo_en_el_central`)
    si lo está o si el cliente todavía es provisorio."""
    if offline.nodo() is None:
        return
    if es_provisorio(cliente_id):
        raise SoloEnElCentral(MENSAJE_PROVISORIO)
    offline.exigir_central("Los clientes se editan y se borran desde la web, no desde el equipo del local: desde acá "
                           "sólo se dan de alta.")


# ── En el central: validar ───────────────────────────────────────────────────


def _texto(datos: Mapping, campo: str, operacion, *, obligatorio: bool = False) -> str | None:
    valor = datos.get(campo)
    if valor is None:
        if obligatorio:
            raise AltaDeClienteInvalida(f"el alta del nodo {operacion.node_id} no trae {campo}")
        return None
    if not isinstance(valor, str):
        raise AltaDeClienteInvalida(f"{campo} {valor!r} del alta del nodo {operacion.node_id} no es un texto")
    valor = valor.strip()
    if obligatorio and not valor:
        raise AltaDeClienteInvalida(f"el alta del nodo {operacion.node_id} no trae {campo}")
    if len(valor) > _LARGOS.get(campo, 10_000_000):
        raise AltaDeClienteInvalida(f"{campo} del alta del nodo {operacion.node_id} pasa de {_LARGOS[campo]} caracteres")
    return valor or None


def _fecha(datos: Mapping, campo: str) -> datetime | None:
    crudo = datos.get(campo)
    if crudo is None:
        return None
    try:
        fecha = datetime.fromisoformat(crudo)
    except (TypeError, ValueError) as exc:
        raise AltaDeClienteInvalida(f"{campo} {crudo!r} no es una fecha ISO 8601") from exc
    if fecha.tzinfo is None:
        raise AltaDeClienteInvalida(f"{campo} {crudo!r} no trae zona horaria")
    return fecha


def _datos_de_alta(operacion) -> dict:
    """Valida el payload de `gestio.cliente_alta` y lo devuelve con los tipos de Python."""
    if operacion.operation_type != offline.TIPO_CLIENTE_ALTA:
        raise AltaDeClienteInvalida(f"se esperaba {offline.TIPO_CLIENTE_ALTA}, llegó {operacion.operation_type!r}")
    if operacion.schema_version != offline.SCHEMA_VERSION:
        raise AltaDeClienteInvalida(
            f"schema {operacion.schema_version} de {offline.TIPO_CLIENTE_ALTA} desconocido "
            f"(se entiende {offline.SCHEMA_VERSION})")
    datos = operacion.payload
    if datos.get("version") != VERSION:
        raise AltaDeClienteInvalida(
            f"versión {datos.get('version')!r} de los datos de {offline.TIPO_CLIENTE_ALTA} desconocida "
            f"(se entiende {VERSION})")
    id_nodo = datos.get("cliente_id")
    if not es_provisorio(id_nodo):
        raise AltaDeClienteInvalida(
            f"el cliente_id {id_nodo!r} del alta del nodo {operacion.node_id} no es un id provisorio (el texto "
            "\"-N\"): el nodo sólo sube altas con id provisorio")
    activo = datos.get("activo", True)
    if not isinstance(activo, bool):
        raise AltaDeClienteInvalida(f"activo {activo!r} del alta del nodo {operacion.node_id} no es un booleano")
    return {
        "cliente_id": id_nodo,
        "nombre": _texto(datos, "nombre", operacion, obligatorio=True),
        "telefono": _texto(datos, "telefono", operacion),
        "email": _texto(datos, "email", operacion),
        "cuit": _texto(datos, "cuit", operacion),
        "condicion_iva": _texto(datos, "condicion_iva", operacion),
        "activo": activo,
        "creada_at": _fecha(datos, "creada_at"),
    }


# ── En el central: la misma persona ──────────────────────────────────────────

_NO_NUMERICO = re.compile(r"[^0-9]")


def _clave_cuit(valor: str | None) -> str:
    """Un CUIT para comparar: sólo los dígitos. Vacío si no hay."""
    return _NO_NUMERICO.sub("", valor or "")


def _clave_email(valor: str | None) -> str:
    return (valor or "").strip().lower()


def _clave_nombre(valor: str | None) -> str:
    return " ".join((valor or "").lower().split())


def _es_la_misma_persona(existente: Mapping, datos: Mapping) -> bool:
    """Para el reintento de un alta ya mapeada: la clave más fuerte que los dos traen decide (CUIT, después correo); si
    no comparten ninguna, el nombre."""
    a, b = _clave_cuit(existente["cuit"]), _clave_cuit(datos["cuit"])
    if a and b:
        return a == b
    a, b = _clave_email(existente["email"]), _clave_email(datos["email"])
    if a and b:
        return a == b
    return _clave_nombre(existente["nombre"]) == _clave_nombre(datos["nombre"])


_SELECT = (
    "SELECT c.id, c.name, c.email, b.cuit FROM agenda_clients c LEFT JOIN client_billing b ON b.id = c.id"
)


def _como_dict(fila) -> dict:
    return {"id": fila[0], "nombre": fila[1], "email": fila[2], "cuit": fila[3]}


def _cliente_existente(conn, datos: Mapping) -> str | None:
    """El cliente activo del central al que corresponde el alta, o `None`. Por CUIT, después por correo; el primero que
    encuentra (el de menor id) y que no choca con otro CUIT. Sin ninguna de las dos claves no deduplica. Los provisorios
    (id que empieza con `-`) no cuentan: no son una persona que el central tenga."""
    consultas = []
    if _clave_cuit(datos["cuit"]):
        consultas.append(("regexp_replace(coalesce(b.cuit, ''), '[^0-9]', '', 'g') = ?", _clave_cuit(datos["cuit"])))
    if _clave_email(datos["email"]):
        consultas.append(("lower(btrim(coalesce(c.email, ''))) = ?", _clave_email(datos["email"])))
    for condicion, valor in consultas:
        filas = conn.execute(
            f"{_SELECT} WHERE c.active AND left(c.id, 1) <> '-' AND {condicion} ORDER BY c.id", (valor,)
        ).fetchall()
        for fila in filas:
            existente = _como_dict(fila)
            a, b = _clave_cuit(existente["cuit"]), _clave_cuit(datos["cuit"])
            if a and b and a != b:
                continue
            return existente["id"]
    return None


def _insertar(conn, datos: Mapping) -> str:
    id_central = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO agenda_clients (id, name, phone, email, active) VALUES (?, ?, ?, ?, ?)",
        (id_central, datos["nombre"], datos["telefono"], datos["email"], datos["activo"]),
    )
    conn.execute(
        "INSERT INTO client_billing (id, cuit, condicion_iva, created_at) VALUES (?, ?, ?, COALESCE(?, now()))",
        (id_central, datos["cuit"], datos["condicion_iva"], datos["creada_at"]),
    )
    return id_central


# ── En el central: aplicar ───────────────────────────────────────────────────


def aplicar_cliente_alta(conn, operacion) -> None:
    """Aplica `gestio.cliente_alta` en el central: usa al cliente que ya tiene (la misma persona) o lo crea con su propio
    id, y anota el mapeo `(nodo, 'agenda_clients', id provisorio) -> id`. Todo en la transacción del receptor: o queda el
    cliente y su mapeo, o ninguno. Idempotente.

    Los errores son `ValueError` (revisión manual): un `IntegrityError` ajeno lo leería el receptor como «duplicado»."""
    from libraedge import mapeo

    datos = _datos_de_alta(operacion)
    node_id, id_nodo = operacion.node_id, datos["cliente_id"]

    id_central = mapeo.traducir_id(conn, node_id, TABLA_CLIENTES, id_nodo, exigir=False)
    if id_central is not None:
        # Entregada otra vez (el outbox entrega al menos una vez). Si el cliente mapeado no es esta persona, el nodo
        # reusó un id provisorio (una PC reemplazada con el mismo `node_id`): revisión manual, no se pisa nada.
        fila = conn.execute(f"{_SELECT} WHERE c.id = ?", (id_central,)).fetchone()
        if fila is None:
            raise ClienteDelNodoError(
                f"el alta del cliente {id_nodo} del nodo {node_id} ya estaba mapeada al {id_central} "
                "y ese cliente ya no existe")
        existente = _como_dict(fila)
        if not _es_la_misma_persona(existente, datos):
            raise ClienteDelNodoError(
                f"el nodo {node_id} reusó el id provisorio {id_nodo}: ya estaba mapeado al cliente {id_central} del "
                f"central ({existente['nombre']!r}) y ahora llega el alta de {datos['nombre']!r}. Un turno a ese "
                "id iría a otra persona: revisar a mano")
        return

    id_central = _cliente_existente(conn, datos)
    if id_central is not None:
        logger.info(
            "gestio.cliente_alta del nodo %s: el cliente provisorio %s es el %s del central (ya existía)",
            node_id, id_nodo, id_central)
    else:
        id_central = _insertar(conn, datos)
    try:
        mapeo.anotar_mapeo(conn, node_id, TABLA_CLIENTES, id_nodo, id_central)
    except mapeo.MapeoEnConflicto as exc:
        raise ClienteDelNodoError(str(exc)) from exc


def aplicadores() -> dict[str, Any]:
    """`{operation_type: (conn, operacion) -> None}` de `gestio.cliente_alta`, para el despachador del central."""
    return {offline.TIPO_CLIENTE_ALTA: aplicar_cliente_alta}
