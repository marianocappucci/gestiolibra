"""Add nullable created_at to client_billing (dashboard: clientes nuevos en un rango)."""
from alembic import op
import sqlalchemy as sa

revision = "0004_client_created_at"
down_revision = "0003_client_billing"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("client_billing", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    with op.batch_alter_table("client_billing") as batch_op:
        batch_op.drop_column("created_at")
