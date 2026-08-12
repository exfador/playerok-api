from __future__ import annotations
import asyncio
import logging
import textwrap
import time
from threading import Event
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    MenuButtonCommands,
    Message,
    TelegramObject,
    Update,
)
from aiogram.client.session.aiohttp import AiohttpSession
from lib.cfg import AppConf as cfg
from lib.ext import all_extensions
from lib.bus import fire as dispatch
from colorama import Fore
from lib.consts import C_SUCCESS, C_BRIGHT
from lib.util import draw_box, get_bot_log_path, proxy_url_for_aiogram
from . import router as main_router
from .cmd import router as cmd_router
from . import ui as templ
from .cmds import panel_bot_command_list
import sys
logger = logging.getLogger('cxh.ctrl')


def _tg_echo_stderr(msg: str) -> None:
    logger.debug(msg)


class _TgRawUpdateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            panel = get_panel()
            if panel is not None:
                panel._last_update_at = time.monotonic()
                panel._updates_received += 1
            parts: list[str] = []
            if event.message:
                m = event.message
                t = (m.text or m.caption or '')[:160]
                parts.append(f'message chat={m.chat.id} user={m.from_user.id if m.from_user else None} {t!r}')
            if event.callback_query:
                q = event.callback_query
                parts.append(f'callback user={q.from_user.id if q.from_user else None} data={q.data!r}')
            if event.edited_message:
                parts.append('edited_message')
            line = ' '.join(parts) if parts else f'тип апдейта без message/callback (id={event.update_id})'
            logger.debug('[tg] RAW UPDATE update_id=%s %s', event.update_id, line)
        return await handler(event, data)


class _TelegramInboundDebugMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            uid = event.from_user.id if event.from_user else None
            txt = (event.text or event.caption or '')[:220]
            logger.debug(
                '[tg] входящее сообщение chat_id=%s user_id=%s type=%s text=%r',
                event.chat.id,
                uid,
                getattr(event, 'content_type', '?'),
                txt or f'({getattr(event, "content_type", "?")}, без текста)',
            )
        elif isinstance(event, CallbackQuery):
            uid = event.from_user.id if event.from_user else None
            logger.debug(
                '[tg] callback user_id=%s data=%r',
                uid,
                (event.data or '')[:220],
            )
            try:
                admins = cfg.read('config')['bot']['admins']
            except Exception:
                admins = []
            if uid not in admins:
                try:
                    await event.answer('⛔ Нет доступа. Введите /start для авторизации.', show_alert=True)
                except Exception:
                    pass
                return UNHANDLED
        try:
            out = await handler(event, data)
        except Exception:
            logger.exception(
                '[tg] ошибка в обработчике Telegram (см. traceback). '
                'Если это команда плагина — проверьте роутеры и FSM.'
            )
            raise
        if out is UNHANDLED:
            if isinstance(event, Message):
                logger.warning(
                    '[tg] ни один handler не обработал сообщение '
                    '(команда не сматчилась или до неё не дошла очередь). '
                    'chat_id=%s user_id=%s text=%r',
                    event.chat.id,
                    event.from_user.id if event.from_user else None,
                    (event.text or event.caption or '')[:160],
                )
            elif isinstance(event, CallbackQuery):
                logger.warning(
                    '[tg] ни один handler не обработал callback data=%r user_id=%s',
                    (event.data or '')[:160],
                    event.from_user.id if event.from_user else None,
                )
        return out


_panel: 'Panel | None' = None


def get_panel() -> 'Panel | None':
    return _panel


def get_panel_loop() -> asyncio.AbstractEventLoop | None:
    p = _panel
    return getattr(p, 'loop', None) if p else None


