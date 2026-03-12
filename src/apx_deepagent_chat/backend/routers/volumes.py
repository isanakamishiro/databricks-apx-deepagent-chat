from databricks.sdk.errors import NotFound, PermissionDenied
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core import Dependencies

router = APIRouter()


class CatalogOut(BaseModel):
    name: str


class SchemaOut(BaseModel):
    name: str


class VolumeOut(BaseModel):
    name: str


@router.get("/volumes/catalogs", operation_id="listCatalogs", response_model=list[CatalogOut])
async def list_catalogs(ws: Dependencies.UserClient) -> list[CatalogOut]:
    try:
        return [CatalogOut(name=c.name) for c in ws.catalogs.list() if c.name]
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/volumes/schemas", operation_id="listSchemas", response_model=list[SchemaOut])
async def list_schemas(
    ws: Dependencies.UserClient,
    catalog: str = Query(...),
) -> list[SchemaOut]:
    try:
        return [SchemaOut(name=s.name) for s in ws.schemas.list(catalog_name=catalog) if s.name]
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/volumes/volumes", operation_id="listVolumes", response_model=list[VolumeOut])
async def list_volumes(
    ws: Dependencies.UserClient,
    catalog: str = Query(...),
    schema: str = Query(...),
) -> list[VolumeOut]:
    try:
        return [
            VolumeOut(name=v.name)
            for v in ws.volumes.list(catalog_name=catalog, schema_name=schema)
            if v.name
        ]
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
