from __future__ import annotations


def get_account():
    from bot.core import active_engine
    eng = active_engine()
    if eng is not None:
        return eng.account
    raise RuntimeError('Нет активного подключения Playerok')
