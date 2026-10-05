import json
import ssl
import uuid
import time
import traceback
from datetime import datetime, timezone
from logging import getLogger
from typing import Generator
from threading import Thread, Lock, current_thread
from queue import Empty, Queue
from threading import Event as ThreadingEvent
from concurrent.futures import ThreadPoolExecutor
import websocket
from .conn import Conn
from .models import ChatMessage, Chat
from .defs import MarketEvent, RoomKind
from .gql import chat, chat_message, QUERIES
from .response import merge_chat_update, system_event_name
from .stream import proxy_options
from . import models as types
from constants.stream import (
    HYDRATION_ATTEMPTS,
    HYDRATION_DELAY,
    MAX_CHAT_SUBSCRIPTIONS,
    MAX_PARSED_MESSAGE_IDS,
    MAX_TRACKED_CHATS,
    MAX_WATCHED_REVIEWS,
    REVIEW_WATCH_SECONDS,
)
from collections import OrderedDict
import time as time_module


class _BoundedSet:

    def __init__(self, limit: int):
        self.limit = limit
        self._items: OrderedDict = OrderedDict()

    def __contains__(self, key) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def add(self, key) -> None:
        self._items[key] = None
        self._items.move_to_end(key)
        while len(self._items) > self.limit:
            self._items.popitem(last=False)

    def discard(self, key) -> None:
        self._items.pop(key, None)

    def clear(self) -> None:
        self._items.clear()


def _parse_api_datetime(value: str) -> datetime:
    raw = (value or '').strip()
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class StreamCell:

    def __init__(self, event_type: MarketEvent, chat: types.Chat):
        self.type = event_type
        self.chat = chat
        self.time = time_module.time()


class RoomSnapshotReady(StreamCell):

    def __init__(self, chat: types.Chat):
        super().__init__(MarketEvent.CHAT_INITIALIZED, chat)
        self.chat: types.Chat = chat


class ChatIngress(StreamCell):

    def __init__(self, message: types.ChatMessage, chat: types.Chat):
        super().__init__(MarketEvent.NEW_MESSAGE, chat)
        self.message: types.ChatMessage = message


class DealCreatedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.NEW_DEAL, chat)
        self.deal: types.ItemDeal = deal


class ReviewCreatedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.NEW_REVIEW, chat)
        self.deal: types.ItemDeal = deal


class ReviewRemovedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.REVIEW_REMOVED, chat)
        self.deal: types.ItemDeal = deal


class ReviewEditedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat, previous_fp: str):
        super().__init__(MarketEvent.REVIEW_UPDATED, chat)
        self.deal: types.ItemDeal = deal
        self.previous_fp: str = previous_fp


class DealConfirmedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.DEAL_CONFIRMED, chat)
        self.deal: types.ItemDeal = deal


class DealRefundedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.DEAL_ROLLED_BACK, chat)
        self.deal: types.ItemDeal = deal


class DealDisputeRaised(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.DEAL_HAS_PROBLEM, chat)
        self.deal: types.ItemDeal = deal


class DealDisputeCleared(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat, resolver_username: str | None = None):
        super().__init__(MarketEvent.DEAL_PROBLEM_RESOLVED, chat)
        self.deal: types.ItemDeal = deal
        self.resolver_username: str | None = resolver_username


class DealStageChanged(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.DEAL_STATUS_CHANGED, chat)
        self.deal: types.ItemDeal = deal


class ListingPaidNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.ITEM_PAID, chat)
        self.deal: types.ItemDeal = deal


class ListingShippedNotice(StreamCell):

    def __init__(self, deal: types.ItemDeal, chat: types.Chat):
        super().__init__(MarketEvent.ITEM_SENT, chat)
        self.deal: types.ItemDeal = deal


