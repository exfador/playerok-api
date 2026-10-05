import os
import sys
import importlib
import uuid
from pathlib import Path
from uuid import UUID
from colorama import Fore
from dataclasses import dataclass
from logging import getLogger
from lib.consts import C_BRIGHT, C_DIM
from lib.bus import graft, prune, graft_mkt, prune_mkt, fire
from lib.util import check_requirements, plural

logger = getLogger('cxh.ext')
ADDONS_DIR = str(Path(__file__).resolve().parent.parent / 'ext')
ADDONS_PKG = 'ext'


@dataclass
class ExtMeta:
    prefix:      str
    version:     str
    name:        str
    description: str
    authors:     str
    links:       str


@dataclass
class Extension:
    uuid:      UUID
    enabled:   bool
    meta:      ExtMeta
    evt_wire:  dict
    mkt_wire:  dict
    bot_paths: list
    _dir_name: str


_extensions: list[Extension] = []


def all_extensions() -> list[Extension]:
    return _extensions


def register_extensions(extensions: list[Extension]) -> None:
    global _extensions
    _extensions = extensions


def _uuid_key(u: UUID | str) -> UUID:
    return u if isinstance(u, UUID) else UUID(str(u))


def find_extension(ext_uuid: UUID | str) -> Extension | None:
    key = _uuid_key(ext_uuid)
    return next((e for e in _extensions if e.uuid == key), None)


async def _enable_extension(ext: Extension) -> None:
    global _extensions
    graft(ext.evt_wire)
    graft_mkt(ext.mkt_wire)
    ext.enabled = True
    idx = _extensions.index(ext)
    _extensions[idx] = ext
    for handler in ext.evt_wire.get('PLUG_IN', []):
        await fire('PLUG_IN', [ext], handler)


def _disabled_names() -> set[str]:
    from lib.db import AppDb
    state = AppDb.get('ext_state') or {}
    return {str(name) for name in state.get('disabled') or []}


def _remember_disabled(name: str, disabled: bool) -> None:
    from lib.db import AppDb
    names = _disabled_names()
    if disabled:
        names.add(name)
    else:
        names.discard(name)
    AppDb.set('ext_state', {'disabled': sorted(names)})


async def start_extension(ext_uuid: UUID) -> bool:
    try:
        ext = find_extension(ext_uuid)
        await _enable_extension(ext)
        _remember_disabled(ext._dir_name, False)
        logger.info('Расширение %s%s%s включено', C_BRIGHT, ext.meta.name, Fore.RESET)
        return True
    except Exception as e:
        logger.error('Ошибка включения расширения %s: %s', ext_uuid, e)
        return False


async def _disable_extension(ext: Extension) -> None:
    global _extensions
    prune(ext.evt_wire)
    prune_mkt(ext.mkt_wire)
    ext.enabled = False
    idx = _extensions.index(ext)
    _extensions[idx] = ext
    for handler in ext.evt_wire.get('PLUG_OUT', []):
        await fire('PLUG_OUT', [ext], handler)


async def stop_extension(ext_uuid: UUID) -> bool:
    try:
        ext = find_extension(ext_uuid)
        await _disable_extension(ext)
        _remember_disabled(ext._dir_name, True)
        logger.info('Расширение %s%s%s выключено', C_BRIGHT, ext.meta.name, Fore.RESET)
        return True
    except Exception as e:
        logger.error('Ошибка выключения расширения %s: %s', ext_uuid, e)
        return False


def _bindings_from_module(py_mod) -> tuple[dict, dict, list]:
    evt_wire:  dict = {}
    mkt_wire:  dict = {}
    bot_paths: list = []
    raw_evt = getattr(py_mod, 'EVT_WIRE', None)
    if raw_evt is not None:
        for key, fns in raw_evt.items():
            evt_wire[key] = list(fns)
    raw_mkt = getattr(py_mod, 'MKT_WIRE', None)
    if raw_mkt is not None:
        for key, fns in raw_mkt.items():
            mkt_wire[key] = list(fns)
    raw_paths = getattr(py_mod, 'BOT_PATHS', None)
    if raw_paths is not None:
        bot_paths.extend(raw_paths)
    return evt_wire, mkt_wire, bot_paths


def _detach_subrouter(router) -> None:
    parent = router.parent_router
    if parent is None:
        return
    try:
        if router in parent.sub_routers:
            parent.sub_routers.remove(router)
    except (ValueError, AttributeError):
        pass
    router._parent_router = None


def _replace_extension_tg_routers(old_routes: list, new_routes: list) -> None:
    from ctrl import router as main_rt
    from ctrl.cmd import router as cmd_router

    if cmd_router.parent_router is None:
        main_rt.include_router(cmd_router)
    removed = old_routes + new_routes
    remaining = [route for route in main_rt.sub_routers if route not in removed]
    following = [route for route in _routers_following_extension(main_rt, old_routes) if route not in removed]
    for route in old_routes:
        _detach_subrouter(route)
    for route in new_routes:
        _detach_subrouter(route)
        main_rt.include_router(route)
    preceding = [route for route in remaining if route not in following]
    main_rt.sub_routers[:] = preceding + new_routes + following


