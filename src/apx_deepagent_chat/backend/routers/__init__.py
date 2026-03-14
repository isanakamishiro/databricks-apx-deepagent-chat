from ..core import create_router
from .system import router as system_router
from .chat_history import router as chat_history_router
from .files import router as files_router
from .volumes import router as volumes_router

router = create_router()
router.include_router(system_router)
router.include_router(chat_history_router)
router.include_router(files_router)
router.include_router(volumes_router)
