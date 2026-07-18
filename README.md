# Gestiolibra

Vertical de gestión de turnos para negocios de servicios no clínicos:
barberías, peluquerías, estética, lavaderos, talleres y similares.

Compone:

- LibraGenda `v0.1.0` — agenda, recursos, servicios y ciclo de vida de turnos.
- LibraCore — administración/facturación/caja, cuando corresponda.

Gestiolibra posee la API HTTP y el flujo de producto. LibraGenda permanece
como paquete reutilizable con PostgreSQL dedicado y migraciones propias.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

La base PostgreSQL y las migraciones de LibraGenda deben estar configuradas
antes de iniciar la aplicación real.
