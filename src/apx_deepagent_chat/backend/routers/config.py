from fastapi import APIRouter

from ..agent import MODEL

router = APIRouter()


@router.get("/config", operation_id="getConfig")
async def get_config():
    return {
        "models": [MODEL],
        "default_model": MODEL,
    }
