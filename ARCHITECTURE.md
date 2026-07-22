# Arquitectura — Gestiolibra

## Propósito y límites

Gestiolibra es la API y producto vertical para negocios de servicios no clínicos. Cubre barberías, peluquerías, estética, lavaderos, talleres y negocios similares.

Gestiolibra posee el flujo HTTP y las reglas propias del negocio; LibraGenda aporta el motor genérico de agenda. No se incorporan historia clínica, recetas, estudios, mesas, comandas, cocina ni food cost.

## Componentes

- `app/main.py`: factory FastAPI, configuración y composición de dependencias.
  Aplica el gating por rol a nivel de router (`include_router(..., dependencies=[...])`),
  no por endpoint.
- `app/dependencies.py`: providers que leen el estado de la aplicación.
- `app/auth.py`: sesión por cookie firmada (reusa `libracore.auth.SessionAuth`)
  + dependencias FastAPI propias (`get_current_user`, `require_role`) que
  responden 401/403 JSON — la app no tiene páginas HTML, así que los
  redirects 307 de `SessionAuth.require_auth`/`require_role` no aplican acá.
- `app/security.py`: hashing de contraseñas (PBKDF2, mismo algoritmo que
  `libracore.db.usuarios`, propio porque ese módulo está acoplado a SQLite).
- `app/services/appointments.py`: capa de aplicación sobre LibraGenda.
- `app/services/users.py`: tabla y repositorio de usuarios propios de
  Gestiolibra (no pertenecen al dominio de LibraGenda).
- `app/routers/`: health (público), auth (login/logout/me), users (admin-only),
  sucursales, recursos, servicios, clientes, disponibilidad, turnos y agenda.
- `MODULES.md`: inventario operativo de módulos.
- LibraGenda `v0.5.0`: dependencia versionada para dominio, persistencia y migraciones propias.
- LibraCore (sin versión de facturación/caja todavía): dependencia versionada
  solo por `libracore.auth.SessionAuth` — ver `DECISIONS.md` ADR-005.

## Autenticación y roles

Sesión por cookie firmada (`itsdangerous`, vía LibraCore), sin JWT ni
tokens de API todavía. Dos roles: `admin` (catálogo completo, disponibilidad,
usuarios) y `staff` (solo su propia agenda: crear/confirmar/cancelar/
reprogramar turnos). La tabla `users` es de Gestiolibra, no de LibraGenda ni
de LibraCore — cada producto de la familia Libra que reusa `SessionAuth`
trae su propia tabla de usuarios en su propio stack de persistencia (ver
`libracore.auth`'s docstring: callback en vez de asumir el schema).

## Persistencia e integración

La aplicación configura LibraGenda mediante `LIBRAGENDA_DATABASE_URL` y usa PostgreSQL dedicado para Gestiolibra. Las migraciones de LibraGenda se ejecutan desde el repositorio upstream en el tag exacto pineado, antes de iniciar la API; no se usa `create_all()` en producción.

La lógica de negocio no debe duplicarse localmente cuando pertenece al motor genérico. Los routers traducen errores de dominio e integridad a respuestas HTTP.

## Entornos y deploy

- Desarrollo: entorno dev con base `gestiolibra` y usuario dedicado.
- Demo: producción controlada para validación.
- Producción: dominio del cliente.

La rama observada actualmente es `main`. La adopción de `develop` como rama de integración queda pendiente de una decisión operativa explícita.
