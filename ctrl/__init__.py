from aiogram import Router
from .priority import router as priority_router
from .actions import router as actions_router

router = Router()
router.include_routers(priority_router, actions_router)
