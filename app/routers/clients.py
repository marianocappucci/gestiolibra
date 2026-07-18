from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from libragenda import Client
from libragenda.catalog_repository import SqlAlchemyCatalogRepository

from ..dependencies import get_catalog_repository

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientCreate(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    active: bool = True


class ClientUpdate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    active: bool = True


class ClientOut(BaseModel):
    id: str
    name: str
    phone: str | None
    email: str | None
    active: bool


def _to_out(client: Client) -> ClientOut:
    return ClientOut(
        id=client.id, name=client.name, phone=client.phone,
        email=client.email, active=client.active,
    )


@router.post("", status_code=201, response_model=ClientOut)
def create_client(
    data: ClientCreate, catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository)
):
    try:
        client = Client(data.id, data.name, data.phone, data.email, data.active)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    try:
        catalog.add_client(client)
    except IntegrityError:
        raise HTTPException(409, "client already exists")
    return _to_out(client)


@router.get("", response_model=list[ClientOut])
def list_clients(catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository)):
    return [_to_out(item) for item in catalog.list_clients()]


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: str, catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository)
):
    client = catalog.get_client(client_id)
    if client is None:
        raise HTTPException(404, "client not found")
    return _to_out(client)


@router.put("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: str,
    data: ClientUpdate,
    catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository),
):
    try:
        client = Client(client_id, data.name, data.phone, data.email, data.active)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    try:
        catalog.update_client(client_id, client)
    except KeyError:
        raise HTTPException(404, "client not found")
    return _to_out(client)


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: str, catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository)
):
    try:
        catalog.delete_client(client_id)
    except KeyError:
        raise HTTPException(404, "client not found")
    return Response(status_code=204)
