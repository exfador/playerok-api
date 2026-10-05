from __future__ import annotations

import hashlib
import threading

DELIVERY_LOCK = threading.RLock()


def good_tag(good) -> str:
    return hashlib.sha256(str(good).encode('utf-8')).hexdigest()[:8]


def find_good(goods: list, index: int | None, tag: str) -> int | None:
    if index is not None and 0 <= index < len(goods) and good_tag(goods[index]) == tag:
        return index
    return next((position for position, good in enumerate(goods) if good_tag(good) == tag), None)
