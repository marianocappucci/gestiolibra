"""Los recordatorios de turno salen por WhatsApp y por mail con los avisos del motor (ADR-040; ADR-090 de libracore).

Lo que se fija, de punta a punta por `POST /reminders/dispatch` y por el script del cron:

- el recordatorio sale por el proveedor que la instancia configuró: **Registro** (anota y no manda) o **Evolution**, y el texto lleva
  el negocio, el día y la hora *en la zona de la sede*, el servicio y con quién, sin datos de más;
- **no sale dos veces**, ni con dos `dispatch` ni cuando se pierde el libro de `libragenda` (la clave `agenda:{turno}:{política}` del motor);
- un cliente sin teléfono queda `omitido` (con su motivo) y el resto de la tanda sigue;
- un fallo de Evolution no corta el despacho, queda `fallido` y el siguiente lo reintenta;
- sin canal configurado la instancia se comporta como antes: nada sale y nada se anota;
- `/api/avisos/*` es de administrador, y en la ruta de despacho no pasa nada real: Evolution va contra un `httpx.MockTransport`.
"""
import importlib.util
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from libracore import config_manager
from libragenda import ReminderNotification, ReminderPolicy
from sqlalchemy import text

from app import notifications, offline

URL = "https://evolution.ejemplo.example"
APIKEY = "apikey-ficticia-0123456789abcdef"
RAIZ = Path(__file__).resolve().parent.parent

#: Un turno en 2099 con anticipos enormes: los dos recordatorios ya vencieron para cualquier «ahora» real, y la corrida no depende de la
#: hora a la que se la lance (mismo recurso que `test_dashboard.py`). Los plazos reales (24 h y 2 h) los fija `test_reminders.py`.
TURNO = "2099-01-01T10:30:00"  # jueves; hora de pared de la sucursal
POLITICAS = [ReminderPolicy("24h", timedelta(days=40_000)), ReminderPolicy("2h", timedelta(days=50_000))]


def _sembrar(client: TestClient, *, telefono: str | None = "11 5555-1234", email: str | None = None,
             zona: str = "America/Argentina/Buenos_Aires", turnos: int = 1) -> list[str]:
    """Una sucursal, un recurso, un servicio y un cliente con un turno. Devuelve los ids de los turnos."""
    assert client.post("/branches", json={"id": "centro", "name": "Centro", "timezone": zona}).status_code == 201
    assert client.post("/resources", json={"id": "sillon-1", "name": "Marta", "branch_id": "centro"}).status_code == 201
    assert client.post("/services", json={"id": "corte", "name": "Corte de pelo", "duration_minutes": 30}).status_code == 201
    for dia in range(7):
        client.post("/resources/sillon-1/availability", json={"weekday": dia, "starts_at": "00:00:00", "ends_at": "23:59:00"})
    cuerpo = {"id": "ana", "name": "Ana Prueba", "phone": telefono, "email": email}
    assert client.post("/clients", json=cuerpo).status_code == 201
    ids = []
    for n in range(turnos):
        hora = f"2099-01-01T{10 + n:02d}:30:00"
        r = client.post("/appointments", json={"resource_id": "sillon-1", "service_id": "corte", "client_id": "ana", "starts_at": hora})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    client.app.state.reminder_dispatcher.policies = POLITICAS
    client.app.state.business_settings.update("Peluquería Estilo Norte", "ARS")
    return ids


