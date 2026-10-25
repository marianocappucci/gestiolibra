"""Las tablas del nodo offline (LibraEdge, PR 9 del plan «GestioLibra, MedLibra y LibraDesk en la versión de escritorio», ADR-036).

`node_identity`, `local_sequences`, `sync_outbox`, `sync_inbox`, `sync_changelog`, `libraedge_mapeo` y, desde libraedge v0.23,
`libraedge_mapeo_texto` (el mapeo de los ids provisorios de texto, ADR-026). Llama a las funciones del paquete en vez de
re-expresar el DDL con `op.create_table(...)`, por el mismo motivo que las del resto de la familia (LibraCargo `0033`,
LibraClub `0014`, ContaLibra `0007`, VentaLibra `0009`): la fuente de verdad es el DDL de LibraEdge, y re-escribirlo acá
crearía **una segunda fuente que se desincroniza en el primer cambio** del motor. Son las mismas funciones que llama el arranque
de `libraedge-nodo` y `libraedge-central`: las dos puntas convergen.

**Se crean en toda instancia, sea nodo o no.** Un central que nunca corra offline igual las necesita: `node_identity` para
autenticar a los nodos que le pushean, `sync_inbox` para deduplicar operaciones repetidas y `sync_changelog` para publicar la
bajada. Crearlas sólo donde la instancia sea un nodo dejaría el esquema de unas instancias distinto del de otras **en
silencio**. Por eso esta revisión **no consulta** la identidad del nodo: corre igual en todas. En una instancia sin nodos son
tablas vacías que nadie escribe, y `app/offline.py` ni siquiera mira `node_identity` mientras no haya una fila activa.

Corre en la base del **dominio** (la de `DATABASE_URL`). En una instancia de una sola base (ADR-035) es también la de LibraCore,
que es donde `libracore.db.core.get_connection()` —lo que usan el receptor de LibraEdge y la cola de ARCA— las busca. La demo,
mientras lleve dos bases, las crea en la del dominio y no monta nada del nodo (`app/main.py`).

Idempotente (`CREATE TABLE IF NOT EXISTS`) y aditiva: no toca ninguna tabla existente. El trigger del changelog **no** se instala
acá: publicar una tabla es una decisión de aprovisionamiento del central (`libraedge-central nodo publicar`), no parte del
esquema del producto.

Revision ID: 0010_libraedge
Revises: 0009_gestiolibra_modulos
Create Date: 2026-10-25
"""
from alembic import op
from libracore.db.migraciones import conexion_libracore
from libraedge.db.changelog import init_changelog_schema
from libraedge.db.schema import init_schema as init_edge_schema

revision = "0010_libraedge"
down_revision = "0009_gestiolibra_modulos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # En PostgreSQL, `ConnectionWrapper` sobre la conexión del driver: traduce los `?`, el `INTEGER PRIMARY KEY AUTOINCREMENT` y
    # saltea el `PRAGMA foreign_keys = ON` con el que arranca `init_schema()` de LibraEdge. Dentro de Alembic,
    # `conexion_libracore` devolvía la conexión cruda y el `PRAGMA` reventaba (el smoke del CI, 2026-10-24); es lo mismo que
    # hacen la `0033` de LibraCargo y la `0014` de LibraClub. En SQLite (tests) sigue `conexion_libracore`.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from libracore.db._postgres import ConnectionWrapper

        conn = ConnectionWrapper(bind.connection.driver_connection)
    else:
        conn = conexion_libracore(bind)
    init_edge_schema(conn)
    init_changelog_schema(conn)


#: Lo que no se puede perder al bajar: las operaciones sin sincronizar, lo ya recibido, los nodos registrados, el mapeo de ids
#: (los dos) y los códigos de vinculación. Las otras tres (`local_sequences`, `sync_changelog` y `libraedge_canje_fallido`) se
#: regeneran (`libraedge-central nodo publicar` rearma la bajada).
_CON_DATOS = (
    "sync_outbox", "sync_inbox", "node_identity", "libraedge_mapeo", "libraedge_mapeo_texto", "libraedge_vinculacion",
)
_TODAS = (*_CON_DATOS, "local_sequences", "sync_changelog", "libraedge_canje_fallido")


def downgrade() -> None:
    # Bajar esta revisión es tirar el outbox: las operaciones que un nodo generó durante un corte y todavía no confirmó no están
    # en ningún otro lado. **Sólo se baja con las tablas vacías** (una instancia sin nodos, o una base de pruebas): con datos se
    # niega, con la misma frase que la `0018` de LibraCargo («restaurar el respaldo»).
    bind = op.get_bind()
    for tabla in _CON_DATOS:
        existe = bind.exec_driver_sql("SELECT to_regclass(%s)", (tabla,)).scalar()
        if existe is not None and bind.exec_driver_sql(f"SELECT 1 FROM {tabla} LIMIT 1").first() is not None:
            raise NotImplementedError(
                f"No se baja: {tabla} tiene filas (operaciones sin sincronizar, nodos o ids mapeados) que no existen "
                "en ninguna otra parte. Para volver atrás hay que restaurar el respaldo."
            )
    for tabla in _TODAS:
        op.execute(f"DROP TABLE IF EXISTS {tabla} CASCADE")
