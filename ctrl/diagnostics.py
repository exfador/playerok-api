from collections.abc import Awaitable, Callable
from logging import Logger

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.types import TelegramObject

from constants.telegram import HANDLER_ENTER_LOG, HANDLER_EXIT_LOG, HANDLER_UNKNOWN


class TelegramHandlerDiagnostics(BaseMiddleware):
    def __init__(self, logger: Logger):
        self.logger = logger

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        name = handler_name(data.get("handler"))
        self.logger.debug(HANDLER_ENTER_LOG, name)
        result = await handler(event, data)
        self.logger.debug(HANDLER_EXIT_LOG, name)
        return result


def handler_name(handler: object) -> str:
    if not isinstance(handler, HandlerObject):
        return HANDLER_UNKNOWN
    callback = handler.callback
    module = getattr(callback, "__module__", type(callback).__module__)
    name = getattr(callback, "__qualname__", type(callback).__qualname__)
    return f"{module}.{name}"
