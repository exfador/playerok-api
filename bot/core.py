from __future__ import annotations
import asyncio
import traceback
import time
import copy
import html
import json
import re
import textwrap
import shutil
from collections import deque
from dataclasses import dataclass as _dc
from datetime import datetime, timedelta, timezone
from threading import Event as ThreadingEvent, Thread, Lock, current_thread
from colorama import Fore
from logging import getLogger

from bot._hub import *
from bot._hub import Conn
from bot._tap import Feed, RoomSnapshotReady, ChatIngress
from bot._tap import ReviewCreatedNotice, ReviewRemovedNotice, ReviewEditedNotice
from bot._tap import ListingPaidNotice, DealCreatedNotice, DealStageChanged
from bot._tap import DealDisputeRaised, DealDisputeCleared
from bot._kit import cfg, db, DATA
from bot._kit import wire, wire_mkt, fire, fire_mkt
from bot._kit import cc_get_items, cc_find_by_trigger
from bot._kit import VERSION
from bot._kit import C_PRIMARY, C_SUCCESS
from bot._kit import C_DIM, C_TEXT, C_BRIGHT
from bot._kit import set_console_title, spawn_async, draw_box, iso_to_display_str
from bot._kit import _norm_title, _title_matches_groups, best_rule_index
from pok.conn import PUBLISHABLE_STAGES, BOOSTABLE_STAGES
from lib.stock import DELIVERY_LOCK
from pok.transport import MutationOutcomeUnknown
from bot._forge import message_body_html, first_link_preview_url
from bot._forge import _build_html, _build_plain

logger = getLogger('cxh.bot')


def _uname(user) -> str:
    return getattr(user, 'username', None) or '—'


def _uid(user) -> str | None:
    return getattr(user, 'id', None)


def _iname(item) -> str:
    return getattr(item, 'name', None) or '—'


def _iprice(item):
    price = getattr(item, 'price', None)
    return price if price is not None else '?'


def _get_panel():
    from ctrl.panel import get_panel
    return get_panel()


def _get_panel_loop():
    from ctrl.panel import get_panel_loop
    return get_panel_loop()


def _log_text(*a, **kw):
    from ctrl.ui.main import fac_034
    return fac_034(*a, **kw)


def _log_mess_kb(*a, **kw):
    from ctrl.ui.main import fac_029
    return fac_029(*a, **kw)


def _log_deal_kb(*a, **kw):
    from ctrl.ui.main import fac_028
    return fac_028(*a, **kw)


def _log_new_review_kb(*a, **kw):
    from ctrl.ui.main import fac_030
    return fac_030(*a, **kw)


def _log_chat_only_kb(*a, **kw):
    from ctrl.ui.main import fac_027
    return fac_027(*a, **kw)


def _log_restore_ok_kb(*a, **kw):
    from ctrl.ui.main import fac_031
    return fac_031(*a, **kw)


def _log_bump_ok_kb(*a, **kw):
    from ctrl.ui.main import fac_025
    return fac_025(*a, **kw)


def _parse_dispute_text(deal: ItemDeal) -> tuple[str | None, str | None]:
    sd = (deal.status_description or '').strip()
    cb = (deal.comment_from_buyer or '').strip()
    if not sd:
        return None, cb or None
    parts = re.split(r'\n\s*\n+', sd, maxsplit=1)
    first  = parts[0].strip()
    second = parts[1].strip() if len(parts) > 1 else ''
    if second:
        return first, second
    if cb and cb != first:
        return first, cb
    return None, first or None


@_dc
class Counters:
    bot_launch_time: datetime
    deals_completed: int
    deals_refunded:  int
    earned_money:    int


def _load_counters() -> Counters:
    d = db.get('stats') or {}
    return Counters(
        bot_launch_time=None,
        deals_completed=int(d.get('deals_completed', 0)),
        deals_refunded=int(d.get('deals_refunded', 0)),
        earned_money=int(d.get('earned_money', 0)),
    )


MIN_BUMP_INTERVAL = 600


