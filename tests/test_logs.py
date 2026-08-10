"""
Logs: actividad del sistema y accesos, admin-only.

El mecanismo es de `libraauth.auditoria` y tiene sus propios tests en el motor.
Lo que se prueba **acá** es lo que es de este producto y nadie más puede
verificar:

1. Que la auditoría esté **enganchada al session_factory del dominio** —el de
   LibraGenda—, que es el que usan los repositorios. Cableada al engine
   equivocado no falla: simplemente no registra nada, y un log vacío se ve
   igual que un sistema donde nadie hizo nada.
2. Que la lista blanca cubra las entidades que importan de ESTE dominio.
3. Que las tablas que ya son historial (las transiciones de un turno) **no**
   entren.
4. Que la pantalla sea admin-only.
"""


def _logs(client, **params) -> dict:
    r = client.get("/logs", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _sucursal(client, nombre="Sucursal Centro") -> dict:
    # El id lo elige quien da de alta (no es autoincrement): es el mismo
    # identificador que después usan los turnos y la disponibilidad.
    r = client.post("/branches", json={"id": "centro", "name": nombre, "address": "Suipacha 123"})
    assert r.status_code == 201, r.text
    return r.json()


def _cliente(client, nombre="Ana Pérez") -> dict:
    r = client.post("/clients", json={"name": nombre, "email": "ana@ejemplo.com"})
    assert r.status_code == 201, r.text
    return r.json()


# ── Que registre, y que lo haga contra la base del dominio ────────────────

def test_crear_un_cliente_queda_registrado(admin_client):
    """`ClientRepository.create` no llama a nada de auditoría: el registro
    cuelga del flush del session_factory de LibraGenda. Si el cableado
    apuntara al engine de auth, esto quedaría vacío sin dar ningún error."""
    _cliente(admin_client)

    # Un alta de cliente deja DOS filas: el cliente y su configuración de
    # facturación, que el repositorio crea en el mismo gesto. Las dos son
    # reales — la de facturación es la que después dice quién cambió los datos
    # fiscales de ese cliente.
    filas = _logs(admin_client)["actividad"]
    assert {f["entidad"] for f in filas} == {"cliente", "facturacion"}

    fila = [f for f in filas if f["entidad"] == "cliente"][0]
    assert fila["accion"] == "crear"
    assert "Ana Pérez" in fila["descripcion"]
    assert fila["usuario"] == "admin"


def test_tambien_registra_las_entidades_de_libragenda(admin_client):
    """La mayoría de los modelos de este producto son del motor de agenda, no
    propios: si la lista blanca se indexara por otra cosa que el nombre de
    clase, esto no entraría."""
    _sucursal(admin_client)
    # Igual que el cliente: el alta de una sucursal crea también su fila de
    # contacto, y las dos son cambios reales del catálogo.
    assert {f["entidad"] for f in _logs(admin_client)["actividad"]} == {"sucursal", "contacto"}


def test_editar_guarda_el_antes_y_el_despues(admin_client):
    cliente = _cliente(admin_client)
    r = admin_client.put(f"/clients/{cliente['id']}", json={
        "name": "Ana Pérez", "email": "otro@ejemplo.com",
    })
    assert r.status_code == 200, r.text

    edicion = [f for f in _logs(admin_client)["actividad"] if f["accion"] == "editar"][0]
    assert edicion["cambios"]["email"] == ["ana@ejemplo.com", "otro@ejemplo.com"]


def test_borrar_conserva_el_id_y_el_nombre(admin_client):
    """Después del borrado la fila ya no está: si el log no guardó el id y el
    nombre, no quedó nada que mirar."""
    cliente = _cliente(admin_client, "Cliente que se va")
    r = admin_client.delete(f"/clients/{cliente['id']}")
    assert r.status_code in (200, 204), r.text

    borrado = [f for f in _logs(admin_client)["actividad"] if f["accion"] == "borrar"][0]
    assert borrado["entidad_id"] == cliente["id"]
    assert "Cliente que se va" in borrado["descripcion"]


def test_las_entidades_del_filtro_son_las_de_este_dominio(admin_client):
    entidades = _logs(admin_client)["entidades"]
    for esperada in ("cliente", "turno", "servicio", "sucursal", "precio"):
        assert esperada in entidades
    # Las tablas que ya son historial no se auditan: la ficha del turno ya
    # muestra sus transiciones y los recordatorios enviados.
    assert "transicion" not in entidades
    assert "recordatorio" not in entidades


def test_el_seed_de_modulos_no_ensucia_el_log(admin_client):
    """`ModuleRepository.ensure_seeded()` corre en CADA arranque del
    contenedor. Auditar `modulos` habría dejado filas de "editar módulo" en
    cada deploy, que no le sirven a nadie."""
    assert "modulo" not in _logs(admin_client)["entidades"]


# ── Accesos ───────────────────────────────────────────────────────────────

def test_el_login_queda_registrado(admin_client):
    accesos = _logs(admin_client)["accesos"]
    assert accesos[0]["evento"] == "login"
    assert accesos[0]["username"] == "admin"


def test_el_intento_fallido_deja_el_usuario_tipeado(admin_client):
    admin_client.post("/auth/login", json={"username": "fantasma", "password": "x"})
    fallidos = [a for a in _logs(admin_client)["accesos"] if a["evento"] == "login_fallido"]
    assert fallidos[0]["username"] == "fantasma"


def test_la_contrasena_no_aparece_en_ningun_lado(admin_client):
    admin_client.post("/auth/login", json={"username": "admin", "password": "clave-secretisima"})
    assert "secretisima" not in str(_logs(admin_client))


# ── Permisos ──────────────────────────────────────────────────────────────

def test_el_staff_no_ve_los_logs(staff_client):
    """Es la pantalla que dice desde qué IP entró cada uno."""
    assert staff_client.get("/logs").status_code == 403


def test_lo_que_escribe_el_staff_queda_a_su_nombre(admin_client, staff_client):
    """El usuario sale de la cookie de cada request: si quedara pegado del
    contexto anterior, el trabajo del empleado aparecería como del admin.

    Se usa un turno y no un cliente porque el staff no puede dar de alta
    clientes en este producto — el catálogo es admin-only.
    """
    admin_client.post("/resources", json={"id": "silla-1", "name": "Silla 1"})
    admin_client.post("/services", json={"id": "corte", "name": "Corte", "duration_minutes": 30})
    cliente = _cliente(admin_client, "Cliente del turno")
    # Sin disponibilidad cargada, el turno se rechaza con 409: la agenda no
    # deja reservar fuera del horario del recurso.
    for weekday in range(7):
        admin_client.post("/resources/silla-1/availability", json={
            "weekday": weekday, "starts_at": "09:00:00", "ends_at": "18:00:00",
        })

    creado = staff_client.post("/appointments", json={
        "resource_id": "silla-1", "service_id": "corte",
        "client_id": cliente["id"], "starts_at": "2026-09-01T10:00:00",
    })
    assert creado.status_code in (200, 201), creado.text

    turnos = [f for f in _logs(admin_client)["actividad"] if f["entidad"] == "turno"]
    assert turnos and turnos[0]["usuario"] == "staff-1"
