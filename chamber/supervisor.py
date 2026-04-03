from __future__ import annotations
import asyncio
import traceback
import time
from collections import deque
from datetime import datetime, timedelta
from threading import Thread, Lock
import textwrap
import shutil
import copy
import html
import json
import re
from colorama import Fore
from moor.sessiongate import SessionGate
from moor.kinds import *
from moor.shapes import *
from moor.tapstream import (
    TapStream,
    WireRoomSnapshot,
    WireChatLine,
    WireRatingAdded,
    WireRatingPulled,
    WireRatingEdited,
    WireSkuFunded,
    WireDealOpened,
    WireDealPhase,
    WireDealDispute,
    WireDisputeResolved,
)
from keel.tone import ACCENT_COLOR, VERSION, C_PRIMARY, C_SUCCESS, C_WARNING, C_ERROR, C_DIM, C_TEXT, C_BRIGHT, C_HIGHLIGHT
from keel.kit import set_console_title, halt, spawn_async, draw_box, _b_top as _box_top, _b_bot as _box_bot, iso_to_display_str
from keel.relay import hook_strata, hook_ingress, broadcast, broadcast_ingress
from keel.shelf import DATA, ConfigShelf as cfg
from keel.aliases import cc_get_items, cc_find_by_trigger
from logging import getLogger
from keel.stash import StateStash as db


def _bump_norm(text: str) -> str:
    return (text or '').lower().replace('ё', 'е').strip()


def _bump_name_matches_groups(name: str, groups: list | None) -> bool:
    if not name or not groups:
        return False
    n = _bump_norm(name)
    for grp in groups:
        if not grp:
            continue
        for phrase in grp:
            p = _bump_norm(phrase)
            if not p:
                continue
            if p in n or n == p:
                return True
    return False


def _get_facade():
    from trellis.facade import get_facade
    return get_facade()


def _get_facade_loop():
    from trellis.facade import get_facade_loop
    return get_facade_loop()


def _log_text(*a, **kw):
    from trellis.ui import log_text
    return log_text(*a, **kw)


def _log_mess_kb(*a, **kw):
    from trellis.ui import log_new_mess_kb
    return log_new_mess_kb(*a, **kw)


def _log_deal_kb(*a, **kw):
    from trellis.ui import log_new_deal_kb
    return log_new_deal_kb(*a, **kw)


def _log_new_review_kb(*a, **kw):
    from trellis.ui import log_new_review_kb
    return log_new_review_kb(*a, **kw)


def _log_chat_only_kb(*a, **kw):
    from trellis.ui import log_chat_only_kb
    return log_chat_only_kb(*a, **kw)


def _log_restore_ok_kb(*a, **kw):
    from trellis.ui.main import log_restore_ok_kb
    return log_restore_ok_kb(*a, **kw)


def _log_bump_ok_kb(*a, **kw):
    from trellis.ui.main import log_bump_ok_kb
    return log_bump_ok_kb(*a, **kw)


def _problem_category_and_detail(deal: ItemDeal) -> tuple[str | None, str | None]:
    sd = (deal.status_description or '').strip()
    cb = (deal.comment_from_buyer or '').strip()
    if not sd:
        return (None, cb or None)
    parts = re.split(r'\n\s*\n+', sd, maxsplit=1)
    first = parts[0].strip()
    second = (parts[1].strip() if len(parts) > 1 else '')
    if second:
        return (first, second)
    if cb and cb != first:
        return (first, cb)
    return (None, first or None)


SYSTEM_CHAT_PLACEHOLDER_LABELS = {
    '{{ITEM_PAID}}': '💳 Оплата по сделке (заказ создан)',
    '{{ITEM_SENT}}': '📤 Продавец отправил товар',
    '{{DEAL_CONFIRMED}}': '✅ Покупатель подтвердил получение',
    '{{DEAL_ROLLED_BACK}}': '↩️ Возврат / сделка отменена',
    '{{DEAL_HAS_PROBLEM}}': '⚠️ Жалоба по сделке',
    '{{DEAL_PROBLEM_RESOLVED}}': '✔️ Жалоба снята',
}


