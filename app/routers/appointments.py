import asyncio
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from libracore.cola_arca_respuesta import cuerpo_en_cola
from libracore.db import facturas as db_facturas
from libragenda import (
    AppointmentConflict,
    AppointmentNotFound,
    AppointmentStatus,
    AppointmentUnavailable,
    DepositStatus,
    InvalidTransition,
)
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.repositories import DepositRepository
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from .. import mensajes_agenda as mensajes
from .. import offline
from ..auth import get_current_user
from ..dependencies import (
    get_appointment_service,
    get_catalog_repository,
    get_client_repository,
    get_deposit_repository,
    get_service_price_repository,
    get_sessions,
)
from ..modules_gate import get_module_repository
from ..services import atencion_nodo
from ..services.appointments import AppointmentService, OutsideBusinessHours, ServiceNotFound
from ..services.atencion_nodo import CobroDelTurno
from ..services.billing import invoice_appointment
from ..services.clients import ClientRepository
from ..services.modules import ModuleRepository
from ..services.service_prices import ServicePriceRepository

router = APIRouter()


class AppointmentRequest(BaseModel):
    resource_id: str
    service_id: str
    client_id: str
    starts_at: datetime


class CancelRequest(BaseModel):
    reason: str | None = None


class CompleteRequest(BaseModel):
    medio_pago: str | None = None


class RescheduleRequest(BaseModel):
    starts_at: datetime
    reason: str | None = None


@router.post("/appointments", status_code=201, dependencies=[Depends(offline.solo_en_el_central)])
def create_appointment(
    data: AppointmentRequest,
    service: AppointmentService = Depends(get_appointment_service),
):
    try:
        appointment = service.create(
            data.resource_id, data.service_id, data.client_id, data.starts_at
        )
    except ServiceNotFound:
        raise HTTPException(404, mensajes.SERVICIO_NO_ENCONTRADO)
    except OutsideBusinessHours:
        raise HTTPException(409, mensajes.FUERA_DE_HORARIO)
    except AppointmentConflict:
        raise HTTPException(409, mensajes.POR_NOMBRE["AppointmentConflict"][1])
    except AppointmentUnavailable:
        raise HTTPException(409, mensajes.POR_NOMBRE["AppointmentUnavailable"][1])
    return {"id": appointment.id, "status": appointment.status.value, "ends_at": appointment.ends_at}


@router.post("/appointments/{appointment_id}/confirm", dependencies=[Depends(offline.solo_en_el_central)])
def confirm_appointment(
    appointment_id: str,
    service: AppointmentService = Depends(get_appointment_service),
):
    try:
        appointment = service.confirm(appointment_id)
    except AppointmentNotFound:
        raise HTTPException(404, mensajes.POR_NOMBRE["AppointmentNotFound"][1])
    except InvalidTransition as exc:
        raise HTTPException(*mensajes.describir(exc))
    return {"id": appointment.id, "status": appointment.status.value}


@router.post("/appointments/{appointment_id}/cancel", dependencies=[Depends(offline.solo_en_el_central)])
def cancel_appointment(
    appointment_id: str,
    data: CancelRequest = CancelRequest(),
    service: AppointmentService = Depends(get_appointment_service),
):
    try:
        appointment = service.cancel(appointment_id, reason=data.reason)
    except AppointmentNotFound:
        raise HTTPException(404, mensajes.POR_NOMBRE["AppointmentNotFound"][1])
    except InvalidTransition as exc:
        raise HTTPException(*mensajes.describir(exc))
    return {"id": appointment.id, "status": appointment.status.value, "reason": appointment.reason}


@router.post("/appointments/{appointment_id}/reschedule", dependencies=[Depends(offline.solo_en_el_central)])
def reschedule_appointment(
    appointment_id: str,
    data: RescheduleRequest,
    service: AppointmentService = Depends(get_appointment_service),
):
    try:
        appointment = service.reschedule(appointment_id, data.starts_at, reason=data.reason)
    except AppointmentNotFound:
        raise HTTPException(404, mensajes.POR_NOMBRE["AppointmentNotFound"][1])
    except InvalidTransition as exc:
        raise HTTPException(*mensajes.describir(exc))
    except OutsideBusinessHours:
        raise HTTPException(409, mensajes.FUERA_DE_HORARIO)
    except AppointmentConflict:
        raise HTTPException(409, mensajes.POR_NOMBRE["AppointmentConflict"][1])
    except AppointmentUnavailable:
        raise HTTPException(409, mensajes.POR_NOMBRE["AppointmentUnavailable"][1])
    return {
        "id": appointment.id, "status": appointment.status.value,
        "starts_at": appointment.starts_at, "reason": appointment.reason,
    }


