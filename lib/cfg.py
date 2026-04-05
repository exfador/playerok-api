import os
import json
import copy
import hashlib
import tempfile
from dataclasses import dataclass, field
from typing import Any


def hash_password(plain: str) -> str:
    h = hashlib.new('sha256')
    h.update(plain.encode('utf-8'))
    return h.hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


@dataclass
class _CfgFile:
    name:         str
    path:         str
    need_restore: bool
    default:      Any = field(default_factory=dict)


_DEFAULTS: dict[str, Any] = {
    'account': {
        'token': '', 'user_agent': '', 'proxy': '',
        'proxy_prompt_ok': False, 'user_agent_prompt_ok': False,
        'timeout': 30, 'listener_delay': None,
    },
    'bot': {
        'token': '', 'proxy': '', 'proxy_prompt_ok': False,
        'password_hash': '', 'admins': [],
    },
    'features': {
        'watermark': {'enabled': True, 'text': 'CXH Playerok', 'position': 'end'},
        'read_chat': True, 'greet': True, 'commands': True, 'deliveries': True,
    },
    'auto': {
        'restore': {
            'sold': True, 'expired': False, 'all': True,
            'premium': False,
            'poll': {'enabled': False, 'interval': 300},
        },
        'confirm': {'enabled': False, 'all': True},
        'bump':    {'enabled': False, 'interval': 3600, 'all': False},
    },
    'alerts': {
        'enabled': True,
        'on': {
            'message': True, 'system': True, 'deal': True, 'review': True,
            'problem': True, 'deal_changed': True, 'restore': True, 'bump': True, 'startup': True,
        },
    },
    'logs':    {'max_mb': 300},
    'debug':   {'verbose': False},
    'display': {'timezone': ''},
}

_CFG = _CfgFile('config',             'conf/config.json',             True,  _DEFAULTS)
_MSG = _CfgFile('messages',           'conf/messages.json',           False, {})
_CC  = _CfgFile('custom_commands',    'conf/custom_commands.json',    False, {'items': []})
_AD  = _CfgFile('auto_deliveries',    'conf/auto_deliveries.json',    False, [])
_ARI = _CfgFile('auto_restore_items', 'conf/auto_restore_items.json', False, {'included': []})
_ACD = _CfgFile('auto_complete_deals','conf/auto_complete_deals.json',False, {'included': []})
_ABI = _CfgFile('auto_bump_items',    'conf/auto_bump_items.json',    False, {'included': [], 'excluded': []})

_STORE: dict[str, _CfgFile] = {
    _CFG.name: _CFG, _MSG.name: _MSG, _CC.name: _CC,
    _AD.name:  _AD,  _ARI.name: _ARI, _ACD.name: _ACD, _ABI.name: _ABI,
}
DATA  = _STORE
FILES = list(_STORE.values())


def _validate(cfg: dict, default: dict) -> bool:
    for key, expected in default.items():
        actual = cfg.get(key)
        if actual is None and key not in cfg:
            return False
        if type(actual) is not type(expected):
            return False
        if isinstance(expected, dict) and not _validate(actual, expected):
            return False
    return True


def _restore(current: dict, blueprint: dict) -> dict:
    out = copy.deepcopy(current)
    for key, default_val in blueprint.items():
        if key not in out:
            out[key] = copy.deepcopy(default_val)
        elif out[key] is None:
            pass
        elif type(out[key]) != type(default_val):
            out[key] = copy.deepcopy(default_val)
        elif isinstance(default_val, dict):
            out[key] = _restore(out[key], default_val)
    return out


def _load(path: str, default: Any, need_restore: bool = True) -> Any:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = None
    try:
        with open(path, encoding='utf-8') as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = None

    if raw is None:
        raw = copy.deepcopy(default)
        _save(path, raw)
        return raw

    if need_restore and isinstance(raw, dict) and isinstance(default, dict):
        merged = _restore(raw, default)
        if merged != raw:
            _save(path, merged)
            return merged

    return raw


def _save(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class AppConf:

    @staticmethod
    def read(name: str, registry: dict | list = _STORE) -> Any:
        if isinstance(registry, dict):
            entry = registry.get(name)
        else:
            entry = next((f for f in registry if f.name == name), None)
        if entry is None:
            return None
        return _load(entry.path, entry.default, entry.need_restore)

    @staticmethod
    def write(name: str, value: Any, registry: dict | list = _STORE) -> None:
        if isinstance(registry, dict):
            entry = registry.get(name)
        else:
            entry = next((f for f in registry if f.name == name), None)
        if entry is not None:
            _save(entry.path, value)
