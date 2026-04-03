import os
import sys
import importlib
import uuid
from uuid import UUID
from colorama import Fore
from dataclasses import dataclass
from logging import getLogger
from keel.tone import C_BRIGHT, C_DIM
from keel.relay import merge_strata, merge_ingress, prune_strata, prune_ingress, broadcast
from keel.kit import check_requirements

logger = getLogger('keel.graft')
ADDONS_DIR = 'ext'
ADDONS_PKG = 'ext'


@dataclass
class GraftCard:
    prefix: str
    version: str
    name: str
    description: str
    authors: str
    links: str


@dataclass
class Graft:
    uuid: UUID
    enabled: bool
    meta: GraftCard
    strata_bind: dict
    ingress_bind: dict
    tg_mounts: list
    _dir_name: str


_extensions: list[Graft] = []


def all_grafts():
    return _extensions


def publish_grafts(extensions: list[Graft]):
    global _extensions
    _extensions = extensions


def _uuid_key(u: UUID | str) -> UUID:
    return u if isinstance(u, UUID) else UUID(str(u))


def seek_graft(ext_uuid: UUID | str) -> Graft | None:
    try:
        key = _uuid_key(ext_uuid)
        return [e for e in _extensions if e.uuid == key][0]
    except Exception:
        return None


async def _arm_graft(ext: Graft) -> bool:
    global _extensions
    merge_strata(ext.strata_bind)
    merge_ingress(ext.ingress_bind)
    ext.enabled = True
    _extensions[_extensions.index(ext)] = ext
    handlers = ext.strata_bind.get('GRAFT_ARM', [])
    for handler in handlers:
        await broadcast('GRAFT_ARM', [ext], handler)


async def arm_graft(ext_uuid: UUID) -> bool:
    try:
        ext = seek_graft(ext_uuid)
        await _arm_graft(ext)
        logger.info(f'Расширение {C_BRIGHT}{ext.meta.name}{Fore.RESET} включено')
        return True
    except Exception as e:
        logger.error(f'Ошибка включения расширения {ext_uuid}: {e}')
        return False


async def _disarm_graft(ext: Graft) -> bool:
    global _extensions
    prune_strata(ext.strata_bind)
    prune_ingress(ext.ingress_bind)
    ext.enabled = False
    _extensions[_extensions.index(ext)] = ext
    handlers = ext.strata_bind.get('GRAFT_DISARM', [])
    for handler in handlers:
        await broadcast('GRAFT_DISARM', [ext], handler)


async def disarm_graft(ext_uuid: UUID) -> bool:
    try:
        ext = seek_graft(ext_uuid)
        await _disarm_graft(ext)
        logger.info(f'Расширение {C_BRIGHT}{ext.meta.name}{Fore.RESET} выключено')
        return True
    except Exception as e:
        logger.error(f'Ошибка выключения расширения {ext_uuid}: {e}')
        return False


async def rearm_graft(ext_uuid: UUID | str):
    try:
        ext = seek_graft(_uuid_key(ext_uuid))
        await _disarm_graft(ext)
        mod_key = f'{ADDONS_PKG}.{ext._dir_name}'
        if mod_key in sys.modules:
            del sys.modules[mod_key]
        importlib.import_module(mod_key)
        await _arm_graft(ext)
        logger.info(f'Расширение {C_BRIGHT}{ext.meta.name}{Fore.RESET} перезагружено')
        return True
    except Exception as e:
        logger.error(f'Ошибка перезагрузки расширения {ext_uuid}: {e}')
        return False


def harvest_grafts() -> list[Graft]:
    global _extensions
    out: list[Graft] = []
    os.makedirs(ADDONS_DIR, exist_ok=True)
    for name in os.listdir(ADDONS_DIR):
        strata_bind = {}
        ingress_bind = {}
        tg_mounts = []
        ext_path = os.path.join(ADDONS_DIR, name)
        if os.path.isdir(ext_path) and '__init__.py' in os.listdir(ext_path):
            try:
                check_requirements(os.path.join(ext_path, 'requirements.txt'))
                py_mod = importlib.import_module(f'{ADDONS_PKG}.{name}')
                if hasattr(py_mod, 'STRATA_TAPS'):
                    for key, funcs in py_mod.STRATA_TAPS.items():
                        strata_bind.setdefault(key, []).extend(funcs)
                if hasattr(py_mod, 'INGRESS_TAPS'):
                    for key, funcs in py_mod.INGRESS_TAPS.items():
                        ingress_bind.setdefault(key, []).extend(funcs)
                if hasattr(py_mod, 'TG_MOUNT_POINTS'):
                    tg_mounts.extend(py_mod.TG_MOUNT_POINTS)
                ext_data = Graft(
                    uuid.uuid4(),
                    enabled=False,
                    meta=GraftCard(py_mod.PREFIX, py_mod.VERSION, py_mod.NAME, py_mod.DESCRIPTION, py_mod.AUTHORS, py_mod.LINKS),
                    strata_bind=strata_bind,
                    ingress_bind=ingress_bind,
                    tg_mounts=tg_mounts,
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
            strata_bind = {}
            ingress_bind = {}
            tg_mounts = []
            if hasattr(py_mod, 'STRATA_TAPS'):
                for key, funcs in py_mod.STRATA_TAPS.items():
                    strata_bind.setdefault(key, []).extend(funcs)
            if hasattr(py_mod, 'INGRESS_TAPS'):
                for key, funcs in py_mod.INGRESS_TAPS.items():
                    ingress_bind.setdefault(key, []).extend(funcs)
            if hasattr(py_mod, 'TG_MOUNT_POINTS'):
                tg_mounts.extend(py_mod.TG_MOUNT_POINTS)
            ext_data = Graft(
                uuid.uuid4(),
                enabled=False,
                meta=GraftCard(py_mod.PREFIX, py_mod.VERSION, py_mod.NAME, py_mod.DESCRIPTION, py_mod.AUTHORS, py_mod.LINKS),
                strata_bind=strata_bind,
                ingress_bind=ingress_bind,
                tg_mounts=tg_mounts,
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


async def ignite_grafts(extensions: list[Graft]):
    global _extensions
    for ext in extensions:
        try:
            await _arm_graft(ext)
        except Exception as e:
            logger.error(f'Ошибка подключения расширения «{ext.meta.name}»: {e}')
    connected = [e for e in _extensions if e.enabled]
    if connected:
        names = ', '.join((f'{C_BRIGHT}{e.meta.name}{Fore.RESET} {C_DIM}{e.meta.version}{Fore.RESET}' for e in connected))
        logger.info(f'{_ext_count_str(len(connected))}: {names}')
