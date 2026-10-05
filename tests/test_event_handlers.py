import asyncio
import itertools
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot.core as core
from lib import bus
from pok.gql import chat_message, item_deal
import tests.test_order_pipeline as pipeline
from tests.test_order_pipeline import BUYER, CHAT_ID, DEAL_ID, ITEM_ID, SELLER, run_feed_frame, user

engine = pipeline.engine
_ids = itertools.count(1)
HANDLERS = {
    "NEW_MESSAGE": core.MarketBridge._on_inbound,
    "NEW_REVIEW": core.MarketBridge._on_review_new,
    "REVIEW_REMOVED": core.MarketBridge._on_review_del,
    "REVIEW_UPDATED": core.MarketBridge._on_review_edit,
    "DEAL_HAS_PROBLEM": core.MarketBridge._on_dispute,
    "DEAL_PROBLEM_RESOLVED": core.MarketBridge._on_dispute_close,
    "DEAL_STATUS_CHANGED": core.MarketBridge._on_stage,
}


class FakePanel:
    def __init__(self):
        self.events = []
        self.seller_calls = []

    def log_event(self, text, kb=None, link_preview_url=None):
        self.events.append(text)

    def call_seller(self, username, chat_id):
        self.seller_calls.append((username, chat_id))


@pytest.fixture
def bridge(engine, monkeypatch):
    panel = FakePanel()
    monkeypatch.setattr(core, "_get_panel", lambda: panel)
    monkeypatch.setattr(core, "_get_panel_loop", lambda: "loop")
    monkeypatch.setattr(core.asyncio, "run_coroutine_threadsafe", lambda coro, loop: None)
    monkeypatch.setattr(core, "active_engine", lambda: engine.engine)
    instance = engine.engine
    instance.config["alerts"] = {"enabled": True, "on": {}}
    instance.custom_commands = {"items": [
        {"id": "c1", "trigger": "!вызвать", "events": ["call_seller"], "reply_lines": ["Продавец скоро ответит"]},
        {"id": "c2", "trigger": "!инфо", "events": [], "reply_lines": ["", "Работаю 24/7"]},
    ]}
    instance._seller_calls = {}
    instance._problem_resolved_notify_at = {}
    instance._problem_resolved_notify_lock = core.Lock()
    instance._thread_chat_handles = {}
    instance.stats = SimpleNamespace(deals_completed=0, deals_refunded=0, earned_money=0)
    engine.store.files["messages"].update({
        "cmd_seller": {"enabled": True, "text": ["$buyer, продавец уведомлён"]},
        "deal_sent": {"enabled": True, "text": ["Заказ «$product» отправлен"]},
        "deal_confirmed": {"enabled": True, "text": ["Спасибо, $buyer! Сделка $deal_id закрыта"]},
        "deal_refunded": {"enabled": True, "text": ["Возврат за «$product» на $price ₽"]},
        "new_review": {"enabled": True, "text": ["Спасибо за $rating ⭐"]},
    })
    engine.account.find_chat_by_name = Mock(side_effect=lambda name: SimpleNamespace(id=f"chat-{name}"))
    engine.account.load_chat = Mock(side_effect=lambda chat_id: SimpleNamespace(id=chat_id))
    return SimpleNamespace(engine=instance, account=engine.account, sent=engine.sent, panel=panel, store=engine.store,
                           deferred=engine.deferred)


def frame(text, sender_id=BUYER, sender_name="buyer", deal_status=None, chat_id=CHAT_ID, **deal_extra):
    message = {"__typename": "ChatMessage", "id": f"00000000-0000-4000-8000-{next(_ids):012d}", "text": text,
               "createdAt": "2026-10-05T10:00:00.000Z", "isRead": False, "user": user(sender_id, sender_name)}
    if deal_status:
        message["deal"] = {"__typename": "ItemDeal", "id": DEAL_ID, "status": deal_status, "direction": "OUT",
                           "user": user(BUYER, "buyer"), "chat": {"id": chat_id, "type": "PM"},
                           "item": {"__typename": "MyItem", "id": ITEM_ID, "name": "Telegram Premium 1 месяц",
                                    "price": 310, "rawPrice": 310, "user": user(SELLER, "seller")}, **deal_extra}
    payload = {"chatUpdated": {"__typename": "Chat", "id": chat_id, "type": "PM",
                               "participants": [user(SELLER, "seller"), user(BUYER, "buyer")], "lastMessage": message}}
    return json.dumps({"id": "sub", "type": "next", "payload": {"data": payload}})


