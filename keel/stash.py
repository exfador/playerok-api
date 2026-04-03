import json
import os
from dataclasses import dataclass


@dataclass
class _DbFile:
    name: str
    path: str
    default: list | dict


_USERS = _DbFile(name='initialized_users', path='db/initialized_users.json', default=[])
_ITEMS = _DbFile(name='saved_items', path='db/saved_items.json', default=[])
_EVENTS = _DbFile(name='latest_events_times', path='db/latest_events_times.json', default={'auto_bump_items': None})
_STATS = _DbFile(name='stats', path='db/stats.json', default={'deals_completed': 0, 'deals_refunded': 0, 'earned_money': 0})
_ALL = [_USERS, _ITEMS, _EVENTS, _STATS]


def _read(path: str, default: dict | list) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default


def _write(path: str, new: dict | list):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(new, f, indent=4, ensure_ascii=False)


class StateStash:

    @staticmethod
    def get(name: str, data: list[_DbFile] = _ALL) -> dict | list | None:
        try:
            item = next((x for x in data if x.name == name))
            return _read(item.path, item.default)
        except Exception:
            return None

    @staticmethod
    def set(name: str, new: list | dict, data: list[_DbFile] = _ALL):
        try:
            item = next((x for x in data if x.name == name))
            _write(item.path, new)
        except Exception:
            pass
