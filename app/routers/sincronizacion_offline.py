"""El central expone la sincronización del nodo offline: `/sync/v1/push`, `/pull` y `/ticket-arca` (ADR-036).

PR 9 del plan «GestioLibra, MedLibra y LibraDesk en la versión de escritorio». Es el mismo armado que LibraCargo y LibraClub,
con las operaciones de GestioLibra.

## Por qué se monta siempre, y no sólo en las instancias con nodos

El gateo está del otro lado: sin un nodo registrado **no existe ningún secreto válido**, así que en una instancia sin nodos
las rutas responden 401 a todo. Montarlas condicionalmente agregaría una bandera más que puede quedar mal puesta, y el
modo de fallar sería el peor posible: un nodo instalado que no puede sincronizar contra un central que «debería» tener el
endpoint.

## La conexión es por request

Se le pasa `libracore.db.core.get_connection` —la fábrica del motor— y no una conexión armada: el router abre una por
request (ver `create_sync_router` en LibraEdge). Con una sola base (ADR-035) esa conexión ve `appointments`,
`caja_movimientos` y `node_identity` a la vez.

## Qué se aplica

Un `Despachador` (libraedge ADR-007) con **todas** las operaciones que un nodo de GestioLibra sube (`armar_despachador`):

| Operación | De quién es | Qué trae |
|---|---|---|
| `turno.atendido` | LibraGenda | la atención de un turno, con lo cobrado en `extra`; si en la web cambió, queda «a revisar» |
| `caja.movimiento`, `caja.movimiento_anulado` | LibraCore | el cobro (seña o saldo) o su anulación, con `extra["turno_id"]` |
| `cola.pedido` | LibraCore | el estado de un pedido de la cola de ARCA (la web consulta) |
| `gestio.factura_turno` | GestioLibra + LibraCore | la factura de un turno con su número y CAE (`facturas_del_nodo`) |
| `gestio.cliente_alta` | GestioLibra | el cliente dado de alta en el nodo (id provisorio) |

Lo que no tiene aplicador **no se marca aplicado**: va a revisión manual (`libraedge-central revision
listar|reintentar|descartar`, con `LIBRAEDGE_DESPACHADOR=app.routers.sincronizacion_offline:despachador`).

El router además controla la versión del esquema (`version_de_alembic`: 409 si el nodo no está migrado igual que el
central) y le presta al nodo el ticket de ARCA (`libracore.nodo_offline.ta_para_el_nodo`, libraedge ADR-009 y ADR-025):
la clave no sale del VPS. GestioLibra no tiene `wscpe`: pedirlo es 501.
"""

from libracore.caja_del_nodo import aplicar_anulacion_del_nodo
from libracore.cola_arca import aplicar_pedido_del_nodo
from libracore.db.core import get_connection
from libracore.nodo_offline import ta_para_el_nodo
from libraedge.sync.api import create_sync_router
from libraedge.sync.despacho import Despachador
from libraedge.sync.esquema import version_de_alembic
from libragenda import atencion_en_nodo

from app import offline
from app.services import clientes_nodo, factura_del_nodo


def armar_despachador() -> Despachador:
    """Las operaciones que el central de GestioLibra sabe aplicar (ver el docstring del módulo).

    `turno.atendido` lo registra LibraGenda (`registrar_en`) con su propia sesión: la aplicación es idempotente por el
    `atencion_id`, así que no hace falta que comparta la transacción del receptor. Sin `al_aplicar` a propósito: lo que se
    cobró no se rehace desde la atención sino que llega por su cuenta (`caja.movimiento`, `gestio.factura_turno`), y una
    atención que quedó «a revisar» no pide nada más del central que la lista."""
    despachador = Despachador()
    version = offline.SCHEMA_VERSION
    despachador.registrar(offline.TIPO_CAJA_MOVIMIENTO, version, factura_del_nodo.aplicar_movimiento_de_caja)
    despachador.registrar(
        offline.TIPO_CAJA_ANULADO, version,
        lambda conn, operacion: aplicar_anulacion_del_nodo(conn, operacion.node_id, operacion.payload),
    )
    despachador.registrar(
        offline.TIPO_COLA_PEDIDO, version, lambda conn, operacion: aplicar_pedido_del_nodo(operacion.payload, conn=conn)
    )
    despachador.registrar(offline.TIPO_FACTURA_DEL_TURNO, version, factura_del_nodo.aplicar_factura_del_turno)
    for tipo, aplicador in clientes_nodo.aplicadores().items():
        despachador.registrar(tipo, version, aplicador)
    atencion_en_nodo.registrar_en(despachador)
    return despachador


despachador = armar_despachador()

router = create_sync_router(
    get_connection, despachador=despachador, version_esquema=version_de_alembic, prestar_ticket=ta_para_el_nodo,
)
