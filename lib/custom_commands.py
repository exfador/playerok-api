from __future__ import annotations

import secrets
from typing import Any


KNOWN_EVENTS: dict[str, str] = {
    'call_seller': 'Вызов продавца в Telegram',
}


def cc_wrap_items(items: list[dict]) -> dict:
    return {'items': items}


def _ensure_item(d: dict) -> dict | None:
    if not isinstance(d, dict):
        return None
    tid = str(d.get('id') or '')
    tr  = str(d.get('trigger') or '').strip()
    if not (tid and tr):
        return None
    ev = d.get('events') if isinstance(d.get('events'), list) else []
    rl = [str(x) for x in (d.get('reply_lines') or []) if str(x).strip()]
    return {
        'id':          tid,
        'trigger':     tr,
        'events':      [str(e) for e in ev if e in KNOWN_EVENTS],
        'reply_lines': rl,
    }


def cc_get_items(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, dict) and isinstance(raw.get('items'), list):
        return [x for x in (_ensure_item(el) for el in raw['items'] if isinstance(el, dict)) if x]
    if isinstance(raw, dict):
        out: list[dict] = []
        for k, v in raw.items():
            if k == 'items':
                continue
            if isinstance(v, dict) and 'trigger' in v:
                x = _ensure_item(v)
                if x:
                    out.append(x)
            elif isinstance(v, list):
                trig = str(k).strip()
                if not trig.startswith('!'):
                    trig = f'!{trig}'
                out.append({
                    'id':          secrets.token_hex(6),
                    'trigger':     trig,
                    'events':      [],
                    'reply_lines': [str(x) for x in v],
                })
        return out
    return []


def cc_find_by_id(items: list[dict], cmd_id: str) -> dict | None:
    return next((it for it in items if it.get('id') == cmd_id), None)


def cc_find_by_trigger(items: list[dict], text: str) -> dict | None:
    t = text.strip().lower()
    return next((it for it in items if str(it.get('trigger', '')).strip().lower() == t), None)


def cc_trigger_taken(items: list[dict], trigger: str, exclude_id: str | None = None) -> bool:
    t = trigger.strip().lower()
    return any(
        str(it.get('trigger', '')).strip().lower() == t
        for it in items
        if not (exclude_id and it.get('id') == exclude_id)
    )


def cc_new_item(trigger: str) -> dict:
    tr = trigger.strip()
    if not tr.startswith('!'):
        tr = f'!{tr}'
    return {'id': secrets.token_hex(6), 'trigger': tr, 'events': [], 'reply_lines': []}


def cc_toggle_event(item: dict, event_id: str) -> None:
    if event_id not in KNOWN_EVENTS:
        return
    ev = item.setdefault('events', [])
    if event_id in ev:
        ev.remove(event_id)
    else:
        ev.append(event_id)


def cc_delete_item(items: list[dict], cmd_id: str) -> bool:
    before = len(items)
    items[:] = [it for it in items if it.get('id') != cmd_id]
    return len(items) < before


def cc_item_summary(item: dict, max_len: int = 36) -> str:
    parts = [KNOWN_EVENTS[e][:16] for e in (item.get('events') or []) if e in KNOWN_EVENTS]
    if item.get('reply_lines'):
        parts.append('текст')
    s = ' · '.join(parts) if parts else 'без действий'
    return s if len(s) <= max_len else s[:max_len - 1] + '…'