def fire(instance, events):
    tables = bus.mkt_table()
    saved = {kind: list(slot._slots) for kind, slot in tables.items()}
    try:
        for kind, slot in tables.items():
            slot._slots = [HANDLERS[kind.name]] if kind.name in HANDLERS else []
        for event in events:
            asyncio.run(bus.fire_mkt(event.type, [instance, event]))
    finally:
        for kind, slots in saved.items():
            tables[kind]._slots = slots


def deal_with(**fields):
    base = {"__typename": "ItemDeal", "id": DEAL_ID, "status": "CONFIRMED", "direction": "OUT",
            "user": user(BUYER, "buyer"), "chat": {"id": CHAT_ID, "type": "PM"},
            "item": {"__typename": "MyItem", "id": ITEM_ID, "name": "Telegram Premium 1 месяц", "price": 310,
                     "rawPrice": 310, "user": user(SELLER, "seller")}}
    base.update(fields)
    return item_deal(base)


def test_buyer_message_is_forwarded_escaped(bridge):
    fire(bridge.engine, run_feed_frame(frame("<b>Где мой заказ?</b>")))
    assert len(bridge.panel.events) == 1
    assert "&lt;b&gt;Где мой заказ?&lt;/b&gt;" in bridge.panel.events[0]
    assert "<b>buyer:</b>" in bridge.panel.events[0]
    assert BUYER in bridge.engine.initialized_users
    assert bridge.sent == []


def test_own_messages_are_not_forwarded_or_treated_as_commands(bridge):
    fire(bridge.engine, run_feed_frame(frame("!вызвать", sender_id=SELLER, sender_name="seller")))
    assert bridge.panel.events == []
    assert bridge.panel.seller_calls == []
    assert bridge.sent == []


def test_call_seller_command_notifies_once_per_two_minutes(bridge):
    fire(bridge.engine, run_feed_frame(frame("!вызвать")))
    fire(bridge.engine, run_feed_frame(frame("!вызвать")))
    assert bridge.panel.seller_calls == [("buyer", CHAT_ID)]
    assert bridge.sent == [(CHAT_ID, "buyer, продавец уведомлён"), (CHAT_ID, "Продавец скоро ответит"),
                           (CHAT_ID, "Продавец скоро ответит")]


def test_reply_command_skips_blank_lines_and_respects_switch(bridge):
    fire(bridge.engine, run_feed_frame(frame("!инфо")))
    assert bridge.sent == [(CHAT_ID, "Работаю 24/7")]
    bridge.engine.config["features"]["commands"] = False
    fire(bridge.engine, run_feed_frame(frame("!инфо")))
    assert len(bridge.sent) == 1


def test_support_chat_never_runs_commands(bridge):
    fire(bridge.engine, run_feed_frame(frame("!вызвать", chat_id="sup")))
    assert bridge.panel.seller_calls == []
    assert bridge.sent == []
    assert len(bridge.panel.events) == 1


def test_confirmed_deal_counts_net_revenue_once_and_thanks_buyer(bridge):
    bridge.account.load_deal = Mock(return_value=deal_with(transaction={"id": "t", "value": 248, "direction": "IN"}))
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_CONFIRMED}}", deal_status="CONFIRMED")))
    assert bridge.engine.stats.deals_completed == 1
    assert bridge.engine.stats.earned_money == 248
    assert bridge.sent == [(CHAT_ID, f"Спасибо, buyer! Сделка {DEAL_ID} закрыта")]
    assert [type(t.target.__self__).__name__ for t in bridge.deferred] == ["MarketBridge"]


def test_confirmed_deal_with_open_problem_is_not_counted(bridge):
    bridge.account.load_deal = Mock(return_value=deal_with(hasProblem=True))
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_CONFIRMED}}", deal_status="CONFIRMED")))
    assert bridge.engine.stats.deals_completed == 0
    assert bridge.engine.stats.earned_money == 0
    assert bridge.sent == []


def test_refund_and_shipping_templates(bridge):
    fire(bridge.engine, run_feed_frame(frame("{{ITEM_SENT}}", sender_id=SELLER, sender_name="seller", deal_status="SENT")))
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_ROLLED_BACK}}", deal_status="ROLLED_BACK")))
    assert bridge.sent == [(CHAT_ID, "Заказ «Telegram Premium 1 месяц» отправлен"),
                           (CHAT_ID, "Возврат за «Telegram Premium 1 месяц» на 310 ₽")]
    assert bridge.engine.stats.deals_refunded == 1


