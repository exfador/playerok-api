from __future__ import annotations
import asyncio
import logging
from typing import Any, Awaitable, Callable
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, MenuButtonCommands, TelegramObject, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.dispatcher.event.bases import UNHANDLED
from keel.shelf import ConfigShelf as cfg
from keel.graft import all_grafts
from keel.relay import broadcast
from colorama import Fore
from keel.tone import C_SUCCESS, C_BRIGHT
from lib.util import draw_box, proxy_url_for_aiogram
from . import router as main_router
from . import ui as templ
from .cmds import facade_command_blueprint

logger = logging.getLogger('trellis.face')

_PANEL_BOT_DESCRIPTION = (
    '🛒 CXH Playerok — панель продавца на Playerok\n\n'
    '✅ Авто-подтверждение заказов\n'
    '🔼 Авто-поднятие лотов\n'
    '♻️ Авто-восстановление товаров на витрине\n'
    '📦 Авто-выдача\n'
    '⌨️ Команды в чате\n'
    '💬 Уведомления в Telegram: ответ текстом или фото, шаблоны, закрытие сделки и возврат, '
    'профиль, статистика\n'
    '✏️ Ватермарк к сообщениям, прокси, пароль для входа\n'
    '🧩 Расширения\n\n'
    'Dev @exfador and @terop11. Official group @coxerhub_playerok.'
)


class AuthGuard(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            uid = event.from_user.id if event.from_user else None
            try:
                admins = cfg.get('config')['bot']['admins']
            except Exception:
                admins = []
            if uid not in admins:
                try:
                    await event.answer('⛔ Нет доступа. Введите /start для авторизации.', show_alert=True)
                except Exception:
                    pass
                return UNHANDLED
        return await handler(event, data)


def get_facade() -> Facade | None:
    if hasattr(Facade, 'instance'):
        return getattr(Facade, 'instance')


def get_facade_loop() -> asyncio.AbstractEventLoop | None:
    if hasattr(get_facade(), 'loop'):
        return getattr(get_facade(), 'loop')


class Facade:

    def __new__(cls, *args, **kwargs) -> Facade:
        if not hasattr(cls, 'instance'):
            cls.instance = super(Facade, cls).__new__(cls)
        return getattr(cls, 'instance')

    def __init__(self):
        logging.getLogger('aiogram').setLevel(logging.CRITICAL)
        logging.getLogger('aiogram.event').setLevel(logging.CRITICAL)
        logging.getLogger('aiogram.dispatcher').setLevel(logging.CRITICAL)
        config = cfg.get('config')
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
        self.dp.callback_query.outer_middleware(AuthGuard())
        for ext in all_grafts():
            for route in ext.tg_mounts:
                main_router.include_router(route)
        self.dp.include_router(main_router)

    async def _set_main_menu(self):
        main_menu_commands = facade_command_blueprint()
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
        short_description = (
            'CXH Playerok: автоподтверждение, поднятие, восстановление, выдача, команды, TG. '
            '@exfador, @terop11 · @coxerhub_playerok'
        )
        if len(short_description) > 120:
            short_description = short_description[:117] + '…'
        for lang in (None, 'ru'):
            try:
                kwargs = {'short_description': short_description}
                if lang:
                    kwargs['language_code'] = lang
                await self.bot.set_my_short_description(**kwargs)
            except Exception as e:
                logger.warning('set_my_short_description (%s): %s', lang or 'default', e)

    async def _set_description(self):
        desc = _PANEL_BOT_DESCRIPTION
        if len(desc) > 512:
            desc = desc[:509] + '…'
        for lang in (None, 'ru'):
            try:
                kwargs = {'description': desc}
                if lang:
                    kwargs['language_code'] = lang
                await self.bot.set_my_description(**kwargs)
            except Exception as e:
                logger.warning('set_my_description (%s): %s', lang or 'default', e)

    async def _send_startup_message(self, playerok_ok: bool = True):
        try:
            config = cfg.get('config')
            alerts = config.get('alerts', {})
            if not alerts.get('enabled', True):
                return
            if not (alerts.get('on') or {}).get('startup', True):
                return
            signed_users = config['bot']['admins']
            for user_id in signed_users:
                try:
                    await self.bot.send_message(chat_id=user_id, text=templ.startup_text(playerok_ok), reply_markup=templ.menu_kb(), parse_mode='HTML')
                except Exception:
                    pass
        except Exception:
            pass

    async def operate(self):
        self.loop = asyncio.get_running_loop()
        await self._set_main_menu()
        await self._set_short_description()
        await self._set_description()
        await broadcast('FACADE_LIVE', [self])
        me = await self.bot.get_me()
        uname = f'@{me.username}' if me.username else f'id:{me.id}'
        logger.info(f'  {C_SUCCESS}✓{Fore.RESET}  {C_BRIGHT}Telegram-бот {uname} запущен{Fore.RESET}')
        logger.debug('Telegram-бот %s', uname)
        await self._send_startup_message(playerok_ok=True)
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
        while True:
            try:
                await self.dp.start_polling(self.bot, skip_updates=True, handle_signals=False)
            except Exception:
                pass

    async def call_seller(self, calling_name: str, chat_id: int | str):
        config = cfg.get('config')
        for user_id in config['bot']['admins']:
            await self.bot.send_message(chat_id=user_id, text=templ.call_seller_text(calling_name, f'https://playerok.com/chats/{chat_id}'), reply_markup=templ.destroy_kb(), parse_mode='HTML')

    async def log_event(self, text: str, kb: InlineKeyboardMarkup | None = None, link_preview_url: str | None = None):
        config = cfg.get('config')
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