@router.post("/appointments/{appointment_id}/complete")
def complete_appointment(
    appointment_id: str,
    data: CompleteRequest = CompleteRequest(),
    service: AppointmentService = Depends(get_appointment_service),
    clients: ClientRepository = Depends(get_client_repository),
    service_prices: ServicePriceRepository = Depends(get_service_price_repository),
    deposits: DepositRepository = Depends(get_deposit_repository),
    catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository),
    modules: ModuleRepository = Depends(get_module_repository),
    sessions: sessionmaker[Session] = Depends(get_sessions),
    user: dict = Depends(get_current_user),
):
    """Completa el turno y, si hay un precio configurado para el servicio
    en la sucursal Y el plan incluye el módulo "facturacion", factura el
    total con LibraCore (una sola factura, reconciliando la sena ya
    cobrada -- si existe -- y el saldo restante como movimientos de caja
    separados). Sin precio configurado, o sin el módulo habilitado, no
    factura nada -- completar el turno nunca se bloquea por el plan,
    solo se salta la parte de facturación.

    La validacion de facturacion (medio_pago requerido si hay saldo) corre
    ANTES de completar el turno en LibraGenda -- si faltara, el turno no
    queda completado sin factura y sin forma de reintentar (COMPLETED no
    admite otra transicion).

    🔴 **`def` y no `async def`, a propósito.** Todo lo que hace esta ruta es
    sincrónico —los repositorios de LibraGenda sobre la base del dominio, y
    adentro de la factura la base de LibraCore y `openssl` por subproceso—, y
    uvicorn corre con **un solo proceso**: como `async def`, cada una de esas
    llamadas frenaba el loop entero, y mientras se completaba un turno con
    factura la instancia no le contestaba a nadie, `/health` incluido. Como
    `def`, FastAPI la corre en el threadpool.

    🔑 `invoice_appointment` es `async` sólo en los bordes: la numeración y el
    CAE van por red asincrónica, pero entre medio escribe la factura y la caja
    en la base, y en producción el numerador firma el TRA con `openssl`. Por
    eso corre con `asyncio.run`, en un loop propio de este hilo: lo sincrónico
    bloquea a este hilo y a nadie más. Su firma no cambia; el arreglo va del
    lado de quien llama."""
    current = service.appointments.get(appointment_id)
    if current is None:
        raise HTTPException(404, mensajes.POR_NOMBRE["AppointmentNotFound"][1])

    price_row = None
    client: dict = {}
    deposit = None
    if modules.is_enabled("facturacion"):
        resource = catalog.get_resource(current.resource_id)
        branch_id = resource.branch_id if resource else None
        if branch_id:
            price_row = service_prices.get(current.service_id, branch_id)
    if price_row is not None:
        client = clients.get(current.client_id) or {}
        deposit = deposits.get_by_appointment(appointment_id)
        paid = deposit is not None and deposit.status is DepositStatus.PAID
        balance = price_row["price"] - (deposit.amount if paid else 0)
        if balance > 0 and not data.medio_pago:
            raise HTTPException(422, f"medio_pago requerido para saldo de {balance}")

    if offline.nodo() is not None:
        cobro = None
        if price_row is not None:
            cobro = _cobro_del_turno(
                catalog, current, price_row["price"], client, deposit, data.medio_pago)
        return _atender_en_el_nodo(
            sessions, appointment_id, AppointmentStatus.COMPLETED, user, cobro=cobro)

    try:
        appointment = service.complete(appointment_id)
    except AppointmentNotFound:
        raise HTTPException(404, mensajes.POR_NOMBRE["AppointmentNotFound"][1])
    except InvalidTransition as exc:
        raise HTTPException(*mensajes.describir(exc))

    factura = None
    if price_row is not None:
        paid = deposit is not None and deposit.status is DepositStatus.PAID
        # En un loop propio de este hilo y no con `await` en el de uvicorn: ver
        # el docstring. Las excepciones salen de `asyncio.run` tal cual.
        factura = asyncio.run(invoice_appointment(
            client, price_row["price"], appointment_id,
            deposit_amount=deposit.amount if paid else None,
            deposit_medio_pago=deposit.medio_pago if paid else None,
            balance_medio_pago=data.medio_pago,
        ))

    return {"id": appointment.id, "status": appointment.status.value, "factura": factura}


# ── En un nodo: atender y cobrar sin conexión (ADR-036) ────────────────────────────────────────────────────────────────


def _cobro_del_turno(catalog, turno, precio, cliente: dict, deposit, medio_pago: str | None) -> CobroDelTurno:
    """Lo que se cobra: la misma cuenta de `billing.invoice_appointment` (el saldo es el precio menos la seña **pagada**),
    con el cliente y el servicio tal como están hoy: la cola guarda esta foto."""
    pagada = deposit is not None and deposit.status is DepositStatus.PAID
    sena = Decimal(deposit.amount) if pagada else Decimal(0)
    servicio = catalog.get_service(turno.service_id)
    return CobroDelTurno(
        precio=Decimal(precio), sena=sena, sena_medio_pago=deposit.medio_pago if pagada else None,
        saldo=Decimal(precio) - sena, saldo_medio_pago=medio_pago,
        cliente={**cliente, "id": turno.client_id}, servicio=servicio.name if servicio else turno.service_id,
    )


