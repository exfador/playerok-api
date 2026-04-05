import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any


@dataclass
class _DbFile:
    name:    str
    path:    str
    default: Any


_USERS  = _DbFile('initialized_users',  'db/initialized_users.json',  [])
_ITEMS  = _DbFile('saved_items',         'db/saved_items.json',         [])
_EVENTS = _DbFile('latest_events_times', 'db/latest_events_times.json', {'auto_bump_items': None})
_STATS  = _DbFile('stats',               'db/stats.json',               {'deals_completed': 0, 'deals_refunded': 0, 'earned_money': 0})

_ALL: list[_DbFile] = [_USERS, _ITEMS, _EVENTS, _STATS]


def _read(path: str, default: Any) -> Any:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding='utf-8') as fh:
            content = fh.read()
        if content.strip():
            return json.loads(content)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    _write(path, default)
    return default


def _write(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class AppDb:

    @staticmethod
    def get(name: str, data: list[_DbFile] = _ALL) -> Any:
        entry = next((d for d in data if d.name == name), None)
        if entry is None:
            return None
        return _read(entry.path, entry.default)

    @staticmethod
    def set(name: str, new: Any, data: list[_DbFile] = _ALL) -> None:
        entry = next((d for d in data if d.name == name), None)
        if entry is not None:
            _write(entry.path, new)
