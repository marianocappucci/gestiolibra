"""Users -- shim sobre libraauth.

Extraído 2026-07-26 a libracore.db.usuarios (el adaptador
id/username/name/role/active y ensure_default_admin() eran byte-idénticos en
Gestiolibra/MedLibra/VentaLibra salvo el prefijo de env var del admin inicial,
ver wiki/analyses/auditoria-duplicacion-familia-libra.md) y **migrado el
2026-07-30 a libraauth**.

Las dos clases son idénticas en interfaz —mismos métodos, mismo parámetro
`roles` con el mismo default `("admin","staff")`, que es justo el vocabulario
de Gestiolibra (`Role` en routers/users.py), así que no hay roles que
configurar acá—. La única diferencia es el constructor: el de libraauth recibe
el `session_factory` de SQLAlchemy del producto (ver main.py), en vez de usar
la conexión sqlite3 global de libracore.
"""
from libraauth.bootstrap import ensure_default_admin as _ensure_default_admin
from libraauth.repository import UserRepository


def ensure_default_admin(repo: UserRepository) -> None:
    _ensure_default_admin(repo, env_prefix="GESTIOLIBRA")
