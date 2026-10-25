"""Un nodo y su central, con dos bases, para probar lo que sube el mostrador sin conexión (ADR-036).

El **nodo** es la app de la suite sobre la base del worker, con la identidad de un nodo en el entorno
(`LIBRAEDGE_NODE_ID`). El **central** es una **copia de esa base** hecha después de cargar la referencia (la sucursal, el
recurso, el servicio y su precio, los clientes, los turnos, la configuración de ARCA): es lo que deja el espejo de LibraEdge,
el nodo tiene las mismas filas con las mismas claves. En el central se registra el nodo con el aprovisionamiento del producto
(`app.offline`). Lo que el nodo hace después (atender, cobrar, facturar, dar de alta un cliente) sólo existe en su base y llega
al central como operaciones del outbox, que acá se aplican con el receptor de LibraEdge y el despachador **reales** del
producto (`routers/sincronizacion_offline.py`).

ARCA y el ticket que presta el central son dobles (`arca_responde` y `ticket_de_prueba`); todo lo demás es el código de verdad.
Datos ficticios.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime

from libracore.db import core
from libracore.nodo_offline import SinConexion
from libracore.respaldo_postgres import con_base
from libraedge import aprovisionamiento as aprov
from libraedge.db.repository import NodeRepository
from libraedge.sync.receiver import SyncReceiver
from libraedge.sync.ticket import SinConexionConElCentral
from motor_de_test import _PG

from app import offline

NODO = "local-1"

#: Lo que el nodo genera y sube: en el central no existe hasta que llega.
TABLAS_DEL_NODO = ("caja_movimientos", "facturas", "cola_arca", "agenda_node_attendances", "sync_outbox", "sync_inbox")


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _url_sqlalchemy(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


class Escenario:
    """El nodo (la app de la suite) y su central (una copia de la base). Ver el docstring del módulo."""

    def __init__(self, cliente, monkeypatch, tmp_path):
        self.cliente = cliente
        self.monkeypatch = monkeypatch
        self.ruta_estado = str(tmp_path / "estado.json")
        self.url_central: str | None = None
        self.nombre_central: str | None = None
        self.secreto: str | None = None
        self.prefijo: str | None = None
        self.datos: dict = {}

    # ── el central ────────────────────────────────────────────────────────────────────────────────────────────────────

    def clonar_el_central(self) -> None:
        """Copia la base del nodo en este momento: la referencia que el espejo ya bajó. `CREATE DATABASE ... TEMPLATE`
        exige que nadie esté conectado: se sueltan los pools y las conexiones vivas (se renuevan solas)."""
        from libragenda.database import get_engine

        get_engine().dispose()
        self.cliente.app.state.auth_engine.dispose()
        nombre = f"{_PG.nombre}_central"
        _PG._soltar(nombre)
        _PG._sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{_PG.nombre}' AND pid <> pg_backend_pid()")
        _PG._crear(nombre, plantilla=_PG.nombre)
        self.nombre_central = nombre
        self.url_central = con_base(_PG.url_original, nombre)

    def registrar_el_nodo(self, sucursal: str = "sucursal-1") -> None:
        """Da de alta el nodo en el central con el aprovisionamiento del producto (de ahí, el secreto y el prefijo)."""
        conn = core.conectar(self.url_central)
        try:
            alta = aprov.registrar(conn, offline.aprovisionamiento, NODO, sucursal=sucursal)
        finally:
            conn.close()
        self.secreto, self.prefijo = alta.secreto, alta.prefijo

    def soltar(self) -> None:
        if self.url_central:
            _PG._soltar(self.nombre_central)

    @contextmanager
    def en_el_central(self):
        """La app apuntada al central y **sin identidad de nodo**, mientras dura el `with`: el motor (`core`) y la base de
        LibraGenda (la que usa `registrar_en` para aplicar `turno.atendido`) miran la copia."""
        import libragenda.database as base_de_la_agenda
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        guardadas = {v: os.environ.pop(v, None) for v in ("LIBRAEDGE_NODE_ID", "LIBRAEDGE_PREFIJO", "GESTIOLIBRA_EDGE_NODE_ID")}
        anterior = core._db_path
        motor_anterior, fabrica_anterior = base_de_la_agenda._engine, base_de_la_agenda._session_factory
        motor_central = create_engine(_url_sqlalchemy(self.url_central))
        core.configure(self.url_central)
        base_de_la_agenda._engine = motor_central
        base_de_la_agenda._session_factory = sessionmaker(motor_central, expire_on_commit=False)
        try:
            yield self
        finally:
            core.configure(anterior)
            base_de_la_agenda._engine, base_de_la_agenda._session_factory = motor_anterior, fabrica_anterior
            motor_central.dispose()
            for variable, valor in guardadas.items():
                if valor is not None:
                    os.environ[variable] = valor

    def sql_central(self, sentencia: str, *params):
        """Una consulta contra la base del central (con `?` como parámetros)."""
        conn = core.conectar(self.url_central)
        try:
            return [tuple(f) for f in conn.execute(sentencia, params).fetchall()]
        finally:
            conn.close()

    def ejecutar_en_el_central(self, sentencia: str, *params) -> None:
        """Un cambio en el central, como el que haría la web (cancelar un turno, mover uno...)."""
        conn = core.conectar(self.url_central)
        try:
            conn.execute(sentencia, params)
            conn.commit()
        finally:
            conn.close()

    # ── el nodo ───────────────────────────────────────────────────────────────────────────────────────────────────────

    def ser_nodo(self) -> None:
        """Desde acá la instancia es el nodo del local."""
        self.monkeypatch.setenv("LIBRAEDGE_NODE_ID", NODO)
        self.monkeypatch.setenv("LIBRAEDGE_PREFIJO", self.prefijo or "S01")
        self.monkeypatch.setenv("LIBRAEDGE_ESTADO", self.ruta_estado)
        self.en_linea(False)

    def en_linea(self, si: bool) -> None:
        """Lo que dice el archivo de estado del proceso del nodo (libracore ADR-074)."""
        with open(self.ruta_estado, "w", encoding="utf-8") as archivo:
            json.dump({"node_id": NODO, "en_linea": si, "ultima_sincronizacion_ok": _ahora_iso()}, archivo)

    def sql_nodo(self, sentencia: str, *params):
        with core.get_connection() as conn:
            return [tuple(f) for f in conn.execute(sentencia, params).fetchall()]

    # ── subir ─────────────────────────────────────────────────────────────────────────────────────────────────────────

    def pendientes(self):
        """Las operaciones que el nodo tiene sin subir, en el orden en que ocurrieron."""
        with core.get_connection() as conn:
            return list(NodeRepository(conn).list_pending_operations(limit=1000))

    def tipos_pendientes(self) -> list[str]:
        return [op.operation_type for op in self.pendientes()]

    def subir(self, operaciones=None):
        """Aplica en el central las operaciones del nodo (o las que se le pasen), una por una, como lo hace el receptor de
        LibraEdge. Devuelve `[(operación, resultado)]`; las aceptadas quedan confirmadas en el nodo."""
        from app.routers.sincronizacion_offline import despachador

        operaciones = self.pendientes() if operaciones is None else operaciones
        resultados = []
        with self.en_el_central():
            conn = core.conectar(self.url_central)
            try:
                receptor = SyncReceiver(conn, despachador=despachador)
                for op in operaciones:
                    resultados.append((op, receptor.accept(op)))
            finally:
                conn.close()
        with core.get_connection() as nodo:
            repo = NodeRepository(nodo)
            for op, resultado in resultados:
                if resultado.result in ("accepted", "duplicate"):
                    repo.acknowledge_operation(op.operation_id, _ahora_iso())
        return resultados

    def subir_todo_y_exigir(self):
        """Sube todo y exige que se haya aceptado: lo que rebota va a revisión manual y el test lo tiene que ver."""
        resultados = self.subir()
        rechazadas = [(op.operation_type, r.error) for op, r in resultados if r.result == "rejected"]
        assert not rechazadas, f"el central rechazó operaciones del nodo: {rechazadas}"
        return resultados


def arca_responde(monkeypatch, *, cae="75123456789012", cae_vto="20261231", ultimo=0, falla_cae=None):
    """Simula a ARCA (WSFE): da el número que sigue por (punto de venta, tipo) y autoriza. Devuelve lo que se le pidió.

    **Lleva la cuenta**: cada CAE autorizado adelanta el último número de su (punto de venta, tipo), como el WSFE. Dos
    facturas seguidas no chocan."""
    from libracore import arca_wsfe

    pedidos: list[tuple] = []
    ultimos: dict[tuple[int, int], int] = {}

    async def ultimo_numero(pv, tipo, cuit, token, sign, ambiente):
        pedidos.append(("ultimo", pv, tipo, cuit))
        return ultimos.get((pv, tipo), ultimo)

    async def solicitar_cae(factura, cuit, token, sign, ambiente):
        pedidos.append(("cae", factura))
        if falla_cae:
            raise RuntimeError(falla_cae)
        ultimos[(factura["punto_venta"], factura["tipo"])] = factura["numero"]
        return {"cae": cae, "cae_vto": cae_vto}

    monkeypatch.setattr(arca_wsfe, "ultimo_numero_autorizado", ultimo_numero)
    monkeypatch.setattr(arca_wsfe, "solicitar_cae", solicitar_cae)
    return pedidos


def ticket_de_prueba(monkeypatch, *, ambiente="produccion", falla=None):
    """El ticket que el central le presta al nodo (doble de `offline.obtener_ta`) y del cliente de LibraEdge
    (`offline.cliente_de_ticket`).

    `falla` es una excepción que levanta en vez de dar el ticket (un corte, un rechazo del central). Devuelve la lista de lo
    que se pidió: `[(servicio, arca)]`."""
    pedidos: list[tuple] = []

    def ticket(arca, servicio):
        return {"token": "TKN", "sign": "SGN", "expiracion": "2099-01-01T00:00:00+00:00", "ambiente": ambiente,
                "servicio": servicio, "cuit": (arca or {}).get("cuit"), "emisor_id": (arca or {}).get("id")}

    async def obtener_ta(arca, servicio="wsfe"):
        if not offline.en_linea():
            raise SinConexion("Sin conexión con el central: se emite al volver la conexión.")
        pedidos.append((servicio, arca))
        if falla is not None:
            raise falla
        return ticket(arca, servicio)

    class Cliente:
        def pedir_ticket(self, emisor_id=None, servicio="wsfe"):
            if not offline.en_linea():
                raise SinConexionConElCentral("El central no respondió.", codigo="sin_conexion")
            pedidos.append((servicio, {"id": emisor_id}))
            if falla is not None:
                raise falla
            return ticket({"id": emisor_id}, servicio)

    monkeypatch.setattr(offline, "obtener_ta", obtener_ta)
    monkeypatch.setattr(offline, "cliente_de_ticket", Cliente)
    return pedidos


__all__ = ["NODO", "Escenario", "arca_responde", "ticket_de_prueba"]
