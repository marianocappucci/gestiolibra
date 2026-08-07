#!/usr/bin/env python3
"""Carga los datos de la demo pública de Gestiolibra — ítem 8 de los pendientes
transversales de Libra.

**Para qué.** Una demo vacía no muestra nada: quien entra ve pantallas en blanco
y se va. Este script deja la instancia con un negocio verosímil andando —una
peluquería con dos sucursales— para que las pantallas se puedan mirar.

**Por la API y no por SQL**, a propósito: así los datos pasan por las mismas
validaciones y los mismos servicios que usa la pantalla. Un seed por SQL puede
crear estados que la aplicación nunca produciría —un turno fuera del horario de
la sucursal, por ejemplo— y entonces lo que se muestra no es el producto.

**No cubre sólo el caso feliz.** Deja a propósito los estados que las pantallas
distinguen: turnos confirmados, pendientes, cancelados y completados; un
recurso inactivo; un servicio con precio distinto por sucursal. Si todo
estuviera en el mismo estado, media pantalla quedaría sin mostrarse.

**Es idempotente**: si el registro ya existe no lo duplica. El cron de reset lo
corre después de recrear la base, pero correrlo dos veces no rompe nada.

> 🔴 **Nunca contra la instancia de un cliente.** Se planta si el host no es de
> dev, demo, prueba o local — ver `url_no_productiva`. Misma guarda que
> `libradesk/scripts/seed_dev.py`.

Uso:
    python scripts/seed_demo.py --url https://demo.gestiolibra.com.ar \\
        --usuario admin --password ...
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from http.cookiejar import CookieJar
from urllib.parse import urlparse

HOY = date.today()

#: Los subdominios que NO son de un cliente. Se compara contra el host entero o
#: su primera etiqueta, **no como substring de la URL**: con substrings, un
#: cliente llamado `demoliciones.gestiolibra.com.ar` pasaría la guarda.
_HOSTS_NO_PRODUCTIVOS = ("dev", "demo", "prueba", "localhost", "127.0.0.1")


def url_no_productiva(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return host in _HOSTS_NO_PRODUCTIVOS or host.split(".")[0] in _HOSTS_NO_PRODUCTIVOS


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def _pedir(self, metodo: str, ruta: str, cuerpo=None):
        datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
        req = urllib.request.Request(
            f"{self.base}{ruta}", data=datos, method=metodo,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=30) as r:
                crudo = r.read()
                return json.loads(crudo) if crudo else None
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"{metodo} {ruta} -> {e.code}: {detalle}") from None

    def get(self, ruta):
        return self._pedir("GET", ruta)

    def post(self, ruta, cuerpo=None):
        return self._pedir("POST", ruta, cuerpo)

    def put(self, ruta, cuerpo=None):
        return self._pedir("PUT", ruta, cuerpo)


def obtener_o_crear(api: Api, ruta: str, clave: str, valor, cuerpo: dict):
    """Crea el registro si no está. Devuelve `(registro, es_nuevo)`.

    La idempotencia va por un campo con significado —el id o el nombre— y no
    por "¿la tabla está vacía?": así el seed se puede correr después de agregar
    un ítem nuevo sin duplicar los anteriores.
    """
    for existente in api.get(ruta) or []:
        if existente.get(clave) == valor:
            return existente, False
    return api.post(ruta, cuerpo), True


# ── El negocio ────────────────────────────────────────────────────────────
#
# Una peluquería con dos sucursales. Se eligió un rubro donde el turno es la
# unidad de trabajo —que es lo que este producto hace— y donde se entiende sin
# explicación que un servicio dure distinto y cueste distinto según dónde.

SUCURSALES = [
    {"id": "centro", "name": "Sucursal Centro", "timezone": "America/Argentina/Buenos_Aires",
     "phone": "11 4383-1200", "address": "Av. Corrientes 1234, CABA"},
    {"id": "norte", "name": "Sucursal Norte", "timezone": "America/Argentina/Buenos_Aires",
     "phone": "11 4747-8890", "address": "Av. Maipú 2450, Vicente López"},
]

SERVICIOS = [
    {"id": "corte", "name": "Corte de pelo", "duration_minutes": 30},
    {"id": "color", "name": "Coloración", "duration_minutes": 90},
    {"id": "brushing", "name": "Brushing", "duration_minutes": 45},
    {"id": "barba", "name": "Arreglo de barba", "duration_minutes": 20},
    # Inactivo a propósito: la pantalla del catálogo distingue activos de
    # inactivos, y con todo activo esa mitad no se ve.
    {"id": "permanente", "name": "Permanente", "duration_minutes": 120, "active": False},
]

#: Precio por servicio y sucursal. **Distinto entre sucursales a propósito**:
#: es la razón de que este producto tenga precios por sucursal en vez de uno
#: solo, y con un único precio esa pantalla no dice nada.
PRECIOS = {
    "corte": {"centro": 12000, "norte": 10500},
    "color": {"centro": 38000, "norte": 34000},
    "brushing": {"centro": 15000, "norte": 13500},
    "barba": {"centro": 7000, "norte": 6500},
}

RECURSOS = [
    {"id": "silla-1", "name": "Andrea Sosa", "branch_id": "centro"},
    {"id": "silla-2", "name": "Martín Ferreyra", "branch_id": "centro"},
    {"id": "silla-3", "name": "Lucía Benítez", "branch_id": "norte"},
    # Inactivo: alguien de licencia. La agenda no tiene que ofrecerlo.
    {"id": "silla-4", "name": "Pablo Quiroga", "branch_id": "norte", "active": False},
]

CLIENTES = [
    {"name": "María Elena Ruiz", "phone": "11 5544-2210", "email": "meruiz@example.com.ar",
     "cuit": "27-24567890-4", "condicion_iva": "Consumidor Final"},
    {"name": "Jorge Fernández", "phone": "11 6677-3345", "email": "jfernandez@example.com.ar",
     "condicion_iva": "Consumidor Final"},
    {"name": "Peluquería Norte SRL", "phone": "11 4747-1100",
     "email": "admin@example.com.ar", "cuit": "30-71234567-8",
     "condicion_iva": "Responsable Inscripto"},
    {"name": "Carolina Méndez", "phone": "11 3322-9987"},
    {"name": "Sofía Aguirre", "phone": "11 2211-4455", "email": "saguirre@example.com.ar"},
    # Inactiva: la pantalla de clientes filtra por activos.
    {"name": "Rodrigo Paz", "phone": "11 8899-1234", "active": False},
]

#: Horario de atención, igual en las dos sucursales: lunes a sábado.
#: **Domingo no**, para que se vea que el horario existe y no es "siempre".
HORARIOS = [(dia, time(9, 0), time(19, 0)) for dia in range(0, 6)]

#: Disponibilidad de cada recurso. **Es otra cosa que el horario de la
#: sucursal**: la sucursal abre 9 a 19, pero cada persona tiene su propia
#: agenda dentro de eso. Sin esto, LibraGenda rechaza todo con
#: `appointment unavailable` — que fue exactamente lo que paso la primera vez
#: que se corrio este seed.
DISPONIBILIDAD = [(dia, time(9, 0), time(19, 0)) for dia in range(0, 6)]

# ⚠️ **Los turnos de ejemplo van entre las 10 y las 14, no mas tarde.**
#
# `AppointmentService._resolve_utc` interpreta la hora naive como hora local de
# la sucursal y la convierte a **UTC**; despues `is_within_hours` compara esa
# hora UTC contra las ventanas de `branch_hours`, que se cargan como hora
# local. Con `America/Argentina/Buenos_Aires` (UTC-3) eso corre la comparacion
# tres horas: una sucursal abierta de 9 a 19 rechaza en la practica todo lo que
# empiece despues de las 16 locales.
#
# **Es un defecto del producto, no del seed**, y no se arregla aca: tocar la
# conversion de husos de la agenda es un cambio con su propia verificacion.
# Esta anotado en la pagina del wiki. Mientras tanto los ejemplos se agendan en
# la franja donde las dos lecturas coinciden.


def sembrar(api: Api) -> None:
    hechos = {}

    def contar(clave: str, nuevo: bool):
        creados, existentes = hechos.get(clave, (0, 0))
        hechos[clave] = (creados + int(nuevo), existentes + int(not nuevo))

    print("Sucursales…")
    for s in SUCURSALES:
        _, nuevo = obtener_o_crear(api, "/branches", "id", s["id"], s)
        contar("sucursales", nuevo)

    print("Horarios de atención…")
    for s in SUCURSALES:
        ya = {h["weekday"] for h in (api.get(f"/branches/{s['id']}/hours") or [])}
        for dia, desde, hasta in HORARIOS:
            if dia in ya:
                contar("horarios", False)
                continue
            api.post(f"/branches/{s['id']}/hours",
                     {"weekday": dia, "starts_at": desde, "ends_at": hasta})
            contar("horarios", True)

    print("Servicios…")
    for s in SERVICIOS:
        _, nuevo = obtener_o_crear(api, "/services", "id", s["id"], s)
        contar("servicios", nuevo)

    print("Precios por sucursal…")
    for servicio, por_sucursal in PRECIOS.items():
        for sucursal, precio in por_sucursal.items():
            # `PUT` idempotente por definición: fija el precio, no lo agrega.
            api.put(f"/services/{servicio}/prices",
                    {"branch_id": sucursal, "price": precio})
            contar("precios", True)

    print("Recursos…")
    for r in RECURSOS:
        _, nuevo = obtener_o_crear(api, "/resources", "id", r["id"], r)
        contar("recursos", nuevo)

    print("Disponibilidad de cada recurso…")
    for r in RECURSOS:
        ya = {d["weekday"] for d in (api.get(f"/resources/{r['id']}/availability") or [])}
        for dia, desde, hasta in DISPONIBILIDAD:
            if dia in ya:
                contar("disponibilidad", False)
                continue
            api.post(f"/resources/{r['id']}/availability",
                     {"weekday": dia, "starts_at": desde, "ends_at": hasta})
            contar("disponibilidad", True)

    print("Clientes…")
    clientes = {}
    for c in CLIENTES:
        registro, nuevo = obtener_o_crear(api, "/clients", "name", c["name"], c)
        clientes[c["name"]] = registro["id"]
        contar("clientes", nuevo)

    print("Turnos…")
    _sembrar_turnos(api, clientes, contar)

    # El logo del negocio, para que los comprobantes salgan como los de
    # un cliente y no con un hueco arriba.
    _cargar_logo(api, "Peluquería Estilo Norte", "E", (124, 58, 237), contar)

    print()
    for clave, (creados, existentes) in sorted(hechos.items()):
        print(f"  {clave:<12} {creados} creados, {existentes} ya estaban")


def _sembrar_turnos(api: Api, clientes: dict, contar) -> None:
    """Turnos en los cuatro estados que la agenda distingue.

    Se reparten entre ayer, hoy y los próximos días para que el dashboard y la
    agenda tengan algo en cada vista. Los de ayer van **completados**: un turno
    pasado que sigue "pendiente" se lee como un error del sistema, no como un
    dato de ejemplo.
    """
    #: Los días que el negocio atiende, tomados de HORARIOS: si mañana se suma
    #: el domingo, esto lo sigue solo.
    DIAS_HABILES = {dia for dia, _, _ in HORARIOS}

    def _habil(fecha: date) -> bool:
        return fecha.weekday() in DIAS_HABILES

    def cuando(dias: int, hora: int, minuto: int = 0) -> datetime:
        """El día hábil número `dias` contando desde hoy (negativo = hacia atrás).

        🔴 **No es `HOY + días`, y esa era la falla.** Con desplazamientos de
        calendario, un turno a "+1" corrido un sábado cae domingo y LibraGenda
        lo rechaza —correctamente— por estar fuera del horario. El seed lo
        avisaba y seguía, así que la demo amanecía con menos turnos sin que
        nada fallara a la vista, y el reset corre todas las noches.
        """
        fecha = HOY
        paso = 1 if dias >= 0 else -1
        restantes = abs(dias)
        while not _habil(fecha):
            fecha += timedelta(days=1)
        while restantes:
            fecha += timedelta(days=paso)
            if _habil(fecha):
                restantes -= 1
        return datetime.combine(fecha, time(hora, minuto))

    # ⚠️ **No hay `GET /appointments`**: la agenda se lista por recurso y rango
    # (`/resources/{id}/agenda`). Preguntarle a la ruta que uno se imagina
    # devuelve el HTML de la SPA, que es el catch-all — no un 404. Es la misma
    # trampa que un dominio derivado de la convención: el 200 engaña.
    desde, hasta = HOY - timedelta(days=2), HOY + timedelta(days=5)
    ya_cargados = sum(
        len(api.get(f"/resources/{r['id']}/agenda"
                    f"?date_from={desde}&date_to={hasta}") or [])
        for r in RECURSOS
    )
    if ya_cargados >= 8:
        contar("turnos", False)
        print(f"  (ya hay {ya_cargados} turnos cargados)")
        return

    # (dias, hora, recurso, servicio, cliente, estado_final)
    #
    # Ningun turno arranca despues de las 14 — ver el aviso del huso horario
    # arriba. Y ninguno cae en domingo: la sucursal no abre, y un ejemplo
    # rechazado no es un ejemplo.
    # Las acciones son las rutas del router, **en ingles**: `confirm`,
    # `cancel`, `complete`. No traducirlas — el 405 que devuelve una accion
    # inventada no dice cual es la buena.
    #
    # 🔴 **Es una maquina de estados, no un campo.** Un turno `pending` no se
    # puede completar de una: hay que confirmarlo primero
    # (`cannot transition pending to completed`). Por eso la ultima columna es
    # una LISTA de pasos y no un estado final.
    PLAN = [
        (-1, 10, "silla-1", "corte", "María Elena Ruiz", ["confirm", "complete"]),
        (-1, 11, "silla-3", "color", "Sofía Aguirre", ["confirm", "complete"]),
        (0, 11, "silla-1", "brushing", "Carolina Méndez", ["confirm"]),
        (0, 12, "silla-2", "barba", "Jorge Fernández", ["confirm"]),
        (0, 13, "silla-3", "corte", "María Elena Ruiz", []),
        (1, 10, "silla-2", "color", "Peluquería Norte SRL", ["confirm"]),
        (1, 12, "silla-1", "corte", "Sofía Aguirre", []),
        (2, 9, "silla-3", "brushing", "Carolina Méndez", ["cancel"]),
        (2, 14, "silla-1", "barba", "Jorge Fernández", []),
    ]

    #: Lo que espera cada accion como cuerpo.
    CUERPOS = {
        "confirm": {},
        "complete": {"medio_pago": "efectivo"},
        "cancel": {"reason": "El cliente avisó que no podía"},
    }

    for dias, hora, recurso, servicio, cliente, pasos in PLAN:
        inicio = cuando(dias, hora)
        try:
            turno = api.post("/appointments", {
                "resource_id": recurso, "service_id": servicio,
                "client_id": clientes[cliente], "starts_at": inicio,
            })
        except RuntimeError as e:
            # Un turno que se pisa con otro, o fuera de horario, no corta el
            # seed: se avisa y se sigue. Es el mismo criterio que el catálogo
            # que no responde en el formulario de comprobante de LibraDesk.
            print(f"  -- {inicio:%d/%m %H:%M} {recurso}: {e}")
            continue
        contar("turnos", True)
        for paso in pasos:
            try:
                api.post(f"/appointments/{turno['id']}/{paso}", CUERPOS[paso])
            except RuntimeError as e:
                # Una transición inválida no corta el seed: el turno queda
                # creado y en su estado anterior, que también es un estado real.
                print(f"  -- {inicio:%d/%m %H:%M} {paso}: {e}")
                break



def _cargar_logo(api, nombre: str, inicial: str, color: tuple, contar) -> None:
    """Dibuja el logo del negocio y lo sube a Configuración.

    🔴 **Se genera, no se commitea.** PIL viene en la imagen del producto, así
    que el seed lo dibuja en el momento: no hay binarios en el repo y cambiar
    el color es cambiar una línea. Mismo criterio que el resto del seed — el
    estado limpio es código, no un archivo guardado a mano.

    Sin logo, los PDF de la demo salen con un hueco arriba: el interesado ve
    dónde iría el suyo pero no cómo se ve.

    ⚠️ El campo del multipart se llama **`logo`**, no `file`: con `file` la API
    contesta 422. Está leído del openapi de la instancia.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  (sin PIL: se saltea el logo)")
        return

    # 🔴 La ruta de configuración no es la misma en todos los productos, y
    # pedir la que no existe **no da 404**: el catch-all de la SPA contesta
    # 200 con el index.html y el parseo revienta. Así que la guarda no puede
    # depender de acertarla: ante cualquier duda se sube el logo, que es
    # inocuo, en vez de arriesgar quedarse sin él.
    for ruta in ("/api/config/empresa", "/api/config"):
        try:
            actual = api.get(ruta)
        except Exception:
            continue
        if isinstance(actual, dict):
            plano = str(actual)
            if '"logo"' in plano or "'logo'" in plano:
                if any("logo" in str(k) and v for k, v in actual.items()):
                    contar("logo", False)
                    return
            break

    imagen = Image.new("RGBA", (520, 160), (255, 255, 255, 0))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rounded_rectangle((8, 20, 128, 140), radius=24, fill=color)
    dibujo.text((52, 60), inicial, fill=(255, 255, 255))
    dibujo.text((150, 55), nombre, fill=(30, 30, 30))
    dibujo.line((150, 95, 150 + min(340, len(nombre) * 11), 95), fill=color, width=4)

    import io
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")

    limite = "----seed" + "0" * 12
    cuerpo = (
        f"--{limite}\r\n"
        'Content-Disposition: form-data; name="logo"; filename="logo.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + buffer.getvalue() + f"\r\n--{limite}--\r\n".encode()

    import urllib.request
    pedido = urllib.request.Request(
        f"{api.base}/api/config/empresa/logo", data=cuerpo, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={limite}"},
    )
    try:
        api.opener.open(pedido, timeout=30)
        contar("logo", True)
    except Exception as e:
        print(f"  -- logo: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument(
        "--force", action="store_true",
        help="Correr contra una URL que no parece de dev ni de demo. No usar.",
    )
    args = ap.parse_args()

    if not url_no_productiva(args.url) and not args.force:
        print(f"ERROR: {args.url} no parece una instancia de dev ni de demo.",
              file=sys.stderr)
        print("Este script NO se corre contra la instancia de un cliente.",
              file=sys.stderr)
        return 2

    api = Api(args.url)
    api.post("/auth/login", {"username": args.usuario, "password": args.password})
    sembrar(api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
