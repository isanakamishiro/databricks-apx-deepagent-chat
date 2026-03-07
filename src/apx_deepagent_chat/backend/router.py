from databricks.sdk.service.iam import User as UserOut

from .core import Dependencies, create_router
from .models import VersionOut
from .routers.chat_history import router as chat_history_router
from .routers.config import router as config_router
from .routers.files import router as files_router

router = create_router()


@router.get("/version", response_model=VersionOut, operation_id="version")
async def version():
    return VersionOut.from_metadata()


@router.get("/current-user", response_model=UserOut, operation_id="currentUser")
def me(user_ws: Dependencies.UserClient):
    return user_ws.current_user.me()


router.include_router(config_router)
router.include_router(chat_history_router)
router.include_router(files_router)