class Panel:

    def __new__(cls):
        if _panel is not None:
            return _panel
        return super().__new__(cls)

    def __init__(self):
        global _panel
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        logging.getLogger('aiogram').setLevel(logging.CRITICAL)
        logging.getLogger('aiogram.event').setLevel(logging.CRITICAL)
        logging.getLogger('aiogram.dispatcher').setLevel(logging.CRITICAL)
        config = cfg.read('config')
        self.token = config['bot']['token']
        self.proxy = config['bot']['proxy']
        if self.proxy:
            purl = proxy_url_for_aiogram(self.proxy)
            session = AiohttpSession(proxy=purl) if purl else None
            if self.proxy and not purl:
                logger.warning('Некорректный bot.proxy в config — Telegram без прокси-сессии')
        else:
            session = None
        self.bot = Bot(token=self.token, session=session)
        self.dp = Dispatcher()
        self.dp.update.outer_middleware(_TgRawUpdateMiddleware())
        mw = _TelegramInboundDebugMiddleware()
        self.dp.message.outer_middleware(mw)
        self.dp.callback_query.outer_middleware(mw)
        if cmd_router.parent_router is None:
            for ext in all_extensions():
                for route in ext.bot_paths:
                    self.dp.include_router(route)
            main_router.include_router(cmd_router)
        self.dp.include_router(main_router)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = Event()
        self._polling_active = False
        self._started_at: float | None = None
        self._last_api_success_at: float | None = None
        self._last_update_at: float | None = None
        self._last_error: str | None = None
        self._poll_failures = 0
        self._updates_received = 0
        self._session_closed = False
        try:
            chain = ' → '.join(repr(r.name) for r in self.dp.sub_routers)
            logger.debug('Telegram: порядок обработки dp.sub_routers = %s', chain)
        except Exception:
            pass
        _panel = self
        _tg_echo_stderr(f'Панель собрана; лог файл: {get_bot_log_path()}')

    def health(self) -> dict:
        return {
            'polling_active': self._polling_active,
            'started_at': self._started_at,
            'last_api_success_at': self._last_api_success_at,
            'last_update_at': self._last_update_at,
            'last_error': self._last_error,
            'poll_failures': self._poll_failures,
            'updates_received': self._updates_received,
            'stopping': self._stop_event.is_set(),
        }

    async def stop(self) -> None:
        global _panel
        self._stop_event.set()
        try:
            await self.dp.stop_polling()
        except (RuntimeError, AttributeError):
            pass
        if not self._session_closed:
            self._session_closed = True
            await self.bot.session.close()
        if _panel is self:
            _panel = None

    async def _set_main_menu(self):
        main_menu_commands = panel_bot_command_list()
        try:
            await self.bot.set_my_commands(main_menu_commands)
        except Exception as e:
            logger.warning('Не удалось зарегистрировать команды (основной список): %s', e)
        try:
            await self.bot.set_my_commands(main_menu_commands, language_code='ru')
        except Exception as e:
            logger.warning('Не удалось зарегистрировать команды (ru): %s', e)
        try:
            await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception as e:
            logger.warning('Не удалось выставить кнопку «команды» в меню: %s', e)

    async def _set_short_description(self):
        try:
            short_description = 'CXH Playerok — панель магазина на playerok.com'
            await self.bot.set_my_short_description(short_description=short_description)
        except Exception:
            pass

    async def _set_description(self):
        try:
            description = textwrap.dedent('\n                🏪 Онлайн-витрина и сделки\n                ♻️ Возврат лотов на полку\n                🔝 Обновление позиций в поиске\n                💸 Автовыплаты на реквизиты\n                🚀 Выдача товара по фразе в названии\n                ⌨️ Свои команды в чате (!команды)\n                ✉️ Шаблоны ответов покупателю\n                📊 Сводка по сессии\n                📢 Сигналы о событиях сюда в Telegram\n                🧩 Подключаемые расширения\n            ')
            await self.bot.set_my_description(description=description)
        except Exception:
            pass

    async def _send_startup_message(self, playerok_ok: bool = True):
        try:
            config = cfg.read('config')
            alerts = config.get('alerts', {})
            if not alerts.get('enabled', True):
                return
            if not (alerts.get('on') or {}).get('startup', True):
                return
            signed_users = config['bot']['admins']
            for user_id in signed_users:
                try:
                    await self.bot.send_message(chat_id=user_id, text=templ.fac_040(), reply_markup=templ.fac_039(), parse_mode='HTML', link_preview_options=LinkPreviewOptions(is_disabled=True))
                except Exception:
                    pass
        except Exception:
            pass

    async def _health_probe(self) -> None:
        while not self._stop_event.is_set():
            try:
                stopped = await asyncio.wait_for(
                    asyncio.to_thread(self._stop_event.wait), timeout=60,
                )
                if stopped:
                    return
            except asyncio.TimeoutError:
                pass
            try:
                await self.bot.get_me()
                self._last_api_success_at = time.monotonic()
                if self._polling_active:
                    self._last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = f'health probe: {type(exc).__name__}: {exc}'

    async def run_bot(self):
        self.loop = asyncio.get_running_loop()
        self._started_at = time.monotonic()
        _tg_echo_stderr(f'run_bot старт, loop={id(self.loop)}, log={get_bot_log_path()}')
        await self._set_main_menu()
        await self._set_short_description()
        await self._set_description()
        await dispatch('PANEL_UP', [self])
        startup_notified = False
        health_task = asyncio.create_task(self._health_probe(), name='telegram-health-probe')
        if self.proxy:
            from lib.util import proxy_display_parts
            ip, port, user, password = proxy_display_parts(self.proxy)
            if ip and port:
                ip_parts = ip.split('.')
                if len(ip_parts) == 4 and all(p.isdigit() for p in ip_parts):
                    ip_masked = '.'.join(('*' * len(n) if i >= 2 else n for i, n in enumerate(ip_parts)))
                else:
                    ip_masked = ip[:4] + '***' if len(ip) > 4 else '***'
                port_masked = f'{port[:2]}***' if len(port) >= 2 else '***'
                user_masked = f'{user[:3]}***' if user else '—'
                pass_masked = '●●●●●●' if password else '—'
                draw_box('ПРОКСИ TELEGRAM', [('Адрес', f'{ip_masked}:{port_masked}'), ('Логин', user_masked), ('Пароль', pass_masked)])
            else:
                draw_box('ПРОКСИ TELEGRAM', [('Прокси', 'задан (формат см. conf/config.json)')])
        try:
            while not self._stop_event.is_set():
                attempt_started = time.monotonic()
                try:
                    me = await self.bot.get_me()
                    self._last_api_success_at = time.monotonic()
                    self._last_error = None
                    uname = f'@{me.username}' if me.username else f'id:{me.id}'
                    logger.info(f'  {C_SUCCESS}✓{Fore.RESET}  {C_BRIGHT}Telegram-бот {uname} запущен{Fore.RESET}')
                    logger.debug('Telegram-бот %s', uname)
                    if not startup_notified:
                        await self._send_startup_message(playerok_ok=True)
                        startup_notified = True
                    self._polling_active = True
                    await self.dp.start_polling(self.bot, skip_updates=True, handle_signals=False)
                    if not self._stop_event.is_set():
                        raise RuntimeError('Telegram polling завершился без команды остановки')
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if time.monotonic() - attempt_started >= 60:
                        self._poll_failures = 0
                    self._poll_failures += 1
                    self._last_error = f'{type(exc).__name__}: {exc}'
                    delay = min(60, 2 ** min(self._poll_failures, 6))
                    logger.exception('[tg] polling завершился с ошибкой — повтор через %s с', delay)
                    if self._stop_event.is_set():
                        return
                    await asyncio.sleep(delay)
                finally:
                    self._polling_active = False
        finally:
            health_task.cancel()
            await asyncio.gather(health_task, return_exceptions=True)

    async def call_seller(self, calling_name: str, chat_id: int | str):
        config = cfg.read('config')
        for user_id in config['bot']['admins']:
            await self.bot.send_message(chat_id=user_id, text=templ.fac_014(calling_name, f'https://playerok.com/chats/{chat_id}'), reply_markup=templ.fac_016(), parse_mode='HTML')

    async def notify_update(self, tag: str, html_url: str, download_url: str, body: str = '', current_version: str = '') -> None:
        import html as _html
        from .cb import CX
        title = _html.escape(tag or 'обновление')
        cur = _html.escape(current_version or '')
        notes = (body or '').strip()
        if len(notes) > 600:
            notes = notes[:600].rstrip() + '…'
        notes_html = _html.escape(notes)
        text = (
            f'🆕 <b>Вышло обновление CXH Playerok</b> — <code>{title}</code>\n'
            f'Текущая версия: <code>{cur or "—"}</code>\n\n'
            f'{notes_html if notes_html else "<i>Описание в релизе — см. ссылку ниже.</i>"}'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📥 Загрузить и применить', callback_data=CX.sys_dl_do)],
            [InlineKeyboardButton(text='📝 Что нового', url=html_url)],
        ])
        config = cfg.read('config')
        for user_id in config.get('bot', {}).get('admins') or []:
            try:
                await self.bot.send_message(
                    chat_id=user_id, text=text, reply_markup=kb, parse_mode='HTML',
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except Exception:
                logger.debug('notify_update: не удалось отправить user=%s', user_id)

    async def notify_broadcast(self, title: str, text: str, buttons: list | None = None, pinned: bool = False, html: bool = False) -> bool:
        import html as _html
        head = (title or '').strip()
        body = (text or '').strip()
        if not head and not body:
            return False
        rows = []
        for entry in buttons or []:
            try:
                label, link = str(entry[0]).strip(), str(entry[1]).strip()
            except Exception:
                continue
            if label and (link.startswith('http://') or link.startswith('https://') or link.startswith('tg://')):
                rows.append([InlineKeyboardButton(text=label, url=link)])
        kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

        def _compose(as_html: bool) -> str:
            safe_body = body if as_html else _html.escape(body)
            if head:
                parts = [f'📣 <b>{_html.escape(head)}</b>']
                if body:
                    parts.append(safe_body)
                return '\n\n'.join(parts)
            return f'📣 {safe_body}' if body else ''

        config = cfg.read('config')
        delivered = False
        for user_id in config.get('bot', {}).get('admins') or []:
            sent_msg = None
            for as_html in ((True, False) if html else (False,)):
                try:
                    sent_msg = await self.bot.send_message(
                        chat_id=user_id, text=_compose(as_html), reply_markup=kb,
                        parse_mode='HTML',
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
                    break
                except Exception:
                    sent_msg = None
            if sent_msg is None:
                logger.debug('notify_broadcast: не удалось отправить user=%s', user_id)
                continue
            delivered = True
            if pinned:
                try:
                    await self.bot.pin_chat_message(
                        chat_id=user_id, message_id=sent_msg.message_id, disable_notification=True,
                    )
                except Exception:
                    pass
        return delivered

    async def log_event(self, text: str, kb: InlineKeyboardMarkup | None = None, link_preview_url: str | None = None):
        config = cfg.read('config')
        lp = LinkPreviewOptions(
            is_disabled=False,
            url=link_preview_url,
            prefer_large_media=True,
            show_above_text=True,
        ) if link_preview_url else None
        for user_id in config['bot']['admins']:
            try:
                await self.bot.send_message(
                    chat_id=user_id, text=text, reply_markup=kb, parse_mode='HTML',
                    link_preview_options=lp,
                )
            except Exception:
                pass
