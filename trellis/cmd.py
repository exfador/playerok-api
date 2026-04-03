from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from logging import getLogger
from tempfile import NamedTemporaryFile
import math
import os
import asyncio
import re
import html
import secrets

from keel.shelf import ConfigShelf as cfg, verify_password
from keel.aliases import cc_get_items, cc_wrap_items, cc_new_item, cc_trigger_taken, cc_find_by_id
from keel.graft import all_grafts
from keel.kit import token_ok, ua_ok, proxy_ok, proxy_reachable, proxy_probe_html_suffix
from . import ui as templ
from . import states
from . import keys as calls
from .helpers import throw_float_message, do_auth, edit_message_text_or_fallback

logger = getLogger('trellis.face')
router = Router()

@router.message(Command('start'))
async def handler_start(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    if message.from_user.id not in config['bot']['admins']:
        return await do_auth(message, state)
    await throw_float_message(state=state, message=message, text=templ.menu_text(), reply_markup=templ.menu_kb())

@router.message(Command('stats'))
async def handler_stats(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    if message.from_user.id not in config['bot']['admins']:
        return await do_auth(message, state)
    await throw_float_message(state=state, message=message, text=templ.stats_text(), reply_markup=templ.stats_kb())

@router.message(Command('logs'))
async def handler_logs(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    if message.from_user.id not in config['bot']['admins']:
        return await do_auth(message, state)
    await throw_float_message(state=state, message=message, text=templ.logs_text(), reply_markup=templ.logs_kb())

@router.message(states.SystemStates.waiting_for_password, F.text)
async def handler_waiting_for_password(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        config = cfg.get('config')
        if not verify_password(message.text.strip(), config['bot']['password_hash']):
            raise Exception('❌ Неверный пароль.')
        config['bot']['admins'].append(message.from_user.id)
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.menu_text(), reply_markup=templ.menu_kb())
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.sign_text(e), reply_markup=templ.destroy_kb())

@router.message(states.ActionsStates.waiting_for_message_content, F.text | F.photo)
async def handler_waiting_for_message_content(message: types.Message, state: FSMContext):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await state.set_state(None)
    data = await state.get_data()
    username = data.get('username')
    accent_id = data.get('accent_message_id')
    sent_msg = ''
    last_sent = None
    photo_fid = message.photo[-1].file_id if message.photo else None
    caption_raw = (message.caption or '').strip() if message.photo else ''
    try:
        from chamber.supervisor import active_supervisor as get_runtime
        eng = get_runtime()
        chat = eng.find_chat_by_name(username)
        if message.text:
            if not message.text.strip():
                raise Exception('Пустое сообщение')
            last_sent = eng.send_message(chat.id, text=message.text.strip())
            sent_msg = message.text
        elif message.photo:
            photo = message.photo[-1]
            with NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                await message.bot.download(photo, destination=tmp.name)
                tmp_path = tmp.name
            if caption_raw:
                eng.send_message(chat.id, text=caption_raw)
                sent_msg += caption_raw + ' '
                await asyncio.sleep(1)
            last_sent = eng.send_message(chat.id, photo_file_path=tmp_path)
            os.remove(tmp_path)
            sent_msg += '[фото]'
        preview = sent_msg[:60].replace('\n', ' ')
        po_url = last_sent.file.url if last_sent and last_sent.file else None
        if po_url:
            logger.info(f'[tg] сообщение отправлено  →  {username}  «{preview}»  {po_url}')
        else:
            logger.info(f'[tg] сообщение отправлено  →  {username}  «{preview}»')
        try:
            await message.delete()
        except Exception:
            pass
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')],
            [InlineKeyboardButton(text='Закрыть', callback_data='destroy')],
        ])
        if photo_fid:
            cap_lines = [f'✅ Отправлено <b>{html.escape(username)}</b>']
            if caption_raw:
                cap_lines.append(html.escape(caption_raw))
            if po_url:
                cap_lines.append(f'<a href="{html.escape(po_url)}">Просмотр на Playerok</a>')
            caption = '\n'.join(cap_lines)
            if len(caption) > 1024:
                caption = caption[:1021] + '…'
            if accent_id:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=accent_id)
                except Exception:
                    pass
            await message.answer_photo(photo=photo_fid, caption=caption, parse_mode='HTML', reply_markup=kb)
        else:
            result_text = f'✅ Отправлено <b>{html.escape(username)}</b>:\n<blockquote>{html.escape(sent_msg[:300])}</blockquote>'
            if accent_id:
                m = await edit_message_text_or_fallback(
                    message.bot, message.chat.id, accent_id, result_text, kb,
                )
                if m is not None:
                    await state.update_data(accent_message_id=m.message_id)
                    return
            await message.answer(result_text, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')],
        ])
        try:
            await message.delete()
        except Exception:
            pass
        if accent_id:
            err_text = f'❌ Ошибка отправки: {e}'
            m = await edit_message_text_or_fallback(
                message.bot, message.chat.id, accent_id, err_text, kb,
            )
            if m is not None:
                await state.update_data(accent_message_id=m.message_id)
                return
        await message.answer(f'❌ Ошибка: {e}', reply_markup=kb, parse_mode='HTML')

