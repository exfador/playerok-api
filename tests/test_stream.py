import json
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import websocket

from pok.feed import Feed
from pok.gql import chat, chat_message
from pok.stream import StreamConnection, StreamProtocolError


def test_ping_before_ack_is_answered():
    owner = SimpleNamespace(_ca_bundle=None, user_agent="fixture", proxy=None, _cookie_header=lambda: "token=fixture")
    socket = Mock()
    socket.recv.side_effect = ['{"type":"ping","payload":{"test":1}}', '{"type":"connection_ack"}']
    stream = StreamConnection(owner, socket)
    assert stream.connect()["type"] == "connection_ack"
    frames = [json.loads(call.args[0]) for call in socket.send.call_args_list]
    assert frames[-1] == {"type": "pong", "payload": {"test": 1}}
    assert socket.connect.call_args.kwargs["origin"] == "https://playerok.com"


def test_subscription_error_is_visible():
    socket = Mock()
    socket.recv.return_value = '{"type":"error","payload":[{"message":"invalid"}]}'
    with pytest.raises(StreamProtocolError):
        StreamConnection(Mock(), socket).receive()


def test_heartbeat_detects_silent_connection():
    socket = Mock()
    socket.recv.side_effect = websocket.WebSocketTimeoutException()
    clock = Mock(side_effect=[0, 70])
    with pytest.raises(StreamProtocolError, match="heartbeat"):
        StreamConnection(Mock(), socket, clock=clock).receive()


def test_reconnect_clears_stale_subscription_ids():
    feed = Feed(SimpleNamespace(id="user"))
    feed.ws = Mock()
    feed.chats = [chat({"id": "chat", "type": "PM"})]
    feed.chat_subscriptions["old-subscription"] = "chat"
    feed.process_ws_message(json.dumps({"type": "connection_ack"}))
    assert "old-subscription" not in feed.chat_subscriptions
    assert list(feed.chat_subscriptions.values()) == ["chat"]
    assert feed.ws.send.call_count == 4


def test_new_chat_without_participants_is_loaded_once():
    loaded = chat({"id": "new", "type": "PM", "participants": [{"id": "buyer", "username": "buyer"}]})
    conn = Mock()
    conn.load_chat.return_value = loaded
    feed = Feed(conn)
    feed.q = Queue()
    feed.ws = Mock()
    feed.proccess_ws_message(json.dumps({"type": "next", "payload": {"data": {
        "chatUpdated": {"id": "new", "unreadMessagesCounter": 1, "lastMessage": None},
    }}}))
    assert feed.chats[0].users[0].username == "buyer"
    conn.load_chat.assert_called_once_with("new")


def test_failed_new_chat_load_does_not_break_stream():
    conn = Mock()
    conn.load_chat.side_effect = RuntimeError("network")
    feed = Feed(conn)
    feed.q = Queue()
    feed.ws = Mock()
    feed.proccess_ws_message(json.dumps({"type": "next", "payload": {"data": {
        "chatUpdated": {"id": "new", "unreadMessagesCounter": 1, "lastMessage": None},
    }}}))
    assert [c.id for c in feed.chats] == ["new"]


def test_system_message_with_deal_does_not_wait_for_hydration():
    feed = Feed(Mock())
    feed._get_actual_message = Mock(side_effect=AssertionError("must not hydrate"))
    message = chat_message({"id": "m", "text": "{{ITEM_PAID}}", "deal": {"id": "deal", "status": "PAID"}})
    events = feed._parse_message_events(message, chat({"id": "chat"}))
    assert [entry.type.name for entry in events] == ["NEW_DEAL", "ITEM_PAID"]


def test_plain_text_looking_like_system_event_without_deal_is_a_message():
    feed = Feed(Mock())
    feed._get_actual_message = Mock(return_value=None)
    message = chat_message({"id": "m", "text": "{{ITEM_PAID}}"})
    events = feed._parse_message_events(message, chat({"id": "chat"}))
    assert [entry.type.name for entry in events] == ["NEW_MESSAGE"]


