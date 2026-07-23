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

from libracore.provisioning import configure
from libracore.provisioning.nuevo_cliente import (
    ClienteError, ask, build_image, crear_cliente, image_exists, main,
    network_exists, next_port, slugify, used_ports,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    product_name="GESTIOLIBRA",
    image_name="gestiolibra:latest",
    container_prefix="gestiolibra",
    db_filename="gestiolibra.db",
    repo_root=REPO_ROOT,
    base_port=8076,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = REPO_ROOT / "clientes"

if __name__ == "__main__":
    main()
