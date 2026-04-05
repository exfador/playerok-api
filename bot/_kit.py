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
    return (text or '').lower().replace('ё', 'е').strip()


def _title_matches_groups(name: str, groups: list | None) -> bool:
    if not name or not groups:
        return False
    n = _norm_title(name)
    return any(
        _norm_title(phrase) and (_norm_title(phrase) in n or n == _norm_title(phrase))
        for grp in groups if grp
        for phrase in grp
    )
