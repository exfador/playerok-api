import asyncio
import copy
import uuid
from types import SimpleNamespace

import pytest

from lib import ext
from lib.custom_commands import cc_find_by_id, cc_get_items


@pytest.fixture
def memory_db(monkeypatch):
    import lib.db as db
    store = {}
    monkeypatch.setattr(db.AppDb, "get", staticmethod(lambda name, *a: copy.deepcopy(store.get(name))))
    monkeypatch.setattr(db.AppDb, "set", staticmethod(lambda name, value, *a: store.__setitem__(name, copy.deepcopy(value))))
    return store


def make_ext(name):
    meta = ext.ExtMeta("p", "1.0", name, "d", "a", "l")
    return ext.Extension(uuid=uuid.uuid4(), enabled=False, meta=meta, evt_wire={}, mkt_wire={}, bot_paths=[], _dir_name=name)


def test_disabled_extension_stays_off_after_restart(memory_db, monkeypatch):
    first, second = make_ext("alpha"), make_ext("beta")
    ext.register_extensions([first, second])
    asyncio.run(ext.activate_extensions([first, second]))
    assert first.enabled and second.enabled
    asyncio.run(ext.stop_extension(second.uuid))
    assert memory_db["ext_state"] == {"disabled": ["beta"]}
    restarted = [make_ext("alpha"), make_ext("beta")]
    ext.register_extensions(restarted)
    asyncio.run(ext.activate_extensions(restarted))
    assert [e.enabled for e in restarted] == [True, False]
    asyncio.run(ext.start_extension(restarted[1].uuid))
    assert memory_db["ext_state"] == {"disabled": []}
    ext.register_extensions([])


@pytest.mark.parametrize("count,word", [(1, "расширение"), (2, "расширения"), (5, "расширений"), (11, "расширений"),
                                        (12, "расширений"), (21, "расширение"), (22, "расширения"), (111, "расширений")])
def test_extension_count_is_declined_correctly(count, word):
    assert ext._ext_count_str(count).endswith(word)


def test_legacy_commands_keep_stable_ids():
    raw = {"продавец": ["Сейчас позову"], "!помощь": ["Пишите сюда"]}
    first, second = cc_get_items(raw), cc_get_items(raw)
    assert [c["id"] for c in first] == [c["id"] for c in second]
    assert cc_find_by_id(second, first[0]["id"])["trigger"] == "!продавец"
