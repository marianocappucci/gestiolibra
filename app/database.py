"""Módulos y add-ons: el contrato que espera el backoffice.

🔴 El backoffice prende/apaga add-ons y lee su estado corriendo un snippet
DENTRO del contenedor de la instancia (`libracore.admin.services`), y ese
snippet importa `app.database.get_modulos` / `app.database.set_addon`. Es el
contrato que Gestiolibra tiene que cumplir desde que declaró
`ADDONS = {"resguardo_externo"}` en `plans.py`. Hasta entonces este módulo no
existía: sin él el `docker exec` muere con `ImportError`, y la lectura del
backoffice lo muestra como "no se pudo leer".

🔑 **Desde ADR-034 ya no delegan en `libracore.db.modulos`.** Hasta entonces la tabla del
producto se llamaba `modulos`, igual que la del motor, y el shim la leía por esa coincidencia
de nombre. Ahora la del producto es `gestiolibra_modulos` (la `modulos` es la de LibraCore:
con una sola base por producto no pueden llamarse igual) y lo que decide el 403 de
`require_module` es lo que lee `ModuleRepository`. Así que el contrato se cumple por el mismo
repositorio que lee la app: un solo camino, y el add-on que prende el backoffice es el que la
app ve. Cuando las filas pasen a la `modulos` del motor (ADR-034, punto 3) esto vuelve a
delegar en `libracore.db.modulos`.

No toca el estado global de `libracore.db.core`: antes lo apuntaba a la base del dominio y
tenía que rechazar el proceso donde el core ya lo había configurado la app (que en este
producto era OTRA base). Acá se abre un engine propio contra la base del dominio y se suelta.
"""
from contextlib import contextmanager


@contextmanager
def _repositorio():
    """Un `ModuleRepository` contra la base del DOMINIO de esta instancia; el engine se suelta al salir.

    Bajo `docker exec python3 -c "from app.database import get_modulos"` no corrió ningún
    arranque, así que la URL sale del entorno (`url_de_instancia`), igual que en `asgi.py`.
    """
    from libracore.db.url_de_instancia import url_de_instancia
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from .services.modules import ModuleRepository

    url = url_de_instancia("gestiolibra", requerida=True)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    try:
        yield ModuleRepository(sessionmaker(bind=engine))
    finally:
        engine.dispose()


def get_modulos() -> dict[str, bool]:
    """`{modulo: habilitado}` de esta instancia."""
    with _repositorio() as modulos:
        return modulos.get_all()


def set_addon(nombre: str, habilitado: bool) -> None:
    """Prende/apaga un add-on suelto en esta instancia. Crea la fila si falta.

    Efecto inmediato: `ModuleRepository.is_enabled` relee la fila en cada
    request. No valida que `nombre` sea un add-on: eso lo hace el backoffice
    contra `plans.ADDONS` antes de llamar."""
    with _repositorio() as modulos:
        modulos.set_addon(nombre, habilitado)
