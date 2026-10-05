import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import bot.core as core
from ctrl import actions
from lib.stock import DELIVERY_LOCK, find_good, good_tag


class Store:
    def __init__(self, rules):
        self.rules = rules
        self.locked_reads = []

    def read(self, name, *args):
        assert name == "auto_deliveries"
        self.locked_reads.append(DELIVERY_LOCK._is_owned())
        return copy.deepcopy(self.rules)

    def write(self, name, value):
        assert DELIVERY_LOCK._is_owned()
        self.rules = copy.deepcopy(value)


@pytest.fixture
def store(monkeypatch):
    shared = Store([{"keyphrases": ["Steam"], "piece": True, "goods": ["KEY-A", "KEY-B", "KEY-C"]}])
    monkeypatch.setattr(actions.cfg, "read", shared.read)
    monkeypatch.setattr(actions.cfg, "write", shared.write)
    monkeypatch.setattr(actions, "hx_026", AsyncMock())
    monkeypatch.setattr(actions, "hx_001", AsyncMock())
    monkeypatch.setattr(actions, "emit_overlay", AsyncMock())
    return shared


def make_state(**values):
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=10, user_id=10))
    asyncio.run(state.update_data(**values))
    return state


def drop(index, good):
    return SimpleNamespace(index=index, tag=good_tag(good))


def make_callback():
    return SimpleNamespace(message=SimpleNamespace(message_id=1, chat=SimpleNamespace(id=10)), answer=AsyncMock())


def test_drop_removes_the_shown_key_even_after_a_sale_shifted_the_list(store):
    state = make_state(auto_delivery_index=0, auto_delivery_keys=["Steam"])
    store.rules[0]["goods"] = ["KEY-B", "KEY-C"]
    asyncio.run(actions.hx_020(make_callback(), drop(2, "KEY-C"), state))
    assert store.rules[0]["goods"] == ["KEY-B"]


def test_drop_of_already_sold_key_changes_nothing(store):
    state = make_state(auto_delivery_index=0, auto_delivery_keys=["Steam"])
    store.rules[0]["goods"] = ["KEY-B", "KEY-C"]
    callback = make_callback()
    asyncio.run(actions.hx_020(callback, drop(0, "KEY-A"), state))
    assert store.rules[0]["goods"] == ["KEY-B", "KEY-C"]
    assert callback.answer.call_args.kwargs.get("show_alert") is True


def test_panel_reads_and_writes_stock_under_shared_lock(store):
    state = make_state(auto_delivery_index=0, auto_delivery_keys=["Steam"])
    asyncio.run(actions.hx_020(make_callback(), drop(1, "KEY-B"), state))
    assert store.locked_reads and all(store.locked_reads)
    assert store.rules[0]["goods"] == ["KEY-A", "KEY-C"]


def test_rule_delete_refuses_when_rule_was_replaced(store):
    state = make_state(auto_delivery_index=0, auto_delivery_keys=["Robux"])
    callback = make_callback()
    asyncio.run(actions.hx_018(callback, state))
    assert len(store.rules) == 1
    assert callback.answer.call_args.kwargs.get("show_alert") is True


def test_engine_uses_the_same_stock_lock(monkeypatch):
    monkeypatch.setattr(core, "db", SimpleNamespace(get=lambda k: [] if k != "latest_events_times" else {}, set=Mock()))
    monkeypatch.setattr(core.cfg, "read", lambda name, *a: {"account": {}} if name == "config" else ([] if name == "auto_deliveries" else {}))
    monkeypatch.setattr(core, "Conn", lambda **kw: SimpleNamespace(get=lambda: SimpleNamespace()))
    engine = core.MarketBridge()
    assert engine._delivery_lock is DELIVERY_LOCK


def test_phrase_drop_removes_shown_phrase_after_list_shift(monkeypatch):
    data = {"included": [["Steam"], ["Robux"], ["Telegram"]]}
    monkeypatch.setattr(actions.cfg, "read", lambda name: copy.deepcopy(data))
    monkeypatch.setattr(actions.cfg, "write", lambda name, value: data.update(value))
    data["included"].pop(0)
    assert actions._drop_tagged("auto_restore_items", "included", SimpleNamespace(index=2, tag=good_tag(["Telegram"])))
    assert data["included"] == [["Robux"]]
    assert not actions._drop_tagged("auto_restore_items", "included", SimpleNamespace(index=0, tag=good_tag(["Steam"])))
    assert not actions._drop_tagged("auto_restore_items", "included", SimpleNamespace(index=0, tag=""))
    assert data["included"] == [["Robux"]]


def test_own_purchase_does_not_start_restore(monkeypatch):
    started = []
    monkeypatch.setattr(core, "Thread", lambda **kw: SimpleNamespace(start=lambda: started.append(kw)))
    engine = object.__new__(core.MarketBridge)
    engine.account = SimpleNamespace(id="me")
    engine.config = {"auto": {"restore": {"sold": True}}}
    item = SimpleNamespace(id="item", keep_in_sale=False)
    asyncio.run(engine._on_paid(SimpleNamespace(deal=SimpleNamespace(id="d", user=SimpleNamespace(id="me"), item=item))))
    assert started == []
    asyncio.run(engine._on_paid(SimpleNamespace(deal=SimpleNamespace(id="d", user=SimpleNamespace(id="buyer"), item=item))))
    assert len(started) == 1


def test_find_good_prefers_exact_position_for_duplicates():
    goods = ["KEY-X", "KEY-Y", "KEY-X"]
    assert find_good(goods, 2, good_tag("KEY-X")) == 2
    assert find_good(goods, 1, good_tag("KEY-X")) == 0
    assert find_good(goods, 0, good_tag("KEY-Z")) is None
