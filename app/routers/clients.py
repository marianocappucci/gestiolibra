from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .. import offline
from ..auth import require_admin
from ..dependencies import get_client_repository, get_sessions
from ..services import clientes_nodo
from ..services.clients import ClientRepository

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientCreate(BaseModel):
    id: str | None = None
    name: str
    phone: str | None = None
    email: str | None = None
    active: bool = True
    cuit: str | None = None
    condicion_iva: str | None = None


class ClientUpdate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    active: bool = True
    cuit: str | None = None
    condicion_iva: str | None = None


class ClientOut(BaseModel):
    id: str
    name: str
    phone: str | None
    email: str | None
    active: bool
    cuit: str | None
    condicion_iva: str | None


# Alta abierta a staff: el router entero ya exige `require_staff` (staff **o**
# admin, ver `main.py`), y quien atiende tiene que poder dar de alta al cliente
# desde el selector del turno (ADR-071 de libra-ui). Editar y borrar siguen
# siendo sólo de admin.
@router.post("", status_code=201, response_model=ClientOut)
def create_client(
    data: ClientCreate, clients: ClientRepository = Depends(get_client_repository),
    sessions: sessionmaker[Session] = Depends(get_sessions),
):
    """`id` es opcional: a diferencia de sucursales/recursos/servicios
    (catálogo que arma un admin una vez, con slugs pensados a mano),
    clientes se dan de alta todo el tiempo durante la operación diaria
    -- pedirle a quien atiende que invente un id único para cada
    cliente nuevo es friccion real sin ningún beneficio. Sigue
    aceptándose explícito para uso scripteado que ya lo pase.

    🔑 **En un nodo de LibraEdge el cliente nace con un id provisorio** (`"-N"`, ADR-036): el que pase `id` se ignora. El
    central le asigna el definitivo al recibirlo (y si ya existía con ese CUIT, lo une a su ficha). Fuera de un nodo no
    cambia nada."""
    if offline.nodo() is not None:
        try:
            return clientes_nodo.alta_en_el_nodo(
                sessions, nombre=data.name, telefono=data.phone, email=data.email, cuit=data.cuit,
                condicion_iva=data.condicion_iva,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    client_id = data.id or str(uuid4())
    try:
        return clients.create(
            client_id, data.name, data.phone, data.email, data.active,
            data.cuit, data.condicion_iva,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except IntegrityError:
        raise HTTPException(409, "client already exists")


@router.get("", response_model=list[ClientOut])
def list_clients(clients: ClientRepository = Depends(get_client_repository)):
    return clients.list()


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: str, clients: ClientRepository = Depends(get_client_repository)):
    client = clients.get(client_id)
    if client is None:
        raise HTTPException(404, "client not found")
    return client


@router.put("/{client_id}", response_model=ClientOut, dependencies=[Depends(require_admin)])
def update_client(
    client_id: str, data: ClientUpdate,
    clients: ClientRepository = Depends(get_client_repository),
):
    clientes_nodo.exigir_cliente_modificable(client_id)
    try:
        return clients.update(
            client_id, data.name, data.phone, data.email, data.active,
            data.cuit, data.condicion_iva,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError:
        raise HTTPException(404, "client not found")


@router.delete("/{client_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_client(client_id: str, clients: ClientRepository = Depends(get_client_repository)):
    clientes_nodo.exigir_cliente_modificable(client_id)
    try:
        clients.delete(client_id)
    except KeyError:
        raise HTTPException(404, "client not found")
    except IntegrityError:
        raise HTTPException(409, "client still has dependent records")
    return Response(status_code=204)