def test_dispute_notification_includes_topic_and_details(bridge):
    bridge.account.load_deal = Mock(return_value=deal_with(
        status="CONFIRMED", hasProblem=True, statusDescription="Товар не пришёл\n\nКод не активируется <script>"))
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_HAS_PROBLEM}}", deal_status="CONFIRMED")))
    problem = [e for e in bridge.panel.events if "Спор" in e]
    assert len(problem) == 1
    assert "<b>Тема:</b> Товар не пришёл" in problem[0]
    assert "Код не активируется &lt;script&gt;" in problem[0]


def test_dispute_survives_failed_deal_reload(bridge):
    bridge.account.load_deal = Mock(side_effect=RuntimeError("502"))
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_HAS_PROBLEM}}", deal_status="CONFIRMED")))
    assert any("Спор" in e for e in bridge.panel.events)


def test_dispute_resolution_is_reported_once(bridge):
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_PROBLEM_RESOLVED}}", sender_id="support", sender_name="Поддержка",
                                             deal_status="CONFIRMED")))
    fire(bridge.engine, run_feed_frame(frame("{{DEAL_PROBLEM_RESOLVED}}", sender_id="support", sender_name="Поддержка",
                                             deal_status="CONFIRMED")))
    closed = [e for e in bridge.panel.events if "Спор закрыт" in e]
    assert len(closed) == 1
    assert "Поддержка" in closed[0]


def test_own_purchase_events_are_ignored(bridge):
    message = {"__typename": "ChatMessage", "id": "00000000-0000-4000-8000-999999999999", "text": "{{DEAL_CONFIRMED}}",
               "createdAt": "2026-10-05T10:00:00.000Z", "isRead": False, "user": user(SELLER, "seller"),
               "deal": {"__typename": "ItemDeal", "id": DEAL_ID, "status": "CONFIRMED", "direction": "IN",
                        "user": user(SELLER, "seller"), "chat": {"id": CHAT_ID, "type": "PM"},
                        "item": {"__typename": "Item", "id": ITEM_ID, "name": "Чужой лот", "price": 50,
                                 "user": user(BUYER, "buyer")}}}
    payload = {"chatUpdated": {"__typename": "Chat", "id": CHAT_ID, "type": "PM",
                               "participants": [user(SELLER, "seller"), user(BUYER, "buyer")], "lastMessage": message}}
    fire(bridge.engine, run_feed_frame(json.dumps({"id": "s", "type": "next", "payload": {"data": payload}})))
    assert bridge.engine.stats.deals_completed == 0
    assert bridge.sent == []


def review(rating, text, review_id="r1"):
    return {"__typename": "Testimonial", "id": review_id, "rating": rating, "text": text, "status": "APPROVED",
            "createdAt": "2026-10-05T11:00:00.000Z", "creator": user(BUYER, "buyer")}


def review_events(bridge, *deals):
    from pok.feed import Feed
    conn = SimpleNamespace(id=SELLER, load_deal=Mock(side_effect=list(deals)), load_chat=Mock(return_value=SimpleNamespace(id=CHAT_ID)))
    feed = Feed(conn)
    feed.review_check_deals.append(DEAL_ID)
    feed._should_check_watch_deal = lambda deal_id, *a, **k: True
    stream = feed.listen_new_reviews()
    events = []
    for _ in deals:
        events.append(next(stream))
    feed._stop_event.set()
    return events


def test_review_created_edited_and_removed(bridge):
    events = review_events(
        bridge,
        deal_with(testimonial=review(5, "Отлично")),
        deal_with(testimonial=review(2, "Ключ <не> работал")),
        deal_with(testimonial=None),
    )
    assert [type(e).__name__ for e in events] == ["ReviewCreatedNotice", "ReviewEditedNotice", "ReviewRemovedNotice"]
    fire(bridge.engine, events)
    created, edited, removed = bridge.panel.events
    assert "⭐⭐⭐⭐⭐" in created and "Отлично" in created
    assert "(5) — Отлично" in edited and "(2) — Ключ &lt;не&gt; работал" in edited
    assert "Отзыв удалён" in removed
    assert bridge.sent == [(CHAT_ID, "Спасибо за 5 ⭐")]


