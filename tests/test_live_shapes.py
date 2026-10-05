import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot.core as core
from bot._forge import _build_html, _build_plain
from pok.defs import AccountRole, ChatMessageButtonTypes, DealFlow, DealStage, ItemLogEvents, RoomKind, TxKind
from pok.feed import Feed
from pok.gql import chat, chat_message, item_deal
from pok.models import MyItem

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "live_shapes.json").read_text(encoding="utf-8"))
ME = "00000000-0000-4000-8000-000000000001"


@pytest.fixture
def messages():
    return [chat_message(row) for row in FIXTURE["messages"]]


def test_real_sale_deal_is_decoded_with_seller_item():
    deal = item_deal(FIXTURE["sale_deal"])
    assert (deal.status, deal.previous_status, deal.direction) == (DealStage.CONFIRMED, DealStage.SENT, DealFlow.OUT)
    assert deal.user.username == "caps001" and deal.user.id != ME
    assert isinstance(deal.item, MyItem)
    assert deal.item.priority.name == "PREMIUM" and deal.item.user.id == ME
    assert deal.item.required_seller_reviews == 20 and deal.item.lacks_seller_reviews
    assert deal.transaction.value == 248 and deal.transaction.operation == TxKind.SELL
    assert deal.review.rating == 5
    assert deal.logs[0].event == ItemLogEvents.PAID
    assert deal.obtaining_fields[0].value == "x"


def test_real_sale_income_is_payout_after_fee():
    instance = object.__new__(core.MarketBridge)
    instance.account = SimpleNamespace(load_deal=Mock(side_effect=RuntimeError("offline")))
    assert instance._calc_net(item_deal(FIXTURE["sale_deal"])) == 248


def test_real_messages_decode(messages):
    admin, confirmed, sent, started, with_file, auto = messages
    assert admin.user.role == AccountRole.ADMIN and admin.buttons[0].type == ChatMessageButtonTypes.REDIRECT
    assert confirmed.deal.status == DealStage.CONFIRMED and confirmed.user.id == ME
    assert sent.user.username == "user010"
    assert started.event == "CHAT_STARTED" and started.user.role == AccountRole.SECURITY and started.text is None
    assert with_file.file.url and with_file.text is None
    assert auto.user is None and auto.is_auto_response


def test_real_system_messages_produce_deal_events(messages):
    feed = Feed(Mock())
    room = chat({"id": "chat", "type": "PM"})
    kinds = lambda msg: [type(event).__name__ for event in feed._parse_message_events(msg, room)]
    _, confirmed, sent, started, with_file, auto = messages
    assert kinds(confirmed) == ["DealConfirmedNotice", "DealStageChanged"]
    assert kinds(sent) == ["ListingShippedNotice", "DealStageChanged"]
    assert kinds(started) == ["ChatIngress"]
    assert kinds(with_file) == ["ChatIngress"]
    assert kinds(auto) == ["ChatIngress"]


def test_real_messages_render_for_telegram(messages):
    admin, confirmed, sent, started, with_file, auto = messages
    assert "🔗" in _build_html(admin)
    assert "подтвердил" in _build_html(confirmed) and "Оставить отзыв" in _build_html(confirmed)
    assert "отправил" in _build_plain(sent)
    assert "Начат чат" in _build_html(started)
    assert "📎" in _build_html(with_file)
    assert _build_html(auto) == "x"


def test_message_without_sender_is_ignored_by_engine(messages):
    instance = object.__new__(core.MarketBridge)
    instance._store_msg = Mock()
    instance.account = SimpleNamespace(id=ME, system_chat_id="s", support_chat_id="p")
    event = SimpleNamespace(message=messages[5], chat=SimpleNamespace(id="chat"))
    asyncio.run(instance._on_inbound(event))
    instance._store_msg.assert_not_called()


def test_confirmed_purchase_is_not_treated_as_own_sale(messages):
    instance = object.__new__(core.MarketBridge)
    instance.account = SimpleNamespace(id=ME, load_deal=Mock())
    instance.config = {"alerts": {"enabled": False}, "auto": {"restore": {"sold": True}}}
    instance._stop_event = threading.Event()
    instance._push = Mock()
    event = SimpleNamespace(deal=messages[1].deal, chat=SimpleNamespace(id="chat", type=RoomKind.PM))
    asyncio.run(instance._on_stage(event))
    instance._push.assert_not_called()
    instance.account.load_deal.assert_not_called()
