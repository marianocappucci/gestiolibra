# Tasks — Gestiolibra

Trabajo concreto vigente. La dirección estratégica permanece en `ROADMAP.md`; este archivo no es un historial.

## En curso

Ninguna en curso registrada. Fase 1 (MVP operativo) quedó completa con login
y roles — ver `ROADMAP.md`.

## Próximas

- [ ] Configuración comercial por negocio más allá del CRUD básico de sucursales.
- [ ] Evaluar composición con LibraCore para facturación y caja (ya se sumó
      como dependencia para `SessionAuth`; falta decidir si además se usa
      para caja/facturación).
- [ ] Preparar recordatorios, señas y políticas de cancelación.
- [ ] Gestiolibra todavía no tiene Alembic propio: la tabla `users` (y
      cualquier tabla futura que no pertenezca a LibraGenda) solo se crea
      vía `Base.metadata.create_all()` en `create_app()` — documentado como
      "demo only" pero hoy es el único mecanismo real para sus propias
      tablas. Definir migraciones propias antes de un deploy real.

## Después del MVP

- [ ] Dashboard y reportes operativos.
- [ ] Onboarding multi-negocio.
- [ ] Branding y dominio por cliente.

## Bloqueadas

Ninguna bloqueada registrada.

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
