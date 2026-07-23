from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..auth import require_admin
from ..dependencies import get_client_repository
from ..services.clients import ClientRepository

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientCreate(BaseModel):
    id: str
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


@router.post("", status_code=201, response_model=ClientOut, dependencies=[Depends(require_admin)])
def create_client(
    data: ClientCreate, clients: ClientRepository = Depends(get_client_repository),
):
    try:
        return clients.create(
            data.id, data.name, data.phone, data.email, data.active,
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
    try:
        clients.delete(client_id)
    except KeyError:
        raise HTTPException(404, "client not found")
    except IntegrityError:
        raise HTTPException(409, "client still has dependent records")
    return Response(status_code=204)
