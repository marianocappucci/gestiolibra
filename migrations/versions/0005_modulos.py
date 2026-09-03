"""Create modulos: gating de recordatorios/senas/facturacion/dashboard por plan.

Mismo patron que `modulos` de Contalibra/Restolibra (libracore.db.modulos),
pero propio de Gestiolibra -- no vive en LibraCore porque el catalogo de
modulos gateables es especifico de cada producto (ver plans.py).
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_modulos"
down_revision = "0004_client_created_at"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "modulos",
        sa.Column("modulo", sa.String(50), primary_key=True),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("plan", sa.String(20), nullable=False, server_default="premium"),
    )

def downgrade():
    op.drop_table("modulos")