class Feed:

    def __init__(self, conn: Conn, ws_path: str = '/chats', processed_deals: list | None = None,
                 since: datetime | None = None):
        self.conn: Conn = conn
        self._since = since or datetime.now(timezone.utc)
        self.ws_path = '/' + (ws_path or 'chats').strip('/')
        self.chat_subscriptions = {}
        self.review_check_deals = []
        self.review_watch_deals = []
        self.review_snapshots = {}
        self.review_deal_times = {}
        self.review_watch_times = {}
        self.chats = []
        self.processed_deals = processed_deals if processed_deals is not None else []
        self.ws = None
        self.q = None
        self._stop_event = ThreadingEvent()
        self._worker_threads: list[Thread] = []
        self._health_lock = Lock()
        self._connected = False
        self._connected_at: float | None = None
        self._last_message_at: float | None = None
        self._last_ping_at: float | None = None
        self._last_pong_at: float | None = None
        self._last_disconnect_at: float | None = None
        self._last_error: str | None = None
        self._reconnect_count = 0
        self._consecutive_failures = 0
        self._pending_ping_nonce: str | None = None
        self._possible_new_chat = ThreadingEvent()
        self._recover_missed = ThreadingEvent()
        self._deals_lock = Lock()
        self._core_subscriptions: dict[str, str] = {}
        self._last_chat_check = 0
        self._parsed_ws_message_ids = _BoundedSet(MAX_PARSED_MESSAGE_IDS)
        self._ws_message_dedupe_lock = Lock()
        self._ws_send_lock = Lock()
        self._ws_generation_lock = Lock()
        self._ws_generation = 0
        self._ws_generation_socket = None
        self._ws_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='playerok-ws')
        from threading import BoundedSemaphore
        self._ws_capacity = BoundedSemaphore(32)
        self._deal_event_cooldown: dict[str, float] = {}
        self.logger = getLogger('pl.feed')

    @staticmethod
    def _timezone_offset_minutes() -> int:
        if time.localtime().tm_isdst and time.daylight:
            offset_seconds = -time.altzone
        else:
            offset_seconds = -time.timezone
        return int(-(offset_seconds // 60))

    def health(self) -> dict:
        with self._health_lock:
            return {
                'connected': self._connected,
                'connected_at': self._connected_at,
                'last_message_at': self._last_message_at,
                'last_ping_at': self._last_ping_at,
                'last_pong_at': self._last_pong_at,
                'last_disconnect_at': self._last_disconnect_at,
                'last_error': self._last_error,
                'reconnect_count': self._reconnect_count,
                'subscriptions': len(self.chat_subscriptions),
                'stopping': self._stop_event.is_set(),
            }

    def stop(self) -> None:
        self._stop_event.set()
        with self._ws_generation_lock:
            self._ws_generation += 1
            self._ws_generation_socket = None
            closing_ws = self.ws
            self.ws = None
        if closing_ws is not None:
            try:
                closing_ws.close()
            except Exception:
                pass
        self._ws_executor.shutdown(wait=False, cancel_futures=True)
        deadline = time.monotonic() + 2
        for worker in self._worker_threads:
            if worker is current_thread() or not worker.is_alive():
                continue
            worker.join(timeout=max(0.0, deadline - time.monotonic()))

    def _sleep(self, seconds: float) -> bool:
        return self._stop_event.wait(seconds)

    def _report_failure(self, what: str) -> None:
        import sys
        error = sys.exc_info()[1]
        self.logger.warning('%s: %s: %s', what, type(error).__name__ if error else '—', str(error)[:300] if error else '')
        self.logger.debug('Трассировка: %s', traceback.format_exc())

    def _get_actual_message(self, message_id: str, chat_id: str):
        for attempt in range(HYDRATION_ATTEMPTS):
            try:
                msg_list = self.conn.load_messages(chat_id, count=12)
                match = next((msg for msg in msg_list.messages if msg.id == message_id), None)
                if match is not None and match.deal is not None:
                    return match
            except Exception as exc:
                self.logger.debug('Не удалось дозагрузить сообщение %s: %s', message_id, exc)
            if attempt + 1 < HYDRATION_ATTEMPTS and self._sleep(HYDRATION_DELAY):
                return None
        return None

    def _message_shell_empty(self, message: ChatMessage) -> bool:
        if message is None:
            return True
        if message.text:
            return False
        if message.file:
            return False
        if message.images:
            return False
        return True

    def _hydrate_message_if_needed(self, message: ChatMessage, chat_id: str) -> ChatMessage:
        if not self._message_shell_empty(message):
            return message
        delays = (0.0, 0.15, 0.3, 0.5, 0.8)
        for d in delays:
            if d and self._sleep(d):
                return message
            try:
                msg_list = self.conn.load_messages(chat_id, count=24)
            except Exception:
                continue
            for m in msg_list.messages:
                if m.id == message.id:
                    if not self._message_shell_empty(m):
                        return m
                    break
        return message

    _SYSTEM_EVENTS = frozenset({
        'ITEM_PAID', 'ITEM_SENT', 'DEAL_CONFIRMED', 'DEAL_ROLLED_BACK',
        'DEAL_HAS_PROBLEM', 'DEAL_PROBLEM_RESOLVED',
    })

    def _parse_message_events(self, message: ChatMessage, chat_obj: Chat) -> list:
        if not message:
            return []
        event = system_event_name(message)
        if event not in self._SYSTEM_EVENTS:
            return [ChatIngress(message, chat_obj)]
        actual_msg = message if message.deal is not None else (self._get_actual_message(message.id, chat_obj.id) or message)
        deal = actual_msg.deal
        if deal is None:
            return [ChatIngress(message, chat_obj)]
        if event == 'ITEM_PAID':
            with self._deals_lock:
                if deal.id in self.processed_deals:
                    return []
                self.processed_deals.append(deal.id)
                if len(self.processed_deals) > 5000:
                    del self.processed_deals[:1000]
            return [DealCreatedNotice(deal, chat_obj), ListingPaidNotice(deal, chat_obj)]
        if event == 'ITEM_SENT':
            return [ListingShippedNotice(deal, chat_obj), DealStageChanged(deal, chat_obj)]
        if event == 'DEAL_CONFIRMED':
            if deal.id not in self.review_check_deals and deal.id not in self.review_watch_deals:
                self.review_check_deals.append(deal.id)
            return [DealConfirmedNotice(deal, chat_obj), DealStageChanged(deal, chat_obj)]
        if event == 'DEAL_ROLLED_BACK':
            return [DealRefundedNotice(deal, chat_obj), DealStageChanged(deal, chat_obj)]
        if event == 'DEAL_HAS_PROBLEM':
            return [DealDisputeRaised(deal, chat_obj), DealStageChanged(deal, chat_obj)]
        resolver = getattr(getattr(actual_msg, 'user', None), 'username', None)
        return [DealDisputeCleared(deal, chat_obj, resolver_username=resolver)]

    def _generation_is_current(self, generation: int | None) -> bool:
        if generation is None:
            return True
        with self._ws_generation_lock:
            return generation == self._ws_generation and self.ws is self._ws_generation_socket

    def _send_ws(self, payload: dict, generation: int | None = None) -> bool:
        if not self._generation_is_current(generation):
            return False
        encoded = json.dumps(payload)
        with self._ws_send_lock:
            if not self._generation_is_current(generation):
                return False
            ws = self.ws
            if ws is None:
                raise ConnectionError('WebSocket is not connected')
            ws.send(encoded)
            return True

    def _send_connection_init(self, generation: int | None = None):
        self._send_ws({
            'type': 'connection_init',
            'payload': {
                'x-gql-op': 'ws-subscription',
                'x-gql-path': self.ws_path,
                'x-timezone-offset': self._timezone_offset_minutes(),
            },
        }, generation)

    def _subscribe_core(self, operation: str, variables: dict, generation: int | None = None):
        sub_id = str(uuid.uuid4())
        sent = self._send_ws({'id': sub_id, 'payload': {'extensions': {}, 'operationName': operation, 'query': QUERIES.get(operation), 'variables': variables}, 'type': 'subscribe'}, generation)
        if sent and self._generation_is_current(generation):
            self._core_subscriptions[sub_id] = operation

    def _subscribe_chat_updated(self, generation: int | None = None):
        self._subscribe_core('chatUpdated', {'filter': {'userId': self.conn.id}, 'showForbiddenImage': True}, generation)

    def _subscribe_chat_marked_as_read(self, generation: int | None = None):
        self._subscribe_core('chatMarkedAsRead', {'filter': {'userId': self.conn.id}, 'showForbiddenImage': True}, generation)

    def _subscribe_user_updated(self, generation: int | None = None):
        self._subscribe_core('userUpdated', {'userId': self.conn.id}, generation)

    def _handle_subscription_end(self, msg_data: dict, generation: int | None) -> None:
        sub_id = msg_data.get('id')
        chat_id = self.chat_subscriptions.pop(sub_id, None)
        operation = self._core_subscriptions.pop(sub_id, None)
        if msg_data.get('type') != 'error':
            if operation and self._generation_is_current(generation):
                self.logger.warning('Сервер завершил подписку %s — переподключение', operation)
                self._close_current(generation)
            return
        errors = msg_data.get('payload')
        details = '; '.join(str(e.get('message') or e) for e in errors if isinstance(e, dict)) if isinstance(errors, list) else str(errors)
        target = operation or (f'чат {chat_id}' if chat_id else sub_id)
        self.logger.warning('Подписка WebSocket отклонена (%s): %s', target, details[:300])
        with self._health_lock:
            self._last_error = f'subscription {target}: {details[:200]}'

    def _close_current(self, generation: int | None) -> None:
        with self._ws_generation_lock:
            ws = self.ws if generation is None or generation == self._ws_generation else None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _subscribe_chat_message_created(self, chat_id, generation: int | None = None):
        _uuid = str(uuid.uuid4())
        sent = self._send_ws({'id': _uuid, 'payload': {'extensions': {}, 'operationName': 'chatMessageCreated', 'query': QUERIES.get('chatMessageCreated'), 'variables': {'filter': {'chatId': chat_id}, 'showForbiddenImage': True}}, 'type': 'subscribe'}, generation)
        if sent and self._generation_is_current(generation):
            self.chat_subscriptions[_uuid] = chat_id

    def _is_chat_subscribed(self, chat_id):
        for _, sub_chat_id in self.chat_subscriptions.items():
            if chat_id == sub_chat_id:
                return True
        return False

    _DEAL_EVENT_COOLDOWN_SEC = 12.0

    def _apply_deal_event_cooldown(self, events: list) -> list:
        if not events:
            return events
        now = time.time()
        out = []
        cool = self._DEAL_EVENT_COOLDOWN_SEC
        for ev in events:
            t = getattr(ev, 'type', None)
            if t in (MarketEvent.DEAL_PROBLEM_RESOLVED, MarketEvent.DEAL_HAS_PROBLEM):
                deal = getattr(ev, 'deal', None)
                did = getattr(deal, 'id', None) if deal else None
                if did:
                    ck = f'{t.name}:{did}'
                    with self._ws_message_dedupe_lock:
                        last = self._deal_event_cooldown.get(ck)
                        if last is not None and (now - last) < cool:
                            self.logger.debug('[feed] пропуск дубля по cooldown %s (%.2fs назад)', ck, now - last)
                            continue
                        self._deal_event_cooldown[ck] = now
                        if len(self._deal_event_cooldown) > 8000:
                            self._deal_event_cooldown.clear()
            out.append(ev)
        return out

    def _events_for_chat_message(self, chat_obj: Chat, message: ChatMessage) -> list:
        mid = getattr(message, 'id', None)
        key = (chat_obj.id, mid) if mid else None
        if key:
            with self._ws_message_dedupe_lock:
                if key in self._parsed_ws_message_ids:
                    return []
                self._parsed_ws_message_ids.add(key)
        try:
            out = self._parse_message_events(message, chat_obj)
        except Exception:
            if key:
                with self._ws_message_dedupe_lock:
                    self._parsed_ws_message_ids.discard(key)
            raise
        if key and not out:
            with self._ws_message_dedupe_lock:
                self._parsed_ws_message_ids.discard(key)
        return self._apply_deal_event_cooldown(out)

    def _merge_chat(self, incoming: Chat) -> Chat:
        existing = next((c for c in list(self.chats) if c.id == incoming.id), None)
        if existing is None and (not incoming.type or not incoming.users):
            try:
                existing = self.conn.load_chat(incoming.id)
            except Exception as exc:
                self.logger.warning('Не удалось загрузить новый чат %s: %s', incoming.id, exc)
        return merge_chat_update(existing, incoming)

    def _process_new_chat_message(self, chat_obj, message, generation: int | None = None):
        events = []
        if message is not None:
            message = self._hydrate_message_if_needed(message, chat_obj.id)
        if not self._generation_is_current(generation):
            return events
        is_subscribed = self._is_chat_subscribed(chat_obj.id)
        is_new_chat = chat_obj.id not in [c.id for c in self.chats]
        if is_new_chat:
            self.chats.append(chat_obj)
        else:
            for old_chat in list(self.chats):
                if old_chat.id == chat_obj.id:
                    self.chats.remove(old_chat)
                    self.chats.append(chat_obj)
                    break
        if len(self.chats) > MAX_TRACKED_CHATS:
            del self.chats[:len(self.chats) - MAX_TRACKED_CHATS]
        if not is_subscribed:
            self._subscribe_chat_message_created(chat_obj.id, generation)
            self._trim_chat_subscriptions(generation)
            if is_new_chat:
                events.append(RoomSnapshotReady(chat_obj))
        if message is not None:
            events.extend(self._events_for_chat_message(chat_obj, message))
        if not self._generation_is_current(generation):
            return []
        return events

    def _recent_chats(self) -> list:
        return self.chats[-MAX_CHAT_SUBSCRIPTIONS:]

    def _trim_chat_subscriptions(self, generation: int | None = None) -> None:
        if len(self.chat_subscriptions) <= MAX_CHAT_SUBSCRIPTIONS:
            return
        active = {c.id for c in self._recent_chats()}
        for sub_id, chat_id in list(self.chat_subscriptions.items()):
            if chat_id in active:
                continue
            self.chat_subscriptions.pop(sub_id, None)
            try:
                self._send_ws({'id': sub_id, 'type': 'complete'}, generation)
            except Exception as exc:
                self.logger.debug('Не удалось завершить подписку %s: %s', sub_id, exc)

    def _proccess_new_chat_message(self, chat_obj, message):
        return self._process_new_chat_message(chat_obj, message)

    def process_ws_message(self, msg, generation: int | None = None):
        try:
            if not self._generation_is_current(generation):
                return
            try:
                msg_data = json.loads(msg)
            except json.JSONDecodeError:
                return
            message_type = msg_data.get('type')
            now = time.monotonic()
            with self._health_lock:
                self._last_message_at = now
            if message_type == 'ping':
                response = {'type': 'pong'}
                if 'payload' in msg_data:
                    response['payload'] = msg_data['payload']
                if self._send_ws(response, generation):
                    with self._health_lock:
                        self._last_pong_at = now
                return
            if message_type == 'pong':
                nonce = (msg_data.get('payload') or {}).get('nonce')
                with self._health_lock:
                    if self._pending_ping_nonce is None or nonce == self._pending_ping_nonce:
                        self._pending_ping_nonce = None
                        self._last_pong_at = now
                return
            if message_type in ('error', 'complete'):
                self._handle_subscription_end(msg_data, generation)
                return
            payload = msg_data.get('payload')
            payload_data = (payload.get('data') if isinstance(payload, dict) else None) or {}
            self.logger.debug(
                'WS -> type=%s data_keys=%s',
                msg_data.get('type'),
                sorted(payload_data) if isinstance(payload_data, dict) else [],
            )
            if message_type == 'connection_ack':
                try:
                    self.chat_subscriptions.clear()
                    self._core_subscriptions.clear()
                    self._subscribe_chat_updated(generation)
                    self._subscribe_chat_marked_as_read(generation)
                    self._subscribe_user_updated(generation)
                    for chat_ in self._recent_chats():
                        self._subscribe_chat_message_created(chat_.id, generation)
                except Exception as exc:
                    with self._health_lock:
                        self._connected = False
                        self._last_error = f'subscribe: {type(exc).__name__}: {exc}'
                    if self._generation_is_current(generation):
                        try:
                            self.ws.close()
                        except Exception:
                            pass
                    raise
                else:
                    with self._health_lock:
                        self._connected = True
                        self._connected_at = now
                        self._last_error = None
                        self._consecutive_failures = 0
                        reconnected = self._last_disconnect_at is not None
                    if reconnected:
                        self._recover_missed.set()
                        self._possible_new_chat.set()
            else:
                updated_user = payload_data.get('userUpdated')
                if isinstance(updated_user, dict):
                    try:
                        unread_chats = int(updated_user.get('unreadChatsCounter') or 0)
                    except (TypeError, ValueError):
                        unread_chats = 0
                    if unread_chats > 0:
                        self._possible_new_chat.set()
                if payload_data.get('chatUpdated'):
                    _chat = self._merge_chat(chat(payload_data['chatUpdated']))
                    _message = chat_message(payload_data['chatUpdated'].get('lastMessage'))
                    events = self._process_new_chat_message(_chat, _message, generation)
                    for event in events:
                        if self._generation_is_current(generation):
                            self.q.put(event)
                if 'chatMessageCreated' in payload_data:
                    chat_id = self.chat_subscriptions.get(msg_data['id'])
                    try:
                        _chat = [c for c in self.chats if c.id == chat_id][0]
                    except Exception:
                        return
                    _message = chat_message(payload_data['chatMessageCreated'])
                    _message = self._hydrate_message_if_needed(_message, _chat.id)
                    if not self._generation_is_current(generation):
                        return
                    events = self._events_for_chat_message(_chat, _message)
                    for event in events:
                        if self._generation_is_current(generation):
                            self.q.put(event)
        except Exception:
            self._report_failure('Ошибка обработки сообщения WebSocket')

    def _dispatch_ws_message(self, msg: str, generation: int) -> bool:
        if not self._ws_capacity.acquire(blocking=False):
            self.logger.warning('WebSocket очередь переполнена — переподключение для восстановления событий')
            if self._generation_is_current(generation):
                try:
                    self.ws.close()
                except Exception:
                    pass
            return False
        try:
            future = self._ws_executor.submit(self.process_ws_message, msg, generation)
        except Exception:
            self._ws_capacity.release()
            raise
        future.add_done_callback(lambda _future: self._ws_capacity.release())
        return True

    def _dispatch_incoming_ws_message(self, msg: str, generation: int) -> bool:
        try:
            message_type = json.loads(msg).get('type')
        except (json.JSONDecodeError, AttributeError):
            message_type = None
        if message_type in {'ping', 'pong', 'connection_ack'}:
            self.process_ws_message(msg, generation)
            return True
        return self._dispatch_ws_message(msg, generation)

    def proccess_ws_message(self, msg):
        return self.process_ws_message(msg)

    def listen_new_messages(self):
        base_headers = {'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7', 'cache-control': 'no-cache', 'pragma': 'no-cache', 'user-agent': self.conn.user_agent}
        self.chats = []
        for attempt in range(5):
            try:
                self.chats = [c for c in self.conn.load_chats(count=24).chats if c is not None]
                break
            except Exception as exc:
                self.logger.warning('Не удалось загрузить список чатов (%s/5): %s', attempt + 1, exc)
                if self._sleep(min(30, 3 * (attempt + 1))):
                    return
        for chat_ in self.chats:
            yield RoomSnapshotReady(chat_)
        while not self._stop_event.is_set():
            generation = None
            closing_ws = None
            retry_delay = 0
            try:
                cookie_hdr = self.conn._cookie_header() or f'token={self.conn.token}'
                with self._ws_generation_lock:
                    self._ws_generation += 1
                    generation = self._ws_generation
                    self._ws_generation_socket = None
                ws = websocket.WebSocket(sslopt={'ca_certs': self.conn._ca_bundle})
                ws.settimeout(30)
                with self._ws_generation_lock:
                    self.ws = ws
                    self._ws_generation_socket = ws
                ws.connect(
                    'wss://ws.playerok.com/graphql',
                    origin='https://playerok.com',
                    cookie=cookie_hdr,
                    header=[f'{k}: {v}' for k, v in base_headers.items()],
                    subprotocols=['graphql-transport-ws'],
                    timeout=30,
                    **proxy_options(getattr(self.conn, 'proxy_url', None)),
                )
                if not self._generation_is_current(generation) or self._stop_event.is_set():
                    return
                with self._health_lock:
                    if self._last_disconnect_at is not None:
                        self._reconnect_count += 1
                    self._connected = False
                    self._pending_ping_nonce = None
                self.chat_subscriptions.clear()
                self._send_connection_init(generation)
                ack_deadline = time.monotonic() + 30
                pong_deadline = None
                while not self._stop_event.is_set():
                    now = time.monotonic()
                    with self._health_lock:
                        is_acked = self._connected
                        pending_nonce = self._pending_ping_nonce
                    active_deadline = pong_deadline if pending_nonce is not None else (None if is_acked else ack_deadline)
                    if active_deadline is not None and now >= active_deadline:
                        reason = 'pong' if pending_nonce is not None else 'ACK'
                        raise TimeoutError(f'Playerok WebSocket {reason} timeout')
                    self.ws.settimeout(max(0.1, min(30, (active_deadline - now) if active_deadline else 30)))
                    try:
                        msg = self.ws.recv()
                    except websocket._exceptions.WebSocketTimeoutException:
                        with self._health_lock:
                            is_acked = self._connected
                            pending_nonce = self._pending_ping_nonce
                        if not is_acked:
                            raise TimeoutError('Playerok WebSocket ACK timeout')
                        if pending_nonce is not None:
                            raise TimeoutError('Playerok WebSocket pong timeout')
                        nonce = uuid.uuid4().hex
                        with self._health_lock:
                            self._pending_ping_nonce = nonce
                            self._last_ping_at = time.monotonic()
                        pong_deadline = time.monotonic() + 15
                        self._send_ws({'type': 'ping', 'payload': {'nonce': nonce}}, generation)
                        continue
                    if not msg:
                        with self._health_lock:
                            acked = self._connected
                        if not acked:
                            raise ConnectionError('Playerok закрыл WebSocket до подтверждения — вероятно, Cookie устарели или не подходят к IP/User-Agent')
                        raise ConnectionError('Playerok WebSocket closed')
                    self._dispatch_incoming_ws_message(msg, generation)
                    with self._health_lock:
                        pending_after = self._pending_ping_nonce
                    if pending_after is None:
                        pong_deadline = None
                    elif pong_deadline is not None and time.monotonic() >= pong_deadline:
                        raise TimeoutError('Playerok WebSocket pong timeout')
                    if not self.health()['connected'] and time.monotonic() >= ack_deadline:
                        raise TimeoutError('Playerok WebSocket ACK timeout')
            except websocket._exceptions.WebSocketException as e:
                if not self._stop_event.is_set():
                    with self._health_lock:
                        self._last_error = f'{type(e).__name__}: {e}'
                        self._consecutive_failures += 1
                    delay = min(30, 2 ** min(self._consecutive_failures, 5))
                    self.logger.warning('WebSocket: %s — переподключение через %s с', e, delay)
                    retry_delay = delay
            except (ssl.SSLError, OSError, ConnectionError, BrokenPipeError, TimeoutError) as e:
                if not self._stop_event.is_set():
                    with self._health_lock:
                        self._last_error = f'{type(e).__name__}: {e}'
                        self._consecutive_failures += 1
                    delay = min(30, 2 ** min(self._consecutive_failures, 5))
                    self.logger.warning(
                        'WebSocket TLS/сеть (%s): %s — переподключение через %s с',
                        type(e).__name__, e, delay,
                    )
                    retry_delay = delay
            finally:
                with self._ws_generation_lock:
                    self._ws_generation += 1
                    self._ws_generation_socket = None
                    closing_ws = self.ws
                    self.ws = None
                with self._health_lock:
                    self._connected = False
                    self._last_disconnect_at = time.monotonic()
                    self._pending_ping_nonce = None
                try:
                    if closing_ws is not None:
                        closing_ws.close()
                except Exception:
                    pass
            if retry_delay and self._sleep(retry_delay):
                return

    def _review_fingerprint(self, rev: types.Review | None) -> str | None:
        if not rev:
            return None
        st = rev.status.name if rev.status else ''
        return json.dumps(
            {'id': rev.id, 'rating': rev.rating, 'status': st, 'text': (rev.text or '')},
            sort_keys=True,
            ensure_ascii=False,
        )

    def _should_check_review_deal(self, deal_id, delay=30, max_tries=72) -> bool:
        now = time.time()
        info = self.review_deal_times.get(deal_id, {'last': 0, 'tries': 0})
        last_time = info['last']
        tries = info['tries']
        if now - last_time > delay:
            self.review_deal_times[deal_id] = {'last': now, 'tries': tries + 1}
            return True
        elif tries >= max_tries:
            if deal_id in self.review_check_deals:
                self.review_check_deals.remove(deal_id)
            del self.review_deal_times[deal_id]
        return False

    def _forget_watched_review(self, deal_id) -> None:
        if deal_id in self.review_watch_deals:
            self.review_watch_deals.remove(deal_id)
        self.review_snapshots.pop(deal_id, None)
        self.review_watch_times.pop(deal_id, None)

    def _should_check_watch_deal(self, deal_id, delay=120, lifetime=REVIEW_WATCH_SECONDS) -> bool:
        now = time.time()
        while len(self.review_watch_deals) > MAX_WATCHED_REVIEWS:
            self._forget_watched_review(self.review_watch_deals[0])
        info = self.review_watch_times.setdefault(deal_id, {'last': 0, 'tries': 0, 'started': now})
        if now - info.get('started', now) > lifetime:
            self._forget_watched_review(deal_id)
            return False
        if now - info['last'] > delay:
            info['last'] = now
            info['tries'] += 1
            return True
        return False

    def _resolve_deal_chat(self, deal: types.ItemDeal) -> None:
        try:
            deal.chat = [c for c in self.chats if c.id == deal.chat.id][0]
        except Exception:
            try:
                deal.chat = self.conn.load_chat(deal.chat.id)
            except Exception:
                pass

    def listen_new_reviews(self):
        while not self._stop_event.is_set():
            for deal_id in list(self.review_check_deals):
                try:
                    if not self._should_check_review_deal(deal_id):
                        continue
                    try:
                        deal = self.conn.load_deal(deal_id)
                    except Exception:
                        continue
                    fp = self._review_fingerprint(deal.review)
                    old = self.review_snapshots.get(deal_id)
                    if fp and old is None:
                        self.review_snapshots[deal_id] = fp
                        self.review_check_deals.remove(deal_id)
                        self.review_watch_deals.append(deal_id)
                        self._resolve_deal_chat(deal)
                        yield ReviewCreatedNotice(deal, deal.chat)
                except Exception:
                    self.logger.debug(f'Ошибка проверки новых отзывов в сделке {deal_id}: {traceback.format_exc()}')

            for deal_id in list(self.review_watch_deals):
                try:
                    if not self._should_check_watch_deal(deal_id):
                        continue
                    try:
                        deal = self.conn.load_deal(deal_id)
                    except Exception:
                        continue
                    fp = self._review_fingerprint(deal.review)
                    old = self.review_snapshots.get(deal_id)
                    if old and not fp:
                        self.review_snapshots[deal_id] = None
                        self._resolve_deal_chat(deal)
                        yield ReviewRemovedNotice(deal, deal.chat)
                    elif fp and old and fp != old:
                        self.review_snapshots[deal_id] = fp
                        self._resolve_deal_chat(deal)
                        yield ReviewEditedNotice(deal, deal.chat, previous_fp=old)
                    elif fp and old is None:
                        self.review_snapshots[deal_id] = fp
                        self._resolve_deal_chat(deal)
                        yield ReviewCreatedNotice(deal, deal.chat)
                except Exception:
                    self.logger.debug(f'Ошибка отслеживания отзыва по сделке {deal_id}: {traceback.format_exc()}')
            if self._sleep(1):
                return

    def _wait_for_check_new_chats(self, delay=10):
        sleep_time = delay - (time.time() - self._last_chat_check)
        if sleep_time > 0:
            self._sleep(sleep_time)

    def _deal_processed(self, deal_id: str) -> bool:
        with self._deals_lock:
            return deal_id in self.processed_deals

    def _recent_paid_messages(self, chat_id: str, window: float = 600) -> list:
        now = datetime.now(timezone.utc)
        found = []
        for msg in self.conn.load_messages(chat_id, count=12).messages:
            if not msg or system_event_name(msg) != 'ITEM_PAID':
                continue
            try:
                created = _parse_api_datetime(msg.created_at)
            except (TypeError, ValueError, AttributeError):
                continue
            deal_id = getattr(getattr(msg, 'deal', None), 'id', None)
            fresh = created >= self._since and (now - created).total_seconds() <= window
            if fresh and not (deal_id and self._deal_processed(deal_id)):
                found.append(msg)
        return list(reversed(found))

    def listen_new_deals(self):
        while not self._stop_event.is_set():
            try:
                if not self._possible_new_chat.wait(timeout=1):
                    continue
                if self._stop_event.is_set():
                    return
                self._wait_for_check_new_chats()
                self._last_chat_check = time.time()
                self._possible_new_chat.clear()
                recovering = self._recover_missed.is_set()
                self._recover_missed.clear()
                known_chat_ids = [c.id for c in self.chats]
                chats = []
                for _ in range(3):
                    if self._sleep(2):
                        return
                    try:
                        chats = [c for c in self.conn.load_chats(count=10 if recovering else 5, type=RoomKind.PM).chats if c is not None]
                        break
                    except Exception as exc:
                        self.logger.debug('Не удалось получить последние чаты: %s', exc)
                for chat_obj in chats:
                    last = chat_obj.last_message
                    last_is_paid = bool(last) and system_event_name(last) == 'ITEM_PAID'
                    known = chat_obj.id in known_chat_ids
                    if last_is_paid:
                        last_deal_id = getattr(getattr(last, 'deal', None), 'id', None)
                        if not known or (last_deal_id and not self._deal_processed(last_deal_id)):
                            for event in self._process_new_chat_message(chat_obj, last):
                                yield event
                        continue
                    if known and not recovering:
                        continue
                    try:
                        for paid_msg in self._recent_paid_messages(chat_obj.id):
                            for event in self._process_new_chat_message(chat_obj, paid_msg):
                                yield event
                    except Exception:
                        self._report_failure(f'Ошибка получения истории чата {chat_obj.id}')
            except websocket._exceptions.WebSocketException:
                pass
            except Exception:
                self._report_failure('Ошибка проверки новых сделок')

    def listen(self, get_new_message_events: bool = True, get_new_review_events: bool = True) -> Generator:
        if not any((get_new_review_events, get_new_message_events)):
            return
        self.q = Queue()

        def run(gen):
            try:
                for event in gen:
                    if self._stop_event.is_set():
                        return
                    self.q.put(event)
            except Exception:
                if not self._stop_event.is_set():
                    self.logger.exception('Фоновый обработчик Playerok Feed завершился с ошибкой')

        if get_new_message_events:
            self._worker_threads.append(Thread(target=run, args=(self.listen_new_messages(),), daemon=True, name='playerok-ws-listener'))
            self._worker_threads.append(Thread(target=run, args=(self.listen_new_deals(),), daemon=True, name='playerok-deal-listener'))
        if get_new_review_events:
            self._worker_threads.append(Thread(target=run, args=(self.listen_new_reviews(),), daemon=True, name='playerok-review-listener'))
        for worker in self._worker_threads:
            worker.start()
        while not self._stop_event.is_set():
            try:
                yield self.q.get(timeout=1)
            except Empty:
                dead = [worker.name for worker in self._worker_threads if not worker.is_alive()]
                if dead and not self._stop_event.is_set():
                    raise RuntimeError(f'Playerok Feed workers stopped: {", ".join(dead)}')
                continue
