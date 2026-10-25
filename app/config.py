"""Dónde viven la base del dominio y la de LibraCore: **una sola o dos**, según la instancia.

🔑 **Una sola base es el destino** (ADR-034, decisión del humano del 2026-10-21, igual que
LibraClub ADR-020): `usuarios` y `auth_log` son las de `libraauth` y el motor las comparte, y
para que la caja y la factura se escriban junto con el turno tienen que estar en la misma base.
`gestiolibra-dev` ya está unida (ADR-035) y todo alta nueva nace con una; `gestiolibra-demo` todavía lleva
dos, `gestiolibra` y `gestiolibra_core`, y se une con `libracore-unir-bases` en otro paso. Hasta entonces el
código anda con las dos formas:

- **Sin `GESTIOLIBRA_LIBRACORE_DATABASE_URL`** (ni su nombre histórico
  `GESTIOLIBRA_LIBRACORE_DB_PATH`), o con la **misma base** que la del dominio: LibraCore vive
  en la base del dominio. Es la forma de una instancia unida y la de un alta nueva.
- **Con otra base**: la de LibraCore es esa. Es la forma de dev y demo hasta que se unan.

Se resuelve en un solo lugar y devuelve **un solo valor**: si es la misma base, la URL del
dominio tal cual. Quien necesita saber si son dos (el respaldo, que no puede volcar la misma base
dos veces) pregunta `misma_base`.

PostgreSQL y nada más: `services/billing.configure` ya rechaza una ruta de archivo.
"""
from __future__ import annotations

from libracore.db.url_de_instancia import url_de_instancia

PREFIJO = "gestiolibra"


def _normal(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1).split("?", 1)[0].rstrip("/")


def misma_base(a: str, b: str) -> bool:
    """Si dos URLs apuntan a la misma base, aunque una diga `+psycopg` y la otra no.

    Compara servidor, usuario y nombre de la base; ignora el driver, los parámetros
    (`?sslmode=...`) y la barra final. No resuelve nombres de host: dos alias del mismo
    servidor cuentan como distintos, y entonces se trata como dos bases (respaldar de más es
    el error barato; respaldar de menos no)."""
    return _normal(a) == _normal(b)


def url_de_libracore(url_del_dominio: str, entorno=None) -> str:
    """La URL de la base de LibraCore de esta instancia: la propia o, si no hay, la del dominio.

    Sin variable, o con la misma base que el dominio, devuelve **la URL del dominio tal cual**.
    Con una base distinta (las instancias que todavía no se unieron) devuelve esa."""
    propia = url_de_instancia(PREFIJO, core=True, entorno=entorno)
    if not propia or misma_base(url_del_dominio, propia):
        return url_del_dominio
    return propia

