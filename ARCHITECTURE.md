# Arquitectura — Gestiolibra

## Propósito y límites

Gestiolibra es la API y producto vertical para negocios de servicios no clínicos. Cubre barberías, peluquerías, estética, lavaderos, talleres y negocios similares.

Gestiolibra posee el flujo HTTP y las reglas propias del negocio; LibraGenda aporta el motor genérico de agenda. No se incorporan historia clínica, recetas, estudios, mesas, comandas, cocina ni food cost.

## Componentes

- `app/main.py`: factory FastAPI, configuración y composición de dependencias.
- `app/dependencies.py`: providers que leen el estado de la aplicación.
- `app/services/appointments.py`: capa de aplicación sobre LibraGenda.
- `app/routers/`: health, sucursales, recursos, servicios, clientes, disponibilidad, turnos y agenda.
- `MODULES.md`: inventario operativo de módulos.
- LibraGenda `v0.4.2`: dependencia versionada para dominio, persistencia y migraciones propias.

## Persistencia e integración

La aplicación configura LibraGenda mediante `LIBRAGENDA_DATABASE_URL` y usa PostgreSQL dedicado para Gestiolibra. Las migraciones de LibraGenda se ejecutan desde el repositorio upstream en el tag exacto pineado, antes de iniciar la API; no se usa `create_all()` en producción.

La lógica de negocio no debe duplicarse localmente cuando pertenece al motor genérico. Los routers traducen errores de dominio e integridad a respuestas HTTP.

## Entornos y deploy

- Desarrollo: entorno dev con base `gestiolibra` y usuario dedicado.
- Demo: producción controlada para validación.
- Producción: dominio del cliente.

La rama observada actualmente es `main`. La adopción de `develop` como rama de integración queda pendiente de una decisión operativa explícita.
