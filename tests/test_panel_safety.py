import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import bot.core as core
from ctrl import actions
from pok.defs import DealStage


def make_state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=10, user_id=10))


def make_callback(message_id):
    return SimpleNamespace(message=SimpleNamespace(message_id=message_id, chat=SimpleNamespace(id=10)),
                           answer=AsyncMock(), bot=Mock(), id="cb")


@pytest.fixture
def engine(monkeypatch):
    account = SimpleNamespace(load_deal=Mock(return_value=SimpleNamespace(status=DealStage.PAID)), patch_deal=Mock())
    eng = SimpleNamespace(bot_account=account, _render_tpl=Mock(return_value="Привет"),
                          _room_by_alias=Mock(return_value=SimpleNamespace(id="chat-b")),
                          _push=Mock(return_value=SimpleNamespace(file=None)))
    monkeypatch.setattr(core, "live_bridge", lambda: eng)
    monkeypatch.setattr(actions, "emit_overlay", AsyncMock(return_value=None))
    return eng


def test_refund_confirmation_from_stale_message_is_rejected(engine):
    state = make_state()
    asyncio.run(state.update_data(deal_id="deal-B", deal_message_id=2))
    callback = make_callback(message_id=1)
    asyncio.run(actions.hx_067(callback, state))
    engine.bot_account.patch_deal.assert_not_called()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


def test_refund_confirmation_on_its_own_message_runs_once(engine):
    state = make_state()
    asyncio.run(state.update_data(deal_id="deal-B", deal_message_id=2))
    asyncio.run(actions.hx_067(make_callback(message_id=2), state))
    engine.bot_account.patch_deal.assert_called_once_with("deal-B", DealStage.ROLLED_BACK)
    asyncio.run(actions.hx_067(make_callback(message_id=2), state))
    assert engine.bot_account.patch_deal.call_count == 1


def test_template_from_stale_message_is_not_sent(engine):
    state = make_state()
    asyncio.run(state.update_data(username="buyer-B", tpl_pick_order=["greeting"], tpl_message_id=5))
    callback = make_callback(message_id=4)
    asyncio.run(actions.hx_060(callback, SimpleNamespace(idx=0), state))
    engine._push.assert_not_called()


def test_template_on_its_own_message_is_sent_to_that_buyer(engine):
    state = make_state()
    asyncio.run(state.update_data(username="buyer-B", tpl_pick_order=["greeting"], tpl_message_id=5))
    asyncio.run(actions.hx_060(make_callback(message_id=5), SimpleNamespace(idx=0), state))
    engine._room_by_alias.assert_called_once_with("buyer-B")
    engine._push.assert_called_once_with("chat-b", "Привет")


def test_item_payment_from_stale_screen_is_rejected(monkeypatch):
    from ctrl import items
    engine = SimpleNamespace(publish_or_boost=Mock(return_value=("published", None)))
    monkeypatch.setattr(items, "_engine", lambda: engine)
    monkeypatch.setattr(items, "emit_overlay", AsyncMock(return_value=None))
    state = make_state()
    asyncio.run(state.update_data(item_id="item-B", item_message_id=8, item_intent="published",
                                  item_tier={"id": "tier", "type": "PREMIUM", "price": 19}))
    callback = make_callback(message_id=7)
    asyncio.run(items.on_item_action(callback, SimpleNamespace(do="go"), state))
    engine.publish_or_boost.assert_not_called()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


def test_item_payment_cannot_run_twice_at_once(monkeypatch):
    from ctrl import items
    engine = SimpleNamespace(publish_or_boost=Mock(return_value=("published", None)))
    monkeypatch.setattr(items, "_engine", lambda: engine)
    monkeypatch.setattr(items, "emit_overlay", AsyncMock(return_value=None))
    monkeypatch.setattr(items, "_open_item", AsyncMock())
    state = make_state()
    asyncio.run(state.update_data(item_id="item-A", item_message_id=7, item_intent="published",
                                  item_tier={"id": "tier", "type": "PREMIUM", "price": 19}))
    items._PAID_IN_FLIGHT.add("item-A")
    try:
        asyncio.run(items.on_item_action(make_callback(message_id=7), SimpleNamespace(do="go"), state))
    finally:
        items._PAID_IN_FLIGHT.discard("item-A")
    engine.publish_or_boost.assert_not_called()
    asyncio.run(items.on_item_action(make_callback(message_id=7), SimpleNamespace(do="go"), state))
    engine.publish_or_boost.assert_called_once_with("item-A", "tier", False, "published")


def test_template_delete_from_stale_screen_keeps_both(monkeypatch):
    messages = {"tpl_a": {"enabled": True, "text": ["a"]}, "tpl_b": {"enabled": True, "text": ["b"]}}
    monkeypatch.setattr(actions.cfg, "read", lambda name: dict(messages))
    monkeypatch.setattr(actions.cfg, "write", lambda name, value: (messages.clear(), messages.update(value)))
    monkeypatch.setattr(actions, "emit_overlay", AsyncMock(return_value=None))
    monkeypatch.setattr(actions, "hx_063", AsyncMock())
    state = make_state()
    asyncio.run(state.update_data(message_id="tpl_a"))
    asyncio.run(actions.hx_011(make_callback(message_id=1), state))
    asyncio.run(state.update_data(message_id="tpl_b"))
    asyncio.run(actions.hx_011(make_callback(message_id=2), state))
    stale = make_callback(message_id=1)
    asyncio.run(actions.hx_025(stale, state))
    assert set(messages) == {"tpl_a", "tpl_b"}
    assert stale.answer.call_args.kwargs.get("show_alert") is True
    asyncio.run(actions.hx_025(make_callback(message_id=2), state))
    assert set(messages) == {"tpl_a"}


def test_token_only_update_keeps_cookie_string_consistent(monkeypatch):
    from ctrl import cmd
    store = {"config": {"account": {"cookies": "token=aaaa.bbbb.cccc; __ddg5_=x", "token": "aaaa.bbbb.cccc"}}}
    monkeypatch.setattr(cmd.cfg, "read", lambda name: __import__("copy").deepcopy(store[name]))
    monkeypatch.setattr(cmd.cfg, "write", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(cmd, "emit_overlay", AsyncMock())
    message = SimpleNamespace(text="dddd.eeee.ffff", delete=AsyncMock(), chat=SimpleNamespace(id=10))
    asyncio.run(cmd.rx_032(message, make_state()))
    account = store["config"]["account"]
    assert account["token"] == "dddd.eeee.ffff"
    assert "token=dddd.eeee.ffff" in account["cookies"] and "__ddg5_=x" in account["cookies"]
    message.delete.assert_awaited()
    from pok.conn import Conn
    Conn(token=account["token"], cookies=account["cookies"]).close()
