"""De dónde salen los clientes que MercadoPago factura, en Gestiolibra.

Implementa el puerto `libracore.registro_de_clientes.RegistroDeClientes` sobre
el `ClientRepository` de este producto — o sea sobre el `Client` de LibraGenda
más la extensión local `client_billing` (`cuit`, `condicion_iva`).

## Por qué no se usa la tabla `clients` de LibraCore

Porque acá el cliente **es el de la agenda**: de él cuelgan los turnos, con
clave foránea. La tabla de LibraCore existe en esta instancia —la crea
`init_core_schema` para que vivan `facturas` y `caja`— pero está vacía y nadie
la lee. Usarla haría que cada cobro emitiera a "Consumidor Final" con el email
del pagador como razón social, y dejaría filas en una tabla que este producto
no toca. Está analizado el 2026-08-12; ver
`wiki/analyses/clientes-transversal-familia-libra.md`.

## Dos decisiones de este registro

🔑 **Un cobro de alguien que no es cliente NO da de alta un cliente de la
agenda.** El fallback del motor, cuando no encuentra a nadie, pide crear uno.
Acá eso significaría que cualquiera que pague por MercadoPago aparezca en la
agenda del negocio, con nombre sacado del pagador de MP. `crear()` devuelve un
cliente **transitorio**, sin persistir: la factura sale a Consumidor Final a
nombre del pagador, que es lo correcto, y la agenda no se ensucia.

⚠️ **No hay alias de facturación.** `facturacion_alias.cliente_id` es `INTEGER`
y la identidad de un cliente acá es `String(100)`, así que esa tabla no sirve.
No se inventa una propia porque el caso que los alias resuelven —el contador que
paga por su cliente— es de un negocio de suscripciones, no de uno de turnos:
acá el que paga el turno es el que lo toma. Si algún día hace falta, va en este
archivo y en ningún otro lado.
"""

from __future__ import annotations

from app.services.clients import ClientRepository


def _sin_guiones(valor: str | None) -> str:
    return (valor or "").replace("-", "").replace(".", "").strip()


def _como_cliente_del_motor(fila: dict) -> dict:
    """Traduce un cliente de este producto a las claves que espera el motor.

    El motor pide `name`, `cuit_dni`, `iva_condition`, `address`, `email`,
    `auto_facturar` e `id`. Acá `address` no existe —la agenda no guarda
    domicilio— y `auto_facturar` tampoco: la decisión de facturar solo la toma
    el producto, no una bandera por cliente.
    """
    return {
        "id": fila["id"],
        "name": fila.get("name") or "",
        "cuit_dni": fila.get("cuit") or "",
        "iva_condition": fila.get("condicion_iva") or "Consumidor Final",
        "email": fila.get("email") or "",
        "address": "",
        "auto_facturar": False,
    }


class RegistroDeGestiolibra:
    """El puerto, sobre el `ClientRepository` de este producto."""

    def __init__(self, clientes: ClientRepository) -> None:
        self.clientes = clientes

    # ── el puerto ───────────────────────────────────────────────────────────

    def resolver(self, payer_email: str, payer_cuit: str) -> dict | None:
        """Match directo por email o por CUIT normalizado. Sin alias — ver el
        docstring del módulo.

        Recorre la lista en memoria en vez de consultar por índice: son
        instancias de un negocio de turnos, con cientos de clientes y no
        cientos de miles, y `list()` es la API pública del repositorio — así
        este archivo no queda atado a la forma de las tablas de LibraGenda.
        """
        email = (payer_email or "").strip().lower()
        cuit = _sin_guiones(payer_cuit)
        if not email and not cuit:
            return None
        for fila in self.clientes.list():
            if email and (fila.get("email") or "").strip().lower() == email:
                return _como_cliente_del_motor(fila)
            if cuit and _sin_guiones(fila.get("cuit")) == cuit:
                return _como_cliente_del_motor(fila)
        return None

    def crear(self, *, nombre: str, email: str = "", cuit_dni: str = "",
              iva_condition: str = "Consumidor Final", address: str = "") -> dict:
        """🔑 **No persiste nada.** Ver el docstring del módulo: un cobro de
        alguien que no es cliente no puede dar de alta un cliente de la agenda.

        El `id` viene en `None` a propósito, para que quede claro en cualquier
        log o inspección que ese cliente no existe en ningún lado.
        """
        return {
            "id": None, "name": nombre, "cuit_dni": cuit_dni,
            "iva_condition": iva_condition, "email": email,
            "address": address, "auto_facturar": False,
        }

    def buscar_muchos(self, emails: set[str], cuits: set[str]) -> tuple[dict, dict]:
        por_email: dict = {}
        por_cuit: dict = {}
        if not emails and not cuits:
            return por_email, por_cuit
        emails_norm = {(e or "").strip().lower() for e in emails}
        for fila in self.clientes.list():
            cliente = _como_cliente_del_motor(fila)
            correo = (fila.get("email") or "").strip()
            if correo and correo.strip().lower() in emails_norm:
                por_email[correo] = cliente
            cuit = _sin_guiones(fila.get("cuit"))
            if cuit and cuit in cuits:
                por_cuit[cuit] = cliente
        return por_email, por_cuit
