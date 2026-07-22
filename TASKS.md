# Tasks — Gestiolibra

Trabajo concreto vigente. La dirección estratégica permanece en `ROADMAP.md`; este archivo no es un historial.

## En curso

Ninguna en curso registrada. Fase 1 (MVP operativo) quedó completa con login
y roles — ver `ROADMAP.md`.

## Próximas

- [ ] Evaluar composición con LibraCore para facturación y caja (ya se sumó
      como dependencia para `SessionAuth`; falta decidir si además se usa
      para caja/facturación).

## Después del MVP

- [ ] Dashboard y reportes operativos.
- [ ] Onboarding multi-negocio.
- [ ] Branding y dominio por cliente.

## Bloqueadas

Ninguna bloqueada registrada.

Resuelto (2026-07-21): Alembic propio de Gestiolibra para la tabla `users`
(`alembic_version_gestiolibra`, cadena independiente de la de LibraGenda
sobre la misma base) — ver `README.md`.

Resuelto (2026-07-22): configuración comercial del negocio — horario por
sucursal, precio por servicio y sucursal, contacto de sucursal y datos
globales del negocio. Migración `0002_business_config`.

Resuelto (2026-07-22): recordatorios y señas — `POST /reminders/dispatch`,
`POST`/`GET /appointments/{id}/deposit`, `POST /deposits/{id}/mark-paid`/
`mark-failed`/`refund`. Notificaciones y pago con puertos placeholder
(`LoggingNotificationPort`, `ManualPaymentPort`) hasta definir proveedor
real. Sin migración nueva (tablas de LibraGenda ya migradas).

## Notas de testing

- La suite (`pytest`) usa cookies de sesión firmadas con timestamp
  (`itsdangerous`, vía `libracore.auth.SessionAuth`). En este entorno WSL2
  se confirmó empíricamente que el reloj del sistema puede saltar hacia
  atrás ~20s en medio de una corrida (desincronización de reloj WSL2↔host
  Windows) — eso invalida un cookie válido con `SignatureExpired: age <0`,
  causando un 401 intermitente y no reproducible (~1 cada 10-15 corridas
  completas). No es un bug de la app: no ocurre en el servidor real de
  producción (reloj no virtualizado). Si un test de auth falla una sola vez
  de forma aislada sin cambios de código, reintentar antes de investigar.
