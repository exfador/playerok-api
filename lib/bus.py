from colorama import Fore
from logging import getLogger
from pok.defs import MarketEvent

logger = getLogger('pl.bus')

_system_hooks: dict[str, list[callable]] = {
    'ON_EXT_LOAD': [],
    'ON_EXT_UNLOAD': [],
    'ON_STARTUP': [],
    'ON_READY': [],
    'ON_PANEL_READY': [],
    'ON_BOT_READY': [],
}
_market_hooks: dict[MarketEvent, list[callable]] = {
    MarketEvent.CHAT_INITIALIZED: [],
    MarketEvent.NEW_MESSAGE: [],
    MarketEvent.NEW_DEAL: [],
    MarketEvent.NEW_REVIEW: [],
    MarketEvent.DEAL_CONFIRMED: [],
    MarketEvent.DEAL_CONFIRMED_AUTOMATICALLY: [],
    MarketEvent.DEAL_ROLLED_BACK: [],
    MarketEvent.DEAL_HAS_PROBLEM: [],
    MarketEvent.DEAL_PROBLEM_RESOLVED: [],
    MarketEvent.DEAL_STATUS_CHANGED: [],
    MarketEvent.ITEM_PAID: [],
    MarketEvent.ITEM_SENT: [],
    MarketEvent.REVIEW_REMOVED: [],
    MarketEvent.REVIEW_UPDATED: [],
}


def sys_hooks() -> dict[str, list[callable]]:
    return _system_hooks


def set_sys_hooks(data: dict[str, list[callable]]):
    global _system_hooks
    _system_hooks = data


def on_sys(event: str, handler: callable, index: int | None = None):
    global _system_hooks
    if index is None:
        _system_hooks[event].append(handler)
    else:
        _system_hooks[event].insert(index, handler)


def attach_sys(handlers: dict[str, list[callable]]):
    global _system_hooks
    for event_type, funcs in handlers.items():
        if event_type not in _system_hooks:
            _system_hooks[event_type] = []
        _system_hooks[event_type].extend(funcs)


def detach_sys(handlers: dict[str, list[callable]]):
    for event, funcs in handlers.items():
        if event in _system_hooks:
            for func in funcs:
                if func in _system_hooks[event]:
                    _system_hooks[event].remove(func)


def mkt_hooks() -> dict[MarketEvent, list]:
    return _market_hooks


def set_mkt_hooks(data: dict[MarketEvent, list[callable]]):
    global _market_hooks
    _market_hooks = data


def on_mkt(event: MarketEvent, handler: callable, index: int | None = None):
    global _market_hooks
    if index is None:
        _market_hooks[event].append(handler)
    else:
        _market_hooks[event].insert(index, handler)


def attach_mkt(handlers: dict[MarketEvent, list[callable]]):
    global _market_hooks
    for event_type, funcs in handlers.items():
        if event_type not in _market_hooks:
            _market_hooks[event_type] = []
        _market_hooks[event_type].extend(funcs)


def detach_mkt(handlers: dict[MarketEvent, list[callable]]):
    global _market_hooks
    for event, funcs in handlers.items():
        if event in _market_hooks:
            for func in funcs:
                if func in _market_hooks[event]:
                    _market_hooks[event].remove(func)


async def dispatch(event: str, args: list = [], func=None):
    if not func:
        handlers = sys_hooks().get(event, [])
    else:
        handlers = [func]
    logger.debug(f'[dispatch] {event}  handlers={len(handlers)}')
    for handler in handlers:
        try:
            logger.debug(f'  → {handler.__module__}.{handler.__qualname__}')
            await handler(*args)
        except Exception as e:
            logger.error(f'{Fore.LIGHTRED_EX}Ошибка при обработке хендлера «{handler.__module__}.{handler.__qualname__}» для события «{event}»: {Fore.WHITE}{e}')


async def dispatch_market(event: MarketEvent, args: list = []):
    handlers = mkt_hooks().get(event, [])
    logger.debug(f'[dispatch_market] {event.name}  handlers={len(handlers)}')
    for handler in handlers:
        try:
            logger.debug(f'  → {handler.__module__}.{handler.__qualname__}')
            await handler(*args)
        except Exception as e:
            logger.error(f'{Fore.LIGHTRED_EX}Ошибка при обработке хендлера «{handler.__module__}.{handler.__qualname__}» для события Playerok «{event.name}»: {Fore.WHITE}{e}')