def _config(client: TestClient, **cuerpo):
    r = client.put("/api/avisos/config", json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


class Evolution:
    """Un Evolution de mentira: guarda lo que le llega y contesta con lo que se le programe. No sale nada a la red."""

    def __init__(self, *respuestas: int):
        self.pedidos: list[httpx.Request] = []
        self._respuestas = list(respuestas)

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        estado = self._respuestas.pop(0) if self._respuestas else 201
        return httpx.Response(estado, json={"key": {"id": f"MSG{len(self.pedidos)}"}})

    @property
    def textos(self) -> list[str]:
        return [json.loads(p.content)["text"] for p in self.pedidos]


@pytest.fixture
def evolution(monkeypatch, admin_client):
    """Prende Evolution en la instancia y lo apunta a un `MockTransport`. Devuelve el Evolution de mentira."""
    falso = Evolution()
    real = notifications.proveedores
    monkeypatch.setattr(notifications, "proveedores",
                        lambda smtp_config=None, **kw: real(smtp_config, transporte=httpx.MockTransport(falso)))
    _config(admin_client, modo="evolution", url=URL, instancia="peluqueria", apikey=APIKEY)
    return falso


def _envios(client: TestClient, **filtros):
    r = client.get("/api/avisos/envios", params=filtros)
    assert r.status_code == 200, r.text
    return r.json()


# ── Sin canal: como siempre ───────────────────────────────────────────────────────────────────────────────────────────


def test_sin_canal_configurado_no_sale_ni_se_anota_nada(admin_client):
    """El caso de toda instancia que no tocó la pantalla de Avisos: el despacho anda igual que con el `LoggingNotificationPort`."""
    _sembrar(admin_client)
    r = admin_client.post("/reminders/dispatch")
    assert r.status_code == 200
    assert {x["policy_id"] for x in r.json()} == {"24h", "2h"}
    assert _envios(admin_client) == []


# ── Registro: el modo prueba ─────────────────────────────────────────────────────────────────────────────────────────


def test_en_modo_registro_el_recordatorio_se_anota_con_su_texto_y_no_sale(admin_client):
    ids = _sembrar(admin_client)
    _config(admin_client, modo="registro")

    assert admin_client.post("/reminders/dispatch").status_code == 200

    filas = _envios(admin_client, canal="whatsapp")
    assert {(f["clave"], f["estado"], f["tipo"], f["proveedor"]) for f in filas} == {
        (f"agenda:{ids[0]}:24h", "registrado", "recordatorio", "registro"),
        (f"agenda:{ids[0]}:2h", "registrado", "recordatorio", "registro"),
    }
    assert {f["destino"] for f in filas} == {"5491155551234"}


def test_el_texto_dice_negocio_dia_y_hora_de_la_sede_servicio_y_con_quien(admin_client):
    _sembrar(admin_client)
    _config(admin_client, modo="registro")
    admin_client.post("/reminders/dispatch")

    cuerpo = _envios(admin_client)[0]["cuerpo"]
    assert cuerpo == (
        "*Recordatorio de turno*\n"
        "Peluquería Estilo Norte: tu turno es el jueves 01/01 a las 10:30 hs.\n"
        "Servicio: Corte de pelo\n"
        "Con: Marta\n"
        "Si no podés venir, avisanos con tiempo."
    )


def test_la_hora_es_la_de_la_sede_y_no_la_de_utc(admin_client):
    """El turno se guarda como instante UTC (13:30 con la sede en UTC-3). El cliente lee la hora de pared de la sede."""
    _sembrar(admin_client, zona="America/Argentina/Buenos_Aires")
    _config(admin_client, modo="registro")
    admin_client.post("/reminders/dispatch")
    assert "a las 10:30 hs" in _envios(admin_client)[0]["cuerpo"]
    assert "13:30" not in _envios(admin_client)[0]["cuerpo"]


def test_el_texto_no_lleva_datos_de_mas(admin_client):
    _sembrar(admin_client, email="ana@ejemplo.example")
    _config(admin_client, modo="registro")
    admin_client.post("/reminders/dispatch")
    cuerpo = _envios(admin_client)[0]["cuerpo"]
    for de_mas in ("Ana", "5555", "ana@", "$", "CUIT"):
        assert de_mas not in cuerpo


def test_la_sede_se_nombra_solo_si_el_negocio_tiene_mas_de_una(admin_client):
    _sembrar(admin_client)
    _config(admin_client, modo="registro")
    admin_client.post("/reminders/dispatch")
    assert "Sede:" not in _envios(admin_client)[0]["cuerpo"]

    assert admin_client.post("/branches", json={"id": "norte", "name": "Norte", "timezone": "America/Argentina/Buenos_Aires"}).status_code == 201
    admin_client.app.state.reminder_dispatcher.policies = [ReminderPolicy("de-nuevo", timedelta(days=60_000))]
    admin_client.post("/reminders/dispatch")
    nuevo = next(f for f in _envios(admin_client) if f["clave"].endswith(":de-nuevo"))
    assert "Sede: Centro" in nuevo["cuerpo"]


# ── Evolution simulado ───────────────────────────────────────────────────────────────────────────────────────────────


def test_con_evolution_el_recordatorio_sale_normalizado_y_con_la_apikey_en_el_header(admin_client, evolution):
    ids = _sembrar(admin_client)

    assert admin_client.post("/reminders/dispatch").status_code == 200

    assert len(evolution.pedidos) == 2
    pedido = evolution.pedidos[0]
    assert str(pedido.url) == f"{URL}/message/sendText/peluqueria"
    assert pedido.headers["apikey"] == APIKEY
    cuerpo = json.loads(pedido.content)
    assert cuerpo["number"] == "5491155551234"
    assert "Peluquería Estilo Norte: tu turno es el jueves 01/01 a las 10:30 hs." in cuerpo["text"]
    estados = {f["clave"]: f["estado"] for f in _envios(admin_client, canal="whatsapp")}
    assert estados == {f"agenda:{ids[0]}:24h": "enviado", f"agenda:{ids[0]}:2h": "enviado"}


def test_dos_dispatch_mandan_una_sola_vez(admin_client, evolution):
    _sembrar(admin_client)
    admin_client.post("/reminders/dispatch")
    admin_client.post("/reminders/dispatch")
    assert len(evolution.pedidos) == 2  # un turno, dos políticas; el segundo dispatch no encontró nada vencido


def test_si_se_pierde_el_libro_de_libragenda_el_motor_igual_no_repite(admin_client, evolution):
    """La segunda red: aunque `sent_reminders` se vacíe (un restore, un borrado a mano), la clave del motor frena el reenvío."""
    _sembrar(admin_client)
    admin_client.post("/reminders/dispatch")
    with admin_client.app.state.sessions.begin() as sesion:
        sesion.execute(text("DELETE FROM sent_reminders"))

    r = admin_client.post("/reminders/dispatch")

    assert len(r.json()) == 2, "libragenda volvió a encontrarlos vencidos: la prueba está midiendo lo que quiere medir"
    assert len(evolution.pedidos) == 2, "y el motor no los mandó otra vez"
    assert [f["intentos"] for f in _envios(admin_client)] == [1, 1]


def test_un_cliente_sin_telefono_queda_omitido_y_el_resto_de_la_tanda_sigue(admin_client, evolution):
    _sembrar(admin_client, telefono=None)
    assert admin_client.post("/clients", json={"id": "beto", "name": "Beto Prueba", "phone": "11 5555-9876"}).status_code == 201
    r = admin_client.post("/appointments", json={"resource_id": "sillon-1", "service_id": "corte", "client_id": "beto",
                                                 "starts_at": "2099-01-01T12:30:00"})
    assert r.status_code == 201, r.text

    assert admin_client.post("/reminders/dispatch").status_code == 200

    omitidos = _envios(admin_client, estado="omitido")
    assert len(omitidos) == 2 and all("no tiene un teléfono" in f["detalle"] for f in omitidos)
    assert [json.loads(p.content)["number"] for p in evolution.pedidos] == ["5491155559876"] * 2


def test_un_numero_de_telefono_que_no_se_reconoce_queda_omitido(admin_client, evolution):
    _sembrar(admin_client, telefono="5555")  # sin característica: el motor prefiere callar a mandar al número equivocado
    admin_client.post("/reminders/dispatch")
    assert evolution.pedidos == []
    assert {f["estado"] for f in _envios(admin_client)} == {"omitido"}


def test_un_fallo_de_evolution_no_corta_el_despacho_y_el_siguiente_lo_reintenta(monkeypatch, admin_client):
    falso = Evolution(503, 503)  # las dos políticas del primer despacho
    real = notifications.proveedores
    monkeypatch.setattr(notifications, "proveedores",
                        lambda smtp_config=None, **kw: real(smtp_config, transporte=httpx.MockTransport(falso)))
    _config(admin_client, modo="evolution", url=URL, instancia="peluqueria", apikey=APIKEY)
    _sembrar(admin_client)

    r = admin_client.post("/reminders/dispatch")
    assert r.status_code == 200, "un fallo del proveedor no es un 500: el cron lo tomaría por una tanda fallida"
    assert len(r.json()) == 2
    # Un solo intento por aviso: los reintentos van ANTES de `dispatch`, así que el fallo de esta pasada espera a la siguiente.
    assert {(f["estado"], f["intentos"]) for f in _envios(admin_client)} == {("fallido", 1)}
    assert len(falso.pedidos) == 2

    # `libragenda` ya los dio por enviados: nada vence de nuevo, pero la pasada siguiente reintenta lo fallido.
    r = admin_client.post("/reminders/dispatch")
    assert r.json() == []
    assert {f["estado"] for f in _envios(admin_client)} == {"enviado"}
    assert len(falso.pedidos) == 4
    assert [f["intentos"] for f in _envios(admin_client)] == [2, 2]


def test_un_fallo_de_reintentar_no_rompe_el_despacho(monkeypatch, admin_client):
    _sembrar(admin_client)

    def roto():
        raise RuntimeError("clave-secreta-que-no-debe-aparecer")

    monkeypatch.setattr(admin_client.app.state, "reintentar_avisos", roto, raising=True)
    r = admin_client.post("/reminders/dispatch")
    assert r.status_code == 200 and len(r.json()) == 2


# ── Mail ──────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_con_smtp_el_recordatorio_sale_tambien_por_mail(monkeypatch, admin_client):
    """Nada real sale: se reemplaza el envío por SMTP del motor (`email_sender.enviar_texto`) por uno que anota lo que le llega."""
    enviados = []
    monkeypatch.setattr("libracore.email_sender.enviar_texto", lambda **kw: enviados.append(kw))
    r = admin_client.put("/admin/smtp", json={"host": "smtp.ejemplo.example", "port": 587, "user": "u", "password": "p",
                                              "from_email": "avisos@ejemplo.example", "from_name": "Estilo Norte"})
    assert r.status_code == 200, r.text
    _sembrar(admin_client, telefono=None, email="ana@ejemplo.example")

    assert admin_client.post("/reminders/dispatch").status_code == 200

    filas = _envios(admin_client, canal="email")
    assert {(f["estado"], f["destino"]) for f in filas} == {("enviado", "ana@ejemplo.example")}
    assert len(enviados) == 2
    assert {m["asunto"] for m in enviados} == {"Recordatorio de turno - Peluquería Estilo Norte"}
    assert all(m["to_email"] == "ana@ejemplo.example" and "Servicio: Corte de pelo" in m["cuerpo"] for m in enviados)
    assert all("*" not in m["cuerpo"] for m in enviados), "el mail es texto plano: sin los asteriscos de WhatsApp"


# ── El script del cron ───────────────────────────────────────────────────────────────────────────────────────────────


def _cargar_script(app, monkeypatch):
    """Importa `scripts/despachar_recordatorios.py` con `app.asgi` reemplazado por la app del test (el real arma la suya al importarse)."""
    falso = types.ModuleType("app.asgi")
    falso.app = app
    monkeypatch.setitem(sys.modules, "app.asgi", falso)
    spec = importlib.util.spec_from_file_location("despachar_recordatorios_bajo_test", RAIZ / "scripts" / "despachar_recordatorios.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_script_del_cron_despacha_y_reintenta_como_la_ruta(admin_client, evolution, monkeypatch):
    _sembrar(admin_client)
    assert _cargar_script(admin_client.app, monkeypatch).main() == 0
    assert len(evolution.pedidos) == 2
    assert {f["estado"] for f in _envios(admin_client)} == {"enviado"}


def test_el_script_no_hace_nada_en_un_nodo(admin_client, evolution, monkeypatch):
    """Despachar en un nodo marcaría los recordatorios como vistos sin que salga ninguno: lo despacha el central."""
    _sembrar(admin_client)
    monkeypatch.setattr(offline, "nodo", lambda: "local-1")
    assert _cargar_script(admin_client.app, monkeypatch).main() == 0
    assert evolution.pedidos == []
    assert admin_client.post("/reminders/dispatch").status_code == 409  # y la ruta tampoco: es del central


def test_el_script_respeta_el_modulo_apagado(admin_client, evolution, monkeypatch):
    _sembrar(admin_client)
    admin_client.app.state.modules.set_enabled("recordatorios", False)
    assert _cargar_script(admin_client.app, monkeypatch).main() == 0
    assert evolution.pedidos == []
    assert admin_client.post("/reminders/dispatch").status_code == 403


# ── La API de configuración ──────────────────────────────────────────────────────────────────────────────────────────


def test_la_apikey_no_vuelve_por_la_api(admin_client, evolution):
    estado = admin_client.get("/api/avisos/config").json()["whatsapp"]
    assert estado["modo"] == "evolution" and estado["apikey_cargada"] is True and estado["disponible"] is True
    assert APIKEY not in json.dumps(admin_client.get("/api/avisos/config").json())
    # Y tampoco queda en claro en el `config.json`: va al almacén cifrado de la instancia.
    assert APIKEY not in Path(config_manager.CONFIG_PATH).read_text(encoding="utf-8")


def test_en_un_nodo_guardar_y_probar_son_del_central_pero_se_puede_mirar(admin_client, monkeypatch):
    monkeypatch.setattr(offline, "nodo", lambda: "local-1")
    for metodo, ruta, cuerpo in (("PUT", "/api/avisos/config", {"modo": "registro"}),
                                 ("POST", "/api/avisos/probar", {"canal": "whatsapp", "destino": "11 5555-1234"})):
        r = admin_client.request(metodo, ruta, json=cuerpo)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "solo_en_el_central", (metodo, ruta, r.text)
    assert admin_client.get("/api/avisos/config").status_code == 200
    assert admin_client.get("/api/avisos/envios").status_code == 200


def test_en_un_nodo_el_puerto_no_manda_ni_anota(admin_client, evolution, monkeypatch):
    _sembrar(admin_client)
    monkeypatch.setattr(offline, "nodo", lambda: "local-1")
    port = admin_client.app.state.reminder_dispatcher.notification_port
    estados = [e.estado for e in port.send(ReminderNotification("t1", "24h", "sillon-1", "corte", "ana", datetime(2099, 1, 1, 13, 30, tzinfo=UTC)))]
    assert estados == ["en_nodo"], "sólo WhatsApp está disponible (no hay SMTP): un nodo no manda por ese canal"
    assert evolution.pedidos == [] and _envios(admin_client) == []


def test_probar_con_el_canal_apagado_dice_que_no_esta_disponible(admin_client):
    """«Probar envío» es del motor y con Evolution llegaría a la red de verdad, así que acá sólo se mide el cableado: la ruta existe, es del
    administrador y contesta con el motivo cuando el canal no puede mandar. Que el texto de prueba sea fijo y el 502 de Evolution los prueba
    el motor (`tests/test_avisos_router.py` de libracore)."""
    r = admin_client.post("/api/avisos/probar", json={"canal": "whatsapp", "destino": "11 5555-1234"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "no_disponible"
