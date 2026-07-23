# Changelog — Gestiolibra

## [Unreleased]

- **Frontend: SPA en React+Vite, MVP de login + agenda** (ver ADR-019):
  primer frontend de Gestiolibra (`frontend/`), nunca antes existió
  ninguno. Login + vista de agenda por recurso/rango de fechas, alta de
  turno, confirmar/cancelar/completar. Consume la API JSON existente sin
  cambios (cookie de sesión, proxy de Vite en dev, servido desde el
  mismo proceso FastAPI en producción vía `app/asgi.py`). Dockerfile con
  stage nuevo de build de node. Verificado manualmente end-to-end en el
  browser (login admin y staff, alta y ciclo de vida completo de un
  turno, sin errores de consola).
- **Lectura de catálogo abierta a staff** (ver ADR-018):
  `branches`/`resources`/`services`/`clients` pasan de admin-only a
  staff+admin en sus endpoints `GET` (escritura sigue admin-only) —
  necesario para que el frontend funcione también logueado como staff,
  no solo admin. 4 tests nuevos (135 en total).
- **Cierre de Fase 3** (ver ADR-017): flujo automático de dominio+SSL
  verificado de punta a punta contra el cliente `prueba`
  (`_setup_npm_proxy()` real, sin workaround — confirma que el hallazgo
  de ADR-016 era config, no bug) y backups probados end-to-end
  (`panel_admin.py backup`/`restore-db`). Sin cambios de código. El
  cuarto ítem de Fase 3 ("validación con primeros negocios reales")
  queda explícitamente abierto — depende de tener un cliente real.
- **Branding y dominio por cliente** (ver ADR-016): `dev.gestiolibra.com.ar`
  con proxy NPM + certificado Let's Encrypt real, reutilizando la misma
  instancia de NPM y credenciales que ya usan Contalibra/Restolibra. Sin
  cambios de código — la maquinaria (`scripts/npm_api.py`/`npm_setup.py`)
  ya existía. "Branding" más allá de dominio+SSL no aplica sin frontend.
- **Dashboard: sumar facturación/caja** (ver ADR-015): `GET /dashboard`
  ahora incluye `facturacion.facturas_emitidas_en_periodo` y
  `facturacion.caja` (ingresos/egresos/saldo del período + saldo total),
  reutilizando `libracore.db.caja.get_caja_resumen()`/`facturas.
  get_facturas_filtradas()`, ya genéricos. 1 test nuevo (131 en total).
- **Deploy real verificado en el VPS** (cierra el onboarding
  multi-negocio de ADR-013, ver ADR-014): build de `gestiolibra:latest`
  y primer cliente de prueba (`prueba`, puerto 8076, plan Premium)
  provisionados con éxito. Dos bugs reales encontrados y corregidos —
  ninguno visible en desarrollo local, sin Docker en WSL: (1) auth SSH
  con el ssh-agent multi-key del VPS rompía el clone de LibraGenda
  dentro del build (GitHub autentica con la primera key que acepte, sin
  reintentar) — `Dockerfile` ahora usa un alias de `Host` SSH dedicado
  por dependencia con `IdentitiesOnly`; (2) `app/asgi.py` no entendía
  el contrato de env vars que genera `libracore.provisioning`
  (`DATA_DIR`/`ADMIN_USER` en vez de `DATABASE_URL`/`GESTIOLIBRA_*`) —
  ahora deriva uno del otro cuando corresponde. Deploy key dedicada de
  solo lectura para el propio repo Gestiolibra (`id_ed25519_gestiolibra`).
- **Onboarding multi-negocio**: sistema de planes con enforcement real
  (`plans.py`: Básico/Estándar/Premium, $15k/$25k/$40k), tabla `modulos`
  (migración `0005_modulos`), `require_module()` gatea recordatorios/
  señas/facturación/dashboard con 403 (turnos y catálogo nunca se
  gatean; completar un turno nunca se bloquea, solo se salta la
  facturación si el plan no la incluye). Primera infraestructura de
  deploy de Gestiolibra: `Dockerfile`, `docker-compose.yml`, `app/asgi.py`,
  `scripts/{nuevo_cliente,panel_admin,npm_api,npm_setup}.py` (wrappers
  sobre `libracore.provisioning`, mismo patrón que Contalibra/Restolibra).
  Ver `DECISIONS.md` ADR-013.
- **Dashboard**: `GET /dashboard?date_from=&date_to=` (admin-only) —
  turnos (total y por estado en el rango, turnos de hoy), clientes
  (total activos, altas nuevas en el rango vía `client_billing.
  created_at` nuevo, migración `0004_client_created_at`) y
  recordatorios enviados/señas pendientes. Facturación/caja queda para
  una entrega futura (mismo alcance que MedLibra). `libragenda` a
  `v0.9.0` (agrega `list_sent()`/`list_by_status()`). Ver
  `DECISIONS.md` ADR-012.
