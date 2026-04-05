from __future__ import annotations
from colorama import Fore
from logging import getLogger
from pok.defs import MarketEvent

logger = getLogger('cxh.bus')


class Signal:
    __slots__ = ('_name', '_slots')

    def __init__(self, name: str) -> None:
        self._name  = name
        self._slots: list[callable] = []

    def connect(self, fn: callable, pos: int | None = None) -> None:
        self._slots.insert(pos, fn) if pos is not None else self._slots.append(fn)

    def disconnect(self, fn: callable) -> None:
        try:
            self._slots.remove(fn)
        except ValueError:
            pass

    def connect_many(self, fns: list[callable]) -> None:
        for fn in fns:
            if fn not in self._slots:
                self._slots.append(fn)

    def disconnect_many(self, fns: list[callable]) -> None:
        for fn in fns:
            self.disconnect(fn)

    def receivers(self) -> list[callable]:
        return list(self._slots)

    async def send(self, *args, via: callable | None = None) -> None:
        targets = [via] if via else list(self._slots)
        logger.debug('[%s] receivers=%d', self._name, len(targets))
        for fn in targets:
            try:
                await fn(*args)
            except Exception as exc:
                logger.error(
                    '%s[%s] %s.%s → %s%s',
                    Fore.LIGHTRED_EX, self._name,
                    fn.__module__, fn.__qualname__, exc, Fore.RESET,
                )


def _make_sys_signals() -> dict[str, Signal]:
    return {k: Signal(k.lower()) for k in ('BOOT', 'ALIVE', 'PANEL_UP', 'BOT_UP', 'PLUG_IN', 'PLUG_OUT')}


def _make_mkt_signals() -> dict[MarketEvent, Signal]:
    return {ev: Signal(ev.name.lower()) for ev in (
        MarketEvent.CHAT_INITIALIZED,
        MarketEvent.NEW_MESSAGE,
        MarketEvent.NEW_DEAL,
        MarketEvent.NEW_REVIEW,
        MarketEvent.DEAL_CONFIRMED,
        MarketEvent.DEAL_CONFIRMED_AUTOMATICALLY,
        MarketEvent.DEAL_ROLLED_BACK,
        MarketEvent.DEAL_HAS_PROBLEM,
        MarketEvent.DEAL_PROBLEM_RESOLVED,
        MarketEvent.DEAL_STATUS_CHANGED,
        MarketEvent.ITEM_PAID,
        MarketEvent.ITEM_SENT,
        MarketEvent.REVIEW_REMOVED,
        MarketEvent.REVIEW_UPDATED,
    )}


_SYS: dict[str, Signal] = _make_sys_signals()
_MKT: dict[MarketEvent, Signal] = _make_mkt_signals()


def _sys_sig(event: str) -> Signal:
    if event not in _SYS:
        _SYS[event] = Signal(event.lower())
    return _SYS[event]


def _mkt_sig(event: MarketEvent) -> Signal:
    return _MKT[event]


def wire(event: str, fn: callable, pos: int | None = None) -> None:
    _sys_sig(event).connect(fn, pos)


def wire_mkt(event: MarketEvent, fn: callable, pos: int | None = None) -> None:
    _mkt_sig(event).connect(fn, pos)


def graft(table: dict[str, list]) -> None:
    for evt, fns in table.items():
        _sys_sig(evt).connect_many(fns)


def prune(table: dict[str, list]) -> None:
    for evt, fns in table.items():
        if evt in _SYS:
            _SYS[evt].disconnect_many(fns)


def graft_mkt(table: dict[MarketEvent, list]) -> None:
    for evt, fns in table.items():
        _mkt_sig(evt).connect_many(fns)


def prune_mkt(table: dict[MarketEvent, list]) -> None:
    for evt, fns in table.items():
        if evt in _MKT:
            _MKT[evt].disconnect_many(fns)


def sys_table() -> dict[str, Signal]:
    return _SYS


def mkt_table() -> dict[MarketEvent, Signal]:
    return _MKT


async def fire(event: str, args: list = [], fn: callable = None) -> None:
    await _sys_sig(event).send(*args, via=fn)


async def fire_mkt(event: MarketEvent, args: list = []) -> None:
    await _mkt_sig(event).send(*args)
