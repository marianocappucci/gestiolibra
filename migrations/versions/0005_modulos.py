"""Create gestiolibra_modulos: gating de recordatorios/senas/facturacion/dashboard por plan.

Mismo patron que `modulos` de Contalibra/Restolibra (libracore.db.modulos),
pero propio de Gestiolibra -- no vive en LibraCore porque el catalogo de
modulos gateables es especifico de cada producto (ver plans.py).

🔑 **La tabla se llama `gestiolibra_modulos` desde ADR-034** (antes `modulos`). LibraCore
tiene su propia `modulos` --con `id` y `habilitado` entero-- y con una sola base por
producto las dos no pueden convivir. Esta revision la crea ya con el nombre nuevo: en una
base nueva de una sola base, `libracore-migrar` corre ANTES que esta cadena y `modulos` ya
existe (es la del motor); crear aca otra `modulos` moriria con "already exists". Las
instancias que ya pasaron por esta revision con el nombre viejo las renombra `0009`.
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_modulos"
down_revision = "0004_client_created_at"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "gestiolibra_modulos",
        sa.Column("modulo", sa.String(50), primary_key=True),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("plan", sa.String(20), nullable=False, server_default="premium"),
    )

def downgrade():
    """Borra la tabla de este producto, y **nunca la `modulos` de LibraCore**.

    Tras el downgrade de `0009` la tabla vuelve a llamarse `modulos`: se la borra solo si
    tiene la forma de esta (clave `modulo`, sin `id`), porque en una base unida ese nombre
    es el del motor."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table("gestiolibra_modulos"):
        op.drop_table("gestiolibra_modulos")
    elif insp.has_table("modulos") and "id" not in {c["name"] for c in insp.get_columns("modulos")}:
        op.drop_table("modulos")
