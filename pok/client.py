from __future__ import annotations


def get_account():
    from bot.core import active_engine
    eng = active_engine()
    if eng is None:
        raise RuntimeError('Движок не запущен')
    return eng.account