def _routers_following_extension(main_router, old_routes: list) -> list:
    encountered = False
    following = []
    for route in main_router.sub_routers:
        if route in old_routes:
            encountered = True
        elif encountered:
            following.append(route)
    return following


async def refresh_extension(ext_uuid: UUID | str) -> bool:
    ext = find_extension(_uuid_key(ext_uuid))
    if ext is None:
        logger.error('Перезагрузка: расширение %s не найдено', ext_uuid)
        return False

    old_evt  = {k: list(v) for k, v in ext.evt_wire.items()}
    old_mkt  = {k: list(v) for k, v in ext.mkt_wire.items()}
    old_tg   = list(ext.bot_paths)
    mod_key  = f'{ADDONS_PKG}.{ext._dir_name}'
    logger.info('Перезагрузка расширения «%s» (%s)', ext.meta.name, mod_key)

    await _disable_extension(ext)
    detached_old_tg = False
    new_evt:  dict = {}
    new_mkt:  dict = {}
    new_tg:   list = []

    try:
        sys.modules.pop(mod_key, None)
        py_mod = importlib.import_module(mod_key)
        new_evt, new_mkt, new_tg = _bindings_from_module(py_mod)
        _replace_extension_tg_routers(old_tg, new_tg)
        detached_old_tg = True
        ext.evt_wire  = new_evt
        ext.mkt_wire  = new_mkt
        ext.bot_paths = list(new_tg)
        await _enable_extension(ext)
        logger.info(
            'Расширение %s%s%s перезагружено (%s)',
            C_BRIGHT, ext.meta.name, Fore.RESET,
            getattr(py_mod, '__file__', '?'),
        )
        return True
    except Exception:
        logger.exception('Ошибка перезагрузки расширения %s (%s)', ext_uuid, mod_key)
        if detached_old_tg:
            try:
                _replace_extension_tg_routers(new_tg, old_tg)
            except Exception:
                logger.exception('Откат маршрутов Telegram после сбоя')
        ext.evt_wire  = old_evt
        ext.mkt_wire  = old_mkt
        ext.bot_paths = old_tg
        try:
            await _enable_extension(ext)
            logger.warning('Расширение «%s» возвращено к предыдущим хукам', ext.meta.name)
        except Exception:
            logger.exception('Не удалось снова включить расширение после сбоя')
        return False


def _load_addon_from_module(py_mod, dir_name: str) -> Extension:
    evt_wire, mkt_wire, bot_paths = _bindings_from_module(py_mod)
    return Extension(
        uuid=uuid.uuid4(),
        enabled=False,
        meta=ExtMeta(
            py_mod.PREFIX, py_mod.VERSION, py_mod.NAME,
            py_mod.DESCRIPTION, py_mod.AUTHORS, py_mod.LINKS,
        ),
        evt_wire=evt_wire,
        mkt_wire=mkt_wire,
        bot_paths=bot_paths,
        _dir_name=dir_name,
    )


def discover_extensions() -> list[Extension]:
    global _extensions
    out: list[Extension] = []
    os.makedirs(ADDONS_DIR, exist_ok=True)

    for name in sorted(os.listdir(ADDONS_DIR)):
        ext_path = os.path.join(ADDONS_DIR, name)
        if not (os.path.isdir(ext_path) and '__init__.py' in os.listdir(ext_path)):
            continue
        try:
            check_requirements(os.path.join(ext_path, 'requirements.txt'))
            py_mod = importlib.import_module(f'{ADDONS_PKG}.{name}')
            out.append(_load_addon_from_module(py_mod, name))
        except Exception as e:
            logger.error('Ошибка загрузки расширения «%s»: %s', name, e)

    for name in sorted(os.listdir(ADDONS_DIR)):
        if not name.endswith('.py') or name == '__init__.py':
            continue
        ext_path = os.path.join(ADDONS_DIR, name)
        if not os.path.isfile(ext_path):
            continue
        mod_name = name[:-3]
        try:
            check_requirements(os.path.join(ADDONS_DIR, f'{mod_name}.requirements.txt'))
            py_mod = importlib.import_module(f'{ADDONS_PKG}.{mod_name}')
            out.append(_load_addon_from_module(py_mod, mod_name))
        except Exception as e:
            logger.error('Ошибка загрузки расширения «%s»: %s', mod_name, e)

    return out


def _ext_count_str(count: int) -> str:
    word = plural(count, 'расширение', 'расширения', 'расширений')
    return f'Подключено {C_BRIGHT}{count}{Fore.RESET} {word}'


async def activate_extensions(extensions: list[Extension]) -> None:
    global _extensions
    disabled = _disabled_names()
    for ext in extensions:
        if ext._dir_name in disabled:
            logger.info('Расширение «%s» выключено в панели — не подключаю', ext.meta.name)
            continue
        try:
            await _enable_extension(ext)
        except Exception as e:
            logger.error('Ошибка подключения расширения «%s»: %s', ext.meta.name, e)
    connected = [e for e in _extensions if e.enabled]
    if connected:
        names = ', '.join(
            f'{C_BRIGHT}{e.meta.name}{Fore.RESET} {C_DIM}{e.meta.version}{Fore.RESET}'
            for e in connected
        )
        logger.info('%s: %s', _ext_count_str(len(connected)), names)
