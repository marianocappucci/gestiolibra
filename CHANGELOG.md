# Changelog — Gestiolibra

## [Unreleased]

- `POST /appointments/{id}/cancel` y `POST /appointments/{id}/reschedule`,
  ambos con `reason` opcional en el body (usa el campo agregado en
  LibraGenda `v0.5.0`). Completa el MVP operativo de turnos.
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
