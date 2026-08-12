import os
import json
import copy
import hashlib
import hmac
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def hash_password(plain: str) -> str:
    iterations = 310_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt, iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'


def verify_password(plain: str, hashed: str) -> bool:
    try:
        if hashed.startswith('pbkdf2_sha256$'):
            _, raw_iterations, raw_salt, expected = hashed.split('$', 3)
            actual = hashlib.pbkdf2_hmac(
                'sha256', plain.encode('utf-8'), bytes.fromhex(raw_salt), int(raw_iterations),
            ).hex()
            return hmac.compare_digest(actual, expected)
        legacy = hashlib.sha256(plain.encode('utf-8')).hexdigest()
        return hmac.compare_digest(legacy, hashed)
    except (TypeError, ValueError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    return not isinstance(hashed, str) or not hashed.startswith('pbkdf2_sha256$310000$')


@dataclass
class _CfgFile:
    name:         str
    path:         str
    need_restore: bool
    default:      Any = field(default_factory=dict)


_DEFAULTS: dict[str, Any] = {
    'account': {
        'token': '', 'cookies': '', 'ddg5': '',
        'user_agent': '', 'proxy': '',
        'proxy_prompt_ok': False, 'user_agent_prompt_ok': False,
        'cookies_prompt_ok': False,
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
            'update': True, 'broadcast': True,
        },
    },
    'updater': {'enabled': True, 'interval_sec': 3600, 'auto_update': False, 'notify': True},
    'broadcast': {'enabled': True, 'interval_sec': 1800, 'source': 'https://api.github.com/gists/89e52dbb3ca81aee82b6a3d8b51b55e2'},
    'logs':    {'max_mb': 300},
    'debug':   {'verbose': False},
    'display': {'timezone': ''},
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _project_path(relative_path: str) -> str:
    return str(_PROJECT_ROOT / relative_path)


_CFG = _CfgFile('config',             _project_path('conf/config.json'),             True,  _DEFAULTS)
_MSG = _CfgFile('messages',           _project_path('conf/messages.json'),           False, {})
_CC  = _CfgFile('custom_commands',    _project_path('conf/custom_commands.json'),    False, {'items': []})
_AD  = _CfgFile('auto_deliveries',    _project_path('conf/auto_deliveries.json'),    False, [])
_ARI = _CfgFile('auto_restore_items', _project_path('conf/auto_restore_items.json'), False, {'included': []})
_ACD = _CfgFile('auto_complete_deals',_project_path('conf/auto_complete_deals.json'),False, {'included': []})
_ABI = _CfgFile('auto_bump_items',    _project_path('conf/auto_bump_items.json'),    False, {'included': [], 'excluded': []})

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


def _backup_corrupt(path: str) -> None:
    backup = path + '.corrupt.bak'
    suffix = 1
    while os.path.exists(backup):
        backup = f'{path}.corrupt.bak.{suffix}'
        suffix += 1
    try:
        os.replace(path, backup)
    except OSError:
        pass


def _load(path: str, default: Any, need_restore: bool = True) -> Any:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = None
    try:
        with open(path, encoding='utf-8') as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raw = None
    except json.JSONDecodeError:
        _backup_corrupt(path)
        raw = None
    except OSError:
        raw = None

    if raw is not None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    if raw is None:
        raw = copy.deepcopy(default)
        _save(path, raw)
        return raw

    if isinstance(default, dict) and not isinstance(raw, dict):
        _backup_corrupt(path)
        fresh = copy.deepcopy(default)
        _save(path, fresh)
        return fresh
    if isinstance(default, list) and not isinstance(raw, list):
        _backup_corrupt(path)
        fresh = copy.deepcopy(default)
        _save(path, fresh)
        return fresh

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
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
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
