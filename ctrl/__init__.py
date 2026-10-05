from aiogram import Router
from .priority import router as priority_router
from .actions import router as actions_router
from .items import router as items_router
from .access import router as access_router

router = Router()
router.include_routers(priority_router, access_router, items_router, actions_router)