def _display_message_text(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip()
    return SYSTEM_CHAT_PLACEHOLDER_LABELS.get(t, text)


def _incoming_message_plain(message: ChatMessage) -> str:
    parts: list[str] = []
    if message.text:
        parts.append(_display_message_text(message.text) or '')
    if message.file is not None:
        if getattr(message.file, 'url', None):
            fn = message.file.filename or 'файл'
            parts.append(f'[файл] {fn} | {message.file.url}')
        else:
            parts.append(f'[файл] id={message.file.id}')
    for im in (message.images or []):
        if im is None:
            continue
        if getattr(im, 'url', None):
            parts.append(f'[изображение] {im.url}')
        else:
            parts.append(f'[изображение] id={im.id}')
    return '\n'.join(parts)


def _incoming_message_alert_html(message: ChatMessage) -> str:
    parts: list[str] = []
    if message.text:
        shown = _display_message_text(message.text)
        raw = (message.text or '').strip()
        if shown and shown != raw:
            parts.append(html.escape(shown))
        else:
            parts.append(html.escape(message.text))
    if message.file is not None:
        if getattr(message.file, 'url', None):
            fn = html.escape(message.file.filename or 'файл')
            u = html.escape(message.file.url)
            parts.append(f'📎 <a href="{u}">{fn}</a>')
        else:
            parts.append(f'📎 файл (id: {html.escape(str(message.file.id))})')
    for im in (message.images or []):
        if im is None:
            continue
        if getattr(im, 'url', None):
            u = html.escape(im.url)
            parts.append(f'📷 <a href="{u}">изображение</a>')
        else:
            parts.append(f'📷 изображение (id: {html.escape(str(im.id))})')
    if not parts:
        parts.append('<i>нет текста</i>')
    return '\n'.join(parts)


def message_body_html(message: ChatMessage) -> str:
    return _incoming_message_alert_html(message)


def first_link_preview_url(message: ChatMessage) -> str | None:
    for im in (message.images or []):
        if im is not None and getattr(im, 'url', None):
            return im.url
    f = message.file
    if f is not None and getattr(f, 'url', None):
        return f.url
    return None


from datetime import datetime as _dt
from dataclasses import dataclass as _dc


@_dc
class Stats:
    bot_launch_time: _dt
    deals_completed: int
    deals_refunded: int
    earned_money: int


def _load_stats() -> Stats:
    d = db.get('stats') or {}
    return Stats(bot_launch_time=None, deals_completed=int(d.get('deals_completed', 0)), deals_refunded=int(d.get('deals_refunded', 0)), earned_money=int(d.get('earned_money', 0)))


def _save_stats(s: Stats):
    db.set('stats', {'deals_completed': s.deals_completed, 'deals_refunded': s.deals_refunded, 'earned_money': s.earned_money})


_stats = _load_stats()


def get_stats() -> Stats:
    return _stats


def set_stats(new: Stats):
    global _stats
    _stats = new
    _save_stats(new)


logger = getLogger('chamber.sup')


def active_supervisor() -> Supervisor | None:
    if hasattr(Supervisor, 'instance'):
        return getattr(Supervisor, 'instance')


class Supervisor:

    def __new__(cls, *args, **kwargs) -> Supervisor:
        if not hasattr(cls, 'instance'):
            cls.instance = super(Supervisor, cls).__new__(cls)
        return getattr(cls, 'instance')

    def __init__(self):
        self.config = cfg.get('config')
        self.messages = cfg.get('messages')
        self.custom_commands = cfg.get('custom_commands')
        self.auto_deliveries = cfg.get('auto_deliveries')
        self.auto_restore_items = cfg.get('auto_restore_items')
        self.auto_complete_deals = cfg.get('auto_complete_deals')
        self.auto_bump_items = cfg.get('auto_bump_items')
        self.initialized_users = db.get('initialized_users')
        self.saved_items = db.get('saved_items')
        self.latest_events_times = db.get('latest_events_times')
        self.stats = get_stats()
        self.account = self.bot_account = SessionGate(
            token=self.config['account']['token'],
            user_agent=self.config['account']['user_agent'],
            requests_timeout=self.config['account']['timeout'],
            proxy=self.config['account']['proxy'] or None,
        ).get()
        self.__saved_chats: dict[str, Chat] = {}
        self._chat_msg_history: dict[str, deque] = {}
        self._chat_msg_history_lock = Lock()
        self._problem_resolved_notify_at: dict[str, float] = {}
        self._problem_resolved_notify_lock = Lock()

    def remember_chat_message(self, chat_id: str, message: ChatMessage | None) -> None:
        if not message or not getattr(message, 'id', None):
            return
        with self._chat_msg_history_lock:
            d = self._chat_msg_history.setdefault(chat_id, deque(maxlen=25))
            seen = {getattr(m, 'id', None) for m in d}
            if message.id in seen:
                return
            d.append(message)

    def get_recent_chat_messages(self, chat_id: str) -> list:
        with self._chat_msg_history_lock:
            d = self._chat_msg_history.get(chat_id)
            if not d:
                return []
            return list(d)

    def get_chat_by_id(self, chat_id: str) -> Chat:
        if chat_id in self.__saved_chats:
            return self.__saved_chats[chat_id]
        self.__saved_chats[chat_id] = self.account.load_chat(chat_id)
        return self.get_chat_by_id(chat_id)

    def find_chat_by_name(self, username: str) -> Chat:
        if username in self.__saved_chats:
            return self.__saved_chats[username]
        if username.lower() == 'поддержка':
            chat_obj = self.account.load_chat(self.account.support_chat_id)
        elif username.lower() == 'уведомления':
            chat_obj = self.account.load_chat(self.account.system_chat_id)
        else:
            chat_obj = self.account.find_chat_by_name(username)
        self.__saved_chats[username] = chat_obj
        return self.find_chat_by_name(username)

    def refresh_account(self):
        self.account = self.bot_account = self.account.get()

    def check_banned(self):
        user = self.account.load_user(self.account.id)
        if user.is_blocked:
            logger.critical(f'Аккаунт {self.account.username} заблокирован')
            logger.critical('Обратитесь в поддержку платформы для выяснения причины блокировки')
            halt()

    @staticmethod
    def _build_vars(**kwargs) -> dict:
        now = datetime.now()
        base = {
            'time':     now.strftime('%H:%M'),
            'date':     now.strftime('%d.%m.%Y'),
            'datetime': now.strftime('%d.%m.%Y %H:%M'),
        }
        base.update(kwargs)
        return base

    @staticmethod
    def _apply_vars(text: str, variables: dict) -> str:
        import re
        def _replace(m):
            name = m.group(1)
            return str(variables.get(name, m.group(0)))
        return re.sub(r'\$([a-zA-Z_][a-zA-Z0-9_]*)', _replace, text)

    def msg(self, message_name: str, messages_config_name: str = 'messages', messages_data: dict = DATA, **kwargs) -> str | None:
        messages = cfg.get(messages_config_name, messages_data) or {}
        mess = messages.get(message_name, {})
        if not mess.get('enabled'):
            return None
        message_lines: list[str] = mess.get('text', [])
        if not message_lines:
            return None
        try:
            seller = getattr(self.account, 'username', '') or ''
            variables = self._build_vars(seller=seller, **kwargs)
            return '\n'.join(self._apply_vars(line, variables) for line in message_lines)
        except Exception as e:
            logger.debug(f'[msg] ошибка подстановки в {message_name}: {e}')
            return '\n'.join(message_lines)

    def render_template_for_manual(self, message_id: str, buyer_username: str) -> str | None:
        messages = cfg.get('messages') or {}
        mess = messages.get(message_id, {})
        lines: list[str] = mess.get('text') or []
        if not lines:
            return None
        seller = getattr(self.account, 'username', '') or ''
        variables = self._build_vars(
            buyer=buyer_username,
            seller=seller,
            product='',
            price='',
            deal_id='',
            rating='',
            error='',
        )
        try:
            return '\n'.join(self._apply_vars(line, variables) for line in lines)
        except Exception as e:
            logger.debug(f'[render_template_for_manual] {message_id}: {e}')
            return '\n'.join(lines)

    def _event_datetime(self, event: str):
        if self.latest_events_times.get(event):
            return datetime.fromisoformat(self.latest_events_times[event]) + timedelta(seconds=self.config['auto']['bump']['interval'])
        return datetime.now()

    def _telegram_alert_restore_ok(self, item_name: str | None, item_id: str | None):
        if not self.config.get('alerts', {}).get('enabled'):
            return
        if not (self.config.get('alerts', {}).get('on') or {}).get('restore', True):
            return
        try:
            nm = html.escape((item_name or '?')[:220])
            iid = html.escape(str(item_id or ''))
            body = f'<b>{nm}</b>\n<code>{iid}</code>'
            asyncio.run_coroutine_threadsafe(
                _get_facade().log_event(
                    text=_log_text(title='♻️ Лот восстановлен', text=body),
                    kb=_log_restore_ok_kb(),
                ),
                _get_facade_loop(),
            )
        except Exception:
            pass

    def _telegram_alert_bump_ok(self, item_name: str | None, item_id: str | None):
        if not self.config.get('alerts', {}).get('enabled'):
            return
        if not (self.config.get('alerts', {}).get('on') or {}).get('bump', True):
            return
        try:
            nm = html.escape((item_name or '?')[:220])
            iid = html.escape(str(item_id or ''))
            body = f'<b>{nm}</b>\n<code>{iid}</code>'
            asyncio.run_coroutine_threadsafe(
                _get_facade().log_event(
                    text=_log_text(title='🔼 Лот поднят в топ', text=body),
                    kb=_log_bump_ok_kb(),
                ),
                _get_facade_loop(),
            )
        except Exception:
            pass

    def send_message(self, chat_id: str, text: str | None = None, photo_file_path: str | None = None, read_chat: bool = None, exclude_watermark: bool = False, max_attempts: int = 3) -> ChatMessage:
        if not text and not photo_file_path:
            return None
        logger.debug(f'[send_message] chat={chat_id}  text={repr((text or "")[:60])}  photo={bool(photo_file_path)}')
        for _ in range(max_attempts):
            try:
                read_chat_enabled = self.config['features']['read_chat']
                watermark_enabled = self.config['features']['watermark']['enabled']
                watermark = self.config['features']['watermark']['text']
                watermark_pos = self.config['features']['watermark']['position']
                if text and watermark_enabled and watermark and not exclude_watermark:
                    if watermark_pos == 'start':
                        text = f'{watermark}\n\n{text}'
                    else:
                        text += f'\n\n{watermark}'
                read_chat = read_chat_enabled or False if read_chat is None else read_chat
                mess = self.account.send_message(chat_id=chat_id, text=text, photo_file_path=photo_file_path, read_chat=read_chat)
                if mess:
                    self.remember_chat_message(chat_id, mess)
                return mess
            except Exception as e:
                snippet = (text or photo_file_path or '').replace('\n', ' ')[:60]
                logger.error(f'Ошибка отправки «{snippet}» → чат {chat_id}: {e}')
                return
        snippet = (text or photo_file_path or '').replace('\n', ' ')[:60]
        logger.error(f'Не удалось отправить «{snippet}» → чат {chat_id}')

    def _serealize_item(self, item: ItemProfile) -> dict:
        return {'id': item.id, 'slug': item.slug, 'priority': item.priority.name if item.priority else None, 'status': item.status.name if item.status else None, 'name': item.name, 'price': item.price, 'raw_price': item.raw_price, 'seller_type': item.seller_type.name if item.seller_type else None, 'attachment': {'id': item.attachment.id, 'url': item.attachment.url, 'filename': item.attachment.filename, 'mime': item.attachment.mime}, 'user': {'id': item.user.id, 'username': item.user.username, 'role': item.user.role.name if item.user.role else None, 'avatar_url': item.user.avatar_url, 'is_online': item.user.is_online, 'is_blocked': item.user.is_blocked, 'rating': item.user.rating, 'reviews_count': item.user.reviews_count, 'support_chat_id': item.user.support_chat_id, 'system_chat_id': item.user.system_chat_id, 'created_at': item.user.created_at}, 'approval_date': item.approval_date, 'priority_position': item.priority_position, 'views_counter': item.views_counter, 'fee_multiplier': item.fee_multiplier, 'created_at': item.created_at}

    def _deserealize_item(self, item_data: dict) -> ItemProfile:
        item_data = copy.deepcopy(item_data)
        user_data = item_data.pop('user')
        user_data['role'] = AccountRole.__members__.get(user_data['role']) if user_data['role'] else None
        user = UserProfile(**user_data)
        user.__account = self.account
        item_data['user'] = user
        attachment_data = item_data.pop('attachment')
        attachment = FileObject(**attachment_data)
        item_data['attachment'] = attachment
        item_data['priority'] = BoostLevel.__members__.get(item_data['priority']) if item_data['priority'] else None
        item_data['status'] = ListingStage.__members__.get(item_data['status']) if item_data['status'] else None
        item_data['seller_type'] = AccountRole.__members__.get(item_data['seller_type']) if item_data['seller_type'] else None
        return ItemProfile(**item_data)

    def get_my_items(self, count: int = -1, game_id: str | None = None, category_id: str | None = None, statuses: list[ListingStage] | None = None) -> list[ItemProfile]:
        my_items: list[ItemProfile] = []
        svd_items: list[dict] = []
        try:
            user = self.account.load_user(self.account.id)
            next_cursor = None
            while True:
                itm_list = user.load_listings(count=24, after_cursor=next_cursor, game_id=game_id, category_id=category_id, statuses=statuses)
                for itm in itm_list.items:
                    svd_items.append(self._serealize_item(itm))
                    if statuses is None or itm.status in statuses:
                        my_items.append(itm)
                        if len(my_items) >= count and count != -1:
                            return my_items
                if not itm_list.page_info.has_next_page:
                    break
                next_cursor = itm_list.page_info.end_cursor
                time.sleep(0.5)
            self.saved_items = svd_items
        except (UpstreamGraphError, HttpStatusError):
            for itm_dict in list(self.saved_items):
                itm = self._deserealize_item(itm_dict)
                if statuses is None or itm.status in statuses:
                    my_items.append(itm)
                    if len(my_items) >= count and count != -1:
                        return my_items
            if not my_items:
                raise
        return my_items

    def bump_item(self, item: ItemProfile | MyItem) -> str:
        name_short = (item.name or '?')[:100]
        try:
            abi = self.auto_bump_items or {}
            inc_g = abi.get('included') or []
            exc_g = abi.get('excluded') or []
            included = _bump_name_matches_groups(item.name, inc_g)
            excluded = _bump_name_matches_groups(item.name, exc_g)
            all_b = self.config['auto']['bump']['all']
            cond = (all_b and not excluded) or (not all_b and included)
            if not cond:
                if all_b and excluded:
                    logger.debug('[bump] пропуск «%s»: в списке исключений для поднятия', name_short)
                    return 'skip_excluded'
                logger.debug('[bump] пропуск «%s»: режим «по списку» — нет совпадения с белым списком (ё/е считаются одинаковыми)', name_short)
                return 'skip_phrases'
            if not isinstance(item, MyItem):
                try:
                    item = self.account.load_listing(item.id)
                except Exception:
                    logger.debug('[bump] пропуск «%s»: не удалось загрузить полную карточку лота', name_short)
                    return 'skip_load'
            time.sleep(1)
            statuses: list[ItemPriorityStatus] = self.bot_account.load_boost_tiers(item.id, item.raw_price)
            try:
                prem_status = [status for status in statuses if status.type == BoostLevel.PREMIUM or status.price > 0][0]
            except Exception:
                raise Exception('PREMIUM статус не найден')
            time.sleep(1)
            self.bot_account.apply_boost(item.id, prem_status.id)
            sequence = item.sequence
            item_name_frmtd = item.name[:32] + ('...' if len(item.name) > 32 else '')
            logger.info(f'{C_BRIGHT}«{item_name_frmtd}»{Fore.RESET} поднят  {C_DIM}{sequence}{Fore.RESET} → {C_SUCCESS}1{Fore.RESET}')
            logger.debug('[bump] поднят «%s» (sequence %s → 1)', name_short, sequence)
            self._telegram_alert_bump_ok(item.name, item.id)
            return 'bumped'
        except Exception as e:
            logger.error(f'Ошибка при поднятии «{item.name}»: {e}')
            return 'error'

    def bump_items(self):
        self.latest_events_times['auto_bump_items'] = datetime.now().isoformat()
        db.set('latest_events_times', self.latest_events_times)
        n_bumped = 0
        n_skip_priority = 0
        n_skip_phrases = 0
        n_skip_excluded = 0
        n_skip_load = 0
        n_err = 0
        try:
            items = self.get_my_items(statuses=[ListingStage.APPROVED])
            if not items:
                logger.info(
                    '[bump] нет лотов в продаже (статус APPROVED). Проданные (SOLD), на модерации и архив не поднимаются — '
                    'сначала восстановите или опубликуйте объявление.',
                )
            for item in items:
                nm = (item.name or '?')[:100]
                pri = getattr(item.priority, 'name', item.priority)
                if item.priority != BoostLevel.PREMIUM:
                    n_skip_priority += 1
                    logger.debug('[bump] пропуск «%s»: приоритет %s (нужен PREMIUM)', nm, pri)
                    continue
                r = self.bump_item(item)
                if r == 'bumped':
                    n_bumped += 1
                elif r == 'skip_phrases':
                    n_skip_phrases += 1
                elif r == 'skip_excluded':
                    n_skip_excluded += 1
                elif r == 'skip_load':
                    n_skip_load += 1
                else:
                    n_err += 1
            logger.debug(
                '[bump] итог: поднято=%s, не PREMIUM=%s, нет в белом списке=%s, в исключениях=%s, не загрузилась карточка=%s, ошибок=%s',
                n_bumped, n_skip_priority, n_skip_phrases, n_skip_excluded, n_skip_load, n_err,
            )
            logger.info(
                '[bump] поднято: %s · не PREMIUM: %s · не по списку фраз: %s · в исключениях: %s · не загрузилась карточка: %s · ошибок: %s',
                n_bumped, n_skip_priority, n_skip_phrases, n_skip_excluded, n_skip_load, n_err,
            )
        except Exception as e:
            logger.error(f'Ошибка при автоподнятии: {e}')

    def restore_item(self, item: Item | MyItem | ItemProfile):
        try:
            included = any((any((phrase.lower() in item.name.lower() or item.name.lower() == phrase.lower() for phrase in included_item)) for included_item in self.auto_restore_items['included']))
            if self.config['auto']['restore']['all'] or (not self.config['auto']['restore']['all'] and included):
                if not isinstance(item, MyItem):
                    try:
                        item = self.account.load_listing(item.id)
                    except Exception:
                        return
                time.sleep(1)
                priority_statuses = self.account.load_boost_tiers(item.id, item.raw_price)
                try:
                    priority_status = [status for status in priority_statuses if status.type == BoostLevel.DEFAULT or status.price == 0][0]
                except Exception:
                    priority_status = [status for status in priority_statuses][0]
                time.sleep(1)
                new_item = self.account.activate_listing(item.id, priority_status.id)
                item_name_frmtd = item.name[:32] + ('...' if len(item.name) > 32 else '')
                if new_item.status in (ListingStage.PENDING_APPROVAL, ListingStage.APPROVED):
                    logger.info(f'{C_BRIGHT}«{item_name_frmtd}»{Fore.RESET} восстановлен')
                    self._telegram_alert_restore_ok(item.name, item.id)
                else:
                    logger.error(f'Не удалось восстановить «{item_name_frmtd}» — статус: {new_item.status.name}')
        except Exception as e:
            logger.error(f'Ошибка при восстановлении «{item.name}»: {e}')

    def restore_expired_items(self):
        try:
            restored_items = []
            items = self.get_my_items(statuses=[ListingStage.EXPIRED])
            for item in items:
                if item.id in restored_items:
                    continue
                restored_items.append(item.id)
                time.sleep(0.5)
                self.restore_item(item)
        except Exception as e:
            logger.error(f'Ошибка при восстановлении истёкших товаров: {e}')

    def restore_poll_completed_items(self):
        st: list[ListingStage] = []
        if self.config['auto']['restore']['sold']:
            st.append(ListingStage.SOLD)
        if self.config['auto']['restore']['expired']:
            st.append(ListingStage.EXPIRED)
        if not st:
            return
        try:
            items = self.get_my_items(statuses=st)
            logger.debug('[restore/poll] завершённые лоты по API: %s шт. (статусы: %s)', len(items), [s.name for s in st])
            for item in items:
                time.sleep(0.4)
                self.restore_item(item)
        except Exception as e:
            logger.error(f'Ошибка при проверке завершённых лотов для восстановления: {e}')

    def log_new_message(self, message: ChatMessage, chat_obj: Chat):
        eng = active_supervisor()
        try:
            chat_user = [u.username for u in chat_obj.users if u.id != eng.account.id][0]
        except Exception:
            chat_user = message.user.username
        text = _incoming_message_plain(message)
        if not text.strip():
            text = '[пустое сообщение]'
        max_w = shutil.get_terminal_size((80, 20)).columns - 12
        w = min(max_w, 58)
        lines = [_box_top(f'СООБЩЕНИЕ ── {chat_user}', w)]
        sender_line = f'{C_BRIGHT}{message.user.username}:{Fore.RESET}'
        lines.append(f'{C_DIM}  │{Fore.RESET}  {sender_line}')
        for raw in (text or '').split('\n'):
            if not raw.strip():
                lines.append(f'{C_DIM}  │{Fore.RESET}')
                continue
            for chunk in textwrap.wrap(raw, width=w - 6) or [raw]:
                lines.append(f'{C_DIM}  │{Fore.RESET}  {C_TEXT}{chunk}{Fore.RESET}')
        lines.append(_box_bot(w))
        logger.info('\n'.join(lines))

    def log_new_deal(self, deal: ItemDeal):
        draw_box('НОВАЯ СДЕЛКА', [('ID', deal.id), ('Покупатель', deal.user.username), ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽')])

    def log_new_review(self, deal: ItemDeal):
        stars = '★' * (deal.review.rating or 5)
        date = iso_to_display_str(deal.review.created_at, fmt='%d.%m.%Y %H:%M')
        draw_box('НОВЫЙ ОТЗЫВ', [('Сделка', deal.id), ('Оценка', f'{stars} ({deal.review.rating or 5})'), ('Автор', deal.review.creator.username), ('Текст', deal.review.text or '—'), ('Дата', date)])

    def log_review_removed(self, deal: ItemDeal):
        draw_box('ОТЗЫВ УДАЛЁН', [('Сделка', deal.id), ('Покупатель', deal.user.username), ('Товар', deal.item.name or '—')])

    def log_review_updated(self, deal: ItemDeal, prev: dict):
        new = deal.review
        if not new:
            return
        draw_box('ОТЗЫВ ИЗМЕНЁН', [
            ('Сделка', deal.id),
            ('Было', f"⭐{prev.get('rating', '?')}  {prev.get('text') or '—'}"),
            ('Стало', f"⭐{new.rating}  {new.text or '—'}"),
        ])

    def log_deal_status_changed(self, deal: ItemDeal, status_frmtd: str = 'Неизвестно'):
        draw_box('СТАТУС СДЕЛКИ', [('ID', deal.id), ('Новый статус', status_frmtd), ('Покупатель', deal.user.username), ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽')])

    def log_new_problem(self, deal: ItemDeal, category: str | None = None, detail: str | None = None):
        rows = [('Сделка', deal.id), ('От', deal.user.username), ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽')]
        if category:
            rows.append(('Категория', category))
        if detail:
            rows.append(('Текст жалобы' if category else 'Причина', detail))
        draw_box('ЖАЛОБА', rows)

    def log_problem_resolved(self, deal: ItemDeal, resolver_username: str | None = None):
        rows = [('Сделка', deal.id), ('Покупатель', deal.user.username), ('Товар', deal.item.name or '—'), ('Сумма', f'{deal.item.price} ₽')]
        if resolver_username:
            rows.append(('Сообщение от', resolver_username))
        draw_box('ЖАЛОБА СНЯТА', rows)

    async def _on_bot_init(self):
        self.stats.bot_launch_time = datetime.now()

        def endless_loop():
            while True:
                balance = self.account.profile.balance.value if self.account.profile.balance is not None else '?'
                set_console_title(f'CXH Playerok v{VERSION} | {self.account.username}: {balance}₽')
                if self.stats != get_stats():
                    set_stats(self.stats)
                new_config = cfg.get('config')
                if new_config != self.config:
                    old_verbose = self.config.get('debug', {}).get('verbose', False)
                    new_verbose = new_config.get('debug', {}).get('verbose', False)
                    self.config = new_config
                    if old_verbose != new_verbose:
                        from keel.kit import apply_verbose
                        apply_verbose(new_verbose)
                if cfg.get('messages') != self.messages:
                    self.messages = cfg.get('messages')
                if cfg.get('custom_commands') != self.custom_commands:
                    self.custom_commands = cfg.get('custom_commands')
                if cfg.get('auto_deliveries') != self.auto_deliveries:
                    self.auto_deliveries = cfg.get('auto_deliveries')
                if cfg.get('auto_restore_items') != self.auto_restore_items:
                    self.auto_restore_items = cfg.get('auto_restore_items')
                if cfg.get('auto_complete_deals') != self.auto_complete_deals:
                    self.auto_complete_deals = cfg.get('auto_complete_deals')
                if cfg.get('auto_bump_items') != self.auto_bump_items:
                    self.auto_bump_items = cfg.get('auto_bump_items')
                if db.get('initialized_users') != self.initialized_users:
                    db.set('initialized_users', self.initialized_users)
                if db.get('saved_items') != self.saved_items:
                    db.set('saved_items', self.saved_items)
                if db.get('latest_events_times') != self.latest_events_times:
                    db.set('latest_events_times', self.latest_events_times)
                time.sleep(3)

        def refresh_account_loop():
            while True:
                time.sleep(1800)
                try:
                    self.refresh_account()
                except Exception:
                    logger.error(f'Ошибка обновления аккаунта: {traceback.format_exc()}')

        def check_banned_loop():
            while True:
                try:
                    self.check_banned()
                except Exception:
                    logger.error(f'Ошибка проверки блокировки: {traceback.format_exc()}')
                time.sleep(900)

        def restore_expired_items_loop():
            while True:
                poll_on = (self.config.get('auto', {}).get('restore', {}).get('poll') or {}).get('enabled')
                if self.config['auto']['restore']['expired'] and not poll_on:
                    try:
                        self.restore_expired_items()
                    except Exception:
                        logger.error(f'Ошибка автовосстановления товаров: {traceback.format_exc()}')
                time.sleep(45)

        def restore_poll_loop():
            while True:
                poll = (self.config.get('auto', {}).get('restore', {}) or {}).get('poll') or {}
                iv = max(30, int(poll.get('interval') or 300))
                if poll.get('enabled'):
                    try:
                        self.restore_poll_completed_items()
                    except Exception:
                        logger.error(f'Ошибка проверки завершённых лотов (восстановление): {traceback.format_exc()}')
                    time.sleep(iv)
                else:
                    time.sleep(15)

        def bump_items_loop():
            while True:
                if self.config['auto']['bump']['enabled'] and datetime.now() >= self._event_datetime('auto_bump_items'):
                    try:
                        self.bump_items()
                    except Exception:
                        logger.error(f'Ошибка автоподнятия: {traceback.format_exc()}')
                time.sleep(3)

        Thread(target=endless_loop, daemon=True).start()
        Thread(target=refresh_account_loop, daemon=True).start()
        Thread(target=check_banned_loop, daemon=True).start()
        Thread(target=restore_expired_items_loop, daemon=True).start()
        Thread(target=restore_poll_loop, daemon=True).start()
        Thread(target=bump_items_loop, daemon=True).start()

    def _run_custom_chat_command(self, raw_text: str, chat_id: str, username: str) -> None:
        items = cc_get_items(self.custom_commands)
        item = cc_find_by_trigger(items, raw_text)
        if not item:
            return
        for ev in item.get('events') or []:
            if ev == 'call_seller':
                asyncio.run_coroutine_threadsafe(_get_facade().call_seller(username, chat_id), _get_facade_loop())
                self.send_message(chat_id, self.msg('cmd_seller'))
        rl = [x for x in (item.get('reply_lines') or []) if str(x).strip()]
        if rl:
            self.send_message(chat_id, '\n'.join(rl))

    async def _on_room_synced(self, event: WireRoomSnapshot):
        if event.chat.last_message:
            self.remember_chat_message(event.chat.id, event.chat.last_message)

    async def _on_corr_inbound(self, event: WireChatLine):
        logger.debug(f'[event] CORR_INBOUND  user={getattr(event.message.user, "username", "?")}  chat={event.chat.id}')
        if event.message.user is None:
            return
        self.remember_chat_message(event.chat.id, event.message)
        self.log_new_message(event.message, event.chat)
        if event.message.user.id == self.account.id:
            return
        is_support_chat = event.chat.id in (self.account.system_chat_id, self.account.support_chat_id)
        if self.config['alerts']['enabled'] and (self.config['alerts']['on']['message'] or self.config['alerts']['on']['system']):
            do = False
            if self.config['alerts']['on']['message'] and not is_support_chat or (self.config['alerts']['on']['system'] and is_support_chat):
                do = True
            if do:
                body = _incoming_message_alert_html(event.message)
                text = f'<b>{html.escape(event.message.user.username)}:</b>\n{body}'
                asyncio.run_coroutine_threadsafe(_get_facade().log_event(
                    text=_log_text(title=f'💬 Новое сообщение в чате', text=text.strip()),
                    kb=_log_mess_kb(event.message.user.username, event.chat.id),
                    link_preview_url=first_link_preview_url(event.message),
                ), _get_facade_loop())
        if not is_support_chat and event.message.text is not None:
            if event.message.user.id not in self.initialized_users:
                self.initialized_users.append(event.message.user.id)
            if self.config['features']['commands']:
                self._run_custom_chat_command(event.message.text, event.chat.id, event.message.user.username)

    async def _on_stars_new(self, event: WireRatingAdded):
        logger.debug(f'[event] STARS_NEW  deal={event.deal.id}  rating={getattr(event.deal.review, "rating", "?")}')
        if event.deal.user.id == self.account.id:
            return
        self.log_new_review(event.deal)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['review']:
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            rev = event.deal.review
            rtxt = (rev.text or '').strip()
            try:
                date_str = iso_to_display_str(rev.created_at, fmt='%d.%m.%Y · %H:%M')
            except Exception:
                date_str = str(rev.created_at or '')
            stars = '⭐' * max(0, rev.rating or 0) or '—'
            body = (
                f'<b>Оценка:</b> {stars}\n'
                f'<b>Оставил:</b> {html.escape(rev.creator.username or "?")}\n\n'
                '<b>Текст отзыва</b>\n'
                f'<blockquote>{html.escape(rtxt if rtxt else "—")}</blockquote>\n\n'
                f'<i>🕐 {html.escape(date_str)}</i>'
            )
            asyncio.run_coroutine_threadsafe(
                _get_facade().log_event(
                    text=_log_text(title=f'💬✨ Новый отзыв по <a href="https://playerok.com/deal/{event.deal.id}">сделке</a>', text=body),
                    kb=_log_chat_only_kb(_rev_chat),
                ),
                _get_facade_loop(),
            )
        self.send_message(event.chat.id, self.msg('new_review', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price, rating=event.deal.review.rating))

    async def _on_stars_removed(self, event: WireRatingPulled):
        logger.debug(f'[event] STARS_REMOVED  deal={event.deal.id}')
        if event.deal.user.id == self.account.id:
            return
        self.log_review_removed(event.deal)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['review']:
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            body = (
                f'<b>Покупатель:</b> {html.escape(event.deal.user.username)}\n'
                f'<b>Предмет:</b> {html.escape(event.deal.item.name or "")}\n'
                '<i>Покупатель убрал отзыв (или отзыв снят модерацией).</i>'
            )
            asyncio.run_coroutine_threadsafe(
                _get_facade().log_event(
                    text=_log_text(title=f'🗑 Отзыв снят по <a href="https://playerok.com/deal/{event.deal.id}">сделке</a>', text=body),
                    kb=_log_mess_kb(event.deal.user.username, _rev_chat),
                ),
                _get_facade_loop(),
            )

    async def _on_stars_amended(self, event: WireRatingEdited):
        logger.debug(f'[event] STARS_AMENDED  deal={event.deal.id}')
        if event.deal.user.id == self.account.id:
            return
        new = event.deal.review
        if not new:
            return
        try:
            prev = json.loads(event.previous_fp)
        except Exception:
            prev = {}
        self.log_review_updated(event.deal, prev)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['review']:
            _rev_chat = event.deal.chat.id if event.deal.chat else None
            pr = int(prev.get('rating') or 0)
            pt = (prev.get('text') or '') or '—'
            body = (
                f'<b>Покупатель:</b> {html.escape(event.deal.user.username)}\n'
                f'<b>Предмет:</b> {html.escape(event.deal.item.name or "")}\n\n'
                f'<b>Было:</b> {"⭐" * pr} ({pr}) — {html.escape(pt)}\n'
                f'<b>Стало:</b> {"⭐" * new.rating} ({new.rating}) — {html.escape(new.text or "—")}'
            )
            asyncio.run_coroutine_threadsafe(
                _get_facade().log_event(
                    text=_log_text(title=f'✏️ Отзыв изменён по <a href="https://playerok.com/deal/{event.deal.id}">сделке</a>', text=body),
                    kb=_log_new_review_kb(event.deal.user.username, event.deal.id),
                ),
                _get_facade_loop(),
            )

    async def _on_ledger_dispute(self, event: WireDealDispute):
        logger.debug(f'[event] LEDGER_DISPUTE  deal={event.deal.id}  user={event.deal.user.username}')
        if event.deal.user.id == self.account.id:
            return
        deal = event.deal
        try:
            deal = self.account.load_deal(event.deal.id)
        except Exception:
            logger.exception('load_deal for complaint')
        cat, det = _problem_category_and_detail(deal)
        self.log_new_problem(deal, category=cat, detail=det)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['problem']:
            _prob_chat = deal.chat.id if deal.chat else None
            body = f'<b>Покупатель:</b> {html.escape(deal.user.username)}\n<b>Предмет:</b> {html.escape(deal.item.name or "")}'
            if cat:
                body += f'\n<b>Категория:</b> {html.escape(cat)}'
            if det:
                body += f'\n<b>{"Текст жалобы" if cat else "Причина"}:</b> {html.escape(det)}'
            asyncio.run_coroutine_threadsafe(_get_facade().log_event(text=_log_text(title=f'🤬 Новая жалоба в <a href="https://playerok.com/deal/{deal.id}">сделке</a>', text=body), kb=_log_mess_kb(deal.user.username, _prob_chat)), _get_facade_loop())

    async def _on_ledger_dispute_cleared(self, event: WireDisputeResolved):
        logger.debug(f'[event] LEDGER_DISPUTE_CLEARED  deal={event.deal.id}  user={event.deal.user.username}')
        if event.deal.user.id == self.account.id:
            return
        did = event.deal.id
        now = time.time()
        with self._problem_resolved_notify_lock:
            t0 = self._problem_resolved_notify_at.get(did)
            if t0 is not None and (now - t0) < 25.0:
                logger.debug('[bot] пропуск дубля LEDGER_DISPUTE_CLEARED для сделки %s', did)
                return
            self._problem_resolved_notify_at[did] = now
            if len(self._problem_resolved_notify_at) > 3000:
                self._problem_resolved_notify_at.clear()
        self.log_problem_resolved(event.deal, event.resolver_username)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['problem']:
            _chat = event.deal.chat.id if event.deal.chat else None
            body = f'<b>Покупатель:</b> {html.escape(event.deal.user.username)}\n<b>Предмет:</b> {html.escape(event.deal.item.name or "")}'
            if event.resolver_username:
                body += f'\n<b>Сообщение от:</b> {html.escape(event.resolver_username)}'
            asyncio.run_coroutine_threadsafe(_get_facade().log_event(
                text=_log_text(title=f'✔️ Жалоба по <a href="https://playerok.com/deal/{event.deal.id}">сделке</a> снята (поддержка)', text=body),
                kb=_log_chat_only_kb(_chat),
            ), _get_facade_loop())

    async def _on_ledger_open(self, event: WireDealOpened):
        logger.debug(f'[event] LEDGER_OPEN  user={event.deal.user.username}  item={getattr(event.deal.item, "name", "?")}  deal={event.deal.id}')
        if event.deal.user.id == self.account.id:
            return
        try:
            event.deal.item = self.account.load_listing(event.deal.item.id)
        except Exception:
            pass
        self.log_new_deal(event.deal)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['deal']:
            asyncio.run_coroutine_threadsafe(_get_facade().log_event(text=_log_text(title=f'📋 Новая <a href="https://playerok.com/deal/{event.deal.id}">сделка</a>', text=f"<b>Покупатель:</b> {event.deal.user.username}\n<b>Предмет:</b> {event.deal.item.name or '-'}\n<b>Сумма:</b> {event.deal.item.price or '?'}₽"), kb=_log_deal_kb(event.deal.user.username, event.deal.id)), _get_facade_loop())
        self.send_message(event.chat.id, self.msg('new_deal', product=event.deal.item.name or '-', price=event.deal.item.price))
        is_support_chat = event.chat.id in (self.account.system_chat_id, self.account.support_chat_id)
        if event.deal.user.id not in self.initialized_users and not is_support_chat:
            self.send_message(event.chat.id, self.msg('first_message', buyer=event.deal.user.username))
            self.initialized_users.append(event.deal.user.id)
        if self.config['features']['deliveries']:
            for i, auto_delivery in enumerate(list(self.auto_deliveries)):
                for phrase in auto_delivery['keyphrases']:
                    if phrase.lower() in (event.deal.item.name or '').lower() or (event.deal.item.name or '').lower() == phrase.lower():
                        piece = auto_delivery.get('piece', True)
                        if piece:
                            goods = auto_delivery.get('goods', [])
                            try:
                                good = goods[0]
                            except Exception:
                                break
                            mess = self.send_message(event.chat.id, good)
                            if mess:
                                logger.info(f"Автовыдача → {C_BRIGHT}{event.deal.user.username or '?'}{Fore.RESET}  «{good[:40]}»  остаток: {C_BRIGHT}{len(goods) - 1}{Fore.RESET}")
                                self.auto_deliveries[i]['goods'].pop(goods.index(good))
                                cfg.set('auto_deliveries', self.auto_deliveries)
                        else:
                            msg_text = auto_delivery.get('message', '')
                            if msg_text:
                                mess = self.send_message(event.chat.id, '\n'.join(msg_text))
                                if mess:
                                    logger.info(f"Автовыдача → {C_BRIGHT}{event.deal.user.username or '?'}{Fore.RESET}  сообщение «{str(msg_text)[:40]}»")
                        break
        if self.config['auto']['confirm']['enabled']:
            if not event.deal.item.name:
                try:
                    event.deal.item = self.account.load_listing(event.deal.item.id)
                except Exception:
                    return
            included = any((any((phrase.lower() in event.deal.item.name.lower() or event.deal.item.name.lower() == phrase.lower() for phrase in included_item)) for included_item in self.auto_complete_deals['included']))
            if self.config['auto']['confirm']['all'] or (not self.config['auto']['confirm']['all'] and included):
                self.account.patch_deal(event.deal.id, DealStage.SENT)
                logger.info(f'Сделка {C_BRIGHT}{event.deal.id}{Fore.RESET} подтверждена автоматически')

    async def _on_sku_paid(self, event: WireSkuFunded):
        logger.debug(f'[event] SKU_PAID  deal={event.deal.id}  item={getattr(event.deal.item, "name", "?")}')
        if event.deal.user.id == self.account.id:
            return
        if self.config['auto']['restore']['sold']:
            item_id = getattr(event.deal.item, 'id', None)
            if not item_id:
                return
            item = None
            for attempt in range(5):
                try:
                    item = self.account.load_listing(item_id)
                    if getattr(item, 'status', None) == ListingStage.SOLD:
                        break
                    time.sleep(3)
                except Exception:
                    time.sleep(3)
            if item is None or getattr(item, 'status', None) != ListingStage.SOLD:
                logger.debug('[restore/sold] лот %s ещё не SOLD в API, пропуск (подхватит проверка завершённых по таймеру)', item_id)
                return
            self.restore_item(item)

    def _confirmed_deal_earn_rub(self, deal: ItemDeal) -> int:
        try:
            t0 = getattr(deal, 'transaction', None)
            v0 = getattr(t0, 'value', None) if t0 else None
            if not t0 or v0 is None:
                try:
                    deal = self.account.load_deal(deal.id)
                except Exception:
                    pass
            item = getattr(deal, 'item', None)
            item_price = None
            if item is not None:
                try:
                    p = getattr(item, 'price', None)
                    item_price = int(p) if p is not None else None
                except (TypeError, ValueError):
                    item_price = None
            t = getattr(deal, 'transaction', None)
            if t is not None:
                v = getattr(t, 'value', None)
                fee = getattr(t, 'fee', None) or 0
                if v is not None:
                    try:
                        vi = int(v)
                        fi = int(fee)
                        if item_price and vi > 100 * item_price:
                            vi //= 100
                            fi //= 100
                        net = vi - fi
                        if net > 0:
                            return net
                        if vi > 0:
                            return vi
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

    async def _on_ledger_stage(self, event: WireDealPhase):
        logger.debug(f'[event] LEDGER_STAGE  deal={event.deal.id}  status={getattr(event.deal.status, "name", "?")}')
        if event.deal.user.id == self.account.id:
            return
        confirmed_with_open_problem = False
        if event.deal.status is DealStage.CONFIRMED:
            try:
                confirmed_with_open_problem = bool(getattr(self.account.load_deal(event.deal.id), 'has_problem', False))
            except Exception:
                confirmed_with_open_problem = bool(getattr(event.deal, 'has_problem', False))
        status_frmtd = 'Неизвестный'
        if event.deal.status is DealStage.PAID:
            status_frmtd = 'Оплачен'
        elif event.deal.status is DealStage.PENDING:
            status_frmtd = 'В ожидании отправки'
        elif event.deal.status is DealStage.SENT:
            status_frmtd = 'Продавец подтвердил выполнение'
        elif event.deal.status is DealStage.CONFIRMED:
            if confirmed_with_open_problem:
                status_frmtd = 'Открыта жалоба (сделка подтверждена)'
            else:
                status_frmtd = 'Покупатель подтвердил сделку'
        elif event.deal.status is DealStage.ROLLED_BACK:
            status_frmtd = 'Возврат'
        if not confirmed_with_open_problem:
            self.log_deal_status_changed(event.deal, status_frmtd)
        if self.config['alerts']['enabled'] and self.config['alerts']['on']['deal_changed'] and not confirmed_with_open_problem:
            asyncio.run_coroutine_threadsafe(_get_facade().log_event(_log_text(title=f'🔄️📋 Статус <a href="https://playerok.com/deal/{event.deal.id}/">сделки</a> изменился', text=f'<b>Новый статус:</b> {html.escape(status_frmtd)}')), _get_facade_loop())
        if event.deal.status is DealStage.PENDING:
            self.send_message(event.chat.id, self.msg('deal_pending', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
        if event.deal.status is DealStage.SENT:
            self.send_message(event.chat.id, self.msg('deal_sent', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
        if event.deal.status is DealStage.CONFIRMED and not confirmed_with_open_problem:
            self.send_message(event.chat.id, self.msg('deal_confirmed', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
            self.stats.deals_completed += 1
            self.stats.earned_money += self._confirmed_deal_earn_rub(event.deal)
            _save_stats(self.stats)
        if event.deal.status is DealStage.ROLLED_BACK:
            self.send_message(event.chat.id, self.msg('deal_refunded', deal_id=event.deal.id, product=event.deal.item.name, price=event.deal.item.price))
            self.stats.deals_refunded += 1
            _save_stats(self.stats)

    async def operate(self):
        logger.debug('Движок запущен')
        from keel.kit import apply_verbose
        apply_verbose(self.config.get('debug', {}).get('verbose', False))
        nick = (self.account.username or '').strip() or '—'
        logger.info(f'  {C_SUCCESS}✓{Fore.RESET}  {C_BRIGHT}Playerok: авторизованы как «{nick}»{Fore.RESET}')
        stats = self.account.profile.stats.deals
        active_sales = stats.outgoing.total - stats.outgoing.finished
        active_buys = stats.incoming.total - stats.incoming.finished
        acc_rows: list = [('Никнейм', self.account.username), ('ID', str(self.account.id)[:36]), None]
        if self.bot_account.profile.balance:
            bal = self.account.profile.balance
            acc_rows += [('Баланс', f'{bal.value} ₽'), ('  Доступно', f'{bal.available} ₽'), ('  Ожидание', f'{bal.pending_income} ₽'), ('  Заморожено', f'{bal.frozen} ₽'), None]
        acc_rows += [('Продажи', active_sales), ('Покупки', active_buys)]
        proxy = self.config['account']['proxy']
        if proxy:
            from keel.kit import proxy_display_parts
            draw_box('АККАУНТ', acc_rows, lead='\n')
            ip, port, user, password = proxy_display_parts(proxy)
            if ip and port:
                ip_parts = ip.split('.')
                if len(ip_parts) == 4 and all(p.isdigit() for p in ip_parts):
                    ip_masked = '.'.join(('*' * len(n) if i >= 2 else n for i, n in enumerate(ip_parts)))
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
        hook_strata('STREAM_LIVE', Supervisor._on_bot_init, 0)
        hook_ingress(IngressPoint.ROOM_SYNCED, Supervisor._on_room_synced, 0)
        hook_ingress(IngressPoint.CORR_INBOUND, Supervisor._on_corr_inbound, 0)
        hook_ingress(IngressPoint.STARS_NEW, Supervisor._on_stars_new, 0)
        hook_ingress(IngressPoint.STARS_REMOVED, Supervisor._on_stars_removed, 0)
        hook_ingress(IngressPoint.STARS_AMENDED, Supervisor._on_stars_amended, 0)
        hook_ingress(IngressPoint.LEDGER_DISPUTE, Supervisor._on_ledger_dispute, 0)
        hook_ingress(IngressPoint.LEDGER_DISPUTE_CLEARED, Supervisor._on_ledger_dispute_cleared, 0)
        hook_ingress(IngressPoint.LEDGER_OPEN, Supervisor._on_ledger_open, 0)
        hook_ingress(IngressPoint.SKU_PAID, Supervisor._on_sku_paid, 0)
        hook_ingress(IngressPoint.LEDGER_STAGE, Supervisor._on_ledger_stage, 0)

        async def listener_loop():
            feed = TapStream(self.account)
            for event in feed.listen():
                await broadcast_ingress(event.type, [self, event])

        spawn_async(listener_loop)
        await broadcast('STREAM_LIVE', [self])
