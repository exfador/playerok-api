import json
import ssl
import uuid
import time
import traceback
from datetime import datetime, timezone
from logging import getLogger
from typing import Generator
from threading import Thread, Lock
from queue import Queue
from threading import Event as ThreadingEvent
import websocket
from .conn import Conn
from .models import ChatMessage, Chat, ItemDeal
from .defs import MarketEvent, RoomKind
from .gql import chat, chat_message, QUERIES
from . import models as types
import time as time_module


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

    def __init__(self, conn: Conn):
        self.conn: Conn = conn
        self.chat_subscriptions = {}
        self.review_check_deals = []
        self.review_watch_deals = []
        self.review_snapshots = {}
        self.review_deal_times = {}
        self.review_watch_times = {}
        self.chats = []
        self.processed_deals = []
        self.active_deals = {}
        self.last_st_deal_times = {}
        self.ws = None
        self.q = None
        self._possible_new_chat = ThreadingEvent()
        self._last_chat_check = 0
        self._parsed_ws_message_ids: set = set()
        self._ws_message_dedupe_lock = Lock()
        self._deal_event_cooldown: dict[str, float] = {}
        self.logger = getLogger('pl.feed')

    def _get_actual_message(self, message_id: str, chat_id: str):
        for _ in range(3):
            time.sleep(6)
            try:
                msg_list = self.conn.load_messages(chat_id, count=12)
            except Exception:
                return
            try:
                return [msg for msg in msg_list.messages if msg.id == message_id][0]
            except Exception:
                pass

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
            if d:
                time.sleep(d)
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

    def _set_active_deal(self, chat_obj: types.Chat, deal: types.ItemDeal, status_date: datetime):
        if chat_obj.id not in self.active_deals:
            self.active_deals[chat_obj.id] = []
        try:
            deal_tuple = next((t for t in self.active_deals[chat_obj.id] if t[0] == deal.id))
        except StopIteration:
            deal_tuple = ()
        if not deal_tuple:
            self.active_deals[chat_obj.id].append((deal.id, deal.status, status_date))
        else:
            indx = self.active_deals[chat_obj.id].index(deal_tuple)
            self.active_deals[chat_obj.id][indx] = (deal.id, deal.status, status_date)

    def _parse_message_events(self, message: ChatMessage, chat_obj: Chat) -> list:
        if not message:
            return []
        if message.text == '{{ITEM_PAID}}':
            actual_msg = self._get_actual_message(message.id, chat_obj.id) or message
            if actual_msg and actual_msg.deal:
                deal_id = actual_msg.deal.id
                if deal_id not in self.review_check_deals:
                    self.review_check_deals.append(deal_id)
                if deal_id not in self.processed_deals:
                    self.processed_deals.append(deal_id)
                else:
                    return []
                return [DealCreatedNotice(actual_msg.deal, chat_obj), ListingPaidNotice(actual_msg.deal, chat_obj)]
        elif message.text == '{{ITEM_SENT}}':
            actual_msg = self._get_actual_message(message.id, chat_obj.id) or message
            if actual_msg and actual_msg.deal:
                return [ListingShippedNotice(actual_msg.deal, chat_obj), DealStageChanged(actual_msg.deal, chat_obj)]
        elif message.text == '{{DEAL_CONFIRMED}}':
            actual_msg = self._get_actual_message(message.id, chat_obj.id) or message
            if actual_msg and actual_msg.deal:
                deal_id = actual_msg.deal.id
                if deal_id not in self.review_check_deals and deal_id not in self.review_watch_deals:
                    self.review_check_deals.append(deal_id)
                return [DealConfirmedNotice(actual_msg.deal, chat_obj), DealStageChanged(actual_msg.deal, chat_obj)]
        elif message.text == '{{DEAL_ROLLED_BACK}}':
            actual_msg = self._get_actual_message(message.id, chat_obj.id) or message
            if actual_msg and actual_msg.deal:
                return [DealRefundedNotice(actual_msg.deal, chat_obj), DealStageChanged(actual_msg.deal, chat_obj)]
        elif message.text == '{{DEAL_HAS_PROBLEM}}':
            actual_msg = self._get_actual_message(message.id, chat_obj.id) or message
            if actual_msg and actual_msg.deal:
                return [DealDisputeRaised(actual_msg.deal, chat_obj), DealStageChanged(actual_msg.deal, chat_obj)]
        elif message.text == '{{DEAL_PROBLEM_RESOLVED}}':
            actual_msg = self._get_actual_message(message.id, chat_obj.id) or message
            if actual_msg and actual_msg.deal:
                ru = getattr(getattr(actual_msg, 'user', None), 'username', None)
                return [DealDisputeCleared(actual_msg.deal, chat_obj, resolver_username=ru)]
        return [ChatIngress(message, chat_obj)]

    def _send_connection_init(self):
        self.ws.send(json.dumps({'type': 'connection_init', 'payload': {'x-gql-op': 'ws-subscription', 'x-gql-path': '/self.chats/[id]', 'x-timezone-offset': -180}}))

    def _subscribe_chat_updated(self):
        self.ws.send(json.dumps({'id': str(uuid.uuid4()), 'payload': {'extensions': {}, 'operationName': 'chatUpdated', 'query': QUERIES.get('chatUpdated'), 'variables': {'filter': {'userId': self.conn.id}, 'showForbiddenImage': True}}, 'type': 'subscribe'}))

    def _subscribe_chat_marked_as_read(self):
        self.ws.send(json.dumps({'id': str(uuid.uuid4()), 'payload': {'extensions': {}, 'operationName': 'chatMarkedAsRead', 'query': QUERIES.get('chatMarkedAsRead'), 'variables': {'filter': {'userId': self.conn.id}, 'showForbiddenImage': True}}, 'type': 'subscribe'}))

    def _subscribe_user_updated(self):
        self.ws.send(json.dumps({'id': str(uuid.uuid4()), 'payload': {'extensions': {}, 'operationName': 'userUpdated', 'query': QUERIES.get('userUpdated'), 'variables': {'userId': self.conn.id}}, 'type': 'subscribe'}))

    def _subscribe_chat_message_created(self, chat_id):
        _uuid = str(uuid.uuid4())
        self.chat_subscriptions[_uuid] = chat_id
        self.ws.send(json.dumps({'id': _uuid, 'payload': {'extensions': {}, 'operationName': 'chatMessageCreated', 'query': QUERIES.get('chatMessageCreated'), 'variables': {'filter': {'chatId': chat_id}}}, 'type': 'subscribe'}))

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
                if len(self._parsed_ws_message_ids) > 50000:
                    self._parsed_ws_message_ids.clear()
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

    def _proccess_new_chat_message(self, chat_obj, message):
        events = []
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
        if not is_subscribed:
            self._subscribe_chat_message_created(chat_obj.id)
            if is_new_chat:
                events.append(RoomSnapshotReady(chat_obj))
        events.extend(self._events_for_chat_message(chat_obj, message))
        return events

    def proccess_ws_message(self, msg):
        try:
            try:
                msg_data = json.loads(msg)
            except json.JSONDecodeError:
                return
            self.logger.debug(f'WS -> {msg_data}')
            if msg_data['type'] == 'connection_ack':
                self._subscribe_chat_updated()
                self._subscribe_user_updated()
                for chat_ in self.chats:
                    self._subscribe_chat_message_created(chat_.id)
            else:
                payload_data = msg_data.get('payload', {}).get('data', {})
                if 'userUpdated' in payload_data:
                    unread_chats = payload_data['userUpdated'].get('unreadChatsCounter', 0)
                    if unread_chats > 0:
                        self._possible_new_chat.set()
                if 'chatUpdated' in payload_data:
                    _chat = chat(payload_data['chatUpdated'])
                    _message = chat_message(payload_data['chatUpdated']['lastMessage'])
                    events = self._proccess_new_chat_message(_chat, _message)
                    for event in events:
                        self.q.put(event)
                if 'chatMessageCreated' in payload_data:
                    chat_id = self.chat_subscriptions.get(msg_data['id'])
                    try:
                        _chat = [c for c in self.chats if c.id == chat_id][0]
                    except Exception:
                        return
                    _message = chat_message(payload_data['chatMessageCreated'])
                    _message = self._hydrate_message_if_needed(_message, _chat.id)
                    events = self._events_for_chat_message(_chat, _message)
                    for event in events:
                        self.q.put(event)
        except Exception:
            self.logger.debug(f'Ошибка обработки сообщения в WebSocket`е: {traceback.format_exc()}')

    def listen_new_messages(self):
        headers = {'accept-encoding': 'gzip, deflate, br, zstd', 'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7', 'cache-control': 'no-cache', 'connection': 'Upgrade', 'origin': 'https://playerok.com', 'pragma': 'no-cache', 'sec-websocket-extensions': 'permessage-deflate; client_max_window_bits', 'cookie': f'token={self.conn.token}', 'user-agent': self.conn.user_agent}
        try:
            self.chats = self.conn.load_chats(count=24).chats
        except Exception:
            self.chats = []
        for chat_ in self.chats:
            yield RoomSnapshotReady(chat_)
        while True:
            try:
                self.ws = websocket.WebSocket(sslopt={'ca_certs': self.conn._ca_bundle})
                self.ws.connect(url='wss://ws.playerok.com/graphql', header=[f'{k}: {v}' for k, v in headers.items()], subprotocols=['graphql-transport-ws'])
                self._send_connection_init()
                while True:
                    msg = self.ws.recv()
                    Thread(target=self.proccess_ws_message, args=(msg,), daemon=True).start()
            except websocket._exceptions.WebSocketException as e:
                self.logger.warning('WebSocket: %s — переподключение через 3 с', e)
                time.sleep(3)
            except (ssl.SSLError, OSError, ConnectionError, BrokenPipeError, TimeoutError) as e:
                self.logger.warning(
                    'WebSocket TLS/сеть (%s): %s — переподключение через 5 с',
                    type(e).__name__,
                    e,
                )
                time.sleep(5)
            finally:
                try:
                    if self.ws is not None:
                        self.ws.close()
                except Exception:
                    pass
                self.ws = None

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

    def _should_check_watch_deal(self, deal_id, delay=90, max_tries=100000) -> bool:
        now = time.time()
        info = self.review_watch_times.get(deal_id, {'last': 0, 'tries': 0})
        last_time = info['last']
        tries = info['tries']
        if now - last_time > delay:
            self.review_watch_times[deal_id] = {'last': now, 'tries': tries + 1}
            return True
        if tries >= max_tries:
            if deal_id in self.review_watch_deals:
                self.review_watch_deals.remove(deal_id)
            self.review_snapshots.pop(deal_id, None)
            self.review_watch_times.pop(deal_id, None)
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
        while True:
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
            time.sleep(1)

    def _wait_for_check_new_chats(self, delay=10):
        sleep_time = delay - (time.time() - self._last_chat_check)
        if sleep_time > 0:
            time.sleep(sleep_time)

    def listen_new_deals(self):
        while True:
            try:
                self._possible_new_chat.wait()
                self._wait_for_check_new_chats()
                self._last_chat_check = time.time()
                self._possible_new_chat.clear()
                known_chat_ids = [c.id for c in self.chats]
                for _ in range(3):
                    try:
                        time.sleep(6)
                        chats = self.conn.load_chats(count=5, type=RoomKind.PM).chats
                        break
                    except Exception:
                        chats = []
                for chat_obj in chats:
                    if chat_obj.id in known_chat_ids:
                        if chat_obj.last_message and chat_obj.last_message.text == '{{ITEM_PAID}}':
                            lm = chat_obj.last_message
                            lm_deal = getattr(lm, 'deal', None)
                            lm_deal_id = getattr(lm_deal, 'id', None) if lm_deal else None
                            if lm_deal_id and lm_deal_id not in self.processed_deals:
                                events = self._proccess_new_chat_message(chat_obj, lm)
                                for event in events:
                                    yield event
                        continue
                    if chat_obj.last_message and chat_obj.last_message.text == '{{ITEM_PAID}}':
                        events = self._proccess_new_chat_message(chat_obj, chat_obj.last_message)
                        for event in events:
                            yield event
                        continue
                    try:
                        msg_list = self.conn.load_messages(chat_obj.id, count=12)
                        new_paid_msg = next((msg for msg in msg_list.messages if msg.text == '{{ITEM_PAID}}' and (datetime.now(timezone.utc) - datetime.fromisoformat(msg.created_at).astimezone(timezone.utc)).total_seconds() <= 120), None)
                        if new_paid_msg:
                            events = self._proccess_new_chat_message(chat_obj, new_paid_msg)
                            for event in events:
                                yield event
                    except Exception:
                        self.logger.debug(f'Ошибка получения истории для нового чата {chat_obj.id}: {traceback.format_exc()}')
            except websocket._exceptions.WebSocketException:
                pass
            except Exception:
                self.logger.debug(f'Ошибка проверки новых сделок: {traceback.format_exc()}')

    def listen_deal_statuses(self):
        while True:
            for chat_id, deals in list(self.active_deals.items()):
                messages = []
                for _ in range(3):
                    try:
                        msg_list = self.conn.load_messages(chat_id, 24)
                        messages = sorted(msg_list.messages, key=lambda x: datetime.fromisoformat(x.created_at))
                        break
                    except Exception:
                        time.sleep(6)
                for deal_id, last_status, status_date in list(deals):
                    try:
                        status_msgs = [msg for msg in messages if msg.deal and msg.deal.status and (datetime.fromisoformat(msg.created_at) >= status_date)]
                        for msg in status_msgs:
                            msg_date = datetime.fromisoformat(msg.created_at)
                            if msg.deal.status == last_status and msg_date == status_date:
                                continue
                            try:
                                chat_obj = self.conn.load_chat(chat_id)
                            except Exception:
                                continue
                            events = self._parse_message_events(msg, chat_obj)
                            for event in events:
                                yield event
                            self._set_active_deal(chat_obj, msg.deal, msg_date)
                    except Exception:
                        self.logger.debug(f'Ошибка проверки статусов в сделке {deal_id}: {traceback.format_exc()}')
                    time.sleep(8)
            time.sleep(1)

    def listen(self, get_new_message_events: bool = True, get_new_review_events: bool = True) -> Generator:
        if not any((get_new_review_events, get_new_message_events)):
            return
        self.q = Queue()

        def run(gen):
            for event in gen:
                self.q.put(event)

        if get_new_message_events:
            Thread(target=run, args=(self.listen_new_messages(),), daemon=True).start()
            Thread(target=run, args=(self.listen_new_deals(),), daemon=True).start()
        if get_new_review_events:
            Thread(target=run, args=(self.listen_new_reviews(),), daemon=True).start()
        while True:
            yield self.q.get()
