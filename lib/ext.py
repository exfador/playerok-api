import os
import sys
import importlib
import uuid
from uuid import UUID
from colorama import Fore
from dataclasses import dataclass
from logging import getLogger
from lib.consts import C_BRIGHT, C_DIM
from lib.bus import attach_sys, attach_mkt, detach_sys, detach_mkt, dispatch
from lib.util import check_requirements

logger = getLogger('pl.ext')
ADDONS_DIR = 'ext'
ADDONS_PKG = 'ext'


@dataclass
class ExtMeta:
    prefix: str
    version: str
    name: str
    description: str
    authors: str
    links: str


@dataclass
class Extension:
    uuid: UUID
    enabled: bool
    meta: ExtMeta
    system_hooks: dict
    market_hooks: dict
    tg_routes: list
    _dir_name: str


_extensions: list[Extension] = []


def all_extensions():
    return _extensions


def register_extensions(extensions: list[Extension]):
    global _extensions
    _extensions = extensions


def _uuid_key(u: UUID | str) -> UUID:
    return u if isinstance(u, UUID) else UUID(str(u))


def find_extension(ext_uuid: UUID | str) -> Extension | None:
    try:
        key = _uuid_key(ext_uuid)
        return [e for e in _extensions if e.uuid == key][0]
    except Exception:
        return None


async def _enable_extension(ext: Extension) -> bool:
    global _extensions
    attach_sys(ext.system_hooks)
    attach_mkt(ext.market_hooks)
    ext.enabled = True
    _extensions[_extensions.index(ext)] = ext
    handlers = ext.system_hooks.get('ON_EXT_LOAD', [])
    for handler in handlers:
        await dispatch('ON_EXT_LOAD', [ext], handler)


async def start_extension(ext_uuid: UUID) -> bool:
    try:
        ext = find_extension(ext_uuid)
        await _enable_extension(ext)
        logger.info(f'Расширение {C_BRIGHT}{ext.meta.name}{Fore.RESET} включено')
        return True
    except Exception as e:
        logger.error(f'Ошибка включения расширения {ext_uuid}: {e}')
        return False


async def _disable_extension(ext: Extension) -> bool:
    global _extensions
    detach_sys(ext.system_hooks)
    detach_mkt(ext.market_hooks)
    ext.enabled = False
    _extensions[_extensions.index(ext)] = ext
    handlers = ext.system_hooks.get('ON_EXT_UNLOAD', [])
    for handler in handlers:
        await dispatch('ON_EXT_UNLOAD', [ext], handler)


async def stop_extension(ext_uuid: UUID) -> bool:
    try:
        ext = find_extension(ext_uuid)
        await _disable_extension(ext)
        logger.info(f'Расширение {C_BRIGHT}{ext.meta.name}{Fore.RESET} выключено')
        return True
    except Exception as e:
        logger.error(f'Ошибка выключения расширения {ext_uuid}: {e}')
        return False


async def refresh_extension(ext_uuid: UUID | str):
    try:
        ext = find_extension(_uuid_key(ext_uuid))
        await _disable_extension(ext)
        mod_key = f'{ADDONS_PKG}.{ext._dir_name}'
        if mod_key in sys.modules:
            del sys.modules[mod_key]
        importlib.import_module(mod_key)
        await _enable_extension(ext)
        logger.info(f'Расширение {C_BRIGHT}{ext.meta.name}{Fore.RESET} перезагружено')
        return True
    except Exception as e:
        logger.error(f'Ошибка перезагрузки расширения {ext_uuid}: {e}')
        return False


