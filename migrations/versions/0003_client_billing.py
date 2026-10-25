"""Create client_billing: cuit/condicion_iva extension of clients, for
facturacion con LibraCore (mismo patron que patients de MedLibra).

La FK apunta a `agenda_clients`, la tabla de clientes de LibraGenda desde su v0.14.0
(ADR-018 de libragenda, antes `clients`; ADR-034 de este producto). En una instancia
que ya paso por esta revision la FK la siguio sola con el `RENAME` de LibraGenda; en una
base nueva `libragenda-migrar` corre primero y la tabla ya se llama asi.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_client_billing"
down_revision = "0002_business_config"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "client_billing",
        sa.Column("id", sa.String(100), sa.ForeignKey("agenda_clients.id"), primary_key=True),
        sa.Column("cuit", sa.String(20), nullable=True),
        sa.Column("condicion_iva", sa.String(50), nullable=True),
    )

def downgrade():
    op.drop_table("client_billing")
