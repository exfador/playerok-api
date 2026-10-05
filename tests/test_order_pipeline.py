import asyncio
import copy
import json
import threading
from collections import deque
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot.core as core
from lib import bus
from pok.defs import DealStage, ListingStage, MarketEvent
from pok.feed import Feed
from pok.gql import chat_message, item_priority_status, my_item

SELLER = "00000000-0000-4000-8000-000000000001"
BUYER = "00000000-0000-4000-8000-000000000013"
ITEM_ID = "00000000-0000-4000-8000-000000000014"
DEAL_ID = "00000000-0000-4000-8000-000000000012"
CHAT_ID = "00000000-0000-4000-8000-000000000033"


def user(uid, name):
    return {"__typename": "UserFragment", "id": uid, "username": name, "role": "USER", "testimonialCounter": 5}


def listing(status):
    return my_item({"__typename": "MyItem", "id": ITEM_ID, "name": "Telegram Premium 1 месяц", "price": 310, "rawPrice": 310,
                    "status": status, "priority": "DEFAULT", "user": user(SELLER, "seller")})


def paid_message(deal_status="PAID"):
    return {"__typename": "ChatMessage", "id": "00000000-0000-4000-8000-000000000099", "text": "{{ITEM_PAID}}",
            "createdAt": "2026-10-05T10:00:00.000Z", "isRead": False, "user": user(BUYER, "buyer"),
            "deal": {"__typename": "ItemDeal", "id": DEAL_ID, "status": deal_status, "direction": "OUT",
                     "user": user(BUYER, "buyer"), "chat": {"id": CHAT_ID, "type": "PM"},
                     "item": {"__typename": "MyItem", "id": ITEM_ID, "name": "Telegram Premium 1 месяц", "price": 310,
                              "rawPrice": 310, "user": user(SELLER, "seller")}}}


def chat_updated_frame():
    payload = {"chatUpdated": {"__typename": "Chat", "id": CHAT_ID, "type": "PM",
                               "participants": [user(SELLER, "seller"), user(BUYER, "buyer")],
                               "lastMessage": paid_message()}}
    return json.dumps({"id": "sub", "type": "next", "payload": {"data": payload}})


class Store:
    def __init__(self):
        self.files = {
            "auto_deliveries": [{"keyphrases": ["Telegram Premium"], "piece": True, "goods": ["KEY-AAA", "KEY-BBB"]}],
            "messages": {"new_deal": {"enabled": True, "text": ["Спасибо за заказ «$product», $buyer!"]},
                         "first_message": {"enabled": False, "text": ["Привет"]}},
        }

    def read(self, name, *args):
        return copy.deepcopy(self.files.get(name))

    def write(self, name, value):
        self.files[name] = copy.deepcopy(value)


@pytest.fixture
def engine(monkeypatch):
    store = Store()
    monkeypatch.setattr(core.cfg, "read", store.read)
    monkeypatch.setattr(core.cfg, "write", store.write)
    memory = {}
    monkeypatch.setattr(core, "db", SimpleNamespace(get=lambda name: copy.deepcopy(memory.get(name)),
                                                    set=lambda name, value: memory.__setitem__(name, copy.deepcopy(value))))
    deferred = []

    class InlineThread:
        def __init__(self, target, args=(), daemon=None, name=None):
            self.target, self.args = target, args

        def start(self):
            deferred.append(self)

    monkeypatch.setattr(core, "Thread", InlineThread)
    sent = []
    states = {"listing": [listing("SOLD")]}
    account = SimpleNamespace(
        id=SELLER, username="seller", system_chat_id="sys", support_chat_id="sup",
        load_deal=Mock(return_value=chat_message(paid_message()).deal),
        load_listing=Mock(side_effect=lambda _id: states["listing"][-1]),
        send_message=Mock(side_effect=lambda chat_id, text=None, **kw: sent.append((chat_id, text)) or SimpleNamespace(id=f"m{len(sent)}")),
        patch_deal=Mock(),
        load_boost_tiers=Mock(return_value=[item_priority_status({"id": "free", "price": 0, "type": "DEFAULT", "name": "Обычный"})]),
        activate_listing=Mock(side_effect=lambda *a, **k: states["listing"].append(listing("PENDING_APPROVAL")) or states["listing"][-1]),
    )
    instance = object.__new__(core.MarketBridge)
    instance.config = {
        "alerts": {"enabled": False, "on": {}},
        "features": {"deliveries": True, "greet": True, "read_chat": False, "commands": True, "watermark": {"enabled": False}},
        "auto": {"confirm": {"enabled": True, "all": True},
                 "restore": {"sold": True, "expired": False, "all": True, "premium": False, "premium_max_price": 50, "keep_in_sale": False},
                 "bump": {"enabled": False, "all": True, "max_price": 50}, "daily_limit": 200},
    }
    instance.account = account
    instance.initialized_users = []
    instance.auto_restore_items = {"included": []}
    instance.auto_complete_deals = {"included": []}
    instance._stop_event = threading.Event()
    instance._mutation_guard = threading.Lock()
    instance._reactivating_items = set()
    instance._elevating_items = set()
    instance._delivery_lock = threading.Lock()
    instance._chat_msg_history = {}
    instance._chat_msg_history_lock = threading.Lock()
    instance.stats = SimpleNamespace(deals_completed=0, deals_refunded=0, earned_money=0)
    instance._trace_order = Mock()
    return SimpleNamespace(engine=instance, account=account, sent=sent, store=store, deferred=deferred, states=states)


