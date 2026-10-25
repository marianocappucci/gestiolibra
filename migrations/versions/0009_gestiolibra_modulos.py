"""Renombra `modulos` a `gestiolibra_modulos`: LibraCore tiene una `modulos` propia.

🔴 **Por que (ADR-034).** El humano decidio (2026-10-21) una sola base por producto. Hoy
GestioLibra lleva dos (`gestiolibra` y `gestiolibra_core`) y para unirlas
`libracore-unir-bases` corta con cualquier nombre de tabla repetido (ADR-078 de libracore).
`modulos` esta repetida: la de este producto (`modulo` TEXT PRIMARY KEY, `habilitado`
BOOLEAN, `plan`) y la del motor (`id` serial, `modulo` UNIQUE, `habilitado` INTEGER, `plan`).

Es un `RENAME`: ni se copian ni se borran filas. Las filas pasan a la tabla del motor
**despues de unir**, en otro paso (ADR-034, punto 3); esta revision solo despeja el nombre.

La clave primaria tambien cambia de nombre (`modulos_pkey` -> `gestiolibra_modulos_pkey`):
un `RENAME` de tabla no mueve el indice, y en la base unida el `modulos_pkey` del motor
chocaria con el que quedo (mismo cuidado que `0010_agenda_clients` de libragenda).

Corre en tres mundos, y los tres tienen que dejar `gestiolibra_modulos` y nada llamado
`modulos` de este producto:

1. **Instancia de antes** (`0005` la creo como `modulos`): se renombra.
2. **Base nueva** (`0005` ya la creo con el nombre nuevo): no hay nada que hacer.
3. **Una `gestiolibra_modulos` vacia que ya creo el arranque con el codigo nuevo**, porque
   alguien arranco la app antes de migrar (`create_all`): se la descarta y se renombra. Con
   filas no se descarta: aborta, y el mensaje dice por que.

Una `modulos` que NO tiene la forma de este producto (con `id`) es la del motor y **no se
toca nunca**.

Revision ID: 0009_gestiolibra_modulos
Revises: 0008_sin_users
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_gestiolibra_modulos"
down_revision = "0008_sin_users"
branch_labels = None
depends_on = None


def _es_la_del_producto(insp, tabla: str) -> bool:
    """La `modulos` de este producto: clave `modulo`, sin columna `id` (la del motor la tiene)."""
    if not insp.has_table(tabla):
        return False
    columnas = {c["name"] for c in insp.get_columns(tabla)}
    return "modulo" in columnas and "id" not in columnas


def _renombrar_clave(bind, tabla: str, de: str, a: str) -> None:
    """Renombra la clave primaria (PostgreSQL). En SQLite no hay nombre que mover."""
    if bind.dialect.name != "postgresql":
        return
    nombre = sa.inspect(bind).get_pk_constraint(tabla).get("name")
    if nombre == de:
        op.execute(sa.text(f'ALTER TABLE "{tabla}" RENAME CONSTRAINT "{de}" TO "{a}"'))


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _es_la_del_producto(insp, "modulos"):
        return  # base nueva (0005 ya uso el nombre nuevo) o `modulos` es la del motor
    if insp.has_table("gestiolibra_modulos"):
        filas = bind.execute(sa.text("SELECT count(*) FROM gestiolibra_modulos")).scalar()
        if filas:
            raise RuntimeError(
                "Hay una `modulos` y una `gestiolibra_modulos` con filas: no se sabe cual es la "
                "buena. Se aborta sin tocar nada; resolverlo a mano (ADR-034)."
            )
        op.drop_table("gestiolibra_modulos")
    op.rename_table("modulos", "gestiolibra_modulos")
    _renombrar_clave(bind, "gestiolibra_modulos", "modulos_pkey", "gestiolibra_modulos_pkey")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not _es_la_del_producto(insp, "gestiolibra_modulos"):
        return
    if insp.has_table("modulos"):
        raise RuntimeError(
            "No se puede volver a llamar `modulos` a la tabla de este producto: ya existe una "
            "`modulos` (la de LibraCore, la base esta unida). Pasar las filas a la del motor y "
            "borrar `gestiolibra_modulos` es el camino, no volver atras (ADR-034)."
        )
    op.rename_table("gestiolibra_modulos", "modulos")
    _renombrar_clave(bind, "modulos", "gestiolibra_modulos_pkey", "modulos_pkey")