@pytest.mark.parametrize("transaction, fee_multiplier, expected", [
    ({"id": "t", "value": 248}, None, 248),
    ({"id": "t", "value": 310, "fee": 31}, None, 279),
    ({"id": "t", "value": 3100000, "fee": 310000}, None, 27900),
    ({"id": "t", "value": 310, "fee": 400}, None, 310),
    (None, 0.1, 279),
    (None, 1.5, 310),
    (None, None, 310),
])
def test_net_revenue_calculation(bridge, transaction, fee_multiplier, expected):
    deal = deal_with(transaction=transaction)
    deal.item.fee_multiplier = fee_multiplier
    bridge.account.load_deal = Mock(side_effect=RuntimeError("offline"))
    assert bridge.engine._calc_net(deal) == expected


def test_net_revenue_without_any_price_is_zero(bridge):
    deal = deal_with(item=None)
    bridge.account.load_deal = Mock(return_value=deal)
    assert bridge.engine._calc_net(deal) == 0


@pytest.mark.parametrize("description, comment, expected", [
    ("", "", (None, None)),
    ("", "Не пришло", (None, "Не пришло")),
    ("Тема\n\nПодробно", "", ("Тема", "Подробно")),
    ("Тема", "Комментарий", ("Тема", "Комментарий")),
    ("Тема", "Тема", (None, "Тема")),
])
def test_dispute_text_parsing(description, comment, expected):
    deal = SimpleNamespace(status_description=description, comment_from_buyer=comment)
    assert core._parse_dispute_text(deal) == expected


def test_chat_lookup_by_alias_is_cached(bridge):
    support = bridge.engine._room_by_alias("Поддержка")
    system = bridge.engine._room_by_alias("уведомления")
    first = bridge.engine._room_by_alias("buyer")
    again = bridge.engine._room_by_alias("buyer")
    assert (support.id, system.id, first.id) == ("sup", "sys", "chat-buyer")
    assert first is again
    bridge.account.find_chat_by_name.assert_called_once_with("buyer")


def test_missing_chat_is_not_cached(bridge):
    bridge.account.find_chat_by_name = Mock(return_value=None)
    assert bridge.engine._room_by_alias("ghost") is None
    assert bridge.engine._room_by_alias("ghost") is None
    assert bridge.account.find_chat_by_name.call_count == 2


@pytest.mark.parametrize("position, exclude, expected", [
    ("end", False, "Ключ\n\n— магазин"),
    ("start", False, "— магазин\n\nКлюч"),
    ("end", True, "Ключ"),
])
def test_watermark_is_applied_to_outgoing_messages(bridge, position, exclude, expected):
    bridge.engine.config["features"]["watermark"] = {"enabled": True, "text": "— магазин", "position": position}
    bridge.engine._push(CHAT_ID, "Ключ", exclude_watermark=exclude)
    assert bridge.sent[-1] == (CHAT_ID, expected)


def test_push_survives_send_failure_and_skips_empty_text(bridge):
    bridge.account.send_message = Mock(side_effect=RuntimeError("timeout"))
    assert bridge.engine._push(CHAT_ID, "x") is None
    assert bridge.engine._push(CHAT_ID, "") is None
    assert bridge.engine._push(None, "x") is None
    assert bridge.account.send_message.call_count == 1


def test_template_rendering(bridge):
    bridge.store.files["messages"]["t_custom"] = {"enabled": False, "text": ["Привет, $buyer! Я $seller, $unknown"]}
    assert bridge.engine._render_tpl("t_custom", "buyer") == "Привет, buyer! Я seller, $unknown"
    assert bridge.engine._render("t_custom", buyer="buyer") is None
    assert bridge.engine._render_tpl("missing", "buyer") is None
    assert bridge.engine._render("deal_sent", product="X") == "Заказ «X» отправлен"


def test_stage_change_from_deal_status_event_is_ignored_for_unknown_status(bridge):
    event = SimpleNamespace(deal=chat_message({
        "__typename": "ChatMessage", "id": "m", "text": "{{ITEM_PAID}}", "createdAt": "2026-10-05T10:00:00.000Z",
        "user": user(BUYER, "buyer"),
        "deal": {"__typename": "ItemDeal", "id": DEAL_ID, "status": "SOMETHING_NEW", "user": user(BUYER, "buyer"),
                 "item": {"__typename": "MyItem", "id": ITEM_ID, "name": "Лот", "price": 1}}}).deal, chat=None)
    assert event.deal.status is None
    asyncio.run(core.MarketBridge._on_stage(bridge.engine, event))
    assert bridge.sent == []
    assert bridge.engine.stats.deals_completed == 0
    assert any("Неизвестный" in e for e in bridge.panel.events)
