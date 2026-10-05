import asyncio
import html
from logging import getLogger

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from lib.cfg import AppConf as cfg, hash_password
from lib.util import password_ok
from . import keys as calls
from . import states
from .cb import CX
from .helpers import emit_overlay

logger = getLogger('cxh.ctrl')
router = Router(name='access')


async def _admin_label(bot, user_id: int, me: int) -> str:
    name = ''
    try:
        chat = await bot.get_chat(user_id)
        name = f'@{chat.username}' if chat.username else (chat.full_name or '')
    except Exception:
        pass
    suffix = ' · это вы' if user_id == me else ''
    return f'<code>{user_id}</code> {html.escape(name)}{suffix}'.strip()


async def access_text(bot, me: int) -> str:
    admins = cfg.read('config')['bot'].get('admins') or []
    labels = await asyncio.gather(*(_admin_label(bot, uid, me) for uid in admins))
    rows = '\n'.join(f'• {label}' for label in labels) or '—'
    return (
        '🛡 <b>Доступ к панели</b>\n\n'
        f'Администраторов: <b>{len(admins)}</b>\n{rows}\n\n'
        'Любой, кто ввёл пароль, остаётся администратором навсегда. '
        'Если пароль мог попасть к посторонним — смените его: все, кроме вас, будут отключены.'
    )


def access_kb(count: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text='🔐 Сменить пароль', callback_data=CX.acc_pw)]]
    if count > 1:
        rows.append([InlineKeyboardButton(text='🚪 Отключить всех, кроме меня', callback_data=CX.acc_kick)])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _keep_only(user_id: int, password_hash: str | None = None) -> int:
    config = cfg.read('config')
    removed = len([uid for uid in config['bot'].get('admins') or [] if uid != user_id])
    config['bot']['admins'] = [user_id]
    if password_hash:
        config['bot']['password_hash'] = password_hash
    cfg.write('config', config)
    return removed


async def _show_access(callback: CallbackQuery, state: FSMContext, note: str = '') -> None:
    text = await access_text(callback.bot, callback.from_user.id)
    count = len(cfg.read('config')['bot'].get('admins') or [])
    await emit_overlay(state=state, message=callback.message, text=(note + '\n\n' if note else '') + text,
                       reply_markup=access_kb(count), callback=callback)


@router.callback_query(F.data == CX.acc_open)
async def on_access(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await _show_access(callback, state)


@router.callback_query(F.data == CX.acc_kick)
async def on_kick_ask(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='✅ Отключить', callback_data=CX.acc_kick_go),
        InlineKeyboardButton(text='✕ Отмена', callback_data=CX.acc_open),
    ]])
    await emit_overlay(state=state, message=callback.message, callback=callback, reply_markup=kb,
                       text='🚪 Отключить от панели всех администраторов, кроме вас? Им придётся снова ввести пароль.')


@router.callback_query(F.data == CX.acc_kick_go)
async def on_kick(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    removed = _keep_only(callback.from_user.id)
    logger.warning('[tg] администратор %s отключил других: %s', callback.from_user.id, removed)
    await _show_access(callback, state, f'✅ Отключено администраторов: <b>{removed}</b>')


@router.callback_query(F.data == CX.acc_pw)
async def on_password_ask(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduAccessGrp.pdu_new_password)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✕ Отмена', callback_data=CX.acc_open)]])
    await emit_overlay(state=state, message=callback.message, callback=callback, reply_markup=kb,
                       text='🔐 Отправьте новый пароль панели: 6–64 символа, буквы разного регистра и цифры. '
                            'Сообщение с паролем будет удалено, остальные администраторы — отключены.')


@router.message(states.PduAccessGrp.pdu_new_password, F.text)
async def on_password(message: types.Message, state: FSMContext):
    await state.set_state(None)
    password = message.text or ''
    try:
        await message.delete()
    except Exception:
        pass
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ К доступу', callback_data=CX.acc_open)]])
    if not password_ok(password):
        return await emit_overlay(state=state, message=message, reply_markup=kb,
                                  text='❌ Пароль слишком простой или недопустимой длины. Пароль не изменён.')
    removed = _keep_only(message.from_user.id, await asyncio.to_thread(hash_password, password))
    logger.warning('[tg] пароль панели изменён администратором %s, отключено: %s', message.from_user.id, removed)
    await emit_overlay(state=state, message=message, reply_markup=kb,
                       text=f'✅ Пароль изменён. Отключено других администраторов: <b>{removed}</b>.')