def run_feed_frame(frame):
    conn = SimpleNamespace(id=SELLER, load_chat=Mock(), load_messages=Mock())
    feed = Feed(conn)
    feed.q = Queue()
    feed.ws = feed._ws_generation_socket = Mock()
    feed.process_ws_message(frame, generation=feed._ws_generation)
    events = []
    while not feed.q.empty():
        events.append(feed.q.get())
    return events


def dispatch(engine, events):
    handlers = {MarketEvent.NEW_DEAL: core.MarketBridge._on_order, MarketEvent.ITEM_PAID: core.MarketBridge._on_paid}
    saved = {kind: list(bus.mkt_table()[kind]._slots) for kind in handlers}
    try:
        for kind, handler in handlers.items():
            bus.mkt_table()[kind]._slots = [handler]
        for event in events:
            if event.type in handlers:
                asyncio.run(bus.fire_mkt(event.type, [engine, event]))
    finally:
        for kind, slots in saved.items():
            bus.mkt_table()[kind]._slots = slots


def test_paid_order_flows_from_websocket_to_delivery_confirmation_and_restore(engine):
    events = run_feed_frame(chat_updated_frame())
    assert [type(e).__name__ for e in events] == ["RoomSnapshotReady", "DealCreatedNotice", "ListingPaidNotice"]
    dispatch(engine.engine, events)
    assert engine.sent == [(CHAT_ID, "Спасибо за заказ «Telegram Premium 1 месяц», buyer!"), (CHAT_ID, "KEY-AAA")]
    assert engine.store.files["auto_deliveries"][0]["goods"] == ["KEY-BBB"]
    engine.account.patch_deal.assert_called_once_with(DEAL_ID, DealStage.SENT)
    assert BUYER in engine.engine.initialized_users
    assert len(engine.deferred) == 1
    restore = engine.deferred[0]
    assert restore.target(restore.args[0], [0]) == "restored"
    engine.account.activate_listing.assert_called_once_with(ITEM_ID, "free", keep_in_sale=None)
    assert engine.states["listing"][-1].status == ListingStage.PENDING_APPROVAL


def test_duplicate_frame_does_not_deliver_twice(engine):
    frame = chat_updated_frame()
    conn = SimpleNamespace(id=SELLER, load_chat=Mock(), load_messages=Mock())
    feed = Feed(conn)
    feed.q = Queue()
    feed.ws = feed._ws_generation_socket = Mock()
    feed.process_ws_message(frame, generation=feed._ws_generation)
    feed.process_ws_message(frame, generation=feed._ws_generation)
    events = []
    while not feed.q.empty():
        events.append(feed.q.get())
    dispatch(engine.engine, events)
    assert [text for _, text in engine.sent].count("KEY-AAA") == 1
    assert engine.account.patch_deal.call_count == 1


def test_already_delivered_deal_is_not_delivered_again(engine):
    engine.account.load_deal.return_value = chat_message(paid_message("SENT")).deal
    dispatch(engine.engine, run_feed_frame(chat_updated_frame()))
    assert engine.sent == []
    assert engine.store.files["auto_deliveries"][0]["goods"] == ["KEY-AAA", "KEY-BBB"]
    engine.account.patch_deal.assert_not_called()


def test_order_without_delivery_rule_is_not_marked_sent(engine):
    engine.store.files["auto_deliveries"] = []
    dispatch(engine.engine, run_feed_frame(chat_updated_frame()))
    engine.account.patch_deal.assert_not_called()


def test_confirming_undelivered_orders_requires_explicit_opt_out(engine):
    engine.store.files["auto_deliveries"] = []
    engine.engine.config["auto"]["confirm"]["only_delivered"] = False
    dispatch(engine.engine, run_feed_frame(chat_updated_frame()))
    engine.account.patch_deal.assert_called_once_with(DEAL_ID, DealStage.SENT)


def test_failed_delivery_keeps_key_and_skips_confirmation(engine):
    calls = {"n": 0}

    def flaky(chat_id, text=None, **kw):
        calls["n"] += 1
        if text == "KEY-AAA":
            raise RuntimeError("network")
        return SimpleNamespace(id="m")

    engine.account.send_message.side_effect = flaky
    dispatch(engine.engine, run_feed_frame(chat_updated_frame()))
    assert engine.store.files["auto_deliveries"][0]["goods"] == ["KEY-AAA", "KEY-BBB"]
    engine.account.patch_deal.assert_not_called()