def test_partial_chat_update_preserves_participants_and_type():
    feed = Feed(Mock())
    feed.q = Queue()
    original = chat({"id": "chat", "type": "PM", "participants": [{"id": "user", "username": "fixture"}]})
    feed.chats = [original]
    feed.chat_subscriptions["sub"] = "chat"
    feed.proccess_ws_message(json.dumps({"type": "next", "payload": {"data": {
        "chatUpdated": {"id": "chat", "unreadMessagesCounter": 2, "lastMessage": None},
    }}}))
    assert feed.chats[0].type.name == "PM"
    assert feed.chats[0].users[0].id == "user"
    assert feed.chats[0].unread_messages_counter == 2
    feed.conn.load_chat.assert_not_called()


def test_image_links_and_event_are_preserved():
    message = chat_message({"id": "message", "event": "ITEM_SENT", "imageLinks": ["https://playerok.com/image.png"]})
    assert message.event == "ITEM_SENT"
    assert message.images[0].url == "https://playerok.com/image.png"


def test_message_repeated_on_two_subscriptions_is_deduplicated():
    feed = Feed(Mock())
    feed._parse_message_events = Mock(return_value=[SimpleNamespace(type=None)])
    current = chat({"id": "chat"})
    message = chat_message({"id": "message", "text": "fixture"})
    assert len(feed._events_for_chat_message(current, message)) == 1
    assert feed._events_for_chat_message(current, message) == []


@pytest.mark.parametrize("event", ["ITEM_SENT", "ITEM_SENT_AUTOMATICALLY"])
def test_system_event_field_is_used_when_text_format_changes(event):
    feed = Feed(Mock())
    feed._get_actual_message = Mock(return_value=None)
    message = chat_message({"id": "message", "text": "new display text", "event": event,
                            "deal": {"id": "deal", "status": "SENT"}})
    events = feed._parse_message_events(message, chat({"id": "chat"}))
    assert [entry.type.name for entry in events] == ["ITEM_SENT", "DEAL_STATUS_CHANGED"]


def _paid(message_id, deal_id, created_at):
    return chat_message({"id": message_id, "text": "{{ITEM_PAID}}", "event": "ITEM_PAID", "createdAt": created_at,
                         "deal": {"id": deal_id, "status": "PAID"}})


def test_subscription_error_drops_chat_subscription_and_is_reported():
    feed = Feed(SimpleNamespace(id="user"))
    feed.chat_subscriptions["sub"] = "chat"
    feed.process_ws_message(json.dumps({"type": "error", "id": "sub", "payload": [{"message": "forbidden"}]}))
    assert "sub" not in feed.chat_subscriptions
    assert "forbidden" in feed.health()["last_error"]


def test_completed_core_subscription_forces_reconnect():
    feed = Feed(SimpleNamespace(id="user"))
    feed.ws = feed._ws_generation_socket = Mock()
    feed._core_subscriptions["core"] = "chatUpdated"
    feed.process_ws_message(json.dumps({"type": "complete", "id": "core"}))
    feed.ws.close.assert_called_once()


def test_user_update_without_unread_counter_is_ignored():
    feed = Feed(SimpleNamespace(id="user"))
    feed.q = Queue()
    feed.process_ws_message(json.dumps({"type": "next", "payload": {"data": {"userUpdated": {"unreadChatsCounter": None}}}}))
    assert not feed._possible_new_chat.is_set()


def test_reconnect_ack_requests_missed_order_recovery():
    feed = Feed(SimpleNamespace(id="user"))
    feed.ws = Mock()
    feed.process_ws_message(json.dumps({"type": "connection_ack"}))
    assert not feed._recover_missed.is_set()
    feed._last_disconnect_at = 1.0
    feed.process_ws_message(json.dumps({"type": "connection_ack"}))
    assert feed._recover_missed.is_set() and feed._possible_new_chat.is_set()


def test_recovery_skips_orders_before_start_and_already_processed():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    stamp = lambda delta: (now + timedelta(seconds=delta)).isoformat().replace("+00:00", "Z")
    messages = [_paid("m1", "old", stamp(-120)), _paid("m2", "done", stamp(-10)), _paid("m3", "new", stamp(-5)),
                chat_message({"id": "m4", "text": "hello", "createdAt": stamp(-1)})]
    conn = Mock()
    conn.load_messages.return_value = SimpleNamespace(messages=messages)
    feed = Feed(conn, processed_deals=["done"], since=now - timedelta(seconds=60))
    found = feed._recent_paid_messages("chat")
    assert [m.deal.id for m in found] == ["new"]