@router.message(states.SettingsStates.waiting_for_token, F.text)
async def handler_waiting_for_token(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        token = message.text
        if not token_ok(token):
            raise Exception('❌ Неверный формат токена. Пример: eyJhbGciOiJIUzI1NiIsInR5cCI1IkpXVCJ9')
        config = cfg.get('config')
        config['account']['token'] = token
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(f'✅ <b>Токен</b> был успешно изменён на <b>{token}</b>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.message(states.SettingsStates.waiting_for_user_agent, F.text)
async def handler_waiting_for_user_agent(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        user_agent = message.text
        if not ua_ok(user_agent):
            raise Exception('❌ Неверный формат User Agent. Пример: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36')
        config = cfg.get('config')
        config['account']['user_agent'] = user_agent
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(f'✅ <b>User Agent</b> был успешно изменён на <b>{user_agent}</b>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.message(states.SettingsStates.waiting_for_pl_proxy, F.text)
async def handler_waiting_for_pl_proxy(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        proxy = message.text
        if len(proxy) <= 3:
            raise Exception('❌ Слишком короткое значение')
        if not proxy_ok(proxy):
            raise Exception('❌ Неверный формат. Нужен <b>HTTP</b>-прокси: <code>ip:port</code> или <code>user:pass@ip:port</code>')
        if not proxy_reachable(proxy):
            raise Exception('❌ Указанный вами прокси не работает. Нет подключения к playerok.com')
        config = cfg.get('config')
        config['account']['proxy'] = proxy
        cfg.set('config', config)
        probe = await asyncio.to_thread(proxy_probe_html_suffix, proxy)
        await throw_float_message(state=state, message=message, text=templ.settings_conn_float_text(f'✅ <b>Прокси для Playerok</b> (HTTP) сохранён: <b>{html.escape(proxy)}</b>{probe}'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='proxy').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_conn_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='proxy').pack()))

@router.message(states.SettingsStates.waiting_for_tg_proxy, F.text)
async def handler_waiting_for_tg_proxy(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        proxy = message.text
        if len(proxy) <= 3:
            raise Exception('❌ Слишком короткое значение')
        if not proxy_ok(proxy):
            raise Exception('❌ Неверный формат. Нужен <b>HTTP</b>-прокси: <code>ip:port</code> или <code>user:pass@ip:port</code>')
        if not proxy_reachable(proxy, 'https://api.telegram.org/'):
            raise Exception('❌ Указанный вами прокси не работает. Нет подключения к api.telegram.org')
        config = cfg.get('config')
        config['bot']['proxy'] = proxy
        cfg.set('config', config)
        probe = await asyncio.to_thread(proxy_probe_html_suffix, proxy)
        await throw_float_message(state=state, message=message, text=templ.settings_conn_float_text(f'✅ <b>Прокси для Telegram</b> (HTTP) сохранён: <b>{html.escape(proxy)}</b>{probe}'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='proxy').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_conn_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='proxy').pack()))

@router.message(states.SettingsStates.waiting_for_requests_timeout, F.text)
async def handler_waiting_for_requests_timeout(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        timeout = message.text
        if not timeout.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(timeout) < 0:
            raise Exception('❌ Слишком низкое значение')
        config = cfg.get('config')
        config['account']['timeout'] = int(timeout)
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(f'Таймаут запросов изменён на <b>{timeout} с</b>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(str(e)), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.message(states.SettingsStates.waiting_for_listener_requests_delay, F.text)
async def handler_waiting_for_listener_requests_delay(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        delay = message.text
        if not delay.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(delay) < 0:
            raise Exception('❌ Слишком низкое значение')
        config = cfg.get('config')
        config['account']['listener_delay'] = int(delay)
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(f'✅ <b>Периодичность запросов</b> была успешна изменена на <b>{delay}</b>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_auth_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.message(states.SettingsStates.waiting_for_watermark_value, F.text)
async def handler_waiting_for_watermark_value(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        watermark = message.text
        if len(watermark) <= 0 or len(watermark) >= 150:
            raise Exception('❌ Слишком короткое или длинное значение')
        config = cfg.get('config')
        config['features']['watermark']['text'] = watermark
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_watermark_text(), reply_markup=templ.settings_watermark_kb())
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_watermark_float_text(str(e)), reply_markup=templ.back_kb(calls.SettingsNavigation(to='watermark').pack()))

@router.message(states.SettingsStates.waiting_for_logs_max_file_size, F.text)
async def handler_waiting_for_logs_max_file_size(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        max_size = message.text
        if not max_size.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(max_size) <= 0:
            raise Exception('❌ Слишком низкое значение')
        max_size_int = int(max_size)
        config = cfg.get('config')
        config['logs']['max_mb'] = max_size_int
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.logs_float_text(f'✅ <b>Максимальный размер файла логов</b> был успешно изменён на <b>{max_size_int} MB</b>'), reply_markup=templ.back_kb(calls.MenuNavigation(to='logs').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.logs_float_text(e), reply_markup=templ.back_kb(calls.MenuNavigation(to='logs').pack()))

@router.message(states.MessagesStates.waiting_for_page, F.text)
async def handler_waiting_for_messages_page(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        page = int(message.text) - 1
        await state.update_data(last_page=page)
        await throw_float_message(state=state, message=message, text=templ.settings_mess_text(), reply_markup=templ.settings_mess_kb(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_mess_float_text(e), reply_markup=templ.back_kb(calls.MessagesPagination(page=last_page).pack()))

@router.message(states.ExtStates.waiting_for_page, F.text)
async def handler_waiting_for_plugins_page(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        page = int(message.text) - 1
        per_page = 7
        total_pages = max(1, math.ceil(len(all_grafts()) / per_page))
        if page < 0 or page >= total_pages:
            raise Exception(f'❌ Допустимый номер страницы: от 1 до {total_pages}')
        await state.update_data(last_page=page)
        await throw_float_message(state=state, message=message, text=templ.plugins_text(), reply_markup=templ.plugins_kb(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.plugin_page_float_text(e), reply_markup=templ.back_kb(calls.PluginsPagination(page=last_page).pack()))

@router.message(states.MessagesStates.waiting_for_message_text, F.text)
async def handler_waiting_for_message_text(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        message_id = data.get('message_id')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткий текст')
        messages = cfg.get('messages')
        message_split_lines = message.text.split('\n')
        messages[message_id]['text'] = message_split_lines
        cfg.set('messages', messages)
        await throw_float_message(state=state, message=message, text=templ.settings_mess_page_float_text(f'✅ <b>Текст шаблона</b> <code>{message_id}</code> изменён на <blockquote>{message.text}</blockquote>'), reply_markup=templ.back_kb(calls.MessagePage(message_id=message_id).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_mess_page_float_text(e), reply_markup=templ.back_kb(calls.MessagePage(message_id=message_id).pack()))

@router.message(states.MessagesStates.waiting_for_new_template_name, F.text)
async def handler_waiting_for_new_template_name(message: types.Message, state: FSMContext):
    try:
        title = (message.text or '').strip()
        if not title:
            raise Exception('Введите название шаблона')
        if len(title) > 120:
            raise Exception('Название слишком длинное (не более 120 символов)')
        await state.update_data(new_template_title=title)
        await state.set_state(states.MessagesStates.waiting_for_new_template_text)
        await throw_float_message(
            state=state, message=message,
            text=templ.settings_mess_float_text(
                f'Название: <b>{html.escape(title)}</b>\n\n'
                'Теперь отправьте <b>текст шаблона</b> (одним сообщением, можно с переносами строк).\n\n'
                f'<b>Все переменные:</b>\n{templ.msg_vars_full_text()}'
            ),
            reply_markup=templ.back_kb(calls.MessagesPagination(page=0).pack()),
        )
    except Exception as e:
        await throw_float_message(
            state=state, message=message,
            text=templ.settings_mess_float_text(str(e)),
            reply_markup=templ.back_kb(calls.MessagesPagination(page=0).pack()),
        )


@router.message(states.MessagesStates.waiting_for_new_template_text, F.text)
async def handler_waiting_for_new_template_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get('new_template_title')
    try:
        if not title:
            await state.set_state(None)
            raise Exception('Сессия сброшена. Откройте «Добавить шаблон» снова.')
        lines = message.text.split('\n') if message.text else []
        if not any((ln.strip() for ln in lines)):
            raise Exception('Текст не может быть пустым')
        messages = cfg.get('messages')
        key = 't_' + secrets.token_hex(8)
        while key in messages:
            key = 't_' + secrets.token_hex(8)
        messages[key] = {'enabled': True, 'text': lines, 'title': title}
        cfg.set('messages', messages)
        await state.set_state(None)
        await state.update_data(message_id=key, new_template_title=None)
        await throw_float_message(
            state=state, message=message,
            text=templ.settings_mess_page_float_text(
                f'Шаблон <b>{html.escape(title)}</b> сохранён.'
            ),
            reply_markup=templ.back_kb(calls.MessagePage(message_id=key).pack()),
        )
    except Exception as e:
        await throw_float_message(
            state=state, message=message,
            text=templ.settings_mess_float_text(str(e)),
            reply_markup=templ.back_kb(calls.MessagesPagination(page=0).pack()),
        )


@router.message(states.RestoreItemsStates.waiting_for_restore_poll_interval, F.text)
async def handler_waiting_for_restore_poll_interval(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        interval = int(message.text)
        if interval < 30:
            raise Exception('❌ Не меньше 30 секунд')
        config = cfg.get('config')
        if 'poll' not in config['auto']['restore'] or not isinstance(config['auto']['restore'].get('poll'), dict):
            config['auto']['restore']['poll'] = {'enabled': False, 'interval': 300}
        config['auto']['restore']['poll']['interval'] = interval
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_restore_float_text(f'✅ Проверка завершённых раз в <b>{interval}</b> с'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='restore').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_restore_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='restore').pack()))


@router.message(states.BumpItemsStates.waiting_for_bump_items_interval, F.text)
async def handler_waiting_for_bump_items_interval(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(message.text) <= 0:
            raise Exception('❌ Слишком низкое значение')
        interval = int(message.text)
        config = cfg.get('config')
        config['auto']['bump']['interval'] = interval
        cfg.set('config', config)
        await throw_float_message(state=state, message=message, text=templ.settings_bump_float_text(f'✅ <b>Интервал автоподнятия предметов</b> был успешно изменён на <b>{interval}</b>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='bump').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_bump_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='bump').pack()))

@router.message(states.BumpItemsStates.waiting_for_new_included_bump_item_keyphrases, F.text)
async def handler_waiting_for_new_included_bump_item_keyphrases(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_bump_items = cfg.get('auto_bump_items')
        auto_bump_items['included'].append(keyphrases)
        cfg.set('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_new_bump_included_float_text(f"✅ Предмет с ключевыми фразами <code>{'</code>, <code>'.join(keyphrases)}</code> успешно включён в автоподнятие"), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_new_bump_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))

@router.message(states.BumpItemsStates.waiting_for_new_included_bump_items_keyphrases_file, F.document.file_name.lower().endswith('.txt'))
async def handler_waiting_for_new_included_bump_items_keyphrases_file(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        file = await message.bot.get_file(message.document.file_id)
        downloaded_file = await message.bot.download_file(file.file_path)
        file_content = downloaded_file.read().decode('utf-8')
        keyphrases_list = []
        for line in file_content.splitlines():
            line = line.strip()
            if len(line) > 0:
                keyphrases = [phrase.strip() for phrase in line.split(',') if phrase.strip()]
                if len(keyphrases) > 0:
                    keyphrases_list.append(keyphrases)
        if len(keyphrases_list) <= 0:
            raise Exception('❌ Файл не содержит валидных ключевых фраз')
        auto_bump_items = cfg.get('auto_bump_items')
        auto_bump_items['included'].extend(keyphrases_list)
        cfg.set('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_new_bump_included_float_text(f'✅ Успешно включено <b>{len(keyphrases_list)}</b> предметов из файла в автоподнятие'), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_new_bump_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))

@router.message(states.BumpItemsStates.waiting_for_new_excluded_bump_item_keyphrases, F.text)
async def handler_waiting_for_new_excluded_bump_item_keyphrases(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_bump_items = cfg.get('auto_bump_items')
        if 'excluded' not in auto_bump_items:
            auto_bump_items['excluded'] = []
        auto_bump_items['excluded'].append(keyphrases)
        cfg.set('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(
            state=state, message=message,
            text=templ.settings_new_bump_excluded_float_text(
                f"✅ В исключения добавлено: <code>{'</code>, <code>'.join(keyphrases)}</code>",
            ),
            reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_new_bump_excluded_float_text(e), reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()))

@router.message(states.BumpItemsStates.waiting_for_new_excluded_bump_items_keyphrases_file, F.document.file_name.lower().endswith('.txt'))
async def handler_waiting_for_new_excluded_bump_items_keyphrases_file(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        file = await message.bot.get_file(message.document.file_id)
        downloaded_file = await message.bot.download_file(file.file_path)
        file_content = downloaded_file.read().decode('utf-8')
        keyphrases_list = []
        for line in file_content.splitlines():
            line = line.strip()
            if len(line) > 0:
                keyphrases = [phrase.strip() for phrase in line.split(',') if phrase.strip()]
                if len(keyphrases) > 0:
                    keyphrases_list.append(keyphrases)
        if len(keyphrases_list) <= 0:
            raise Exception('❌ Файл не содержит валидных ключевых фраз')
        auto_bump_items = cfg.get('auto_bump_items')
        if 'excluded' not in auto_bump_items:
            auto_bump_items['excluded'] = []
        auto_bump_items['excluded'].extend(keyphrases_list)
        cfg.set('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(
            state=state, message=message,
            text=templ.settings_new_bump_excluded_float_text(f'✅ В исключения добавлено строк из файла: <b>{len(keyphrases_list)}</b>'),
            reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_new_bump_excluded_float_text(e), reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()))

@router.message(states.CustomCommandsStates.waiting_for_page, F.text)
async def handler_waiting_for_custom_commands_page(message: types.Message, state: FSMContext):
    try:
        if not message.text.strip().isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        await state.update_data(last_page=int(message.text.strip()) - 1)
        await state.set_state(None)
        await throw_float_message(state=state, message=message, text=templ.settings_comms_text(), reply_markup=templ.settings_comms_kb(page=int(message.text) - 1))
    except Exception as e:
        data = await state.get_data()
        await throw_float_message(state=state, message=message, text=templ.settings_comms_float_text(e), reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=data.get('last_page', 0)).pack()))

@router.message(states.CustomCommandsStates.waiting_for_new_custom_command, F.text)
async def handler_waiting_for_new_custom_command(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    try:
        raw = message.text.strip()
        if len(raw) < 2 or len(raw) > 64:
            raise Exception('❌ Длина команды: от 2 до 64 символов')
        if not raw.startswith('!'):
            raise Exception('❌ Команда должна начинаться с <code>!</code>')
        items = cc_get_items(cfg.get('custom_commands'))
        if cc_trigger_taken(items, raw):
            raise Exception('❌ Такая команда уже есть')
        new_item = cc_new_item(raw)
        items.append(new_item)
        cfg.set('custom_commands', cc_wrap_items(items))
        await state.update_data(custom_cmd_id=new_item['id'])
        await state.set_state(None)
        await throw_float_message(
            state=state,
            message=message,
            text=templ.settings_comm_page_text(new_item['id']),
            reply_markup=templ.settings_comm_page_kb(new_item['id'], last_page),
        )
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_comm_float_text(e), reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=last_page).pack()))

@router.message(states.CustomCommandsStates.waiting_for_custom_command_answer, F.text)
async def handler_waiting_for_custom_command_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    cmd_id = data.get('custom_cmd_id')
    try:
        if not cmd_id:
            raise Exception('❌ Сессия сброшена')
        items = cc_get_items(cfg.get('custom_commands'))
        item = cc_find_by_id(items, cmd_id)
        if not item:
            raise Exception('❌ Команда не найдена')
        raw = message.text or ''
        item['reply_lines'] = [ln.rstrip() for ln in raw.split('\n') if ln.strip()]
        cfg.set('custom_commands', cc_wrap_items(items))
        await state.set_state(None)
        await throw_float_message(
            state=state,
            message=message,
            text=templ.settings_comm_page_float_text(f"✅ Текст ответа для <code>{item['trigger']}</code> обновлён"),
            reply_markup=templ.back_kb(calls.CustomCommandPage(cmd_id=cmd_id).pack()),
        )
    except Exception as e:
        err = str(e)
        if not cmd_id or 'Сессия сброшена' in err or 'не найдена' in err:
            await state.set_state(None)
        await throw_float_message(
            state=state,
            message=message,
            text=templ.settings_comm_page_float_text(e),
            reply_markup=templ.back_kb(calls.CustomCommandPage(cmd_id=cmd_id).pack()) if cmd_id else templ.back_kb(calls.CustomCommandsPagination(page=last_page).pack()),
        )

@router.message(states.CompleteDealsStates.waiting_for_new_included_complete_deal_keyphrases, F.text)
async def handler_waiting_for_new_included_complete_deal_keyphrases(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_complete_deals = cfg.get('auto_complete_deals')
        auto_complete_deals['included'].append(keyphrases)
        cfg.set('auto_complete_deals', auto_complete_deals)
        await throw_float_message(state=state, message=message, text=templ.settings_new_complete_included_float_text('✅ Предмет успешно включён в автоподтверждение'), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_complete_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))

@router.message(states.CompleteDealsStates.waiting_for_new_included_complete_deals_keyphrases_file, F.document.file_name.lower().endswith('.txt'))
async def handler_waiting_for_new_included_complete_deals_keyphrases_file(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        file = await message.bot.get_file(message.document.file_id)
        downloaded_file = await message.bot.download_file(file.file_path)
        file_content = downloaded_file.read().decode('utf-8')
        keyphrases_list = []
        for line in file_content.splitlines():
            line = line.strip()
            if len(line) > 0:
                keyphrases = [phrase.strip() for phrase in line.split(',') if phrase.strip()]
                if len(keyphrases) > 0:
                    keyphrases_list.append(keyphrases)
        if len(keyphrases_list) <= 0:
            raise Exception('❌ Файл не содержит валидных ключевых фраз')
        auto_complete_deals = cfg.get('auto_complete_deals')
        auto_complete_deals['included'].extend(keyphrases_list)
        cfg.set('auto_complete_deals', auto_complete_deals)
        await throw_float_message(state=state, message=message, text=templ.settings_new_complete_included_float_text(f'✅ Успешно включено <b>{len(keyphrases_list)} предметов</b> из файла в автоподтверждение'), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_complete_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))

@router.message(states.RestoreItemsStates.waiting_for_new_included_restore_item_keyphrases, F.text)
async def handler_waiting_for_new_included_restore_item_keyphrases(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_restore_items = cfg.get('auto_restore_items')
        auto_restore_items['included'].append(keyphrases)
        cfg.set('auto_restore_items', auto_restore_items)
        await throw_float_message(state=state, message=message, text=templ.settings_new_restore_included_float_text(f"✅ Предмет с ключевыми фразами <code>{'</code>, <code>'.join(keyphrases)}</code> успешно включён в автовосстановление"), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_restore_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))

@router.message(states.RestoreItemsStates.waiting_for_new_included_restore_items_keyphrases_file, F.document.file_name.lower().endswith('.txt'))
async def handler_waiting_for_new_included_restore_items_keyphrases_file(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        file = await message.bot.get_file(message.document.file_id)
        downloaded_file = await message.bot.download_file(file.file_path)
        file_content = downloaded_file.read().decode('utf-8')
        keyphrases_list = []
        for line in file_content.splitlines():
            line = line.strip()
            if len(line) > 0:
                keyphrases = [phrase.strip() for phrase in line.split(',') if phrase.strip()]
                if len(keyphrases) > 0:
                    keyphrases_list.append(keyphrases)
        if len(keyphrases_list) <= 0:
            raise Exception('❌ Файл не содержит валидных ключевых фраз')
        auto_restore_items = cfg.get('auto_restore_items')
        auto_restore_items['included'].extend(keyphrases_list)
        cfg.set('auto_restore_items', auto_restore_items)
        await throw_float_message(state=state, message=message, text=templ.settings_new_restore_included_float_text(f'✅ Успешно включено <b>{len(keyphrases_list)}</b> предметов из файла в автовосстановление'), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_restore_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_page, F.text)
async def handler_waiting_for_auto_deliveries_page(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        page = int(message.text) - 1
        await state.update_data(last_page=page)
        await throw_float_message(state=state, message=message, text=templ.settings_delivs_float_text(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.settings_delivs_kb(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await throw_float_message(state=state, message=message, text=templ.settings_delivs_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_new_auto_delivery_keyphrases, F.text)
async def handler_waiting_for_new_auto_delivery_keyphrases(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',')]
        await state.update_data(new_auto_delivery_keyphrases=keyphrases)
        await state.set_state(states.AutoDeliveriesStates.waiting_for_auto_delivery_piece)
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_float_text(f'🛒 Выберите <b>тип автовыдачи</b>:'), reply_markup=templ.settings_new_deliv_piece_kb(last_page))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_new_auto_delivery_message, F.text)
async def handler_waiting_for_new_auto_delivery_message(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        await state.update_data(new_auto_delivery_message=message.text)
        keyphrases = data.get('new_auto_delivery_keyphrases')
        phrases = '</code>, <code>'.join(keyphrases)
        msg = message.text
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_float_text(f'✔️ Подтвердите <b>добавление автовыдачи</b>:\n<b>· Ключевые фразы:</b> <code>{phrases}</code>\n<b>· Тип выдачи:</b> Сообщением\n<b>· Сообщение:</b> {msg}'), reply_markup=templ.confirm_kb(confirm_cb='add_new_auto_delivery', cancel_cb=calls.AutoDeliveriesPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_new_auto_delivery_goods, F.text | F.document)
async def handler_waiting_for_new_auto_delivery_goods(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if message.text:
            if len(message.text.strip()) == 0:
                raise Exception('❌ Слишком короткое значение')
            goods = [g.strip() for g in message.text.splitlines() if g.strip()]
        elif message.document:
            file = await message.bot.get_file(message.document.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            content = file_bytes.read().decode('utf-8', errors='ignore')
            if len(content.strip()) == 0:
                raise Exception('❌ Файл пустой')
            goods = [g.strip() for g in content.splitlines() if g.strip()]
        else:
            raise Exception('❌ Отправьте текст или файл')
        if not goods:
            raise Exception('❌ Не удалось извлечь товары')
        await state.update_data(new_auto_delivery_goods=goods)
        keyphrases = data.get('new_auto_delivery_keyphrases')
        phrases = '</code>, <code>'.join(keyphrases)
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_float_text(f'✔️ Подтвердите <b>добавление автовыдачи</b>:\n<b>· Ключевые фразы:</b> <code>{phrases}</code>\n<b>· Тип выдачи:</b> Поштучно\n<b>· Товары:</b> {len(goods)} шт.'), reply_markup=templ.confirm_kb(confirm_cb='add_new_auto_delivery', cancel_cb=calls.AutoDeliveriesPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_auto_delivery_keyphrases, F.text)
async def handler_waiting_for_auto_delivery_keyphrases(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        index = data.get('auto_delivery_index')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        auto_deliveries = cfg.get('auto_deliveries')
        keyphrases = [phrase.strip() for phrase in message.text.split(',')]
        auto_deliveries[index]['keyphrases'] = keyphrases
        cfg.set('auto_deliveries', auto_deliveries)
        keyphrases_str = '</code>, <code>'.join(keyphrases)
        await throw_float_message(state=state, message=message, text=templ.settings_deliv_page_float_text(f'✅ <b>Ключевые фразы</b> были успешно изменены на: <code>{keyphrases_str}</code>'), reply_markup=templ.back_kb(calls.AutoDeliveryPage(index=index).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_deliv_page_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveryPage(index=index).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_auto_delivery_message, F.text)
async def handler_waiting_for_auto_delivery_message(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        index = data.get('auto_delivery_index')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткий текст')
        auto_deliveries = cfg.get('auto_deliveries')
        auto_deliveries[index]['message'] = message.text.splitlines()
        cfg.set('auto_deliveries', auto_deliveries)
        await throw_float_message(state=state, message=message, text=templ.settings_deliv_page_float_text(f'✅ <b>Сообщение автовыдачи</b> было успешно изменено на: <blockquote>{message.text}</blockquote>'), reply_markup=templ.back_kb(calls.AutoDeliveryPage(index=index).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_deliv_page_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveryPage(index=index).pack()))

@router.message(states.AutoDeliveriesStates.waiting_for_auto_delivery_goods_add, F.text | F.document)
async def handler_waiting_for_auto_delivery_goods_add(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if message.text:
            if len(message.text.strip()) == 0:
                raise Exception('❌ Слишком короткое значение')
            goods = [g.strip() for g in message.text.splitlines() if g.strip()]
        elif message.document:
            file = await message.bot.get_file(message.document.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            content = file_bytes.read().decode('utf-8', errors='ignore')
            if len(content.strip()) == 0:
                raise Exception('❌ Файл пустой')
            goods = [g.strip() for g in content.splitlines() if g.strip()]
        else:
            raise Exception('❌ Отправьте текст или файл')
        if not goods:
            raise Exception('❌ Не удалось извлечь товары')
        auto_deliveries = cfg.get('auto_deliveries')
        auto_deliveries[index]['goods'].extend(goods)
        cfg.set('auto_deliveries', auto_deliveries)
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_goods_float_text(f'✅ <b>{len(goods)} товаров</b> успешно добавлено в автовыдачу'), reply_markup=templ.back_kb(calls.DelivGoodsPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=message, text=templ.settings_new_deliv_goods_float_text(e), reply_markup=templ.back_kb(calls.DelivGoodsPagination(page=last_page).pack()))
