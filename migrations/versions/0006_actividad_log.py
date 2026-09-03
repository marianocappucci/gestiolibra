"""Create actividad_log: quien creo, edito o borro que, y que cambio.

La escribe el `flush` de SQLAlchemy via `libraauth.auditoria` (v0.9.0), no los
repositorios -- ver `app/auditoria.py` para la lista de lo que se audita.

**Va en la base del DOMINIO** (la de LibraGenda), no en la de LibraCore donde
vive `usuarios`: es donde ocurren las escrituras que audita y donde vive la
transaccion en la que se escribe la fila.

**Tabla nueva y nada mas**: no toca ninguna existente, no migra datos y no tiene
backfill posible. Lo que paso antes de esta revision no quedo registrado en
ningun lado, asi que el log arranca vacio y desde hoy. Fabricarle filas
historicas a partir de los `created_at` de cada tabla daria un log que *parece*
completo y no lo es, que es peor que uno que declara desde cuando empieza.

`auth_log` (accesos) NO esta aca: en este producto vive en la base de LibraCore
y ya la crea su schema. Lo unico que cambia es que ahora alguien la escribe.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_actividad_log"
down_revision = "0005_modulos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "actividad_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("usuario", sa.String(100), nullable=False),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("entidad", sa.String(50), nullable=False),
        # Nullable: un borrado deja el id de la fila que se fue, pero nada
        # garantiza que toda entidad auditable tenga uno al anotarla.
        sa.Column("entidad_id", sa.Integer()),
        sa.Column("descripcion", sa.String(500), nullable=False),
        # JSON en texto: cada entidad tiene sus propias columnas y no se filtra
        # por adentro de este campo, solo se muestra.
        sa.Column("cambios", sa.Text()),
    )
    op.create_index("ix_actividad_log_ts", "actividad_log", ["ts"])
    op.create_index("ix_actividad_log_accion", "actividad_log", ["accion"])
    op.create_index("ix_actividad_log_entidad", "actividad_log", ["entidad"])


def downgrade():
    op.drop_index("ix_actividad_log_entidad", table_name="actividad_log")
    op.drop_index("ix_actividad_log_accion", table_name="actividad_log")
    op.drop_index("ix_actividad_log_ts", table_name="actividad_log")
    op.drop_table("actividad_log")
