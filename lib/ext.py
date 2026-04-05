import os
import sys
import importlib
import uuid
from uuid import UUID
from colorama import Fore
from dataclasses import dataclass
from logging import getLogger
from lib.consts import C_BRIGHT, C_DIM
from lib.bus import graft, prune, graft_mkt, prune_mkt, fire
from lib.util import check_requirements

logger = getLogger('cxh.ext')
ADDONS_DIR = 'ext'
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


async def start_extension(ext_uuid: UUID) -> bool:
    try:
        ext = find_extension(ext_uuid)
        await _enable_extension(ext)
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


def _attach_ext_routes_before_cmd(main_router, routes: list) -> None:
    from ctrl.cmd import router as cmd_router
    try:
        cmd_idx = main_router.sub_routers.index(cmd_router)
    except ValueError:
        cmd_idx = len(main_router.sub_routers)
    for i, r in enumerate(routes):
        if r.parent_router is not None:
            _detach_subrouter(r)
        main_router.sub_routers.insert(cmd_idx + i, r)
        r._parent_router = main_router


def _replace_extension_tg_routers(old_routes: list, new_routes: list) -> None:
    from ctrl import router as main_rt
    from ctrl.panel import get_panel

    panel = get_panel()
    dp = getattr(panel, 'dp', None) if panel else None
    if dp is not None and main_rt.parent_router is dp:
        for r in old_routes:
            _detach_subrouter(r)
        try:
            main_idx = dp.sub_routers.index(main_rt)
        except ValueError:
            main_idx = len(dp.sub_routers)
        for i, r in enumerate(new_routes):
            if r.parent_router is not None:
                _detach_subrouter(r)
            dp.sub_routers.insert(main_idx + i, r)
            r._parent_router = dp
        return
    for r in old_routes:
        _detach_subrouter(r)
    _attach_ext_routes_before_cmd(main_rt, new_routes)


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
    last = int(str(count)[-1])
    if last == 1:
        return f'Подключено {C_BRIGHT}{count}{Fore.RESET} расширение'
    elif 2 <= last <= 4:
        return f'Подключено {C_BRIGHT}{count}{Fore.RESET} расширения'
    return f'Подключено {C_BRIGHT}{count}{Fore.RESET} расширений'


async def activate_extensions(extensions: list[Extension]) -> None:
    global _extensions
    for ext in extensions:
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
