from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message, CallbackQuery, InputMediaPhoto, FSInputFile
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from . import ui as templ


async def adm_gate(message: Message, state: FSMContext) -> Message | None:
    from . import states
    await state.set_state(states.PduGateGrp.pdu_gate_secret)
    return await emit_overlay(state=state, message=message, text=templ.fac_120(), reply_markup=templ.fac_016())


async def get_accent_message_id(state: FSMContext, message: Message, bot) -> int | None:
    data = await state.get_data()
    if message.from_user and message.from_user.id != bot.id:
        return data.get('accent_message_id')
    return message.message_id


def need_new_message(message: Message, bot, send: bool) -> bool:
    if send:
        return True
    if message.text and message.from_user.id != bot.id:
        return message.text.startswith('/')
    return False


async def msg_swap_surface(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str = 'HTML') -> Message | None:
    bot = message.bot
    chat_id = message.chat.id
    if message.photo or message.document or message.video or message.animation:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)


async def msg_force_edit(bot, chat_id: int, message_id: int, text: str, reply_markup: InlineKeyboardMarkup | None, parse_mode: str = 'HTML') -> Message | None:
    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        err = (e.message or '').lower()
        if 'message to edit not found' in err or 'message not found' in err:
            return None
        if 'message is not modified' in err:
            return None
        if 'there is no text' in err or 'no text in the message' in err:
            try:
                await bot.delete_message(chat_id, message_id)
            except TelegramBadRequest:
                pass
            return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        raise


async def try_edit_message(bot, chat_id, message_id, text, photo, reply_markup, callback):
    try:
        if photo:
            media = InputMediaPhoto(media=FSInputFile(photo), caption=text, parse_mode='HTML')
            return await bot.edit_message_media(chat_id=chat_id, message_id=message_id, media=media, reply_markup=reply_markup)
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
    except TelegramAPIError as e:
        msg = (e.message or '').lower()
        if 'message to edit not found' in msg:
            return None
        if 'message is not modified' in msg:
            if callback:
                await bot.answer_callback_query(callback.id, cache_time=0)
            return 'not_modified'
        if 'query is too old' in msg:
            return 'callback_expired'
        if not photo and ('there is no text' in msg or 'no text in the message' in msg):
            try:
                await bot.delete_message(chat_id, message_id)
            except TelegramBadRequest:
                pass
            return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        raise


async def send_new_message(bot, chat_id, text, photo, reply_markup):
    if photo:
        return await bot.send_photo(chat_id=chat_id, photo=FSInputFile(photo), caption=text, reply_markup=reply_markup, parse_mode='HTML')
    return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')


async def emit_overlay(state: FSMContext, message: Message, text: str = None, reply_markup: InlineKeyboardMarkup = None, callback: CallbackQuery = None, photo: str = None, send: bool = False) -> Message | None:
    if not text and not photo:
        return None
    from .panel import get_panel
    bot = get_panel().bot
    accent_id = await get_accent_message_id(state, message, bot)
    new_message_needed = need_new_message(message, bot, send)
    mess = None
    if accent_id and not new_message_needed:
        mess = await try_edit_message(bot=bot, chat_id=message.chat.id, message_id=accent_id, text=text, photo=photo, reply_markup=reply_markup, callback=callback)
        if message.from_user.id != bot.id:
            try:
                await bot.delete_message(message.chat.id, message.message_id)
            except TelegramBadRequest:
                pass
        if mess in ('not_modified', 'callback_expired'):
            return None
    if not mess:
        mess = await send_new_message(bot=bot, chat_id=message.chat.id, text=text, photo=photo, reply_markup=reply_markup)
    if callback:
        await bot.answer_callback_query(callback.id, cache_time=0)
    if mess and mess not in ('not_modified', 'callback_expired'):
        mid = getattr(mess, 'message_id', None)
        if mid is not None:
            await state.update_data(accent_message_id=mid)
    return mess
