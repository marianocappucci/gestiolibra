"""Módulos habilitados por plan comercial (ver `plans.py` en la raíz del
repo -- fuente de verdad del mapeo plan→módulos, compartida con
`libracore.provisioning`).

Solo catálogo/turnos/clientes son siempre gratis; lo gateable es
recordatorios, señas, facturación y dashboard. Por defecto (instancia
recién migrada, sin plan asignado todavía) **todo queda habilitado** --
mismo criterio que Contalibra: el seed inicial no bloquea nada, y recién
`aplicar_plan_en_db()` (llamado por el provisioning al dar de alta un
cliente real con un plan elegido) achica el acceso según corresponda.

🔴 **Los add-ons (`plans.ADDONS`) son la excepción, y al revés: arrancan
APAGADOS.** No pertenecen a ningún plan, así que no se siembran ni los toca
un plan; se prenden por instancia desde el backoffice. Ver `is_enabled`.

🔑 **La tabla es `gestiolibra_modulos`** (ADR-034), no `modulos`: `modulos` es la de LibraCore
(`libracore.db.modulos`, con `id` y `habilitado` entero) y con una sola base por producto
las dos no pueden llamarse igual. Mientras las filas no pasen a la del motor (ADR-034,
punto 3) todo lo que lee o escribe módulos en este producto va por acá: el repositorio, el
contrato del backoffice (`app.database`) y `plans.aplicar_plan_en_db`.
"""
from libragenda.sqlalchemy_repository import Base
from sqlalchemy import select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from plans import ADDONS, TODOS_LOS_MODULOS


class ModuleRow(Base):
    __tablename__ = "gestiolibra_modulos"

    modulo: Mapped[str] = mapped_column(primary_key=True)
    habilitado: Mapped[bool] = mapped_column(default=True)
    plan: Mapped[str] = mapped_column(default="premium")


class ModuleRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def ensure_seeded(self) -> None:
        """Inserta los módulos que falten con `habilitado=True` -- no pisa
        el estado de los que ya existen (INSERT OR IGNORE vía try/except,
        idempotente ante reinicios).

        Siembra sólo `TODOS_LOS_MODULOS`, **nunca un add-on**: sembrarlo con
        `habilitado=True` lo prendería en todas las instancias al arrancar,
        que es justo lo que un add-on no tiene que hacer. Su fila la crea el
        backoffice (`app.database.set_addon`) la primera vez que lo prende."""
        with self.session_factory.begin() as session:
            existentes = {row.modulo for row in session.scalars(select(ModuleRow)).all()}
            for modulo in sorted(TODOS_LOS_MODULOS - existentes):
                session.add(ModuleRow(modulo=modulo, habilitado=True, plan="premium"))

    def is_enabled(self, modulo: str) -> bool:
        """Tres casos, y el orden importa:

        1. **Add-on** (`plans.ADDONS`): prendido sólo si tiene fila y
           `habilitado` es verdadero. Sin fila, **apagado**. Es la regla
           inversa a la de los módulos de plan, y va primero porque un add-on
           tampoco está en `TODOS_LOS_MODULOS`: sin esta rama caía en el caso
           2 y quedaba prendido para todos, con `require_module` sin dar nunca
           un 403.
        2. Módulos que no son gateables (no están en TODOS_LOS_MODULOS, ej.
           catálogo/turnos): siempre habilitados, incluso si nunca se
           sembraron una fila -- no tiene sentido gatear el core.
        3. Módulo de plan: lo que diga su fila; sin fila, habilitado (el
           default "todo prendido" hasta que un plan achique)."""
        if modulo in ADDONS:
            with self.session_factory() as session:
                row = session.get(ModuleRow, modulo)
                return row is not None and bool(row.habilitado)
        if modulo not in TODOS_LOS_MODULOS:
            return True
        with self.session_factory() as session:
            row = session.get(ModuleRow, modulo)
            return bool(row.habilitado) if row is not None else True

    def get_all(self) -> dict[str, bool]:
        with self.session_factory() as session:
            rows = session.scalars(select(ModuleRow)).all()
            return {row.modulo: bool(row.habilitado) for row in rows}

    def set_addon(self, modulo: str, habilitado: bool) -> None:
        """Prende o apaga un add-on. Crea la fila si falta, con `plan="addon"`, y **sólo cambia
        `habilitado`** en una que ya existe (igual que `libracore.db.modulos.set_addon`, que este
        método reemplaza mientras la tabla sea la del producto)."""
        with self.session_factory.begin() as session:
            row = session.get(ModuleRow, modulo)
            if row is None:
                session.add(ModuleRow(modulo=modulo, habilitado=habilitado, plan="addon"))
            else:
                row.habilitado = habilitado

    def aplicar_plan(self, plan: str, activos: set[str], todos: set[str]) -> None:
        """Escribe `habilitado` y `plan` de cada módulo de `todos` según `activos`. Idempotente.

        Es el cuerpo de `libracore.provisioning.apply_plan_modules`, que escribe en una tabla
        llamada `modulos` y por eso ya no llega a esta. Quien llama resta los add-ons de `todos`:
        un plan nunca los toca."""
        with self.session_factory.begin() as session:
            for modulo in sorted(todos):
                row = session.get(ModuleRow, modulo)
                if row is None:
                    session.add(ModuleRow(modulo=modulo, habilitado=modulo in activos, plan=plan))
                else:
                    row.habilitado, row.plan = modulo in activos, plan

    def set_enabled(self, modulo: str, habilitado: bool) -> None:
        """Prende/apaga un módulo puntual, sin pasar por un plan completo
        -- usado por tests y por un futuro ajuste manual desde el
        backoffice. `aplicar_plan_en_db()` (`plans.py`) es la vía real
        para asignar un plan completo al dar de alta un cliente."""
        with self.session_factory.begin() as session:
            row = session.get(ModuleRow, modulo)
            if row is None:
                session.add(ModuleRow(modulo=modulo, habilitado=habilitado, plan="custom"))
            else:
                row.habilitado = habilitado
