import os
import json
import copy
import hashlib
import tempfile
from dataclasses import dataclass


def hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode('utf-8')).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode('utf-8')).hexdigest() == hashed


@dataclass
class _CfgFile:
    name: str
    path: str
    need_restore: bool
    default: list | dict


_CFG = _CfgFile(name='config', path='conf/config.json', need_restore=True, default={'account': {'token': '', 'user_agent': '', 'proxy': '', 'timeout': 30, 'listener_delay': None}, 'bot': {'token': '', 'proxy': '', 'password_hash': '', 'admins': []}, 'features': {'watermark': {'enabled': True, 'text': 'CXH Playerok', 'position': 'end'}, 'read_chat': True, 'greet': True, 'commands': True, 'deliveries': True}, 'auto': {'restore': {'sold': True, 'expired': False, 'all': True, 'poll': {'enabled': False, 'interval': 300}}, 'confirm': {'enabled': False, 'all': True}, 'bump': {'enabled': False, 'interval': 3600, 'all': False}}, 'alerts': {'enabled': True, 'on': {'message': True, 'system': True, 'deal': True, 'review': True, 'problem': True, 'deal_changed': True, 'restore': True, 'bump': True}}, 'logs': {'max_mb': 300}, 'debug': {'verbose': False}, 'display': {'timezone': ''}})
_MSG = _CfgFile(name='messages', path='conf/messages.json', need_restore=False, default={})
_CC = _CfgFile(name='custom_commands', path='conf/custom_commands.json', need_restore=False, default={'items': []})
_AD = _CfgFile(name='auto_deliveries', path='conf/auto_deliveries.json', need_restore=False, default=[])
_ARI = _CfgFile(name='auto_restore_items', path='conf/auto_restore_items.json', need_restore=False, default={'included': []})
_ACD = _CfgFile(name='auto_complete_deals', path='conf/auto_complete_deals.json', need_restore=False, default={'included': []})
_ABI = _CfgFile(name='auto_bump_items', path='conf/auto_bump_items.json', need_restore=False, default={'included': [], 'excluded': []})
FILES = [_CFG, _MSG, _CC, _AD, _ARI, _ACD, _ABI]
DATA = FILES


def _validate(cfg: dict, default: dict) -> bool:
    for k, v in default.items():
        if k not in cfg:
            return False
        if type(cfg[k]) is not type(v):
            return False
        if isinstance(v, dict) and isinstance(cfg[k], dict):
            if not _validate(cfg[k], v):
                return False
    return True


def _restore(cfg: dict, default: dict) -> dict:
    cfg = copy.deepcopy(cfg)

    def _fill(c, d):
        for k, v in dict(d).items():
            if k not in c:
                c[k] = v
            elif c[k] is None:
                pass
            elif type(v) is not type(c[k]):
                c[k] = v
            elif isinstance(v, dict) and isinstance(c[k], dict):
                _fill(c[k], v)
        return c
    return _fill(cfg, default)


def _load(path: str, default: dict, need_restore: bool = True) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if need_restore:
            new = _restore(cfg, default)
            if cfg != new:
                cfg = new
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        cfg = copy.deepcopy(default)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    finally:
        return cfg


def _save(path: str, new: dict):
    d = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=d, delete=False) as tmp:
        json.dump(new, tmp, ensure_ascii=False, indent=4)
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp.name, path)


class ConfigShelf:

    @staticmethod
    def get(name: str, data: list[_CfgFile] = FILES) -> dict | list | None:
        try:
            f = next((x for x in data if x.name == name))
            return _load(f.path, f.default, f.need_restore)
        except Exception:
            return None

    @staticmethod
    def set(name: str, new: list | dict, data: list[_CfgFile] = FILES):
        try:
            f = next((x for x in data if x.name == name))
            _save(f.path, new)
        except Exception:
            pass
