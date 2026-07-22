"""Create client_billing: cuit/condicion_iva extension of clients, for
facturacion con LibraCore (mismo patron que patients de MedLibra).
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_client_billing"
down_revision = "0002_business_config"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "client_billing",
        sa.Column("id", sa.String(100), sa.ForeignKey("clients.id"), primary_key=True),
        sa.Column("cuit", sa.String(20), nullable=True),
        sa.Column("condicion_iva", sa.String(50), nullable=True),
    )

def downgrade():
    op.drop_table("client_billing")
