import re

from lib.consts import ACCENT_COLOR, VERSION
from lib.consts import C_PRIMARY, C_SUCCESS, C_WARNING, C_ERROR
from lib.consts import C_DIM, C_TEXT, C_BRIGHT, C_HIGHLIGHT
from lib.util import set_console_title, halt, spawn_async
from lib.util import draw_box, iso_to_display_str
from lib.bus import wire, wire_mkt, graft, prune, graft_mkt, prune_mkt, fire, fire_mkt
from lib.cfg import DATA, AppConf as cfg
from lib.custom_commands import cc_get_items, cc_find_by_trigger
from lib.db import AppDb as db


def _norm_title(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').lower().replace('ё', 'е')).strip()


def clean_phrases(phrases) -> list[str]:
    if isinstance(phrases, str):
        phrases = phrases.split(',')
    return [str(p).strip() for p in (phrases or []) if str(p).strip()]


def phrase_in_title(name: str, phrase: str) -> bool:
    n, p = _norm_title(name), _norm_title(phrase)
    if not n or not p:
        return False
    if n == p:
        return True
    left = r'(?<!\d)' if p[0].isdigit() else ''
    right = r'(?!\d)' if p[-1].isdigit() else ''
    return re.search(left + re.escape(p) + right, n) is not None


def best_phrase_length(name: str, phrases) -> int:
    return max((len(_norm_title(p)) for p in clean_phrases(phrases) if phrase_in_title(name, p)), default=0)


def _title_matches_groups(name: str, groups: list | None) -> bool:
    if not name or not groups:
        return False
    return any(best_phrase_length(name, grp) for grp in groups if grp)


def best_rule_index(name: str, rules: list, key: str = 'keyphrases') -> int | None:
    best_index, best_len = None, 0
    for index, rule in enumerate(rules or []):
        if not isinstance(rule, dict):
            continue
        length = best_phrase_length(name, rule.get(key))
        if length > best_len:
            best_index, best_len = index, length
    return best_index
