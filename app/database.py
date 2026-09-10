"""Módulos y add-ons: el contrato que espera el backoffice.

🔴 El backoffice prende/apaga add-ons y lee su estado corriendo un snippet
DENTRO del contenedor de la instancia (`libracore.admin.services`), y ese
snippet importa `app.database.get_modulos` / `app.database.set_addon`. Es el
contrato que Gestiolibra tiene que cumplir desde que declaró
`ADDONS = {"resguardo_externo"}` en `plans.py`. Hasta entonces este módulo no
existía: sin él el `docker exec` muere con `ImportError`, y la lectura del
backoffice lo muestra como "no se pudo leer".

Delegan en `libracore.db.modulos`, que es donde vive la implementación única
de la familia. Acá no se copia lógica: se cumple el contrato. Mismo patrón que
`libradesk/app/database.py`, **con una diferencia que no es de estilo** — ver
`_asegurar_core_configurado`.
"""

#: Si fue ESTE módulo el que apuntó `libracore.db.core` a la base del dominio.
#: Hace falta para distinguir "lo configuré yo en una llamada anterior" de "lo
#: configuró otro", que en este producto significa otra base.
_apuntado_por_este_modulo = False


def _asegurar_core_configurado() -> None:
    """Apunta `libracore.db.core` a la base del DOMINIO de esta instancia.

    La tabla `modulos` que lee `ModuleRepository` —y por lo tanto la que
    decide el 403 de `require_module`— vive en la base del dominio
    (`url_de_instancia("gestiolibra")`, la base `gestiolibra`).

    🔴 **Acá no alcanza con "si nadie lo configuró, lo configuro".** En
    LibraDesk sí, porque la app configura el core contra su única base. En
    Gestiolibra la app lo configura en `billing.configure(libracore_db_path)`
    contra la base **de LibraCore** (`gestiolibra_core`), que es otra: tiene su
    propia tabla `modulos`, vacía, que nadie consulta. Un shim que aceptara ese
    core ya configurado leería `{}` y escribiría el add-on donde la app no lo
    ve — el backoffice mostraría "prendido" y la pantalla seguiría en 403.

    Así que hay dos casos, y el tercero se rechaza en voz alta:

    - Bajo `docker exec python3 -c "from app.database import get_modulos"` no
      corrió ningún arranque: el core está sin configurar y se apunta al
      dominio. Es el caso del backoffice.
    - Una segunda llamada en ese mismo proceso: ya lo apuntó este módulo.
    - Un proceso donde el core lo configuró otro (la app viva, la suite): ahí
      apunta a la base de LibraCore, y en vez de leer la tabla equivocada en
      silencio se levanta `RuntimeError`. Pisar la configuración tampoco es
      opción: le cambiaría la base a la facturación de una app viva.
    """
    global _apuntado_por_este_modulo
    from libracore.db import core as libracore_core
    from libracore.db.url_de_instancia import url_de_instancia

    if _apuntado_por_este_modulo:
        return
    if libracore_core.esta_configurado():
        raise RuntimeError(
            "app.database de Gestiolibra se usa en un proceso nuevo (el `docker exec` "
            "del backoffice): acá libracore.db.core ya está configurado, y en este "
            "producto eso es la base de LibraCore, no la del dominio donde vive la "
            "tabla `modulos` que decide los add-ons. Dentro de la app se usa "
            "`app.state.modules`."
        )
    libracore_core.configure(url_de_instancia("gestiolibra", requerida=True))
    _apuntado_por_este_modulo = True


def get_modulos() -> dict[str, bool]:
    """`{modulo: habilitado}` de esta instancia. Ver `_asegurar_core_configurado`."""
    _asegurar_core_configurado()
    from libracore.db.modulos import get_modulos as _get_modulos

    return _get_modulos()


def set_addon(nombre: str, habilitado: bool) -> None:
    """Prende/apaga un add-on suelto en esta instancia. Crea la fila si falta.

    Efecto inmediato: `ModuleRepository.is_enabled` relee la fila en cada
    request. No valida que `nombre` sea un add-on: eso lo hace el backoffice
    contra `plans.ADDONS` antes de llamar."""
    _asegurar_core_configurado()
    from libracore.db.modulos import set_addon as _set_addon

    _set_addon(nombre, habilitado)
