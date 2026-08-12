import json
import os
import tempfile
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class _DbFile:
    name:    str
    path:    str
    default: Any


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _project_path(relative_path: str) -> str:
    return str(_PROJECT_ROOT / relative_path)


_USERS  = _DbFile('initialized_users',  _project_path('db/initialized_users.json'),  [])
_ITEMS  = _DbFile('saved_items',         _project_path('db/saved_items.json'),         [])
_EVENTS = _DbFile('latest_events_times', _project_path('db/latest_events_times.json'), {'auto_bump_items': None})
_STATS  = _DbFile('stats',               _project_path('db/stats.json'),               {'deals_completed': 0, 'deals_refunded': 0, 'earned_money': 0})
_UPD    = _DbFile('updater_state',       _project_path('db/updater_state.json'),       {'last_notified_tag': '', 'latest_tag': '', 'latest_html_url': '', 'latest_download_url': '', 'checked_at': ''})
_BCAST  = _DbFile('broadcast_state',     _project_path('db/broadcast_state.json'),     {'seen': [], 'checked_at': ''})

_ALL: list[_DbFile] = [_USERS, _ITEMS, _EVENTS, _STATS, _UPD, _BCAST]


def _read(path: str, default: Any) -> Any:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding='utf-8') as fh:
            content = fh.read()
        if content.strip():
            return json.loads(content)
    except json.JSONDecodeError:
        backup = path + '.corrupt.bak'
        suffix = 1
        while os.path.exists(backup):
            backup = f'{path}.corrupt.bak.{suffix}'
            suffix += 1
        try:
            os.replace(path, backup)
        except OSError:
            pass
    except (FileNotFoundError, OSError):
        pass
    value = copy.deepcopy(default)
    _write(path, value)
    return value


def _write(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
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