def discover_extensions() -> list[Extension]:
    global _extensions
    out: list[Extension] = []
    os.makedirs(ADDONS_DIR, exist_ok=True)
    for name in os.listdir(ADDONS_DIR):
        system_hooks = {}
        market_hooks = {}
        tg_routes = []
        ext_path = os.path.join(ADDONS_DIR, name)
        if os.path.isdir(ext_path) and '__init__.py' in os.listdir(ext_path):
            try:
                check_requirements(os.path.join(ext_path, 'requirements.txt'))
                py_mod = importlib.import_module(f'{ADDONS_PKG}.{name}')
                if hasattr(py_mod, 'SYSTEM_HOOKS'):
                    for key, funcs in py_mod.SYSTEM_HOOKS.items():
                        system_hooks.setdefault(key, []).extend(funcs)
                if hasattr(py_mod, 'MARKET_HOOKS'):
                    for key, funcs in py_mod.MARKET_HOOKS.items():
                        market_hooks.setdefault(key, []).extend(funcs)
                if hasattr(py_mod, 'TG_ROUTES'):
                    tg_routes.extend(py_mod.TG_ROUTES)
                ext_data = Extension(
                    uuid.uuid4(),
                    enabled=False,
                    meta=ExtMeta(py_mod.PREFIX, py_mod.VERSION, py_mod.NAME, py_mod.DESCRIPTION, py_mod.AUTHORS, py_mod.LINKS),
                    system_hooks=system_hooks,
                    market_hooks=market_hooks,
                    tg_routes=tg_routes,
                    _dir_name=name,
                )
                out.append(ext_data)
            except Exception as e:
                logger.error(f'Ошибка загрузки расширения «{name}»: {e}')
    for name in os.listdir(ADDONS_DIR):
        if not name.endswith('.py') or name in ('__init__.py',):
            continue
        ext_path = os.path.join(ADDONS_DIR, name)
        if not os.path.isfile(ext_path):
            continue
        mod_name = name[:-3]
        try:
            check_requirements(os.path.join(ADDONS_DIR, f'{mod_name}.requirements.txt'))
            py_mod = importlib.import_module(f'{ADDONS_PKG}.{mod_name}')
            system_hooks = {}
            market_hooks = {}
            tg_routes = []
            if hasattr(py_mod, 'SYSTEM_HOOKS'):
                for key, funcs in py_mod.SYSTEM_HOOKS.items():
                    system_hooks.setdefault(key, []).extend(funcs)
            if hasattr(py_mod, 'MARKET_HOOKS'):
                for key, funcs in py_mod.MARKET_HOOKS.items():
                    market_hooks.setdefault(key, []).extend(funcs)
            if hasattr(py_mod, 'TG_ROUTES'):
                tg_routes.extend(py_mod.TG_ROUTES)
            ext_data = Extension(
                uuid.uuid4(),
                enabled=False,
                meta=ExtMeta(py_mod.PREFIX, py_mod.VERSION, py_mod.NAME, py_mod.DESCRIPTION, py_mod.AUTHORS, py_mod.LINKS),
                system_hooks=system_hooks,
                market_hooks=market_hooks,
                tg_routes=tg_routes,
                _dir_name=mod_name,
            )
            out.append(ext_data)
        except Exception as e:
            logger.error(f'Ошибка загрузки расширения «{mod_name}»: {e}')
    return out


def _ext_count_str(count: int) -> str:
    last = int(str(count)[-1])
    if last == 1:
        return f'Подключено {C_BRIGHT}{count}{Fore.RESET} расширение'
    elif 2 <= last <= 4:
        return f'Подключено {C_BRIGHT}{count}{Fore.RESET} расширения'
    return f'Подключено {C_BRIGHT}{count}{Fore.RESET} расширений'


async def activate_extensions(extensions: list[Extension]):
    global _extensions
    for ext in extensions:
        try:
            await _enable_extension(ext)
        except Exception as e:
            logger.error(f'Ошибка подключения расширения «{ext.meta.name}»: {e}')
    connected = [e for e in _extensions if e.enabled]
    if connected:
        names = ', '.join((f'{C_BRIGHT}{e.meta.name}{Fore.RESET} {C_DIM}{e.meta.version}{Fore.RESET}' for e in connected))
        logger.info(f'{_ext_count_str(len(connected))}: {names}')
