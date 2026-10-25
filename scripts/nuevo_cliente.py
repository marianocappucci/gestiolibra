#!/usr/bin/env python3
"""
Onboarding de nuevo cliente Gestiolibra.
Uso: python3 scripts/nuevo_cliente.py

Wrapper de configuración sobre libracore.provisioning.nuevo_cliente (lógica
compartida con Contalibra/Restolibra — ver wiki/entities/libracore.md).
Solo fija las constantes propias de Gestiolibra; la lógica real vive en
LibraCore.
"""
from pathlib import Path

from libracore.provisioning import configure, get_config
from libracore.provisioning.nuevo_cliente import (
    ClienteError,
    ask,
    build_image,
    crear_cliente,
    image_exists,
    main,
    network_exists,
    next_port,
    slugify,
    used_ports,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    postgres=True,
    # ⚠️ **Tiene que decir lo mismo que `scripts/panel_admin.py`.** Hasta el
    # 2026-08-24 este archivo no pasaba `backup_zip` y el otro sí. Como pisan un
    # `_cfg` GLOBAL y `libracore.admin.services` importa los dos módulos en el
    # mismo proceso, una diferencia acá hace que el resultado dependa del orden
    # de los imports. `tests/test_provisioning.py` lo compara entero con
    # `asdict`.
    #
    # **No estaba mordiendo**: todo camino que hoy lee `cfg.backup_zip` entra por
    # `panel_admin.py`, que ya lo tenía en `True`. Se ve en el servidor — las
    # instancias vienen armando su ZIP diario en `data/backups/`. Era una mina,
    # no un incendio.
    #
    # `True` es el valor correcto y no un empate arbitrario: este producto sirve
    # su pantalla de Backups con el `build_backup_router` de `libracore.respaldo`,
    # así que el ZIP del cron es exactamente el que el cliente puede listar,
    # bajar y restaurar solo. Sin el flag, el `tar.gz` empaqueta `data/` mientras
    # el dump de PostgreSQL queda **afuera**.
    backup_zip=True,
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
    # 2. `libraauth-migrar` — las seis tablas de auth. `--base dominio`: desde el 2026-10-25 dev y demo son
    #    de UNA sola base (ADR-037) y no queda ninguna instancia de dos (ADR-035 punto 2 lo dejaba en
    #    `--base core` por la demo, que todavía tenía dos).
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
        # `--base dominio` (ADR-037): la base única de la instancia. `libraauth-migrar` migra la de
        # `GESTIOLIBRA_DATABASE_URL` (o su histórico `DATABASE_URL`), que es donde viven también LibraGenda y LibraCore.
        # Antes iba `--base core`, a propósito: con `dominio` una instancia de DOS bases crearía las tablas de auth vacías
        # en la base equivocada y dejaría la unión imposible (`auth_en_los_dos`). Ya no queda ninguna.
        ("libraauth-migrar", "upgrade", "--prefijo", "gestiolibra", "--base", "dominio"),
        ("libracore-migrar", "upgrade", "--prefijo", "gestiolibra"),
        ("alembic", "upgrade", "head"),
    ),
    repo_root=REPO_ROOT,
    base_port=8076,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = get_config().clientes_dir

if __name__ == "__main__":
    main()