def test_processed_deals_are_shared_between_feed_restarts():
    shared = []
    first = Feed(Mock(), processed_deals=shared)
    first._parse_message_events(_paid("m", "deal", "2026-01-01T00:00:00Z"), chat({"id": "chat"}))
    second = Feed(Mock(), processed_deals=shared)
    assert second._parse_message_events(_paid("m2", "deal", "2026-01-01T00:00:00Z"), chat({"id": "chat"})) == []


def test_recovery_scans_known_chat_history_after_reconnect(monkeypatch):
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(seconds=60)
    created = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    known = chat({"id": "chat", "type": "PM", "lastMessage": {"id": "later", "text": "спасибо"}})
    conn = Mock()
    conn.load_chats.return_value = SimpleNamespace(chats=[known])
    conn.load_messages.return_value = SimpleNamespace(messages=[_paid("paid", "deal", created)])
    feed = Feed(conn, since=since)
    feed.chats = [known]
    feed._sleep = lambda seconds: False
    feed._process_new_chat_message = lambda chat_obj, message, generation=None: feed._parse_message_events(message, chat_obj)
    feed._recover_missed.set()
    feed._possible_new_chat.set()
    events = []
    for event in feed.listen_new_deals():
        events.append(event)
        if len(events) == 2:
            feed._stop_event.set()
    assert {type(e).__name__ for e in events} == {"DealCreatedNotice", "ListingPaidNotice"}


def test_chat_subscriptions_are_capped_and_old_ones_completed(monkeypatch):
    import pok.feed as feed_module
    monkeypatch.setattr(feed_module, "MAX_CHAT_SUBSCRIPTIONS", 3)
    feed = Feed(SimpleNamespace(id="user"))
    sent = []
    feed._send_ws = lambda payload, *args: sent.append(payload) or True
    feed._hydrate_message_if_needed = lambda message, chat_id: message
    for index in range(5):
        feed._process_new_chat_message(chat({"id": f"chat{index}", "type": "PM"}), None)
    assert sorted(feed.chat_subscriptions.values()) == ["chat2", "chat3", "chat4"]
    completed = [p for p in sent if p.get("type") == "complete"]
    assert len(completed) == 2


def test_reconnect_resubscribes_only_recent_chats(monkeypatch):
    import pok.feed as feed_module
    monkeypatch.setattr(feed_module, "MAX_CHAT_SUBSCRIPTIONS", 2)
    feed = Feed(SimpleNamespace(id="user"))
    feed.chats = [chat({"id": f"chat{index}", "type": "PM"}) for index in range(5)]
    feed.ws = Mock()
    feed.process_ws_message(json.dumps({"type": "connection_ack"}))
    assert sorted(feed.chat_subscriptions.values()) == ["chat3", "chat4"]


def test_tracked_chats_are_capped(monkeypatch):
    import pok.feed as feed_module
    monkeypatch.setattr(feed_module, "MAX_TRACKED_CHATS", 4)
    feed = Feed(SimpleNamespace(id="user"))
    feed._send_ws = lambda payload, *args: True
    feed._hydrate_message_if_needed = lambda message, chat_id: message
    for index in range(10):
        feed._process_new_chat_message(chat({"id": f"chat{index}", "type": "PM"}), None)
    assert [c.id for c in feed.chats] == ["chat6", "chat7", "chat8", "chat9"]


def test_parsed_message_ids_forget_oldest_first():
    from pok.feed import _BoundedSet
    seen = _BoundedSet(3)
    for key in ("a", "b", "c"):
        seen.add(key)
    seen.add("a")
    seen.add("d")
    assert "a" in seen and "d" in seen and "b" not in seen and len(seen) == 3


def test_review_polling_starts_only_after_confirmation():
    feed = Feed(Mock())
    room = chat({"id": "chat", "type": "PM"})
    feed._parse_message_events(_paid("m1", "deal", "2026-01-01T00:00:00Z"), room)
    assert feed.review_check_deals == []
    confirmed = chat_message({"id": "m2", "text": "{{DEAL_CONFIRMED}}", "deal": {"id": "deal", "status": "CONFIRMED"}})
    feed._parse_message_events(confirmed, room)
    assert feed.review_check_deals == ["deal"]
