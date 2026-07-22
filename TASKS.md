# Tasks — Gestiolibra

Trabajo concreto vigente. La dirección estratégica permanece en `ROADMAP.md`; este archivo no es un historial.

## En curso

Ninguna en curso registrada. Fase 1 (MVP operativo) quedó completa con login
y roles — ver `ROADMAP.md`.

## Próximas

- [ ] Dashboard y reportes operativos.
- [ ] Onboarding multi-negocio.
- [ ] Branding y dominio por cliente.
- [ ] Upload real de certificado/clave ARCA (`PUT /config/arca` hoy acepta
      solo paths en el filesystem del servidor — ver ADR-011).
- [ ] Revisar el cálculo de IVA de facturación (21% fijo) con un contador
      antes de facturar contra ARCA real (ver ADR-011).
- [ ] Cargar credenciales ARCA reales cuando el usuario las tenga — hoy
      solo funciona en modo mock (`ENV=development`).

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

Resuelto (2026-07-22): SQLite como destino de producción por defecto
(estándar de familia, ver `DECISIONS.md` ADR-010). LibraGenda a `v0.6.0`.
Bug real corregido: `BranchRepository.delete()` con orden de borrado
invertido (FK), invisible sin FKs forzadas. `DELETE` de sucursales/
recursos/servicios/clientes ahora devuelve 409 en vez de 500 con
dependientes. CI simplificado (sin servicio Postgres).

Resuelto (2026-07-22): facturación/caja con LibraCore (ver ADR-011).
`client_billing` extiende `Client` con `cuit`/`condicion_iva` (migración
`0003_client_billing`, primera extensión propia de Client — antes se
usaba el genérico de LibraGenda sin extensión). `POST /appointments/
{id}/complete` factura el turno (LibraGenda `v0.7.0`) cuando el servicio
tiene precio configurado — una sola factura con `libracore.
arca_facturacion` (LibraCore `v0.16.1`), tipo A/B según condición de
IVA, seña ya cobrada y saldo restante como movimientos de caja
separados apuntando a la misma factura. `PUT`/`GET /config/arca`
(admin-only, instancia única). `libragenda` a `v0.8.0` (`medio_pago`
opcional en depósitos). Mismo diseño exacto que MedLibra, portado casi
verbatim — ver `DECISIONS.md` de ese repo (ADR-016) para el detalle
completo. 30 tests nuevos, verificado además end-to-end contra
archivos SQLite reales.

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
