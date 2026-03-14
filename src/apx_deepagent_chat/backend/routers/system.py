from databricks.sdk.service.iam import User as UserOut

from fastapi import APIRouter

from ..agent import load_models_config
from ..core import Dependencies
from ..models import VersionOut

router = APIRouter()


@router.get("/version", response_model=VersionOut, operation_id="version")
async def version():
    return VersionOut.from_metadata()


@router.get("/current-user", response_model=UserOut, operation_id="currentUser")
def me(user_ws: Dependencies.UserClient):
    return user_ws.current_user.me()


@router.get("/config", operation_id="getConfig")
async def get_config(ws: Dependencies.Client):
    model_config = load_models_config()
    models = [
        {"id": model_id, "display_name": cfg.get("display_name", model_id)}
        for model_id, cfg in model_config.items()
    ]
    default_model = next(model_id for model_id, cfg in model_config.items() if cfg.get("default"))
    host = ws.config.host or ""
    return {
        "models": models,
        "default_model": default_model,
        "workspace_url": host,
    }