def _atender_en_el_nodo(sessions, appointment_id: str, estado: AppointmentStatus, user: dict, *,
                        cobro: CobroDelTurno | None = None) -> dict:
    """Lo que contesta el nodo al atender un turno: el nuevo estado y, si se cobró, cómo quedó la factura.

    - Con conexión, la factura se intenta en el acto (`factura`): el cliente se lleva la de siempre.
    - Sin conexión, o si se corta, queda en la cola (`factura_en_cola`) y sale sola al volver; el cliente se lleva el
      **comprobante no fiscal** (`comprobante_no_fiscal`: la ruta del PDF).
    """
    actor = user.get("name") or user.get("username")
    try:
        pedido = atencion_nodo.atender(sessions, appointment_id, estado, actor=actor, cobro=cobro)
    except AppointmentNotFound:
        raise HTTPException(404, mensajes.POR_NOMBRE["AppointmentNotFound"][1])
    except InvalidTransition as exc:
        raise HTTPException(*mensajes.describir(exc))
    respuesta: dict = {
        "id": appointment_id, "status": estado.value, "factura": None, "atendido_sin_conexion": True,
        "factura_en_cola": None, "comprobante_no_fiscal": None, "mensaje": None,
    }
    if pedido is None:
        return respuesta
    pedido = atencion_nodo.emitir_si_hay_conexion(pedido, usuario_id=user.get("id"))
    if pedido["estado"] == "emitido":
        respuesta["factura"] = db_facturas.get_factura(int(pedido["resultado"]["factura_id"]))
        return respuesta
    respuesta["factura_en_cola"] = pedido
    respuesta["mensaje"] = atencion_nodo.mensaje_del_pedido(pedido)
    respuesta["comprobante_no_fiscal"] = f"/appointments/{appointment_id}/comprobante-no-fiscal"
    # La forma única del «en cola» (libracore ADR-084), la que reconoce el kit (`esRespuestaEnCola`, libra-ui ADR-094): la
    # pantalla muestra el aviso «Se emite al volver la conexión» en vez de dar la factura por emitida. El turno ya se atendió:
    # se contesta 200 y el pedido en cola es una parte de la respuesta (el kit decide por el cuerpo, no por el código).
    respuesta.update(cuerpo_en_cola(pedido, mensaje=respuesta["mensaje"]))
    return respuesta


@router.post("/appointments/{appointment_id}/start")
def start_appointment(
    appointment_id: str, sessions: sessionmaker[Session] = Depends(get_sessions),
    user: dict = Depends(get_current_user),
):
    """Marca el turno «en curso». **Sólo en un nodo** (ADR-036): en la web el turno se completa directamente. Es la
    atención del mostrador sin conexión, que sube sola al volver (`turno.atendido`)."""
    offline.exigir_nodo(offline.MENSAJE_SOLO_EN_EL_NODO_START)
    return _atender_en_el_nodo(sessions, appointment_id, AppointmentStatus.IN_PROGRESS, user)


@router.post("/appointments/{appointment_id}/no-show")
def no_show_appointment(
    appointment_id: str, sessions: sessionmaker[Session] = Depends(get_sessions),
    user: dict = Depends(get_current_user),
):
    """Marca que el cliente «no vino». **Sólo en un nodo** (ADR-036), por lo mismo que `start`."""
    offline.exigir_nodo(offline.MENSAJE_SOLO_EN_EL_NODO_NO_SHOW)
    return _atender_en_el_nodo(sessions, appointment_id, AppointmentStatus.NO_SHOW, user)


@router.get("/appointments/{appointment_id}/comprobante-no-fiscal")
def comprobante_no_fiscal(appointment_id: str):
    """El comprobante que se lleva el cliente cuando se cobró sin conexión y la factura todavía no salió: un PDF «no válido
    como factura» con la leyenda «La factura se emite al volver la conexión». Se puede reimprimir. 404 si el turno no se
    cobró en este equipo, 409 si la factura ya salió."""
    try:
        pdf = atencion_nodo.comprobante_no_fiscal(appointment_id)
    except atencion_nodo.SinComprobanteNoFiscal as exc:
        raise HTTPException(404, str(exc))
    except atencion_nodo.YaFacturado as exc:
        raise HTTPException(409, {"codigo": "ya_facturado", "mensaje": str(exc)})
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="comprobante-no-fiscal-{appointment_id[:8]}.pdf"'})
