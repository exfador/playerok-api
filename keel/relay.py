from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from logging import getLogger
from typing import Any, Awaitable, Callable

from colorama import Fore
from moor.kinds import IngressPoint

log = getLogger('keel.relay')

AsyncFn = Callable[..., Awaitable[Any]]


def _fn_label(cb: AsyncFn) -> str:
    return f'{cb.__module__}.{cb.__qualname__}'


@dataclass
class _StratumMux:
    _rows: dict[str, list[AsyncFn]] = field(default_factory=lambda: defaultdict(list))

    def as_map(self) -> dict[str, list[AsyncFn]]:
        return self._rows

    def replace(self, incoming: dict[str, list[AsyncFn]]) -> None:
        self._rows.clear()
        for k, v in incoming.items():
            self._rows[k] = list(v)

    def enqueue(self, phase: str, cb: AsyncFn, *, before_index: int | None = None) -> None:
        row = self._rows[phase]
        if before_index is None:
            row.append(cb)
        else:
            row.insert(before_index, cb)

    def merge(self, bundle: dict[str, list[AsyncFn]]) -> None:
        for phase, cbs in bundle.items():
            self._rows[phase].extend(cbs)

    def strip(self, bundle: dict[str, list[AsyncFn]]) -> None:
        for phase, cbs in bundle.items():
            row = self._rows.get(phase)
            if not row:
                continue
            for cb in cbs:
                while cb in row:
                    row.remove(cb)


@dataclass
class _PulseMux:
    _rows: dict[IngressPoint, list[AsyncFn]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._rows:
            self._rows = {p: [] for p in IngressPoint}

    def as_map(self) -> dict[IngressPoint, list[AsyncFn]]:
        return self._rows

    def replace(self, incoming: dict[IngressPoint, list[AsyncFn]]) -> None:
        base = {p: [] for p in IngressPoint}
        for k, v in incoming.items():
            if k in base:
                base[k] = list(v)
        self._rows = base

    def enqueue(self, pulse: IngressPoint, cb: AsyncFn, *, before_index: int | None = None) -> None:
        row = self._rows[pulse]
        if before_index is None:
            row.append(cb)
        else:
            row.insert(before_index, cb)

    def merge(self, bundle: dict[IngressPoint, list[AsyncFn]]) -> None:
        for pulse, cbs in bundle.items():
            if pulse not in self._rows:
                self._rows[pulse] = []
            self._rows[pulse].extend(cbs)

    def strip(self, bundle: dict[IngressPoint, list[AsyncFn]]) -> None:
        for pulse, cbs in bundle.items():
            row = self._rows.get(pulse)
            if not row:
                continue
            for cb in cbs:
                while cb in row:
                    row.remove(cb)


_RUNTIME = _StratumMux(
    _rows=defaultdict(
        list,
        {
            'GRAFT_ARM': [],
            'GRAFT_DISARM': [],
            'BOOT_TAIL': [],
            'STREAM_LIVE': [],
            'FACADE_LIVE': [],
            'JOB_SLOT': [],
        },
    )
)
_VENUE = _PulseMux()


async def _invoke_chain(kind: str, key: str, cbs: list[AsyncFn], payload: list[Any]) -> None:
    log.debug('signal %s key=%s count=%s', kind, key, len(cbs))
    for cb in cbs:
        log.debug('  call %s', _fn_label(cb))
        try:
            await cb(*payload)
        except Exception as err:
            log.error(
                '%s%s failed in %s for key %r: %s%s',
                Fore.LIGHTRED_EX,
                _fn_label(cb),
                kind,
                key,
                err,
                Fore.RESET,
            )


def strata_map() -> dict[str, list[AsyncFn]]:
    return _RUNTIME.as_map()


def set_strata_map(data: dict[str, list[AsyncFn]]) -> None:
    _RUNTIME.replace(data)


def hook_strata(phase: str, handler: AsyncFn, index: int | None = None) -> None:
    _RUNTIME.enqueue(phase, handler, before_index=index)


def merge_strata(handlers: dict[str, list[AsyncFn]]) -> None:
    _RUNTIME.merge(handlers)


def prune_strata(handlers: dict[str, list[AsyncFn]]) -> None:
    _RUNTIME.strip(handlers)


def ingress_map() -> dict[IngressPoint, list[AsyncFn]]:
    return _VENUE.as_map()


def set_ingress_map(data: dict[IngressPoint, list[AsyncFn]]) -> None:
    _VENUE.replace(data)


def hook_ingress(pulse: IngressPoint, handler: AsyncFn, index: int | None = None) -> None:
    _VENUE.enqueue(pulse, handler, before_index=index)


def merge_ingress(handlers: dict[IngressPoint, list[AsyncFn]]) -> None:
    _VENUE.merge(handlers)


def prune_ingress(handlers: dict[IngressPoint, list[AsyncFn]]) -> None:
    _VENUE.strip(handlers)


async def broadcast(phase: str, args: list | None = None, func: AsyncFn | None = None) -> None:
    payload = args if args is not None else []
    cbs = [func] if func is not None else list(_RUNTIME.as_map().get(phase, []))
    await _invoke_chain('runtime', phase, cbs, payload)


async def broadcast_ingress(pulse: IngressPoint, args: list | None = None) -> None:
    payload = args if args is not None else []
    cbs = list(_VENUE.as_map().get(pulse, []))
    await _invoke_chain('venue', pulse.name, cbs, payload)
