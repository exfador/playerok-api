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
from datetime import datetime, timedelta
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
from bot._kit import ACCENT_COLOR, VERSION
from bot._kit import C_PRIMARY, C_SUCCESS, C_WARNING, C_ERROR
from bot._kit import C_DIM, C_TEXT, C_BRIGHT, C_HIGHLIGHT
from bot._kit import set_console_title, halt, spawn_async, draw_box, iso_to_display_str
from bot._kit import _norm_title, _title_matches_groups
from bot._forge import message_body_html, first_link_preview_url
from bot._forge import _build_html, _build_plain, _humanize_msg, SYS_MSG_LABELS

logger = getLogger('cxh.bot')


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
        self._thread_chat_handles[username] = obj
        return obj

    def _sync_profile(self) -> None:
        self.account = self.bot_account = self.account.get()

    def _verify_access(self) -> None:
        user = self.account.load_user(self.account.id)
        if user.is_blocked:
            logger.critical('Аккаунт %s заблокирован', self.account.username)
            logger.critical('Обратитесь в поддержку платформы для выяснения причины блокировки')
            halt()

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
        if self.latest_events_times.get(event):
            return (
                datetime.fromisoformat(self.latest_events_times[event])
                + timedelta(seconds=self.config['auto']['bump']['interval'])
            )
        return datetime.now()

    def _push_notify(self, alert_key: str, text: str, kb) -> None:
        if not self.config.get('alerts', {}).get('enabled'):
            return
        if not (self.config.get('alerts', {}).get('on') or {}).get(alert_key, True):
            return
        try:
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(text=text, kb=kb),
                _get_panel_loop(),
            )
        except Exception:
            pass

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
               read_chat: bool | None = None, exclude_watermark: bool = False, max_attempts: int = 3) -> ChatMessage | None:
        if not text and not photo_file_path:
            return None
        logger.debug('[_push] chat=%s  text=%r  photo=%s', chat_id, (text or '')[:60], bool(photo_file_path))
        wm_cfg      = self.config['features']['watermark']
        wm_enabled  = wm_cfg['enabled']
        wm_text     = wm_cfg['text']
        wm_pos      = wm_cfg['position']
        read_enabled = self.config['features']['read_chat']
        for _ in range(max_attempts):
            try:
                body = text
                if body and wm_enabled and wm_text and not exclude_watermark:
                    body = f'{wm_text}\n\n{body}' if wm_pos == 'start' else f'{body}\n\n{wm_text}'
                use_read = read_enabled if read_chat is None else read_chat
                mess = self.account.send_message(chat_id=chat_id, text=body, photo_file_path=photo_file_path, read_chat=use_read)
                if mess:
                    self._store_msg(chat_id, mess)
                return mess
            except Exception as e:
                snippet = (text or photo_file_path or '').replace('\n', ' ')[:60]
                logger.error('Ошибка отправки «%s» → чат %s: %s', snippet, chat_id, e)
                return None
        return None

    def _pack(self, item: ItemProfile) -> dict:
        return {
            'id': item.id, 'slug': item.slug,
            'priority':   item.priority.name if item.priority else None,
            'status':     item.status.name   if item.status   else None,
            'name': item.name, 'price': item.price, 'raw_price': item.raw_price,
            'seller_type': item.seller_type.name if item.seller_type else None,
            'attachment': {
                'id': item.attachment.id, 'url': item.attachment.url,
                'filename': item.attachment.filename, 'mime': item.attachment.mime,
            },
            'user': {
                'id': item.user.id, 'username': item.user.username,
                'role': item.user.role.name if item.user.role else None,
                'avatar_url': item.user.avatar_url,
                'is_online': item.user.is_online, 'is_blocked': item.user.is_blocked,
                'rating': item.user.rating, 'reviews_count': item.user.reviews_count,
                'support_chat_id': item.user.support_chat_id,
                'system_chat_id': item.user.system_chat_id,
                'created_at': item.user.created_at,
            },
            'approval_date': item.approval_date,
            'priority_position': item.priority_position,
            'views_counter': item.views_counter,
            'fee_multiplier': item.fee_multiplier,
            'created_at': item.created_at,
        }

    def _unpack(self, item_data: dict) -> ItemProfile:
        data = copy.deepcopy(item_data)
        ud = data.pop('user')
        ud['role'] = AccountRole.__members__.get(ud['role']) if ud['role'] else None
        user = UserProfile(**ud)
        data['user'] = user
        ad = data.pop('attachment')
        data['attachment'] = FileObject(**ad)
        data['priority']    = BoostLevel.__members__.get(data['priority'])    if data['priority']    else None
        data['status']      = ListingStage.__members__.get(data['status'])    if data['status']      else None
        data['seller_type'] = AccountRole.__members__.get(data['seller_type'])if data['seller_type'] else None
        return ItemProfile(**data)

    def _listings(self, count: int = -1, game_id: str | None = None,
                  category_id: str | None = None, statuses: list[ListingStage] | None = None) -> list[ItemProfile]:
        my_items:  list[ItemProfile] = []
        svd_items: list[dict]        = []
        try:
            user        = self.account.load_user(self.account.id)
            next_cursor = None
            seen_cursors: set[str] = set()
            while True:
                itm_list = user.load_listings(count=24, after_cursor=next_cursor, game_id=game_id,
                                              category_id=category_id, statuses=statuses)
                for itm in itm_list.items:
                    svd_items.append(self._pack(itm))
                    if statuses is None or itm.status in statuses:
                        my_items.append(itm)
                        if 0 < count <= len(my_items):
                            return my_items
                if not itm_list.page_info.has_next_page:
                    break
                new_cursor = itm_list.page_info.end_cursor
                if not new_cursor or new_cursor == next_cursor or new_cursor in seen_cursors:
                    raise RuntimeError('Playerok вернул повторяющийся cursor при загрузке лотов')
                seen_cursors.add(new_cursor)
                next_cursor = new_cursor
                time.sleep(0.5)
            self.saved_items = svd_items
        except (RequestApiError, RequestFailedError):
            for itm_dict in list(self.saved_items):
                itm = self._unpack(itm_dict)
                if statuses is None or itm.status in statuses:
                    my_items.append(itm)
                    if 0 < count <= len(my_items):
                        return my_items
            if not my_items:
                raise
        return my_items

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
            inc_g = abi.get('included') or []
            exc_g = abi.get('excluded') or []
            all_b = self.config['auto']['bump']['all']
            included = _title_matches_groups(item.name, inc_g)
            excluded = _title_matches_groups(item.name, exc_g)

            if all_b and excluded:
                logger.debug('[elevate] пропуск «%s»: в исключениях', name_short)
                return 'skip_excluded'
            if not all_b and not included:
                logger.debug('[elevate] пропуск «%s»: нет совпадения с белым списком', name_short)
                return 'skip_phrases'
            my_item: MyItem | None = item if isinstance(item, MyItem) else None
            if my_item is None:
                try:
                    loaded = self.account.load_listing(item.id)
                except Exception:
                    logger.debug('[elevate] пропуск «%s»: не удалось загрузить карточку', name_short)
                    return 'skip_load'
                if not isinstance(loaded, MyItem):
                    logger.debug('[elevate] пропуск «%s»: карточка не MyItem', name_short)
                    return 'skip_load'
                my_item = loaded
            time.sleep(1)
            statuses = self.bot_account.load_boost_tiers(my_item.id, my_item.raw_price)
            try:
                prem_status = next(s for s in statuses if s.type == BoostLevel.PREMIUM or s.price > 0)
            except StopIteration:
                raise Exception('PREMIUM статус не найден')
            time.sleep(1)
            previous_sequence = my_item.sequence
            try:
                self.bot_account.apply_boost(my_item.id, prem_status.id)
            except Exception:
                refreshed = self.account.load_listing(my_item.id)
                if (
                    isinstance(refreshed, MyItem)
                    and refreshed.priority == BoostLevel.PREMIUM
                    and refreshed.sequence != previous_sequence
                ):
                    my_item = refreshed
                else:
                    raise
            short = my_item.name[:32] + ('...' if len(my_item.name) > 32 else '')
            logger.info('%s«%s»%s поднят  %s%s%s → %s1%s', C_BRIGHT, short, Fore.RESET, C_DIM, my_item.sequence, Fore.RESET, C_SUCCESS, Fore.RESET)
            self._notify_elevated(my_item.name, my_item.id)
            return 'bumped'
        except Exception as e:
            logger.error('Ошибка при поднятии «%s»: %s', item.name, e)
            return 'error'

    def _elevate_all(self) -> None:
        self.latest_events_times['auto_bump_items'] = datetime.now().isoformat()
        db.set('latest_events_times', self.latest_events_times)
        counters_map = {'bumped': 0, 'skip_priority': 0, 'skip_phrases': 0, 'skip_excluded': 0, 'skip_load': 0, 'skip_in_progress': 0, 'error': 0}
        try:
            items = self._listings(statuses=[ListingStage.APPROVED])
            if not items:
                logger.info('[elevate_all] нет лотов со статусом APPROVED.')
            for item in items:
                if item.priority != BoostLevel.PREMIUM:
                    counters_map['skip_priority'] += 1
                    continue
                result = self._elevate(item)
                counters_map[result if result in counters_map else 'error'] += 1
            logger.info(
                '[elevate_all] поднято: %s · не PREMIUM: %s · нет в списке: %s · исключено: %s · не загружено: %s · уже выполняется: %s · ошибок: %s',
                counters_map['bumped'], counters_map['skip_priority'], counters_map['skip_phrases'],
                counters_map['skip_excluded'], counters_map['skip_load'], counters_map['skip_in_progress'], counters_map['error'],
            )
        except Exception as e:
            logger.error('Ошибка при автоподнятии: %s', e)

    def bump_items(self) -> None:
        self._elevate_all()

    def _reactivate(self, item: Item | MyItem | ItemProfile, retry_delays: list[int] | None = None) -> None:
        item_id = str(item.id)
        with self._mutation_guard:
            if item_id in self._reactivating_items:
                logger.debug('Восстановление «%s» уже выполняется, дубликат пропущен', item_id)
                return
            self._reactivating_items.add(item_id)
        try:
            self._reactivate_once(item, retry_delays)
        finally:
            with self._mutation_guard:
                self._reactivating_items.discard(item_id)

    def _reactivate_once(self, item: Item | MyItem | ItemProfile, retry_delays: list[int] | None = None) -> None:
        try:
            ari = self.auto_restore_items
            included = any(
                any(p.lower() in item.name.lower() or item.name.lower() == p.lower() for p in grp)
                for grp in ari['included']
            )
            if not (self.config['auto']['restore']['all'] or included):
                return
            if not isinstance(item, MyItem):
                try:
                    item = self.account.load_listing(item.id)
                except Exception:
                    return
            premium_allowed = bool((self.config.get('auto', {}).get('restore') or {}).get('premium', False))
            delays = retry_delays if retry_delays is not None else [5, 15, 30]
            short = item.name[:32] + ('...' if len(item.name) > 32 else '')
            for attempt, delay in enumerate(delays, 1):
                time.sleep(delay)
                try:
                    logger.debug('Восстановление «%s»: попытка бесплатной публикации', item.name[:32])
                    time.sleep(1)
                    new_item = self.account.activate_listing(item.id, None)
                    if new_item.status in (ListingStage.PENDING_APPROVAL, ListingStage.APPROVED):
                        logger.info('%s«%s»%s восстановлен (бесплатно)', C_BRIGHT, short, Fore.RESET)
                        self._notify_reactivated(item.name, item.id)
                        return
                    logger.warning('Попытка %d: «%s» — статус %s, повтор...', attempt, short, new_item.status.name)
                except Exception as free_err:
                    try:
                        refreshed = self.account.load_listing(item.id)
                        if refreshed.status in (ListingStage.PENDING_APPROVAL, ListingStage.APPROVED):
                            logger.info('%s«%s»%s восстановлен (подтверждено после сетевой ошибки)', C_BRIGHT, short, Fore.RESET)
                            self._notify_reactivated(item.name, item.id)
                            return
                    except Exception:
                        pass
                    logger.debug('Восстановление «%s»: бесплатная публикация не сработала (%s), проверяю тиры...', item.name[:32], free_err)
                    try:
                        tiers = self.account.load_boost_tiers(item.id, item.raw_price)
                        if not tiers:
                            if attempt < len(delays):
                                logger.warning('Попытка %d: «%s» — тиры не получены, повтор через %d с...', attempt, short, delays[attempt])
                            else:
                                logger.error('Ошибка при восстановлении «%s»: не удалось получить тиры', short)
                            continue
                        free_tier = next((s for s in tiers if s.type == BoostLevel.DEFAULT or s.price == 0), None)
                        if free_tier is not None:
                            tier = free_tier
                            logger.debug('Восстановление «%s»: бесплатный тир %s (0₽)', item.name[:32], tier.id)
                        elif premium_allowed:
                            tier = tiers[0]
                            logger.info('Восстановление «%s»: платный тир «%s» (%s₽) — PREMIUM разрешён',
                                        item.name[:32],
                                        tier.name if hasattr(tier, 'name') else tier.id,
                                        getattr(tier, 'price', '?'))
                        else:
                            logger.info('%s«%s»%s пропущен: нет бесплатного тира, платное восстановление выключено',
                                        C_DIM, short, Fore.RESET)
                            return
                        time.sleep(1)
                        new_item = self.account.activate_listing(item.id, tier.id)
                        if new_item.status in (ListingStage.PENDING_APPROVAL, ListingStage.APPROVED):
                            label = 'бесплатно' if free_tier is not None else 'PREMIUM'
                            logger.info('%s«%s»%s восстановлен (%s)', C_BRIGHT, short, Fore.RESET, label)
                            self._notify_reactivated(item.name, item.id)
                            return
                        logger.warning('Попытка %d: «%s» — статус %s, повтор...', attempt, short, new_item.status.name)
                    except Exception as e:
                        if attempt < len(delays):
                            logger.warning('Попытка %d: не удалось восстановить «%s» (%s), повтор через %d с...', attempt, short, e, delays[attempt])
                        else:
                            logger.error('Ошибка при восстановлении «%s»: %s', short, e)
        except Exception as e:
            logger.error('Ошибка при восстановлении «%s»: %s', item.name, e)

    def _reactivate_expired(self) -> None:
        try:
            seen: list[str] = []
            for item in self._listings(statuses=[ListingStage.EXPIRED]):
                if item.id in seen:
                    continue
                seen.append(item.id)
                time.sleep(0.5)
                self._reactivate(item)
        except Exception as e:
            logger.error('Ошибка при восстановлении истёкших товаров: %s', e)

    def _reactivate_polled(self) -> None:
        statuses: list[ListingStage] = []
        if self.config['auto']['restore']['sold']:
            statuses.append(ListingStage.SOLD)
        if self.config['auto']['restore']['expired']:
            statuses.append(ListingStage.EXPIRED)
        if not statuses:
            return
        try:
            items = self._listings(statuses=statuses)
            logger.debug('[reactivate_polled] лотов: %d (статусы: %s)', len(items), [s.name for s in statuses])
            for item in items:
                time.sleep(0.4)
                self._reactivate(item)
        except Exception as e:
            logger.error('Ошибка при проверке завершённых лотов: %s', e)

    def _trace_msg(self, message: ChatMessage, chat_obj) -> None:
        eng = active_engine()
        try:
            chat_user = next(u.username for u in chat_obj.users if u.id != eng.account.id)
        except Exception:
            chat_user = message.user.username
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
            ('ID', deal.id), ('Покупатель', deal.user.username),
            ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽'),
        ])

    def _trace_review(self, deal: ItemDeal) -> None:
        stars = '★' * (deal.review.rating or 5)
        date  = iso_to_display_str(deal.review.created_at, fmt='%d.%m.%Y %H:%M')
        draw_box('НОВЫЙ ОТЗЫВ', [
            ('Сделка', deal.id), ('Оценка', f'{stars} ({deal.review.rating or 5})'),
            ('Автор', deal.review.creator.username), ('Текст', deal.review.text or '—'), ('Дата', date),
        ])

    def _trace_review_del(self, deal: ItemDeal) -> None:
        draw_box('ОТЗЫВ УДАЛЁН', [
            ('Сделка', deal.id), ('Покупатель', deal.user.username), ('Товар', deal.item.name or '—'),
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
            ('Покупатель', deal.user.username), ('Товар', deal.item.name or '—'),
            ('Сумма', f'{deal.item.price} ₽'),
        ])

    def _trace_dispute(self, deal: ItemDeal, category: str | None = None, detail: str | None = None) -> None:
        rows = [
            ('Сделка', deal.id), ('От', deal.user.username),
            ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽'),
        ]
        if category:
            rows.append(('Категория', category))
        if detail:
            rows.append(('Текст жалобы' if category else 'Причина', detail))
        draw_box('ЖАЛОБА', rows)

    def _trace_dispute_close(self, deal: ItemDeal, resolver_username: str | None = None) -> None:
        rows = [
            ('Сделка', deal.id), ('Покупатель', deal.user.username),
            ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽'),
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
                except Exception:
                    logger.error('Ошибка синхронизации конфигурации/состояния: %s', traceback.format_exc())
                if self._stop_event.wait(3):
                    return

        def _refresh_profile_loop():
            while not self._stop_event.wait(1800):
                try:
                    self._sync_profile()
                except Exception:
                    logger.error('Ошибка обновления аккаунта: %s', traceback.format_exc())

        def _access_check_loop():
            while not self._stop_event.is_set():
                try:
                    self._verify_access()
                except Exception:
                    logger.error('Ошибка проверки блокировки: %s', traceback.format_exc())
                if self._stop_event.wait(900):
                    return

        def _reactivate_expired_loop():
            while not self._stop_event.is_set():
                poll_on = (self.config.get('auto', {}).get('restore', {}).get('poll') or {}).get('enabled')
                if self.config['auto']['restore']['expired'] and not poll_on:
                    try:
                        self._reactivate_expired()
                    except Exception:
                        logger.error('Ошибка автовосстановления: %s', traceback.format_exc())
                if self._stop_event.wait(45):
                    return

        def _reactivate_poll_loop():
            while not self._stop_event.is_set():
                poll = (self.config.get('auto', {}).get('restore') or {}).get('poll') or {}
                iv   = max(30, int(poll.get('interval') or 300))
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
                if self.config['auto']['bump']['enabled'] and datetime.now() >= self._next_at('auto_bump_items'):
                    try:
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
                iv = max(300, int(upd_cfg.get('interval_sec') or 3600))
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
                iv = max(120, int(bc.get('interval_sec') or 1800))
                source = str(bc.get('source') or '').strip() or DEFAULT_SOURCE
                if not bc.get('enabled', True) or not source:
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

        targets = (_sync_loop, _refresh_profile_loop, _access_check_loop, _reactivate_expired_loop, _reactivate_poll_loop, _elevate_loop, _update_check_loop, _broadcast_loop)
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
                asyncio.run_coroutine_threadsafe(
                    _get_panel().call_seller(username, chat_id), _get_panel_loop(),
                )
                self._push(chat_id, self._render('cmd_seller'))
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
        alerts = self.config['alerts']
        if alerts['enabled']:
            want_msg = alerts['on']['message'] and not is_support
            want_sys = alerts['on']['system']  and is_support
            if want_msg or want_sys:
                body = _build_html(event.message)
                text = f'<b>{html.escape(event.message.user.username)}:</b>\n{body}'
                asyncio.run_coroutine_threadsafe(_get_panel().log_event(
                    text=_log_text(title='📩 Входящее сообщение', text=text.strip()),
                    kb=_log_mess_kb(event.message.user.username, event.chat.id),
                    link_preview_url=first_link_preview_url(event.message),
                ), _get_panel_loop())
        if not is_support and event.message.text is not None:
            if event.message.user.id not in self.initialized_users:
                self.initialized_users.append(event.message.user.id)
            if self.config['features']['commands']:
                self._exec_cmd(event.message.text, event.chat.id, event.message.user.username)

    async def _on_review_new(self, event: ReviewCreatedNotice) -> None:
        logger.debug('[event] NEW_REVIEW  deal=%s  rating=%s', event.deal.id, getattr(event.deal.review, 'rating', '?'))
        if event.deal.user.id == self.account.id:
            return
        self._trace_review(event.deal)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['review']:
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
                f'<b>Автор:</b> {html.escape(rev.creator.username or "?")}\n\n'
                '<b>Комментарий</b>\n'
                f'<blockquote>{html.escape(rtxt if rtxt else "—")}</blockquote>\n\n'
                f'<i>⏱ {html.escape(date_str)}</i>'
            )
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(
                    text=_log_text(title=f'⭐ Отзыв к заказу <a href="https://playerok.com/deal/{event.deal.id}">#{str(event.deal.id)[:8]}…</a>', text=body),
                    kb=_log_chat_only_kb(_rev_chat),
                ),
                _get_panel_loop(),
            )
        self._push(event.chat.id, self._render('new_review', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price, rating=event.deal.review.rating))

    async def _on_review_del(self, event: ReviewRemovedNotice) -> None:
        logger.debug('[event] REVIEW_REMOVED  deal=%s', event.deal.id)
        if event.deal.user.id == self.account.id:
            return
        self._trace_review_del(event.deal)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['review']:
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            body = (
                f'<b>Клиент:</b> {html.escape(event.deal.user.username)}\n'
                f'<b>Лот:</b> {html.escape(event.deal.item.name or "")}\n'
                '<i>Отзыв удалён или снят модерацией.</i>'
            )
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(
                    text=_log_text(title=f'🧹 Отзыв снят — заказ <a href="https://playerok.com/deal/{event.deal.id}">#{str(event.deal.id)[:8]}…</a>', text=body),
                    kb=_log_mess_kb(event.deal.user.username, _rev_chat),
                ),
                _get_panel_loop(),
            )

    async def _on_review_edit(self, event: ReviewEditedNotice) -> None:
        logger.debug('[event] REVIEW_UPDATED  deal=%s', event.deal.id)
        if event.deal.user.id == self.account.id:
            return
        new = event.deal.review
        if not new:
            return
        try:
            prev = json.loads(event.previous_fp)
        except Exception:
            prev = {}
        self._trace_review_edit(event.deal, prev)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['review']:
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            pr = int(prev.get('rating') or 0)
            pt = (prev.get('text') or '') or '—'
            body = (
                f'<b>Клиент:</b> {html.escape(event.deal.user.username)}\n'
                f'<b>Лот:</b> {html.escape(event.deal.item.name or "")}\n\n'
                f'<b>До правки:</b> {"⭐" * pr} ({pr}) — {html.escape(pt)}\n'
                f'<b>После:</b> {"⭐" * new.rating} ({new.rating}) — {html.escape(new.text or "—")}'
            )
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(
                    text=_log_text(title=f'📝 Правка отзыва — <a href="https://playerok.com/deal/{event.deal.id}">заказ</a>', text=body),
                    kb=_log_new_review_kb(event.deal.user.username, event.deal.id),
                ),
                _get_panel_loop(),
            )

    async def _on_dispute(self, event: DealDisputeRaised) -> None:
        logger.debug('[event] DEAL_HAS_PROBLEM  deal=%s  user=%s', event.deal.id, event.deal.user.username)
        if event.deal.user.id == self.account.id:
            return
        deal = event.deal
        try:
            deal = self.account.load_deal(event.deal.id)
        except Exception:
            logger.exception('load_deal for dispute')
        cat, det = _parse_dispute_text(deal)
        self._trace_dispute(deal, category=cat, detail=det)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['problem']:
            _prob_chat = deal.chat.id if deal.chat else None
            body = f'<b>Клиент:</b> {html.escape(deal.user.username)}\n<b>Лот:</b> {html.escape(deal.item.name or "")}'
            if cat:
                body += f'\n<b>Тема:</b> {html.escape(cat)}'
            if det:
                body += f'\n<b>{"Детали" if cat else "Описание"}:</b> {html.escape(det)}'
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(
                    text=_log_text(title=f'⚠️ Спор по <a href="https://playerok.com/deal/{deal.id}">заказу</a>', text=body),
                    kb=_log_mess_kb(deal.user.username, _prob_chat),
                ),
                _get_panel_loop(),
            )

    async def _on_dispute_close(self, event: DealDisputeCleared) -> None:
        logger.debug('[event] DEAL_PROBLEM_RESOLVED  deal=%s  user=%s', event.deal.id, event.deal.user.username)
        if event.deal.user.id == self.account.id:
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
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['problem']:
            _chat = event.deal.chat.id if event.deal.chat else None
            body = f'<b>Клиент:</b> {html.escape(event.deal.user.username)}\n<b>Лот:</b> {html.escape(event.deal.item.name or "")}'
            if event.resolver_username:
                body += f'\n<b>Отметка:</b> {html.escape(event.resolver_username)}'
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(
                    text=_log_text(title=f'🟢 Спор закрыт — <a href="https://playerok.com/deal/{event.deal.id}">заказ</a>', text=body),
                    kb=_log_chat_only_kb(_chat),
                ),
                _get_panel_loop(),
            )

    async def _on_order(self, event: DealCreatedNotice) -> None:
        logger.debug('[event] NEW_DEAL  user=%s  item=%s  deal=%s', event.deal.user.username, getattr(event.deal.item, 'name', '?'), event.deal.id)
        if event.deal.user.id == self.account.id:
            return
        try:
            event.deal.item = self.account.load_listing(event.deal.item.id)
        except Exception:
            pass
        self._trace_order(event.deal)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['deal']:
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(
                    text=_log_text(
                        title=f'🛒 Новый заказ <a href="https://playerok.com/deal/{event.deal.id}">↗</a>',
                        text=f"<b>Клиент:</b> {event.deal.user.username}\n<b>Позиция:</b> {event.deal.item.name or '—'}\n<b>К оплате:</b> {event.deal.item.price or '?'} ₽",
                    ),
                    kb=_log_deal_kb(event.deal.user.username, event.deal.id),
                ),
                _get_panel_loop(),
            )
        self._push(event.chat.id, self._render('new_deal', product=event.deal.item.name or '-', price=event.deal.item.price))
        is_support = event.chat.id in (self.account.system_chat_id, self.account.support_chat_id)
        if event.deal.user.id not in self.initialized_users and not is_support:
            self._push(event.chat.id, self._render('first_message', buyer=event.deal.user.username))
            self.initialized_users.append(event.deal.user.id)
        if self.config['features']['deliveries']:
            item_name = (event.deal.item.name or '').lower()
            for i, delivery in enumerate(list(self.auto_deliveries)):
                match = any(p.lower() in item_name or item_name == p.lower() for p in delivery['keyphrases'])
                if not match:
                    continue
                if delivery.get('piece', True):
                    goods = delivery.get('goods', [])
                    if not goods:
                        break
                    good = goods[0]
                    mess = self._push(event.chat.id, good)
                    if mess:
                        logger.info('Автовыдача → %s%s%s  «%s»  остаток: %s%d%s',
                                    C_BRIGHT, event.deal.user.username or '?', Fore.RESET,
                                    good[:40], C_BRIGHT, len(goods) - 1, Fore.RESET)
                        self.auto_deliveries[i]['goods'].pop(0)
                        cfg.write('auto_deliveries', self.auto_deliveries)
                else:
                    msg_text = delivery.get('message', '')
                    if msg_text:
                        mess = self._push(event.chat.id, '\n'.join(msg_text))
                        if mess:
                            logger.info('Автовыдача → %s%s%s  сообщение «%s»',
                                        C_BRIGHT, event.deal.user.username or '?', Fore.RESET,
                                        str(msg_text)[:40])
                break
        if self.config['auto']['confirm']['enabled']:
            if not event.deal.item.name:
                try:
                    event.deal.item = self.account.load_listing(event.deal.item.id)
                except Exception:
                    return
            item_name = event.deal.item.name or ''
            included = any(
                any(p.lower() in item_name.lower() or item_name.lower() == p.lower() for p in grp)
                for grp in self.auto_complete_deals['included']
            )
            if self.config['auto']['confirm']['all'] or included:
                self.account.patch_deal(event.deal.id, DealStage.SENT)
                logger.info('Сделка %s%s%s подтверждена автоматически', C_BRIGHT, event.deal.id, Fore.RESET)

    async def _on_paid(self, event: ListingPaidNotice) -> None:
        logger.debug('[event] ITEM_PAID  deal=%s  item=%s', event.deal.id, getattr(event.deal.item, 'name', '?'))
        if self.config['auto']['restore']['sold']:
            item_id = getattr(event.deal.item, 'id', None)
            if item_id:
                def _restore_on_paid(iid: str) -> None:
                    try:
                        it = self.account.load_listing(iid)
                        self._reactivate(it, retry_delays=[30, 60, 120])
                    except Exception as exc:
                        logger.error('Ошибка при восстановлении после оплаты: %s', exc)
                Thread(target=_restore_on_paid, args=(item_id,), daemon=True).start()

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
        if event.deal.user.id == self.account.id:
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
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['deal_changed'] and not confirmed_with_problem:
            asyncio.run_coroutine_threadsafe(
                _get_panel().log_event(_log_text(
                    title=f'🔁 Этап заказа обновлён <a href="https://playerok.com/deal/{event.deal.id}/">↗</a>',
                    text=f'<b>Сейчас:</b> {html.escape(status_frmtd)}',
                )),
                _get_panel_loop(),
            )
        if event.deal.status is DealStage.PENDING:
            self._push(event.chat.id, self._render('deal_pending', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
        if event.deal.status is DealStage.SENT:
            self._push(event.chat.id, self._render('deal_sent', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
        if event.deal.status is DealStage.CONFIRMED and not confirmed_with_problem:
            self._push(event.chat.id, self._render('deal_confirmed', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
            self.stats.deals_completed += 1
            self.stats.earned_money    += self._calc_net(event.deal)
            _flush_counters(self.stats)
            if self.config['auto']['restore']['sold']:
                item_id = getattr(event.deal.item, 'id', None)
                if item_id:
                    def _restore_after_confirm(iid: str) -> None:
                        try:
                            it = self.account.load_listing(iid)
                            self._reactivate(it, retry_delays=[30, 60, 120])
                        except Exception as exc:
                            logger.error('Ошибка при восстановлении после подтверждения: %s', exc)
                    Thread(target=_restore_after_confirm, args=(item_id,), daemon=True).start()
        if event.deal.status is DealStage.ROLLED_BACK:
            self._push(event.chat.id, self._render('deal_refunded', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
            self.stats.deals_refunded += 1
            _flush_counters(self.stats)

    async def start(self) -> None:
        logger.debug('Движок запущен')
        from lib.util import apply_verbose
        apply_verbose(self.config.get('debug', {}).get('verbose', False))
        nick = (self.account.username or '').strip() or '—'
        logger.info('  %s✓%s  %sPlayerok: авторизованы как «%s»%s', C_SUCCESS, Fore.RESET, C_BRIGHT, nick, Fore.RESET)
        stats       = self.account.profile.stats.deals
        active_sales = stats.outgoing.total  - stats.outgoing.finished
        active_buys  = stats.incoming.total  - stats.incoming.finished
        acc_rows: list = [('Никнейм', self.account.username), ('ID', str(self.account.id)[:36]), None]
        if self.bot_account.profile.balance:
            bal = self.account.profile.balance
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

        async def _event_loop():
            delay = 1
            while not self._stop_event.is_set():
                feed = Feed(self.account, ws_path='/chats')
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