- **Facturación/caja con LibraCore**: `client_billing` extiende `Client`
  con `cuit`/`condicion_iva` (migración `0003_client_billing`, primera
  extensión propia de Client), `PUT`/`GET /config/arca` (config ARCA de
  instancia única, admin-only), `POST /appointments/{id}/complete` — una
  factura por turno completado cuando el servicio tiene precio
  configurado (tipo A/B según condición de IVA), seña ya cobrada y saldo
  restante como movimientos de caja separados sobre la misma factura.
  `libragenda` a `v0.8.0`, `libracore` a `v0.16.1`. Mismo diseño exacto
  que MedLibra. Ver `DECISIONS.md` ADR-011.
- **SQLite pasa a ser el destino de producción por defecto** (arquitectura
  silo, mismo estándar que toda la familia Libra) — Postgres sigue
  soportado, ver `DECISIONS.md` ADR-010. LibraGenda actualizado a
  `v0.6.0` (activa `PRAGMA foreign_keys=ON` en toda conexión SQLite). CI
  ya no levanta un servicio Postgres, corre contra un archivo SQLite.
  Bug real corregido de paso: `BranchRepository.delete()` borraba el
  `Branch` antes que `BranchContactRow` (FK invertida) — invisible en
  SQLite sin FKs forzadas, ahora corregido. `DELETE` de sucursales,
  recursos, servicios y clientes ahora devuelve 409 (antes 500) cuando
  todavía tienen registros dependientes.
- Recordatorios y señas: `POST /reminders/dispatch` (admin-only, dispara
  avisos vencidos — 24h y 2h antes, fijo) y `POST`/`GET /appointments/{id}/deposit`
  + `POST /deposits/{id}/mark-paid`/`mark-failed`/`refund` (admin-only para
  confirmar). Notificaciones y pago sin proveedor real todavía: puertos
  placeholder (`LoggingNotificationPort`, `ManualPaymentPort`) que loguean
  en vez de enviar/cobrar — decisión acordada con el usuario, ver ADR-009.
  Sin migración nueva (`deposits`/`sent_reminders` son tablas de LibraGenda).
- Configuración comercial del negocio: `/branches/{id}/hours` (horario
  comercial semanal por sucursal, opt-in — sin configurar no gatea nada),
  `/services/{id}/prices` (precio por servicio y sucursal), `/branches`
  ahora acepta `phone`/`address`, `/business` (nombre comercial y moneda,
  singleton). `AppointmentService.create()`/`reschedule()` validan el
  horario comercial cuando está configurado. Migración
  `0002_business_config`.
- CI (GitHub Actions): `pytest` + smoke check de las dos cadenas de Alembic
  (LibraGenda + propia) contra Postgres de servicio, en cada push/PR a
  `main`. Requiere el secret `LIBRA_PAT` (ver `README.md`).
- Alembic propio (`migrations/`) para la tabla `users` — antes solo se
  creaba vía `create_all()`, sin efecto en un deploy real. Cadena de
  versión independiente (`alembic_version_gestiolibra`) para no colisionar
  con la de LibraGenda sobre la misma base.
- Login y roles básicos: `POST /auth/login`, `/auth/logout`, `GET /auth/me`,
  CRUD de usuarios admin-only en `/users`. Reusa `libracore.auth.SessionAuth`
  (cookie firmada); tabla `users` propia. Dos roles: `admin` (todo) y
  `staff` (solo su agenda de turnos). Todos los routers existentes quedan
  gateados por rol. Completa la Fase 1 (MVP operativo). Suma `libracore`
  como dependencia nueva.
- `POST /appointments/{id}/cancel` y `POST /appointments/{id}/reschedule`,
  ambos con `reason` opcional en el body (usa el campo agregado en
  LibraGenda `v0.5.0`).
- LibraGenda actualizado a `v0.5.0` (motivo opcional en cancelación/
  reprogramación de turnos). Base `gestiolibra` migrada a `0007_appointment_reason`.
- Normalización documental al estándar híbrido por producto.

## 2026-07-18 — Disponibilidad y agenda

- CRUD de ventanas semanales, bloqueos y excepciones por recurso.
- Agenda por rango de fechas.
- Validación de turnos contra disponibilidad real configurada.
- Corrección upstream en LibraGenda para datetimes UTC-aware entre SQLite y PostgreSQL.

## 2026-07-18 — CRUD del MVP

- CRUD de sucursales, recursos, servicios y clientes.
- Repositorio compartido LibraGenda extendido con operaciones get/update/delete.

## 2026-07-18 — Integración inicial

- Separación de routers y servicios de aplicación.
- LibraGenda `v0.3.0` pineado.
- PostgreSQL dedicado migrado y verificado end-to-end en entorno dev real.
- Smoke test HTTP inicial.