def _seconds(value, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        number = default
    number = max(minimum, number)
    return min(number, maximum) if maximum is not None else number


def _flush_counters(s: Counters) -> None:
    db.set('stats', {
        'deals_completed': s.deals_completed,
        'deals_refunded':  s.deals_refunded,
        'earned_money':    s.earned_money,
    })


_counters = _load_counters()


def counters() -> Counters:
    return _counters


def update_counters(new: Counters) -> None:
    global _counters
    _counters = new
    _flush_counters(new)


_SPEND_LOCK = Lock()


def _today() -> str:
    return datetime.now().strftime('%Y-%m-%d')


_engine: 'MarketBridge | None' = None


def active_engine() -> 'MarketBridge | None':
    return _engine


def boot_engine() -> 'MarketBridge':
    global _engine
    if _engine is None:
        _engine = MarketBridge()
    return _engine


live_bridge = active_engine
make_bridge  = boot_engine


class MarketBridge:

    def __init__(self):
        self.config               = cfg.read('config')
        self.messages             = cfg.read('messages')
        self.custom_commands      = cfg.read('custom_commands')
        self.auto_deliveries      = cfg.read('auto_deliveries')
        self.auto_restore_items   = cfg.read('auto_restore_items')
        self.auto_complete_deals  = cfg.read('auto_complete_deals')
        self.auto_bump_items      = cfg.read('auto_bump_items')
        self.initialized_users    = db.get('initialized_users')
        self.saved_items          = db.get('saved_items')
        self.latest_events_times  = db.get('latest_events_times')
        self.stats                = counters()
        self.account = self.bot_account = Conn(
            token=self.config['account'].get('token') or None,
            cookies=self.config['account'].get('cookies') or None,
            ddg5=self.config['account'].get('ddg5') or '',
            user_agent=self.config['account'].get('user_agent') or '',
            requests_timeout=self.config['account'].get('timeout') or 30,
            proxy=self.config['account'].get('proxy') or None,
        ).get()
        self._thread_chat_handles:        dict[str, object]  = {}
        self._chat_msg_history:           dict[str, deque]   = {}
        self._chat_msg_history_lock       = Lock()
        self._problem_resolved_notify_at: dict[str, float]   = {}
        self._mutation_guard = Lock()
        self._reactivating_items: set[str] = set()
        self._elevating_items: set[str] = set()
        self._alive_lock = Lock()
        self._alive_started = False
        self._worker_threads: list[Thread] = []
        self._started_worker_names: set[str] = set()
        self._stop_event = ThreadingEvent()
        self._feed: Feed | None = None
        self._feed_thread: Thread | None = None
        self._feed_restarts = 0
        self._feed_last_event_at: float | None = None
        self._problem_resolved_notify_lock = Lock()
        self._delivery_lock = DELIVERY_LOCK
        self._seller_calls: dict[str, float] = {}
        self._restore_skip_until: dict[str, float] = {}

    def health(self) -> dict:
        feed_health = self._feed.health() if self._feed is not None else {'connected': False}
        workers = {thread.name: thread.is_alive() for thread in self._worker_threads}
        return {
            'started_at': self.stats.bot_launch_time,
            'stopping': self._stop_event.is_set(),
            'feed': feed_health,
            'feed_restarts': self._feed_restarts,
            'feed_supervisor_alive': bool(self._feed_thread and self._feed_thread.is_alive()),
            'feed_last_event_at': self._feed_last_event_at,
            'workers': workers,
        }

    def persist_state(self) -> None:
        for key in ('initialized_users', 'saved_items', 'latest_events_times'):
            value = getattr(self, key, None)
            if value is not None:
                db.set(key, value)
        if getattr(self, 'stats', None) is not None:
            _flush_counters(self.stats)

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop_event.set()
        feed = self._feed
        if feed is not None:
            feed.stop()
        deadline = time.monotonic() + max(0.0, join_timeout)
        for worker in [*self._worker_threads, self._feed_thread]:
            if worker is None or worker is current_thread() or not worker.is_alive():
                continue
            worker.join(timeout=max(0.0, deadline - time.monotonic()))

    def _store_msg(self, chat_id: str, message: ChatMessage | None) -> None:
        if not message or not getattr(message, 'id', None):
            return
        with self._chat_msg_history_lock:
            bucket = self._chat_msg_history.setdefault(chat_id, deque(maxlen=25))
            seen = {getattr(m, 'id', None) for m in bucket}
            if message.id not in seen:
                bucket.append(message)

    def _recent_msgs(self, chat_id: str) -> list:
        with self._chat_msg_history_lock:
            bucket = self._chat_msg_history.get(chat_id)
            return list(bucket) if bucket else []

    def _room(self, chat_id: str):
        if chat_id not in self._thread_chat_handles:
            self._thread_chat_handles[chat_id] = self.account.load_chat(chat_id)
        return self._thread_chat_handles[chat_id]

    def _room_by_alias(self, username: str):
        if username in self._thread_chat_handles:
            return self._thread_chat_handles[username]
        low = username.lower()
        if low == 'поддержка':
            obj = self.account.load_chat(self.account.support_chat_id)
        elif low == 'уведомления':
            obj = self.account.load_chat(self.account.system_chat_id)
        else:
            obj = self.account.find_chat_by_name(username)
        if obj is not None:
            self._thread_chat_handles[username] = obj
        return obj

    def _sync_profile(self) -> None:
        self.account = self.bot_account = self.account.get()

    @staticmethod
    def _config_cookie_jar(account_cfg: dict) -> dict:
        from pok.cookies import parse_cookies_lenient
        jar = dict(parse_cookies_lenient(account_cfg.get('cookies') or None))
        if account_cfg.get('token'):
            jar['token'] = account_cfg['token']
        if account_cfg.get('ddg5'):
            jar['__ddg5_'] = account_cfg['ddg5']
        return jar

    def _persist_rotated_cookies(self) -> bool:
        if not hasattr(self.account, '_cookie_header'):
            return False
        live = dict(getattr(self.account, 'cookies', {}) or {})
        if not live.get('token'):
            return False
        config = cfg.read('config')
        account_cfg = config.get('account') or {}
        stored = self._config_cookie_jar(account_cfg)
        snapshot = getattr(self, '_cookie_snapshot', None)
        if snapshot is None:
            snapshot = self._cookie_snapshot = dict(stored)
        if stored != snapshot:
            self._cookie_snapshot = dict(stored)
            if stored.get('token') and stored != live:
                self.account.replace_cookies(stored)
                self._auth_alerted = False
                logger.info('Cookie Playerok из настроек применены без перезапуска')
            return False
        if live == stored:
            return False
        account_cfg['cookies'] = '; '.join(f'{k}={v}' for k, v in live.items() if v)
        account_cfg['token'] = live.get('token', '')
        account_cfg['ddg5'] = live.get('__ddg5_', '') or account_cfg.get('ddg5', '')
        config['account'] = account_cfg
        cfg.write('config', config)
        self.config = config
        self._cookie_snapshot = self._config_cookie_jar(account_cfg)
        logger.info('Playerok обновил Cookie сессии — сохранено в conf/config.json')
        return True

    def _report_auth_failure(self, exc: Exception) -> None:
        logger.error('Сессия Playerok недействительна: %s', exc)
        if getattr(self, '_auth_alerted', False):
            return
        self._auth_alerted = True
        self._push_notify('system', _log_text(
            title='🔑 Сессия Playerok недействительна',
            text='Автоматизация не может работать с аккаунтом. Экспортируйте свежие Cookie из браузера и загрузите их: '
                 '<b>Настройки → Вход на Playerok</b>. Используйте тот же IP и User-Agent, что в браузере.',
        ), None)

    def _verify_access(self) -> None:
        self._sync_profile()
        if self.account.is_blocked:
            logger.critical('Аккаунт %s заблокирован на Playerok', self.account.username)
            self._push_notify('system', _log_text(
                title='⛔ Аккаунт Playerok заблокирован',
                text='Автоматизация остановлена. Обратитесь в поддержку Playerok.',
            ), None)
            self._stop_event.set()

    @staticmethod
    def _ctx(**kwargs) -> dict:
        now = datetime.now()
        return {
            'time':     now.strftime('%H:%M'),
            'date':     now.strftime('%d.%m.%Y'),
            'datetime': now.strftime('%d.%m.%Y %H:%M'),
            **kwargs,
        }

    @staticmethod
    def _fill(text: str, variables: dict) -> str:
        return re.sub(
            r'\$([a-zA-Z_][a-zA-Z0-9_]*)',
            lambda m: str(variables.get(m.group(1), m.group(0))),
            text,
        )

    def _render(self, message_name: str, messages_config_name: str = 'messages', messages_data: dict = DATA, **kwargs) -> str | None:
        messages = cfg.read(messages_config_name, messages_data) or {}
        mess = messages.get(message_name, {})
        if not mess.get('enabled'):
            return None
        lines: list[str] = mess.get('text', [])
        if not lines:
            return None
        try:
            variables = self._ctx(seller=getattr(self.account, 'username', '') or '', **kwargs)
            return '\n'.join(self._fill(line, variables) for line in lines)
        except Exception as e:
            logger.debug('[_render] ошибка подстановки в %s: %s', message_name, e)
            return '\n'.join(lines)

    def _render_tpl(self, message_id: str, buyer_username: str) -> str | None:
        messages = cfg.read('messages') or {}
        mess = messages.get(message_id, {})
        lines: list[str] = mess.get('text') or []
        if not lines:
            return None
        variables = self._ctx(
            buyer=buyer_username, seller=getattr(self.account, 'username', '') or '',
            product='', price='', deal_id='', rating='', error='',
        )
        try:
            return '\n'.join(self._fill(line, variables) for line in lines)
        except Exception as e:
            logger.debug('[_render_tpl] %s: %s', message_id, e)
            return '\n'.join(lines)

    def _next_at(self, event: str) -> datetime:
        stamp = (self.latest_events_times or {}).get(event)
        if not stamp:
            return datetime.now()
        try:
            last = datetime.fromisoformat(str(stamp))
        except ValueError:
            return datetime.now()
        interval = _seconds(((self.config.get('auto') or {}).get('bump') or {}).get('interval'), 3600, MIN_BUMP_INTERVAL)
        return last + timedelta(seconds=interval)

    def _alert_on(self, alert_key: str) -> bool:
        alerts = self.config.get('alerts') or {}
        return bool(alerts.get('enabled')) and bool((alerts.get('on') or {}).get(alert_key, True))

    @staticmethod
    def _emit(text: str, kb=None, link_preview_url: str | None = None) -> None:
        panel, loop = _get_panel(), _get_panel_loop()
        if panel is None or loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(panel.log_event(text=text, kb=kb, link_preview_url=link_preview_url), loop)
        except Exception as exc:
            logger.debug('Уведомление не поставлено в очередь: %s', exc)

    def _push_notify(self, alert_key: str, text: str, kb, link_preview_url: str | None = None) -> None:
        if self._alert_on(alert_key):
            self._emit(text, kb, link_preview_url)

    def _notify_reactivated(self, item_name: str | None, item_id: str | None) -> None:
        nm  = html.escape((item_name or '?')[:220])
        iid = html.escape(str(item_id or ''))
        self._push_notify(
            'restore',
            _log_text(title='📦 Объявление выставлено повторно', text=f'<b>{nm}</b>\n<code>{iid}</code>'),
            _log_restore_ok_kb(),
        )

    def _notify_elevated(self, item_name: str | None, item_id: str | None) -> None:
        nm  = html.escape((item_name or '?')[:220])
        iid = html.escape(str(item_id or ''))
        self._push_notify(
            'bump',
            _log_text(title='⬆️ Обновлена позиция объявления', text=f'<b>{nm}</b>\n<code>{iid}</code>'),
            _log_bump_ok_kb(),
        )

    def _push(self, chat_id: str, text: str | None = None, photo_file_path: str | None = None,
               read_chat: bool | None = None, exclude_watermark: bool = False) -> ChatMessage | None:
        if not chat_id or (not text and not photo_file_path):
            return None
        logger.debug('[_push] chat=%s  text_len=%s  photo=%s', chat_id, len(text or ''), bool(photo_file_path))
        features = self.config.get('features') or {}
        wm_cfg = features.get('watermark') or {}
        body = text
        if body and wm_cfg.get('enabled') and wm_cfg.get('text') and not exclude_watermark:
            wm_text = wm_cfg['text']
            body = f'{wm_text}\n\n{body}' if wm_cfg.get('position') == 'start' else f'{body}\n\n{wm_text}'
        use_read = bool(features.get('read_chat', True)) if read_chat is None else read_chat
        try:
            mess = self.account.send_message(chat_id=chat_id, text=body, photo_file_path=photo_file_path, read_chat=use_read)
        except Exception as e:
            logger.error('Ошибка отправки в чат %s: %s', chat_id, e)
            return None
        if mess:
            self._store_msg(chat_id, mess)
        return mess

    @staticmethod
    def _enum_name(value):
        return getattr(value, 'name', value)

    def _pack(self, item: ItemProfile) -> dict:
        attachment = getattr(item, 'attachment', None)
        user = getattr(item, 'user', None)
        return {
            'id': item.id, 'slug': item.slug,
            'priority': self._enum_name(item.priority),
            'status': self._enum_name(item.status),
            'name': item.name, 'price': item.price, 'raw_price': item.raw_price,
            'seller_type': self._enum_name(item.seller_type),
            'attachment': {
                'id': attachment.id, 'url': attachment.url,
                'filename': attachment.filename, 'mime': attachment.mime,
            } if attachment else None,
            'user': {
                'id': user.id, 'username': user.username,
                'role': self._enum_name(user.role),
                'avatar_url': user.avatar_url,
                'is_online': user.is_online, 'is_blocked': user.is_blocked,
                'rating': user.rating, 'reviews_count': user.reviews_count,
                'support_chat_id': user.support_chat_id,
                'system_chat_id': user.system_chat_id,
                'created_at': user.created_at,
            } if user else None,
            'approval_date': item.approval_date,
            'priority_position': item.priority_position,
            'views_counter': item.views_counter,
            'fee_multiplier': item.fee_multiplier,
            'created_at': item.created_at,
        }

    def _unpack(self, item_data: dict) -> ItemProfile:
        data = copy.deepcopy(item_data)
        ud = data.pop('user', None)
        user = None
        if ud:
            ud['role'] = AccountRole.__members__.get(ud.get('role')) if ud.get('role') else None
            user = UserProfile(**ud)
        ad = data.pop('attachment', None)
        attachment = FileObject(**ad) if ad else None
        data['priority'] = BoostLevel.__members__.get(data.get('priority')) if data.get('priority') else None
        data['status'] = ListingStage.__members__.get(data.get('status')) if data.get('status') else None
        data['seller_type'] = AccountRole.__members__.get(data.get('seller_type')) if data.get('seller_type') else None
        return ItemProfile(user=user, attachment=attachment, **data)

    def _listings(self, count: int = -1, statuses: list[ListingStage] | None = None) -> list[ItemProfile]:
        my_items: list[ItemProfile] = []
        packed: list[dict] = []
        try:
            for itm in self.account.iter_my_items(statuses=statuses):
                if statuses is not None and itm.status not in statuses:
                    continue
                my_items.append(itm)
                try:
                    packed.append(self._pack(itm))
                except Exception:
                    logger.debug('Не удалось сохранить лот %s в кэш', getattr(itm, 'id', '?'))
                if 0 < count <= len(my_items):
                    break
            cache = {d.get('id'): d for d in (self.saved_items or []) if isinstance(d, dict)}
            cache.update({d['id']: d for d in packed})
            self.saved_items = list(cache.values())[-500:]
        except (RequestApiError, RequestFailedError, RequestSendingError, ValueError):
            cached = []
            for itm_dict in list(self.saved_items or []):
                try:
                    cached.append(self._unpack(itm_dict))
                except Exception:
                    continue
            my_items = [itm for itm in cached if statuses is None or itm.status in statuses]
            if count > 0:
                my_items = my_items[:count]
            if not my_items:
                raise
        return my_items

    @staticmethod
    def _price_of(item) -> int:
        try:
            return int(getattr(item, 'raw_price', None) or getattr(item, 'price', None) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _within_limit(price, limit) -> bool:
        try:
            limit = float(limit or 0)
        except (TypeError, ValueError):
            limit = 0
        return limit <= 0 or float(price or 0) <= limit

    def _pick_restore_tier(self, tiers: list, priority: BoostLevel | None = None) -> tuple[ItemPriorityStatus | None, str]:
        restore_cfg = (self.config.get('auto') or {}).get('restore') or {}
        usable = [t for t in tiers if t is not None and t.id]
        free = [t for t in usable if not t.price]
        paid = sorted((t for t in usable if t.price), key=lambda t: t.price)
        limit = restore_cfg.get('premium_max_price')
        if restore_cfg.get('premium') and priority == BoostLevel.PREMIUM:
            premium = [t for t in paid if t.type == BoostLevel.PREMIUM]
            if premium and self._within_limit(premium[0].price, limit):
                return premium[0], 'paid'
        if free:
            return free[0], 'free'
        if not restore_cfg.get('premium'):
            return None, 'paid_disabled'
        if not paid:
            return None, 'no_tiers'
        if not self._within_limit(paid[0].price, limit):
            return None, 'over_limit'
        return paid[0], 'paid'

    def _daily_limit(self) -> float:
        try:
            return max(0.0, float((self.config.get('auto') or {}).get('daily_limit') or 0))
        except (TypeError, ValueError):
            return 0.0

    def _reserve_spend(self, amount) -> bool:
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return True
        limit = self._daily_limit()
        with _SPEND_LOCK:
            state = db.get('spend_state') or {}
            if state.get('date') != _today():
                state = {'date': _today(), 'total': 0, 'notified': ''}
            total = float(state.get('total') or 0)
            if limit and total + amount > limit:
                first_refusal = state.get('notified') != state['date']
                if first_refusal:
                    state['notified'] = state['date']
                    db.set('spend_state', state)
            else:
                state['total'] = round(total + amount, 2)
                db.set('spend_state', state)
                return True
        logger.warning('Дневной лимит расходов: потрачено %s ₽ из %s ₽, операция на %s ₽ пропущена', f'{total:g}', f'{limit:g}', f'{amount:g}')
        if first_refusal:
            self._push_notify('bump', _log_text(
                title='💳 Дневной лимит расходов исчерпан',
                text=f'Сегодня потрачено <b>{total:g} ₽</b> из <b>{limit:g} ₽</b>. '
                     'Платные автоподнятие и восстановление продолжатся завтра. Лимит меняется в настройках поднятия.',
            ), None)
        return False

    def _release_spend(self, amount) -> None:
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            return
        if amount <= 0:
            return
        with _SPEND_LOCK:
            state = db.get('spend_state') or {}
            if state.get('date') != _today():
                return
            state['total'] = max(0, round(float(state.get('total') or 0) - amount, 2))
            db.set('spend_state', state)

    def _confirm_uncertain_listing(self, item_id: str, check) -> MyItem | None:
        try:
            refreshed = self.account.load_listing(item_id)
        except Exception as exc:
            logger.warning('Не удалось перепроверить лот %s: %s', item_id, exc)
            return None
        return refreshed if isinstance(refreshed, MyItem) and check(refreshed) else None

    def _notify_uncertain(self, action: str, item_name: str | None, item_id: str | None) -> None:
        nm = html.escape((item_name or '?')[:220])
        iid = html.escape(str(item_id or ''))
        self._push_notify(
            'restore',
            _log_text(
                title=f'❔ {action}: результат неизвестен',
                text=f'<b>{nm}</b>\n<code>{iid}</code>\n\nПроверьте лот на Playerok. Повторные платные операции с ним заблокированы до перезапуска или сброса в «Мои лоты».',
            ),
            None,
        )

    def _elevate(self, item: ItemProfile | MyItem) -> str:
        item_id = str(item.id)
        with self._mutation_guard:
            if item_id in self._elevating_items:
                return 'skip_in_progress'
            self._elevating_items.add(item_id)
        try:
            return self._elevate_once(item)
        finally:
            with self._mutation_guard:
                self._elevating_items.discard(item_id)

    def _elevate_once(self, item: ItemProfile | MyItem) -> str:
        name_short = (item.name or '?')[:100]
        try:
            abi = self.auto_bump_items or {}
            bump_cfg = (self.config.get('auto') or {}).get('bump') or {}
            all_b = bool(bump_cfg.get('all'))
            if all_b and _title_matches_groups(item.name, abi.get('excluded') or []):
                logger.debug('[elevate] пропуск «%s»: в исключениях', name_short)
                return 'skip_excluded'
            if not all_b and not _title_matches_groups(item.name, abi.get('included') or []):
                logger.debug('[elevate] пропуск «%s»: нет совпадения с белым списком', name_short)
                return 'skip_phrases'
            current = self.account.load_listing(item.id)
            if not isinstance(current, MyItem):
                return 'skip_load'
            if current.status != ListingStage.APPROVED or current.priority != BoostLevel.PREMIUM:
                return 'skip_priority'
            tiers = self.account.load_boost_tiers(current.id, self._price_of(current))
            premium = sorted((t for t in tiers if t and t.type == BoostLevel.PREMIUM), key=lambda t: t.price or 0)
            if not premium:
                logger.warning('[elevate] «%s»: Playerok не предложил PREMIUM', name_short)
                return 'error'
            tier = premium[0]
            if not self._within_limit(tier.price, bump_cfg.get('max_price')):
                logger.info('[elevate] «%s»: PREMIUM %s₽ дороже лимита %s₽', name_short, tier.price, bump_cfg.get('max_price'))
                return 'skip_price'
            if not self._reserve_spend(tier.price):
                return 'skip_budget'
            previous_position = current.priority_position
            previous_sequence = current.sequence
            try:
                self.account.apply_boost(current.id, tier.id, keep_in_sale=current.keep_in_sale)
            except MutationOutcomeUnknown:
                confirmed = self._confirm_uncertain_listing(
                    current.id,
                    lambda r: r.sequence != previous_sequence or r.priority_position != previous_position,
                )
                if confirmed is None:
                    self._notify_uncertain('Поднятие', current.name, current.id)
                    return 'uncertain'
            except Exception:
                self._release_spend(tier.price)
                raise
            logger.info('%s«%s»%s поднят за %s₽', C_BRIGHT, (current.name or '?')[:40], Fore.RESET, tier.price)
            self._notify_elevated(current.name, current.id)
            return 'bumped'
        except Exception as e:
            logger.error('Ошибка при поднятии «%s»: %s', item.name, e)
            return 'error'

    def _elevate_all(self) -> dict:
        self.latest_events_times['auto_bump_items'] = datetime.now().isoformat()
        db.set('latest_events_times', self.latest_events_times)
        counters_map = {'checked': 0, 'bumped': 0, 'skip_priority': 0, 'skip_phrases': 0, 'skip_excluded': 0, 'skip_load': 0,
                        'skip_in_progress': 0, 'skip_price': 0, 'skip_budget': 0, 'uncertain': 0, 'error': 0}
        try:
            items = self._listings(statuses=[ListingStage.APPROVED])
            counters_map['checked'] = len(items)
            if not items:
                logger.info('[elevate_all] нет лотов со статусом APPROVED.')
            for item in items:
                if self._stop_event.is_set():
                    break
                if item.priority != BoostLevel.PREMIUM:
                    counters_map['skip_priority'] += 1
                    continue
                result = self._elevate(item)
                counters_map[result if result in counters_map else 'error'] += 1
                if result == 'skip_budget':
                    break
            logger.info(
                '[elevate_all] поднято: %s · не PREMIUM: %s · нет в списке: %s · исключено: %s · дороже лимита: %s · '
                'дневной лимит: %s · не загружено: %s · уже выполняется: %s · неизвестно: %s · ошибок: %s',
                counters_map['bumped'], counters_map['skip_priority'], counters_map['skip_phrases'],
                counters_map['skip_excluded'], counters_map['skip_price'], counters_map['skip_budget'],
                counters_map['skip_load'], counters_map['skip_in_progress'], counters_map['uncertain'],
                counters_map['error'],
            )
        except Exception as e:
            logger.error('Ошибка при автоподнятии: %s', e)
        return counters_map

    def bump_items(self) -> dict:
        return self._elevate_all()

    def _reactivate(self, item: Item | MyItem | ItemProfile, retry_delays: list[int] | None = None) -> str:
        item_id = str(item.id)
        with self._mutation_guard:
            if item_id in self._reactivating_items:
                logger.debug('Восстановление «%s» уже выполняется, дубликат пропущен', item_id)
                return 'skip_in_progress'
            self._reactivating_items.add(item_id)
        try:
            return self._reactivate_once(item, retry_delays)
        finally:
            with self._mutation_guard:
                self._reactivating_items.discard(item_id)

    def _reactivate_once(self, item: Item | MyItem | ItemProfile, retry_delays: list[int] | None = None) -> str:
        name = item.name or '?'
        short = name[:32] + ('...' if len(name) > 32 else '')
        restore_cfg = (self.config.get('auto') or {}).get('restore') or {}
        if not restore_cfg.get('all') and not _title_matches_groups(name, (self.auto_restore_items or {}).get('included') or []):
            return 'skip_phrases'
        delays = retry_delays if retry_delays is not None else [0, 15, 45]
        for attempt, delay in enumerate(delays, 1):
            if delay and self._stop_event.wait(delay):
                return 'stopped'
            try:
                current = self.account.load_listing(item.id)
            except Exception as e:
                logger.warning('Восстановление «%s»: не удалось загрузить лот (%s/%s): %s', short, attempt, len(delays), e)
                continue
            if not isinstance(current, MyItem):
                return 'skip_load'
            if current.status not in PUBLISHABLE_STAGES:
                return 'already_active' if current.status in BOOSTABLE_STAGES else 'skip_status'
            if current.lacks_seller_reviews:
                logger.info('%s«%s»%s пропущен: нужно %s отзывов, у аккаунта %s', C_DIM, short, Fore.RESET,
                            current.required_seller_reviews, current.seller_reviews)
                return 'skip_reviews'
            try:
                tiers = self.account.load_boost_tiers(current.id, self._price_of(current))
            except Exception as e:
                logger.warning('Восстановление «%s»: тарифы не получены (%s/%s): %s', short, attempt, len(delays), e)
                continue
            tier, reason = self._pick_restore_tier(tiers, current.priority)
            if tier is None:
                messages = {
                    'paid_disabled': 'нет бесплатного тарифа, платное восстановление выключено',
                    'over_limit': 'платный тариф дороже лимита',
                    'no_tiers': 'Playerok не предложил тарифов',
                }
                logger.info('%s«%s»%s пропущен: %s', C_DIM, short, Fore.RESET, messages.get(reason, reason))
                return f'skip_{reason}'
            if tier.price and not self._reserve_spend(tier.price):
                free = next((t for t in tiers if t is not None and t.id and not t.price), None)
                if free is None:
                    return 'skip_budget'
                tier, reason = free, 'free'
            reserved = tier.price or 0
            keep = None
            if restore_cfg.get('keep_in_sale') and tier.type == BoostLevel.PREMIUM and current.keep_in_sale_available is not False:
                keep = True
            try:
                new_item = self.account.activate_listing(current.id, tier.id, keep_in_sale=keep)
            except MutationOutcomeUnknown:
                confirmed = self._confirm_uncertain_listing(current.id, lambda r: r.status not in PUBLISHABLE_STAGES)
                if confirmed is None:
                    self._notify_uncertain('Восстановление', current.name, current.id)
                    return 'uncertain'
                new_item = confirmed
            except RequestApiError as e:
                self._release_spend(reserved)
                logger.warning('Playerok отклонил восстановление «%s»: %s', short, e)
                return 'skip_rejected'
            except Exception as e:
                self._release_spend(reserved)
                logger.error('Ошибка восстановления «%s»: %s', short, e)
                return 'error'
            label = 'бесплатно' if reason == 'free' else f'{tier.name or "PREMIUM"} за {tier.price}₽'
            logger.info('%s«%s»%s восстановлен (%s), статус %s', C_BRIGHT, short, Fore.RESET, label,
                        getattr(getattr(new_item, 'status', None), 'name', '?'))
            self._notify_reactivated(current.name, current.id)
            return 'restored'
        logger.error('Восстановление «%s» не выполнено после %s попыток', short, len(delays))
        return 'error'

    def my_items(self, statuses: list[ListingStage] | None = None) -> list[ItemProfile]:
        return self._listings(statuses=statuses)

    def listing_card(self, item_id: str) -> MyItem:
        item = self.account.load_listing(item_id)
        if not isinstance(item, MyItem):
            raise ValueError('Лот не найден или принадлежит другому продавцу')
        return item

    def listing_tiers(self, item: MyItem) -> list[ItemPriorityStatus]:
        tiers = [t for t in self.account.load_boost_tiers(item.id, self._price_of(item)) if t and t.id]
        return sorted(tiers, key=lambda t: (t.price or 0, t.name or ''))

    def publish_or_boost(self, item_id: str, tier_id: str, keep_in_sale: bool | None = None,
                         expected: str | None = None) -> tuple[str, MyItem | None]:
        key = str(item_id)
        with self._mutation_guard:
            if key in self._reactivating_items or key in self._elevating_items:
                raise ValueError('С этим лотом сейчас работает автоматика — повторите через минуту')
            self._reactivating_items.add(key)
            self._elevating_items.add(key)
        try:
            return self._publish_or_boost_once(item_id, tier_id, keep_in_sale, expected)
        finally:
            with self._mutation_guard:
                self._reactivating_items.discard(key)
                self._elevating_items.discard(key)

    def _publish_or_boost_once(self, item_id: str, tier_id: str, keep_in_sale: bool | None,
                               expected: str | None) -> tuple[str, MyItem | None]:
        item = self.listing_card(item_id)
        tier = next((t for t in self.listing_tiers(item) if t.id == tier_id), None)
        if tier is None:
            raise ValueError('Тариф больше недоступен — откройте лот заново')
        if tier.type != BoostLevel.PREMIUM:
            keep_in_sale = None
        if item.status in PUBLISHABLE_STAGES and item.lacks_seller_reviews:
            raise ValueError(f'Playerok разрешает выставлять такой лот только при {item.required_seller_reviews}+ отзывах, '
                             f'у аккаунта {item.seller_reviews}')
        if item.status in PUBLISHABLE_STAGES:
            action = 'published'
            before = item.status
            check = lambda r: r.status != before
            call = lambda: self.account.activate_listing(item.id, tier.id, keep_in_sale=keep_in_sale)
        elif item.status in BOOSTABLE_STAGES:
            action = 'boosted'
            before_seq, before_pos = item.sequence, item.priority_position
            check = lambda r: r.sequence != before_seq or r.priority_position != before_pos or r.priority != item.priority
            call = lambda: self.account.apply_boost(item.id, tier.id, keep_in_sale=keep_in_sale)
        else:
            raise ValueError(f'Со статусом {getattr(item.status, "name", "?")} лот нельзя выставить или поднять')
        if expected and expected != action:
            raise ValueError('Статус лота изменился, пока вы подтверждали — операция отменена. Откройте лот заново')
        try:
            call()
        except MutationOutcomeUnknown:
            confirmed = self._confirm_uncertain_listing(item.id, check)
            if confirmed is None:
                return 'uncertain', None
            return action, confirmed
        logger.info('Лот «%s»: %s (%s, %s₽)', (item.name or '?')[:40], action, tier.name, tier.price)
        return action, self.listing_card(item.id)

    def set_keep_in_sale(self, item_id: str, value: bool) -> MyItem:
        card = self.listing_card(item_id)
        if value and (card.priority != BoostLevel.PREMIUM or card.status not in BOOSTABLE_STAGES):
            raise ValueError('Playerok оставляет в продаже только активные лоты с премиум-размещением — сначала выставьте лот с PREMIUM')
        self.account.set_keep_in_sale(item_id, value)
        return self.listing_card(item_id)

    def clone_options(self, item_id: str) -> tuple[MyItem, list[dict]]:
        source = self.listing_card(item_id)
        category = getattr(source, 'category', None)
        if category is None or not category.id:
            return source, []
        page = self.account.load_obtain_types(category.id)
        current = getattr(getattr(source, 'obtaining_type', None), 'id', None)
        reviews = source.seller_reviews
        category_min = getattr(getattr(category, 'props', None), 'min_reviews_for_seller', None) or 0
        options = []
        for kind in sorted((t for t in (page.obtaining_types if page else []) if t and t.id), key=lambda t: t.sequence or 0):
            required = max(getattr(getattr(kind, 'props', None), 'min_reviews_for_seller', None) or 0, category_min)
            options.append({'id': kind.id, 'name': kind.name, 'required': required, 'current': kind.id == current,
                            'locked': reviews is not None and reviews < required})
        return source, options

    def clone_listing(self, item_id: str, price: int | None = None, obtaining_type_id: str | None = None) -> MyItem | Item:
        source = self.listing_card(item_id)
        current = getattr(getattr(source, 'obtaining_type', None), 'id', None)
        if (obtaining_type_id in (None, current)) and source.lacks_seller_reviews:
            raise ValueError(f'Для этого способа получения Playerok требует {source.required_seller_reviews}+ отзывов, '
                             f'у аккаунта {source.seller_reviews}. Выберите другой способ получения')
        created = self.account.clone_listing(source, price=price, obtaining_type_id=obtaining_type_id)
        logger.info('Создана копия лота «%s»: %s', (source.name or '?')[:40], getattr(created, 'id', '?'))
        return created

    def remove_listing(self, item_id: str) -> None:
        self.listing_card(item_id)
        self.account.delete_listing(item_id)

    def reset_listing_lock(self, item_id: str) -> None:
        self.account.forget_uncertain(f'listing:{item_id}')

    def _restore_settings_fingerprint(self) -> str:
        auto = self.config.get('auto') or {}
        return repr((auto.get('restore'), auto.get('daily_limit'), (self.auto_restore_items or {}).get('included')))

    def _restore_batch(self, statuses: list[ListingStage]) -> None:
        now = time.monotonic()
        fingerprint = self._restore_settings_fingerprint()
        if fingerprint != getattr(self, '_restore_skip_fingerprint', None):
            self._restore_skip_until = {}
            self._restore_skip_fingerprint = fingerprint
        self._restore_skip_until = {k: v for k, v in self._restore_skip_until.items() if v > now}
        seen: set[str] = set()
        for item in self._listings(statuses=statuses):
            if self._stop_event.is_set():
                return
            if item.id in seen or self._restore_skip_until.get(item.id, 0) > now:
                continue
            seen.add(item.id)
            result = self._reactivate(item, retry_delays=[0])
            if result.startswith('skip_') and result not in ('skip_in_progress', 'skip_phrases'):
                self._restore_skip_until[item.id] = time.monotonic() + 1800
            if self._stop_event.wait(0.5):
                return

    def _reactivate_expired(self) -> None:
        try:
            self._restore_batch([ListingStage.EXPIRED])
        except Exception as e:
            logger.error('Ошибка при восстановлении истёкших товаров: %s', e)

    def _reactivate_polled(self) -> None:
        restore_cfg = (self.config.get('auto') or {}).get('restore') or {}
        statuses: list[ListingStage] = []
        if restore_cfg.get('sold'):
            statuses.append(ListingStage.SOLD)
        if restore_cfg.get('expired'):
            statuses.append(ListingStage.EXPIRED)
        if not statuses:
            return
        try:
            self._restore_batch(statuses)
        except Exception as e:
            logger.error('Ошибка при проверке завершённых лотов: %s', e)

    def _trace_msg(self, message: ChatMessage, chat_obj) -> None:
        eng = active_engine()
        try:
            chat_user = next(u.username for u in chat_obj.users if u.id != eng.account.id)
        except Exception:
            chat_user = message.user.username
        own = getattr(message.user, 'id', None) == getattr(self.account, 'id', None)
        if own and not (message.event or (message.text or '').strip().startswith('{{')):
            text = f'[исходящее сообщение · {len(message.text or "")} симв.{" · вложение" if message.file or message.images else ""}]'
        else:
            text = _build_plain(message) or '[пустое сообщение]'
        wrap_w = min(max(shutil.get_terminal_size((80, 20)).columns - 8, 40), 100)
        lines  = [f'{C_PRIMARY}Сообщение — {chat_user}{Fore.RESET}', f'  {C_BRIGHT}{message.user.username}:{Fore.RESET}']
        for raw in text.split('\n'):
            if not raw.strip():
                lines.append('')
                continue
            for chunk in textwrap.wrap(raw, width=wrap_w) or [raw]:
                lines.append(f'  {C_TEXT}{chunk}{Fore.RESET}')
        logger.info('\n'.join(lines))

    def _trace_order(self, deal: ItemDeal) -> None:
        draw_box('НОВАЯ СДЕЛКА', [
            ('ID', deal.id), ('Покупатель', _uname(deal.user)),
            ('Товар', _iname(deal.item)), ('Сумма', f'{_iprice(deal.item)} ₽'),
        ])

    def _trace_review(self, deal: ItemDeal) -> None:
        stars = '★' * (deal.review.rating or 5)
        date  = iso_to_display_str(deal.review.created_at, fmt='%d.%m.%Y %H:%M')
        draw_box('НОВЫЙ ОТЗЫВ', [
            ('Сделка', deal.id), ('Оценка', f'{stars} ({deal.review.rating or 5})'),
            ('Автор', _uname(deal.review.creator)), ('Текст', deal.review.text or '—'), ('Дата', date),
        ])

    def _trace_review_del(self, deal: ItemDeal) -> None:
        draw_box('ОТЗЫВ УДАЛЁН', [
            ('Сделка', deal.id), ('Покупатель', _uname(deal.user)), ('Товар', _iname(deal.item)),
        ])

    def _trace_review_edit(self, deal: ItemDeal, prev: dict) -> None:
        new = deal.review
        if not new:
            return
        draw_box('ОТЗЫВ ИЗМЕНЁН', [
            ('Сделка', deal.id),
            ('Было',  f"⭐{prev.get('rating', '?')}  {prev.get('text') or '—'}"),
            ('Стало', f'⭐{new.rating}  {new.text or "—"}'),
        ])

    def _trace_stage(self, deal: ItemDeal, status_frmtd: str = 'Неизвестно') -> None:
        draw_box('СТАТУС СДЕЛКИ', [
            ('ID', deal.id), ('Новый статус', status_frmtd),
            ('Покупатель', _uname(deal.user)), ('Товар', _iname(deal.item)),
            ('Сумма', f'{_iprice(deal.item)} ₽'),
        ])

    def _trace_dispute(self, deal: ItemDeal, category: str | None = None, detail: str | None = None) -> None:
        rows = [
            ('Сделка', deal.id), ('От', _uname(deal.user)),
            ('Товар', _iname(deal.item)), ('Сумма', f'{_iprice(deal.item)} ₽'),
        ]
        if category:
            rows.append(('Категория', category))
        if detail:
            rows.append(('Текст жалобы' if category else 'Причина', detail))
        draw_box('ЖАЛОБА', rows)

    def _trace_dispute_close(self, deal: ItemDeal, resolver_username: str | None = None) -> None:
        rows = [
            ('Сделка', deal.id), ('Покупатель', _uname(deal.user)),
            ('Товар', _iname(deal.item)), ('Сумма', f'{_iprice(deal.item)} ₽'),
        ]
        if resolver_username:
            rows.append(('Сообщение от', resolver_username))
        draw_box('ЖАЛОБА СНЯТА', rows)

    async def _on_alive(self) -> None:
        if not hasattr(self, '_stop_event'):
            self._stop_event = ThreadingEvent()
        if self._stop_event.is_set():
            return
        with self._alive_lock:
            if self._alive_started:
                logger.debug('Фоновые циклы уже запущены; повторный ALIVE пропущен')
                return
            self._alive_started = True
        self.stats.bot_launch_time = datetime.now()

        def _sync_loop():
            while not self._stop_event.is_set():
                try:
                    profile = getattr(self.account, 'profile', None)
                    balance_obj = getattr(profile, 'balance', None)
                    balance = getattr(balance_obj, 'value', '?')
                    set_console_title(f'CXH Playerok v{VERSION} | {self.account.username}: {balance}₽')
                    if self.stats != counters():
                        update_counters(self.stats)
                    new_cfg = cfg.read('config')
                    if isinstance(new_cfg, dict) and new_cfg != self.config:
                        old_verbose = self.config.get('debug', {}).get('verbose', False)
                        new_verbose = new_cfg.get('debug', {}).get('verbose', False)
                        self.config = new_cfg
                        self.account.requests_timeout = _seconds((new_cfg.get('account') or {}).get('timeout'), 30, 5, 300)
                        if old_verbose != new_verbose:
                            from lib.util import apply_verbose
                            apply_verbose(new_verbose)
                    for key in ('messages', 'custom_commands', 'auto_deliveries', 'auto_restore_items', 'auto_complete_deals', 'auto_bump_items'):
                        fresh = cfg.read(key)
                        if fresh != getattr(self, key):
                            setattr(self, key, fresh)
                    for key in ('initialized_users', 'saved_items', 'latest_events_times'):
                        val = getattr(self, key)
                        if db.get(key) != val:
                            db.set(key, val)
                    self._persist_rotated_cookies()
                except Exception:
                    logger.error('Ошибка синхронизации конфигурации/состояния: %s', traceback.format_exc())
                if self._stop_event.wait(3):
                    return

        def _access_check_loop():
            while not self._stop_event.is_set():
                try:
                    self._verify_access()
                    self._auth_alerted = False
                except (UnauthorizedError, HoneypotDetectedException) as exc:
                    self._report_auth_failure(exc)
                except RequestApiError as exc:
                    if exc.error_code in ('UNAUTHENTICATED', 'UNAUTHORIZED', 'FORBIDDEN'):
                        self._report_auth_failure(exc)
                    else:
                        logger.error('Ошибка проверки блокировки: %s', exc)
                except Exception:
                    logger.error('Ошибка проверки блокировки: %s', traceback.format_exc())
                if self._stop_event.wait(900):
                    return

        def _reactivate_expired_loop():
            while not self._stop_event.is_set():
                try:
                    restore_cfg = (self.config.get('auto') or {}).get('restore') or {}
                    if restore_cfg.get('expired') and not (restore_cfg.get('poll') or {}).get('enabled'):
                        self._reactivate_expired()
                except Exception:
                    logger.error('Ошибка автовосстановления: %s', traceback.format_exc())
                if self._stop_event.wait(120):
                    return

        def _reactivate_poll_loop():
            while not self._stop_event.is_set():
                poll = (self.config.get('auto', {}).get('restore') or {}).get('poll') or {}
                iv   = _seconds(poll.get('interval'), 300, 30)
                if poll.get('enabled'):
                    try:
                        self._reactivate_polled()
                    except Exception:
                        logger.error('Ошибка проверки завершённых лотов: %s', traceback.format_exc())
                    if self._stop_event.wait(iv):
                        return
                else:
                    if self._stop_event.wait(15):
                        return

        def _elevate_loop():
            while not self._stop_event.is_set():
                try:
                    bump_cfg = (self.config.get('auto') or {}).get('bump') or {}
                    if bump_cfg.get('enabled') and datetime.now() >= self._next_at('auto_bump_items'):
                        self._elevate_all()
                except Exception:
                    logger.error('Ошибка автоподнятия: %s', traceback.format_exc())
                if self._stop_event.wait(3):
                    return

        def _update_check_loop():
            from lib.updater import fetch_latest_release, is_newer
            from lib.consts import VERSION as _VERSION
            if self._stop_event.wait(20):
                return
            while not self._stop_event.is_set():
                upd_cfg = (self.config.get('updater') or {})
                iv = _seconds(upd_cfg.get('interval_sec'), 3600, 300)
                if not upd_cfg.get('enabled', True):
                    if self._stop_event.wait(iv):
                        return
                    continue
                try:
                    rel = fetch_latest_release(self.config.get('bot', {}).get('proxy') or None)
                    if rel and rel.tag:
                        state = db.get('updater_state') or {}
                        state.update({
                            'latest_tag': rel.tag,
                            'latest_html_url': rel.html_url,
                            'latest_download_url': rel.download_url,
                            'checked_at': datetime.now().isoformat(timespec='seconds'),
                        })
                        db.set('updater_state', state)
                        alerts = self.config.get('alerts') or {}
                        alerts_on = alerts.get('enabled', True) and (alerts.get('on') or {}).get('update', True)
                        notify_on = bool((self.config.get('updater') or {}).get('notify', True))
                        if alerts_on and notify_on and is_newer(rel.tag, _VERSION) and state.get('last_notified_tag') != rel.tag:
                            panel = _get_panel()
                            loop = _get_panel_loop()
                            if panel is not None and loop is not None:
                                asyncio.run_coroutine_threadsafe(
                                    panel.notify_update(
                                        tag=rel.tag, html_url=rel.html_url,
                                        download_url=rel.download_url, body=rel.body,
                                        current_version=_VERSION,
                                    ),
                                    loop,
                                )
                                state['last_notified_tag'] = rel.tag
                                db.set('updater_state', state)
                                logger.info('Доступно обновление: %s (текущая %s)', rel.tag, _VERSION)
                except Exception:
                    logger.debug('Ошибка проверки обновлений: %s', traceback.format_exc())
                if self._stop_event.wait(iv):
                    return

        def _broadcast_loop():
            from lib.broadcast import fetch_bulletins, DEFAULT_SOURCE
            cap = 800
            if self._stop_event.wait(25):
                return
            while not self._stop_event.is_set():
                bc = (self.config.get('broadcast') or {})
                iv = _seconds(bc.get('interval_sec'), 1800, 120)
                source = str(bc.get('source') or '').strip() or DEFAULT_SOURCE
                if not bc.get('enabled', False) or not source:
                    if self._stop_event.wait(iv):
                        return
                    continue
                try:
                    alerts = self.config.get('alerts') or {}
                    alerts_on = alerts.get('enabled', True) and (alerts.get('on') or {}).get('broadcast', True)
                    if alerts_on:
                        bulletins = fetch_bulletins(source, self.config.get('bot', {}).get('proxy') or None)
                        if bulletins:
                            state = db.get('broadcast_state') or {}
                            seen = list(state.get('seen') or [])
                            seen_set = set(seen)
                            fresh = [b for b in bulletins if b.key not in seen_set]
                            panel = _get_panel()
                            loop = _get_panel_loop()
                            if fresh and panel is not None and loop is not None:
                                pre_seed: list[str] = []
                                if not seen_set and len(fresh) > 1:
                                    pre_seed = [b.key for b in fresh[:-1]]
                                    fresh = fresh[-1:]
                                delivered: list[str] = list(pre_seed)
                                for b in fresh:
                                    try:
                                        ok = asyncio.run_coroutine_threadsafe(
                                            panel.notify_broadcast(b.title, b.text, b.buttons, b.pinned, b.html),
                                            loop,
                                        ).result(timeout=30)
                                    except Exception:
                                        ok = False
                                    if ok:
                                        delivered.append(b.key)
                                if delivered:
                                    seen.extend(delivered)
                                    if len(seen) > cap:
                                        seen = seen[-cap:]
                                    state['seen'] = seen
                                    state['checked_at'] = datetime.now().isoformat(timespec='seconds')
                                    db.set('broadcast_state', state)
                                    sent_now = len(delivered) - len(pre_seed)
                                    if sent_now > 0:
                                        logger.info('Рассылка: новых сообщений доставлено — %d', sent_now)
                except Exception:
                    logger.debug('Ошибка рассылки: %s', traceback.format_exc())
                if self._stop_event.wait(iv):
                    return

        targets = (_sync_loop, _access_check_loop, _reactivate_expired_loop, _reactivate_poll_loop, _elevate_loop, _update_check_loop, _broadcast_loop)
        started_names = getattr(self, '_started_worker_names', set())
        self._started_worker_names = started_names
        for target in targets:
            worker_name = f'cxh-{target.__name__.strip("_")}'
            if worker_name in started_names:
                continue
            worker = Thread(target=target, daemon=True, name=worker_name)
            try:
                worker.start()
            except Exception:
                logger.error('Не удалось запустить фоновый цикл %s: %s', worker_name, traceback.format_exc())
                continue
            self._worker_threads.append(worker)
            started_names.add(worker_name)
        with self._alive_lock:
            self._alive_started = len(started_names) == len(targets)
        if not self._alive_started:
            logger.error('Запущены не все фоновые циклы (%s/%s); повторный ALIVE дозапустит отсутствующие', len(started_names), len(targets))

    def _exec_cmd(self, raw_text: str, chat_id: str, username: str) -> None:
        item = cc_find_by_trigger(cc_get_items(self.custom_commands), raw_text)
        if not item:
            return
        for ev in item.get('events') or []:
            if ev == 'call_seller':
                now = time.monotonic()
                last = self._seller_calls.get(chat_id)
                if last is not None and now - last < 120:
                    continue
                self._seller_calls[chat_id] = now
                panel, loop = _get_panel(), _get_panel_loop()
                if panel is not None and loop is not None:
                    asyncio.run_coroutine_threadsafe(panel.call_seller(username, chat_id), loop)
                self._push(chat_id, self._render('cmd_seller', buyer=username))
        rl = [x for x in (item.get('reply_lines') or []) if str(x).strip()]
        if rl:
            self._push(chat_id, '\n'.join(rl))

    async def _on_snapshot(self, event: RoomSnapshotReady) -> None:
        if event.chat.last_message:
            self._store_msg(event.chat.id, event.chat.last_message)

    async def _on_inbound(self, event: ChatIngress) -> None:
        logger.debug('[event] NEW_MESSAGE  user=%s  chat=%s', getattr(event.message.user, 'username', '?'), event.chat.id)
        if event.message.user is None:
            return
        self._store_msg(event.chat.id, event.message)
        self._trace_msg(event.message, event.chat)
        if event.message.user.id == self.account.id:
            return
        is_support = event.chat.id in (self.account.system_chat_id, self.account.support_chat_id)
        sender = _uname(event.message.user)
        if self._alert_on('system' if is_support else 'message'):
            body = _build_html(event.message)
            text = f'<b>{html.escape(sender)}:</b>\n{body}'
            self._emit(_log_text(title='📩 Входящее сообщение', text=text.strip()),
                       _log_mess_kb(sender, event.chat.id), first_link_preview_url(event.message))
        if not is_support and event.message.text is not None:
            if event.message.user.id not in self.initialized_users:
                self.initialized_users.append(event.message.user.id)
            if (self.config.get('features') or {}).get('commands'):
                self._exec_cmd(event.message.text, event.chat.id, sender)

    async def _on_review_new(self, event: ReviewCreatedNotice) -> None:
        logger.debug('[event] NEW_REVIEW  deal=%s  rating=%s', event.deal.id, getattr(event.deal.review, 'rating', '?'))
        if _uid(event.deal.user) == self.account.id:
            return
        self._trace_review(event.deal)
        if self._alert_on('review'):
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            rev  = event.deal.review
            rtxt = (rev.text or '').strip()
            try:
                date_str = iso_to_display_str(rev.created_at, fmt='%d.%m.%Y · %H:%M')
            except Exception:
                date_str = str(rev.created_at or '')
            stars = '⭐' * max(0, rev.rating or 0) or '—'
            body = (
                f'<b>Звёзды:</b> {stars}\n'
                f'<b>Автор:</b> {html.escape(_uname(rev.creator) or "?")}\n\n'
                '<b>Комментарий</b>\n'
                f'<blockquote>{html.escape(rtxt if rtxt else "—")}</blockquote>\n\n'
                f'<i>⏱ {html.escape(date_str)}</i>'
            )
            self._emit(
                _log_text(title=f'⭐ Отзыв к заказу <a href="https://playerok.com/deal/{event.deal.id}">#{str(event.deal.id)[:8]}…</a>', text=body),
                _log_chat_only_kb(_rev_chat),
            )
        self._push(getattr(event.chat, 'id', None), self._render('new_review', buyer=_uname(event.deal.user), deal_id=event.deal.id, product=_iname(event.deal.item), price=_iprice(event.deal.item), rating=getattr(event.deal.review, 'rating', '')))

    async def _on_review_del(self, event: ReviewRemovedNotice) -> None:
        logger.debug('[event] REVIEW_REMOVED  deal=%s', event.deal.id)
        if _uid(event.deal.user) == self.account.id:
            return
        self._trace_review_del(event.deal)
        if self._alert_on('review'):
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            body = (
                f'<b>Клиент:</b> {html.escape(_uname(event.deal.user))}\n'
                f'<b>Лот:</b> {html.escape(_iname(event.deal.item) or "")}\n'
                '<i>Отзыв удалён или снят модерацией.</i>'
            )
            self._emit(
                _log_text(title=f'🧹 Отзыв снят — заказ <a href="https://playerok.com/deal/{event.deal.id}">#{str(event.deal.id)[:8]}…</a>', text=body),
                _log_mess_kb(_uname(event.deal.user), _rev_chat),
            )

    async def _on_review_edit(self, event: ReviewEditedNotice) -> None:
        logger.debug('[event] REVIEW_UPDATED  deal=%s', event.deal.id)
        if _uid(event.deal.user) == self.account.id:
            return
        new = event.deal.review
        if not new:
            return
        try:
            prev = json.loads(event.previous_fp)
        except Exception:
            prev = {}
        self._trace_review_edit(event.deal, prev)
        if self._alert_on('review'):
            try:
                pr = max(0, int(prev.get('rating') or 0))
            except (TypeError, ValueError):
                pr = 0
            nr = max(0, int(new.rating or 0))
            pt = str(prev.get('text') or '') or '—'
            body = (
                f'<b>Клиент:</b> {html.escape(_uname(event.deal.user))}\n'
                f'<b>Лот:</b> {html.escape(_iname(event.deal.item) or "")}\n\n'
                f'<b>До правки:</b> {"⭐" * pr} ({pr}) — {html.escape(pt)}\n'
                f'<b>После:</b> {"⭐" * nr} ({nr}) — {html.escape(new.text or "—")}'
            )
            self._emit(
                _log_text(title=f'📝 Правка отзыва — <a href="https://playerok.com/deal/{event.deal.id}">заказ</a>', text=body),
                _log_new_review_kb(_uname(event.deal.user), event.deal.id),
            )

    async def _on_dispute(self, event: DealDisputeRaised) -> None:
        logger.debug('[event] DEAL_HAS_PROBLEM  deal=%s  user=%s', event.deal.id, _uname(event.deal.user))
        if _uid(event.deal.user) == self.account.id:
            return
        deal = event.deal
        try:
            deal = self.account.load_deal(event.deal.id)
        except Exception:
            logger.exception('load_deal for dispute')
        cat, det = _parse_dispute_text(deal)
        self._trace_dispute(deal, category=cat, detail=det)
        if self._alert_on('problem'):
            _prob_chat = deal.chat.id if deal.chat else None
            body = f'<b>Клиент:</b> {html.escape(_uname(deal.user))}\n<b>Лот:</b> {html.escape(_iname(deal.item) or "")}'
            if cat:
                body += f'\n<b>Тема:</b> {html.escape(cat)}'
            if det:
                body += f'\n<b>{"Детали" if cat else "Описание"}:</b> {html.escape(det)}'
            self._emit(
                _log_text(title=f'⚠️ Спор по <a href="https://playerok.com/deal/{deal.id}">заказу</a>', text=body),
                _log_mess_kb(_uname(deal.user), _prob_chat),
            )

    async def _on_dispute_close(self, event: DealDisputeCleared) -> None:
        logger.debug('[event] DEAL_PROBLEM_RESOLVED  deal=%s  user=%s', event.deal.id, _uname(event.deal.user))
        if _uid(event.deal.user) == self.account.id:
            return
        did = event.deal.id
        now = time.time()
        with self._problem_resolved_notify_lock:
            t0 = self._problem_resolved_notify_at.get(did)
            if t0 is not None and (now - t0) < 25.0:
                logger.debug('[bot] пропуск дубля DEAL_PROBLEM_RESOLVED для сделки %s', did)
                return
            self._problem_resolved_notify_at[did] = now
            if len(self._problem_resolved_notify_at) > 3000:
                self._problem_resolved_notify_at.clear()
        self._trace_dispute_close(event.deal, event.resolver_username)
        if self._alert_on('problem'):
            _chat = event.deal.chat.id if event.deal.chat else None
            body = f'<b>Клиент:</b> {html.escape(_uname(event.deal.user))}\n<b>Лот:</b> {html.escape(_iname(event.deal.item) or "")}'
            if event.resolver_username:
                body += f'\n<b>Отметка:</b> {html.escape(event.resolver_username)}'
            self._emit(
                _log_text(title=f'🟢 Спор закрыт — <a href="https://playerok.com/deal/{event.deal.id}">заказ</a>', text=body),
                _log_chat_only_kb(_chat),
            )

    def _verified_sale(self, deal: ItemDeal) -> tuple[ItemDeal, bool]:
        fresh = None
        for attempt in range(3):
            try:
                fresh = self.account.load_deal(deal.id)
                break
            except Exception as exc:
                logger.warning('Не удалось проверить сделку %s (%s/3): %s', deal.id, attempt + 1, exc)
                if self._stop_event.wait(2):
                    break
        current = fresh or deal
        if fresh is not None:
            if fresh.chat is None:
                fresh.chat = deal.chat
            if fresh.item is None:
                fresh.item = deal.item
        status_ok = current.status in (DealStage.PAID, DealStage.PENDING, None)
        item = current.item
        try:
            loaded = self.account.load_listing(item.id) if item is not None and item.id else None
            if loaded is not None:
                current.item = loaded
        except Exception as exc:
            logger.debug('Не удалось загрузить лот сделки %s: %s', deal.id, exc)
        mine = isinstance(current.item, MyItem) or _uid(getattr(current.item, 'user', None)) == self.account.id
        return current, bool(status_ok and mine)

    def _take_delivery(self, item_name: str) -> tuple[dict | None, str | None, int]:
        with self._delivery_lock:
            rules = cfg.read('auto_deliveries') or []
            index = best_rule_index(item_name, rules)
            if index is None:
                return None, None, 0
            rule = rules[index]
            if not rule.get('piece', True):
                return rule, None, 0
            goods = [g for g in (rule.get('goods') or []) if str(g).strip()]
            if not goods:
                return rule, None, 0
            good = goods.pop(0)
            rule['goods'] = goods
            cfg.write('auto_deliveries', rules)
            self.auto_deliveries = rules
            return rule, good, len(goods)

    @staticmethod
    def _stash_lost_good(rule: dict, good: str) -> str:
        import os
        from lib.util import project_root_dir
        path = os.path.join(project_root_dir(), 'conf', 'lost_goods.txt')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        phrases = ', '.join(str(p) for p in (rule.get('keyphrases') or []))
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(f'{datetime.now().isoformat(timespec="seconds")}\t{phrases}\t{good}\n')
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return 'conf/lost_goods.txt'

    def _return_delivery(self, rule: dict, good: str) -> None:
        with self._delivery_lock:
            rules = cfg.read('auto_deliveries') or []
            target = next((r for r in rules if r.get('keyphrases') == rule.get('keyphrases') and r.get('piece', True)), None)
            if target is None:
                where = self._stash_lost_good(rule, good)
                logger.error('Не удалось вернуть товар в автовыдачу: правило удалено. Товар сохранён в %s', where)
                self._push_notify('deal', _log_text(
                    title='📦 Товар не вернулся в автовыдачу',
                    text=f'Правило удалено, пока товар отправлялся. Товар сохранён в <code>{html.escape(where)}</code>.',
                ), None)
                return
            target.setdefault('goods', []).insert(0, good)
            cfg.write('auto_deliveries', rules)
            self.auto_deliveries = rules

    def _deliver(self, deal: ItemDeal, chat_id: str) -> str:
        item_name = _iname(deal.item)
        rule, good, left = self._take_delivery(item_name)
        if rule is None:
            return 'no_rule'
        buyer = _uname(deal.user)
        if rule.get('piece', True):
            if good is None:
                self._push(chat_id, self._render('out_of_stock', buyer=buyer, product=item_name, deal_id=deal.id))
                self._push_notify('deal', _log_text(
                    title='📦 Автовыдача: товар закончился',
                    text=f'<b>Лот:</b> {html.escape(item_name)}\n<b>Покупатель:</b> {html.escape(buyer)}\n'
                         f'<a href="https://playerok.com/deal/{deal.id}">Сделка</a> ждёт ручной выдачи.',
                ), _log_deal_kb(buyer, deal.id))
                return 'out_of_stock'
            if self._push(chat_id, good):
                logger.info('Автовыдача → %s%s%s  «%s»  остаток: %s%d%s', C_BRIGHT, buyer, Fore.RESET,
                            _norm_title(item_name)[:40], C_BRIGHT, left, Fore.RESET)
                if left <= 3:
                    self._push_notify('deal', _log_text(
                        title='📦 Автовыдача: заканчивается товар',
                        text=f'<b>Лот:</b> {html.escape(item_name)}\nОсталось: <b>{left}</b>',
                    ), None)
                return 'delivered'
            self._return_delivery(rule, good)
            return 'failed'
        text = '\n'.join(rule.get('message') or [])
        if not text.strip():
            return 'no_rule'
        text = self._fill(text, self._ctx(buyer=buyer, product=item_name, deal_id=deal.id, price=_iprice(deal.item),
                                          seller=getattr(self.account, 'username', '') or ''))
        if self._push(chat_id, text):
            logger.info('Автовыдача → %s%s%s  сообщение по правилу', C_BRIGHT, buyer, Fore.RESET)
            return 'delivered'
        return 'failed'

    def _should_autoconfirm(self, item_name: str) -> bool:
        confirm_cfg = (self.config.get('auto') or {}).get('confirm') or {}
        if not confirm_cfg.get('enabled'):
            return False
        if confirm_cfg.get('all'):
            return True
        return _title_matches_groups(item_name, (self.auto_complete_deals or {}).get('included') or [])

    async def _on_order(self, event: DealCreatedNotice) -> None:
        logger.debug('[event] NEW_DEAL  deal=%s', event.deal.id)
        if _uid(event.deal.user) == self.account.id:
            return
        deal, is_my_sale = await asyncio.to_thread(self._verified_sale, event.deal)
        chat_id = getattr(event.chat, 'id', None) or getattr(deal.chat, 'id', None)
        buyer = _uname(deal.user)
        item_name = _iname(deal.item)
        self._trace_order(deal)
        self._push_notify('deal', _log_text(
            title=f'🛒 Новый заказ <a href="https://playerok.com/deal/{deal.id}">↗</a>',
            text=f'<b>Клиент:</b> {html.escape(buyer)}\n<b>Позиция:</b> {html.escape(item_name)}\n'
                 f'<b>К оплате:</b> {html.escape(str(_iprice(deal.item)))} ₽',
        ), _log_deal_kb(buyer, deal.id))
        if not is_my_sale:
            logger.info('Сделка %s не прошла проверку (статус %s) — автоматизация пропущена',
                        deal.id, getattr(deal.status, 'name', '?'))
            return
        self._push(chat_id, self._render('new_deal', buyer=buyer, product=item_name, price=_iprice(deal.item), deal_id=deal.id))
        is_support = chat_id in (self.account.system_chat_id, self.account.support_chat_id)
        buyer_id = _uid(deal.user)
        if buyer_id and buyer_id not in self.initialized_users and not is_support:
            if (self.config.get('features') or {}).get('greet', True):
                self._push(chat_id, self._render('first_message', buyer=buyer, product=item_name))
            self.initialized_users.append(buyer_id)
        delivery = 'disabled'
        if (self.config.get('features') or {}).get('deliveries'):
            delivery = await asyncio.to_thread(self._deliver, deal, chat_id)
        if delivery in ('out_of_stock', 'failed'):
            logger.warning('Автоподтверждение сделки %s пропущено: автовыдача %s', deal.id, delivery)
            return
        confirm_cfg = (self.config.get('auto') or {}).get('confirm') or {}
        if delivery != 'delivered' and confirm_cfg.get('only_delivered', True) and confirm_cfg.get('enabled'):
            logger.info('Сделка %s не подтверждена автоматически: бот ничего не выдал по ней', deal.id)
            return
        if self._should_autoconfirm(item_name):
            try:
                await asyncio.to_thread(self.account.patch_deal, deal.id, DealStage.SENT)
                logger.info('Сделка %s%s%s подтверждена автоматически', C_BRIGHT, deal.id, Fore.RESET)
            except Exception as exc:
                logger.error('Не удалось автоматически подтвердить сделку %s: %s', deal.id, exc)

    async def _on_paid(self, event: ListingPaidNotice) -> None:
        logger.debug('[event] ITEM_PAID  deal=%s', event.deal.id)
        if _uid(event.deal.user) == self.account.id:
            return
        restore_cfg = (self.config.get('auto') or {}).get('restore') or {}
        item = event.deal.item
        if not restore_cfg.get('sold') or not getattr(item, 'id', None):
            return
        if getattr(item, 'keep_in_sale', None):
            return
        Thread(target=self._reactivate, args=(item, [20, 60, 180]), daemon=True, name='cxh-restore-sold').start()

    def _calc_net(self, deal: ItemDeal) -> int:
        try:
            try:
                deal = self.account.load_deal(deal.id)
            except Exception:
                pass
            item       = getattr(deal, 'item', None)
            item_price = None
            if item is not None:
                try:
                    item_price = int(getattr(item, 'price', None) or 0) or None
                except (TypeError, ValueError):
                    pass
            t = getattr(deal, 'transaction', None)
            if t is not None:
                v   = getattr(t, 'value', None)
                fee = getattr(t, 'fee', None) or 0
                if v is not None:
                    try:
                        vi = int(v)
                        fi = int(fee)
                        if item_price and vi > 100 * item_price:
                            vi //= 100
                            fi //= 100
                        net = vi - fi
                        return net if net > 0 else (vi if vi > 0 else 0)
                    except (TypeError, ValueError):
                        pass
            if item_price and item_price > 0:
                fm = getattr(item, 'fee_multiplier', None) if item is not None else None
                try:
                    if fm is not None and isinstance(fm, (int, float)) and 0 < float(fm) < 1:
                        return max(0, int(round(item_price * (1.0 - float(fm)))))
                except (TypeError, ValueError):
                    pass
                return item_price
        except Exception:
            pass
        return 0

    _STAGE_MAP: dict = {
        DealStage.PAID:       'Оплачен',
        DealStage.PENDING:    'В ожидании отправки',
        DealStage.SENT:       'Продавец подтвердил выполнение',
        DealStage.ROLLED_BACK:'Возврат',
    }

    async def _on_stage(self, event: DealStageChanged) -> None:
        logger.debug('[event] DEAL_STATUS_CHANGED  deal=%s  status=%s', event.deal.id, getattr(event.deal.status, 'name', '?'))
        if _uid(event.deal.user) == self.account.id:
            return
        confirmed_with_problem = False
        if event.deal.status is DealStage.CONFIRMED:
            try:
                confirmed_with_problem = bool(getattr(self.account.load_deal(event.deal.id), 'has_problem', False))
            except Exception:
                confirmed_with_problem = bool(getattr(event.deal, 'has_problem', False))
        if event.deal.status is DealStage.CONFIRMED and not confirmed_with_problem:
            status_frmtd = 'Покупатель подтвердил сделку'
        elif event.deal.status is DealStage.CONFIRMED and confirmed_with_problem:
            status_frmtd = 'Открыта жалоба (сделка подтверждена)'
        else:
            status_frmtd = self._STAGE_MAP.get(event.deal.status, 'Неизвестный')
        if not confirmed_with_problem:
            self._trace_stage(event.deal, status_frmtd)
        if self._alert_on('deal_changed') and not confirmed_with_problem:
            self._emit(_log_text(
                title=f'🔁 Этап заказа обновлён <a href="https://playerok.com/deal/{event.deal.id}/">↗</a>',
                text=f'<b>Сейчас:</b> {html.escape(status_frmtd)}',
            ))
        chat_id = getattr(event.chat, 'id', None)
        variables = {'buyer': _uname(event.deal.user), 'deal_id': event.deal.id,
                     'product': _iname(event.deal.item), 'price': _iprice(event.deal.item)}
        if event.deal.status is DealStage.SENT:
            self._push(chat_id, self._render('deal_sent', **variables))
        if event.deal.status is DealStage.CONFIRMED and not confirmed_with_problem:
            self._push(chat_id, self._render('deal_confirmed', **variables))
            self.stats.deals_completed += 1
            self.stats.earned_money    += self._calc_net(event.deal)
            _flush_counters(self.stats)
            restore_cfg = (self.config.get('auto') or {}).get('restore') or {}
            if restore_cfg.get('sold') and getattr(event.deal.item, 'id', None):
                Thread(target=self._reactivate, args=(event.deal.item, [30, 90]), daemon=True, name='cxh-restore-confirmed').start()
        if event.deal.status is DealStage.ROLLED_BACK:
            self._push(chat_id, self._render('deal_refunded', **variables))
            self.stats.deals_refunded += 1
            _flush_counters(self.stats)

    async def start(self) -> None:
        logger.debug('Движок запущен')
        from lib.util import apply_verbose
        apply_verbose(self.config.get('debug', {}).get('verbose', False))
        nick = (self.account.username or '').strip() or '—'
        logger.info('  %s✓%s  %sPlayerok: авторизованы как «%s»%s', C_SUCCESS, Fore.RESET, C_BRIGHT, nick, Fore.RESET)
        profile = self.account.profile
        deals_stats = getattr(getattr(profile, 'stats', None), 'deals', None)

        def _active(part) -> int | str:
            if part is None:
                return '—'
            return (part.total or 0) - (part.finished or 0)

        active_sales = _active(getattr(deals_stats, 'outgoing', None))
        active_buys = _active(getattr(deals_stats, 'incoming', None))
        acc_rows: list = [('Никнейм', self.account.username), ('ID', str(self.account.id)[:36]), None]
        if getattr(profile, 'balance', None):
            bal = profile.balance
            acc_rows += [
                ('Баланс', f'{bal.value} ₽'), ('  Доступно', f'{bal.available} ₽'),
                ('  Ожидание', f'{bal.pending_income} ₽'), ('  Заморожено', f'{bal.frozen} ₽'), None,
            ]
        acc_rows += [('Продажи', active_sales), ('Покупки', active_buys)]
        proxy = self.config['account']['proxy']
        if proxy:
            from lib.util import proxy_display_parts
            draw_box('АККАУНТ', acc_rows, lead='\n')
            ip, port, user, password = proxy_display_parts(proxy)
            if ip and port:
                ip_parts = ip.split('.')
                if len(ip_parts) == 4 and all(p.isdigit() for p in ip_parts):
                    ip_masked = '.'.join('*' * len(n) if i >= 2 else n for i, n in enumerate(ip_parts))
                else:
                    ip_masked = ip[:4] + '***' if len(ip) > 4 else '***'
                port_masked = f'{port[:2]}***' if len(port) >= 2 else '***'
                user_masked = f'{user[:3]}***' if user else '—'
                pass_masked = '●●●●●●' if password else '—'
                draw_box('ПРОКСИ АККАУНТА', [('Адрес', f'{ip_masked}:{port_masked}'), ('Логин', user_masked), ('Пароль', pass_masked)], trail='\n')
            else:
                draw_box('ПРОКСИ АККАУНТА', [('Прокси', 'задан (формат см. conf/config.json)')], trail='\n')
        else:
            draw_box('АККАУНТ', acc_rows, lead='\n', trail='\n')

        wire('ALIVE',                         MarketBridge._on_alive,      0)
        wire_mkt(MarketEvent.CHAT_INITIALIZED, MarketBridge._on_snapshot,  0)
        wire_mkt(MarketEvent.NEW_MESSAGE,      MarketBridge._on_inbound,   0)
        wire_mkt(MarketEvent.NEW_REVIEW,       MarketBridge._on_review_new, 0)
        wire_mkt(MarketEvent.REVIEW_REMOVED,   MarketBridge._on_review_del, 0)
        wire_mkt(MarketEvent.REVIEW_UPDATED,   MarketBridge._on_review_edit, 0)
        wire_mkt(MarketEvent.DEAL_HAS_PROBLEM, MarketBridge._on_dispute,   0)
        wire_mkt(MarketEvent.DEAL_PROBLEM_RESOLVED, MarketBridge._on_dispute_close, 0)
        wire_mkt(MarketEvent.NEW_DEAL,         MarketBridge._on_order,     0)
        wire_mkt(MarketEvent.ITEM_PAID,        MarketBridge._on_paid,      0)
        wire_mkt(MarketEvent.DEAL_STATUS_CHANGED, MarketBridge._on_stage,  0)

        processed_deals: list = []
        feed_since = datetime.now(timezone.utc)

        async def _event_loop():
            delay = 1
            while not self._stop_event.is_set():
                feed = Feed(self.account, ws_path='/chats', processed_deals=processed_deals, since=feed_since)
                self._feed = feed
                try:
                    for event in feed.listen():
                        if self._stop_event.is_set():
                            return
                        self._feed_last_event_at = time.monotonic()
                        delay = 1
                        await fire_mkt(event.type, [self, event])
                    if not self._stop_event.is_set():
                        raise RuntimeError('Playerok Feed завершился без команды остановки')
                except Exception:
                    if not self._stop_event.is_set():
                        self._feed_restarts += 1
                        logger.exception('Playerok Feed упал — перезапуск через %s с', delay)
                finally:
                    feed.stop()
                if self._stop_event.wait(delay):
                    return
                delay = min(30, delay * 2)

        self._feed_thread = spawn_async(_event_loop, name='PlayerokFeedSupervisor')
        await fire('ALIVE', [self])
