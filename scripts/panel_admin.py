#!/usr/bin/env python3
"""
Panel de administración Gestiolibra.
Gestiona todos los contenedores de clientes desde un menú interactivo.
Uso: python3 scripts/panel_admin.py [comando] [slug]
     python3 scripts/panel_admin.py           → menú interactivo
     python3 scripts/panel_admin.py listar
     python3 scripts/panel_admin.py backup micliente

Wrapper de configuración sobre libracore.provisioning.panel_admin (lógica
compartida con Contalibra/Restolibra — ver wiki/entities/libracore.md).
Solo fija las constantes propias de Gestiolibra; la lógica real vive en
LibraCore.
"""
from pathlib import Path

from libracore.provisioning import (
    client_from_config,
    configure,
    forward_host_from_config,
    get_config,
    le_email_from_config,
    npm_available,
)
from libracore.provisioning.panel_admin import (
    _set_servicio_estado,
    cli,
    cmd_activar,
    cmd_actualizar,
    cmd_backup,
    cmd_backup_all,
    cmd_eliminar,
    cmd_estado_servicio,
    cmd_info,
    cmd_list_backups,
    cmd_listar,
    cmd_logs,
    cmd_npm_crear,
    cmd_npm_eliminar,
    cmd_npm_listar,
    cmd_pausar,
    cmd_restart,
    cmd_restore_db,
    cmd_start,
    cmd_stop,
    cmd_suspender,
    compose,
    container_status,
    find_client,
    interactive,
    load_clients,
    pick_client,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    # El backup del cron arma el MISMO ZIP que la pantalla de Backups, en
    # `data/backups/`, en vez de un `tar.gz` aparte que la pantalla no lista
    # y el cliente no puede restaurar. Requiere libracore >= v1.29.0.
    #
    # Este producto puede prenderlo porque su pantalla sale de
    # `libracore.respaldo` (`build_backup_router` en app/main.py). Contalibra
    # y Restolibra tienen implementacion propia y todavia no.
    backup_zip=True,
    postgres=True,
    # 🔑 UNA sola base (ADR-035, sobre el ADR-034 y el ADR-083 de libracore): ya no se pasa
    # `base_core_separada=True` --el motor lo ignora para los productos de `_UNA_SOLA_BASE`, entre
    # ellos este-- y el alta nace con `gestiolibra` y nada más, sin `gestiolibra_core`. Lo único que
    # el motor no puede adivinar es cómo se llama la tabla de módulos de este producto en esa base:
    # la `modulos` a secas es la del motor (ADR-034, punto 3), la de acá es `gestiolibra_modulos`.
    # Va en `nuevo_cliente.py` Y en `panel_admin.py`: `configure()` pisa una configuración global
    # y el que corre último gana. Cuando este producto lea la `modulos` del motor, se saca.
    tabla_modulos="gestiolibra_modulos",
    product_name="GESTIOLIBRA",
    image_name="gestiolibra:latest",
    container_prefix="gestiolibra",
    db_filename="gestiolibra.db",
    # Las dos cadenas de Alembic de este producto, corridas por
    # `panel_admin.py actualizar` antes de mover la instancia a la imagen nueva,
    # y por el alta antes del primer arranque. Requiere libracore >= v1.51.0
    # (que es la que acepta una SECUENCIA de comandos) y libragenda >= v0.9.1
    # (que es la que trae `libragenda-migrar` como comando instalable).
    #
    # 🔴 **`v0.9.1` y no `v0.10.0`, a proposito.** Entre esos dos tags del motor
    # entraron recursos secundarios, historial de estados y **reserva atomica**
    # (ADR-009 a ADR-013), y ese ultimo le cambia la interfaz al repositorio de
    # turnos: `_TurnosEnHoraLocal` no implementa `reserve()`, asi que subir a
    # `v0.10.0` rompe mas de 20 tests de agenda de este producto. Lo verifico el
    # CI el 2026-08-24, no una lectura del changelog. Ese salto es un trabajo
    # aparte; la `v0.9.1` es un backport que trae SOLO el empaquetado de las
    # migraciones, con `application.py` identico a la `v0.9.0`.
    #
    # 🔑 **El orden no es estetico.** Las revisiones de este producto tienen FK
    # contra tablas de LibraGenda (`branches`), asi que la cadena del motor va
    # primero. Al reves, la primera revision que las toque muere con
    # `relation "branches" does not exist`.
    #
    # Son tablas de version distintas: `alembic_version_libragenda` para LibraGenda
    # (desde su v0.14.0, ADR-017 de libragenda; antes `alembic_version`, que es la de
    # LibraCore y la que `libragenda-migrar` renombra solo), `alembic_version_gestiolibra`
    # para esta cadena y `alembic_version` para la de `libracore-migrar`.
    #
    # 🔑 ORDEN (ADR-034): LibraGenda va SIEMPRE primero. Su `0010_agenda_clients` renombra
    # `clients` -> `agenda_clients`, y en una base nueva de una sola base la `0002` de
    # LibraCore crea SU `clients` (id entero): al reves, las dos pisarian el nombre. Despues
    # va libraauth, despues libracore y la propia al final (sus FK apuntan a `agenda_clients`
    # y a `branches`). Lo ata `tests/test_migraciones_en_el_deploy.py`.
    # 🔴 **CUATRO cadenas, y el orden no es decorativo.**
    #
    # 1. `libragenda-migrar` — va primero porque las revisiones propias de este
    #    producto tienen FK contra tablas de LibraGenda.
    # 2. `libraauth-migrar` — las seis tablas de auth. `--base core`, **a propósito, y no
    #    `--base dominio`** (ver abajo).
    # 3. `libracore-migrar` — el esquema de LibraCore. Con una sola base (ADR-035) no hay
    #    `GESTIOLIBRA_LIBRACORE_DATABASE_URL` y el comando cae a la base del dominio, porque
    #    `gestiolibra` figura en `_UNA_SOLA_BASE` desde libracore v1.194.0 (ADR-083). Ver
    #    `libracore.migrar.url_de_core`.
    # 4. `alembic` — la cadena propia.
    #
    # La del motor no la corría nadie hasta el 2026-08-25: sus migraciones no
    # viajaban en el wheel. Medido, `gestiolibra_core` de la demo no tiene
    # `alembic_version` ninguna y le faltan las cuatro columnas que la revisión
    # `0002` le agrega a `clients`.
    migraciones=(
        ("libragenda-migrar", "upgrade"),
        # 🔴 `--base core` y NO `--base dominio`, medido el 2026-10-25. Con `--base core` el comando usa la base
        # del core si la instancia todavía tiene la variable (la demo, hasta que se una) y, si no, cae a la del
        # dominio (dev unida y todo alta nueva). Con `--base dominio` migraría SIEMPRE la del dominio: en una
        # instancia que aún tiene dos bases crea ahí las ocho tablas de auth, vacías, al lado de las reales, y
        # `libracore-unir-bases verificar` corta después con `auth_en_los_dos`. Es el mismo destino en una base
        # única; cambiarlo a `dominio` es un PR aparte, cuando no quede ninguna instancia de dos bases.
        ("libraauth-migrar", "upgrade", "--prefijo", "gestiolibra", "--base", "core"),
        ("libracore-migrar", "upgrade", "--prefijo", "gestiolibra"),
        ("alembic", "upgrade", "head"),
    ),
    repo_root=REPO_ROOT,
    base_port=8076,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = get_config().clientes_dir
_NPM_AVAILABLE = npm_available()

if __name__ == "__main__":
    cli()
