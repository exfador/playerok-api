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

from lib.cfg import AppConf as cfg, verify_password
from lib.custom_commands import cc_get_items, cc_wrap_items, cc_new_item, cc_trigger_taken, cc_find_by_id
from lib.ext import all_extensions
from lib.util import token_ok, ua_ok, proxy_ok, proxy_reachable, proxy_probe_html_suffix
from . import ui as templ
from . import states
from . import keys as calls
from .cb import CX
from .helpers import emit_overlay, adm_gate, msg_force_edit

logger = getLogger('pl.ctrl')
router = Router()

@router.message(Command('start'))
async def on_cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    if message.from_user.id not in config['bot']['admins']:
        return await adm_gate(message, state)
    await emit_overlay(state=state, message=message, text=templ.fac_040(), reply_markup=templ.fac_039())

@router.message(Command('stats'))
async def on_cmd_stats(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    if message.from_user.id not in config['bot']['admins']:
        return await adm_gate(message, state)
    await emit_overlay(state=state, message=message, text=templ.fac_126(), reply_markup=templ.fac_123())

@router.message(Command('logs'))
async def on_cmd_logs(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    if message.from_user.id not in config['bot']['admins']:
        return await adm_gate(message, state)

    from lib.util import project_root_dir
    from aiogram.types import BufferedInputFile
    import datetime

    args = (message.text or '').split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        available = []
        logs_dir = os.path.join(project_root_dir(), 'logs')
        if os.path.isdir(logs_dir):
            for d in sorted(os.listdir(logs_dir), reverse=True):
                try:
                    dt = datetime.datetime.strptime(d, '%Y-%m-%d')
                    available.append(dt.strftime('%d.%m.%Y'))
                except ValueError:
                    pass
        hint = '\n'.join(f'  • /logs {d}' for d in available[:10]) if available else '  (нет сохранённых логов)'
        await message.answer(
            '📋 <b>Логи по дате</b>\n\n'
            'Введите команду в формате:\n'
            '<code>/logs ДД.ММ.ГГГГ</code>\n\n'
            'Например: <code>/logs ' + datetime.datetime.now().strftime('%d.%m.%Y') + '</code>\n\n'
            '<b>Доступные даты:</b>\n' + hint,
            parse_mode='HTML'
        )
        return

    date_str = args[1].strip()
    try:
        dt = datetime.datetime.strptime(date_str, '%d.%m.%Y')
    except ValueError:
        await message.answer('❌ Неверный формат даты. Используйте <code>ДД.ММ.ГГГГ</code>, например: <code>05.04.2026</code>', parse_mode='HTML')
        return

    log_path = os.path.join(project_root_dir(), 'logs', dt.strftime('%Y-%m-%d'), 'bot.log')
    if not os.path.exists(log_path):
        await message.answer(f'❌ Лог за <b>{date_str}</b> не найден.', parse_mode='HTML')
        return

    content = open(log_path, 'rb').read()
    filename = f'log_{dt.strftime("%d-%m-%Y")}.txt'
    size_kb = len(content) / 1024
    line_count = content.count(b'\n')
    err_count = content.count(b'| ERROR |')
    caption = f'📋 Лог за <b>{date_str}</b>\n{line_count} строк · {size_kb:.1f} KB · ошибок: {err_count}'
    await message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption=caption,
        parse_mode='HTML'
    )

@router.message(states.PduGateGrp.pdu_gate_secret, F.text)
async def rx_026(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        config = cfg.read('config')
        if not verify_password(message.text.strip(), config['bot']['password_hash']):
            raise Exception('❌ Неверный пароль.')
        config['bot']['admins'].append(message.from_user.id)
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_040(), reply_markup=templ.fac_039())
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_121(e), reply_markup=templ.fac_016())

@router.message(states.PduReplyDraftGrp.pdu_reply_body, F.text | F.photo)
async def rx_009(message: types.Message, state: FSMContext):
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
        from bot.core import live_bridge
        eng = live_bridge()
        chat = eng._room_by_alias(username)
        if message.text:
            if not message.text.strip():
                raise Exception('Пустое сообщение')
            last_sent = eng._push(chat.id, text=message.text.strip())
            sent_msg = message.text
        elif message.photo:
            photo = message.photo[-1]
            with NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                await message.bot.download(photo, destination=tmp.name)
                tmp_path = tmp.name
            if caption_raw:
                eng._push(chat.id, text=caption_raw)
                sent_msg += caption_raw + ' '
                await asyncio.sleep(1)
            last_sent = eng._push(chat.id, photo_file_path=tmp_path)
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
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data=CX.evt_back)],
            [InlineKeyboardButton(text='Закрыть', callback_data=CX.dismiss)],
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
                m = await msg_force_edit(
                    message.bot, message.chat.id, accent_id, result_text, kb,
                )
                if m is not None:
                    await state.update_data(accent_message_id=m.message_id)
                    return
            await message.answer(result_text, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data=CX.evt_back)],
        ])
        try:
            await message.delete()
        except Exception:
            pass
        if accent_id:
            err_text = f'❌ Ошибка отправки: {e}'
            m = await msg_force_edit(
                message.bot, message.chat.id, accent_id, err_text, kb,
            )
            if m is not None:
                await state.update_data(accent_message_id=m.message_id)
                return
        await message.answer(f'❌ Ошибка: {e}', reply_markup=kb, parse_mode='HTML')

@router.message(states.PduConnGrp.pdu_golden_key, F.text)
async def rx_032(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        token = message.text
        if not token_ok(token):
            raise Exception('❌ Неверный формат токена. Пример: eyJhbGciOiJIUzI1NiIsInR5cCI1IkpXVCJ9')
        config = cfg.read('config')
        config['account']['token'] = token
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050(f'✅ <b>Токен</b> был успешно изменён на <b>{token}</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.message(states.PduConnGrp.pdu_browser_ua, F.text)
async def rx_033(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        user_agent = message.text
        if not ua_ok(user_agent):
            raise Exception('❌ Неверный формат User Agent. Пример: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36')
        config = cfg.read('config')
        config['account']['user_agent'] = user_agent
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050(f'✅ <b>User Agent</b> был успешно изменён на <b>{user_agent}</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.message(states.PduConnGrp.pdu_pl_proxy_line, F.text)
async def rx_027(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        proxy = message.text
        if len(proxy) <= 3:
            raise Exception('❌ Слишком короткое значение')
        if not proxy_ok(proxy):
            raise Exception('❌ Неверный формат. Нужен <b>HTTP</b>-прокси: <code>ip:port</code> или <code>user:pass@ip:port</code>')
        if not proxy_reachable(proxy):
            raise Exception('❌ Указанный вами прокси не работает. Нет подключения к playerok.com')
        config = cfg.read('config')
        config['account']['proxy'] = proxy
        cfg.write('config', config)
        probe = await asyncio.to_thread(proxy_probe_html_suffix, proxy)
        await emit_overlay(state=state, message=message, text=templ.fac_068(f'✅ <b>Прокси для Playerok</b> (HTTP) сохранён: <b>{html.escape(proxy)}</b>{probe}'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_068(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))

@router.message(states.PduConnGrp.pdu_tg_proxy_line, F.text)
async def rx_031(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        proxy = message.text
        if len(proxy) <= 3:
            raise Exception('❌ Слишком короткое значение')
        if not proxy_ok(proxy):
            raise Exception('❌ Неверный формат. Нужен <b>HTTP</b>-прокси: <code>ip:port</code> или <code>user:pass@ip:port</code>')
        if not proxy_reachable(proxy, 'https://api.telegram.org/'):
            raise Exception('❌ Указанный вами прокси не работает. Нет подключения к api.telegram.org')
        config = cfg.read('config')
        config['bot']['proxy'] = proxy
        cfg.write('config', config)
        probe = await asyncio.to_thread(proxy_probe_html_suffix, proxy)
        await emit_overlay(state=state, message=message, text=templ.fac_068(f'✅ <b>Прокси для Telegram</b> (HTTP) сохранён: <b>{html.escape(proxy)}</b>{probe}'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_068(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))

@router.message(states.PduConnGrp.pdu_http_timeout, F.text)
async def rx_029(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        timeout = message.text
        if not timeout.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(timeout) < 0:
            raise Exception('❌ Слишком низкое значение')
        config = cfg.read('config')
        config['account']['timeout'] = int(timeout)
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050(f'Таймаут запросов изменён на <b>{timeout} с</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(str(e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.message(states.PduConnGrp.pdu_listener_delay, F.text)
async def rx_007(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        delay = message.text
        if not delay.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(delay) < 0:
            raise Exception('❌ Слишком низкое значение')
        config = cfg.read('config')
        config['account']['listener_delay'] = int(delay)
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050(f'✅ <b>Периодичность запросов</b> была успешна изменена на <b>{delay}</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.message(states.PduConnGrp.pdu_wm_text, F.text)
async def rx_034(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        watermark = message.text
        if len(watermark) <= 0 or len(watermark) >= 150:
            raise Exception('❌ Слишком короткое или длинное значение')
        config = cfg.read('config')
        config['features']['watermark']['text'] = watermark
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_119(), reply_markup=templ.fac_118())
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_117(str(e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='watermark').pack()))

@router.message(states.PduConnGrp.pdu_log_tail, F.text)
async def rx_008(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        max_size = message.text
        if not max_size.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(max_size) <= 0:
            raise Exception('❌ Слишком низкое значение')
        max_size_int = int(max_size)
        config = cfg.read('config')
        config['logs']['max_mb'] = max_size_int
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_036(f'✅ <b>Максимальный размер файла логов</b> был успешно изменён на <b>{max_size_int} MB</b>'), reply_markup=templ.fac_023(calls.PduRootNav(to='logs').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_036(e), reply_markup=templ.fac_023(calls.PduRootNav(to='logs').pack()))

@router.message(states.PduTplGrp.pdu_tpl_sheet, F.text)
async def rx_011(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        page = int(message.text) - 1
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.fac_089(), reply_markup=templ.fac_085(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_084(e), reply_markup=templ.fac_023(calls.PduTplGrid(page=last_page).pack()))

@router.message(states.PduAddonGrp.pdu_addon_sheet, F.text)
async def rx_028(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        page = int(message.text) - 1
        per_page = 7
        total_pages = max(1, math.ceil(len(all_extensions()) / per_page))
        if page < 0 or page >= total_pages:
            raise Exception(f'❌ Допустимый номер страницы: от 1 до {total_pages}')
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.fac_047(), reply_markup=templ.fac_046(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_043(e), reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()))

@router.message(states.PduTplGrp.pdu_tpl_body, F.text)
async def rx_010(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        message_id = data.get('message_id')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткий текст')
        messages = cfg.read('messages')
        message_split_lines = message.text.split('\n')
        messages[message_id]['text'] = message_split_lines
        cfg.write('messages', messages)
        await emit_overlay(state=state, message=message, text=templ.fac_086(f'✅ <b>Текст шаблона</b> <code>{message_id}</code> изменён на <blockquote>{message.text}</blockquote>'), reply_markup=templ.fac_023(calls.PduTplOpen(message_id=message_id).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_086(e), reply_markup=templ.fac_023(calls.PduTplOpen(message_id=message_id).pack()))

@router.message(states.PduTplGrp.pdu_tpl_name_new, F.text)
async def rx_024(message: types.Message, state: FSMContext):
    try:
        title = (message.text or '').strip()
        if not title:
            raise Exception('Введите название шаблона')
        if len(title) > 120:
            raise Exception('Название слишком длинное (не более 120 символов)')
        await state.update_data(new_template_title=title)
        await state.set_state(states.PduTplGrp.pdu_tpl_text_new)
        await emit_overlay(
            state=state, message=message,
            text=templ.fac_084(
                f'Название: <b>{html.escape(title)}</b>\n\n'
                'Теперь отправьте <b>текст шаблона</b> (одним сообщением, можно с переносами строк).\n\n'
                f'<b>Все переменные:</b>\n{templ.fac_041()}'
            ),
            reply_markup=templ.fac_023(calls.PduTplGrid(page=0).pack()),
        )
    except Exception as e:
        await emit_overlay(
            state=state, message=message,
            text=templ.fac_084(str(e)),
            reply_markup=templ.fac_023(calls.PduTplGrid(page=0).pack()),
        )


@router.message(states.PduTplGrp.pdu_tpl_text_new, F.text)
async def rx_025(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get('new_template_title')
    try:
        if not title:
            await state.set_state(None)
            raise Exception('Сессия сброшена. Откройте «Добавить шаблон» снова.')
        lines = message.text.split('\n') if message.text else []
        if not any((ln.strip() for ln in lines)):
            raise Exception('Текст не может быть пустым')
        messages = cfg.read('messages')
        key = 't_' + secrets.token_hex(8)
        while key in messages:
            key = 't_' + secrets.token_hex(8)
        messages[key] = {'enabled': True, 'text': lines, 'title': title}
        cfg.write('messages', messages)
        await state.set_state(None)
        await state.update_data(message_id=key, new_template_title=None)
        await emit_overlay(
            state=state, message=message,
            text=templ.fac_086(
                f'Шаблон <b>{html.escape(title)}</b> сохранён.'
            ),
            reply_markup=templ.fac_023(calls.PduTplOpen(message_id=key).pack()),
        )
    except Exception as e:
        await emit_overlay(
            state=state, message=message,
            text=templ.fac_084(str(e)),
            reply_markup=templ.fac_023(calls.PduTplGrid(page=0).pack()),
        )


@router.message(states.PduReviveGrp.pdu_revive_poll_sec, F.text)
async def rx_030(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        interval = int(message.text)
        if interval < 30:
            raise Exception('❌ Не меньше 30 секунд')
        config = cfg.read('config')
        if 'poll' not in config['auto']['restore'] or not isinstance(config['auto']['restore'].get('poll'), dict):
            config['auto']['restore']['poll'] = {'enabled': False, 'interval': 300}
        config['auto']['restore']['poll']['interval'] = interval
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_103(f'✅ Проверка завершённых раз в <b>{interval}</b> с'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='restore').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_103(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='restore').pack()))


@router.message(states.PduBoostGrp.pdu_boost_interval_sec, F.text)
async def rx_004(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        if int(message.text) <= 0:
            raise Exception('❌ Слишком низкое значение')
        interval = int(message.text)
        config = cfg.read('config')
        config['auto']['bump']['interval'] = interval
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_056(f'✅ <b>Интервал автоподнятия предметов</b> был успешно изменён на <b>{interval}</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_056(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))

@router.message(states.PduBoostGrp.pdu_boost_allow_line, F.text)
async def rx_018(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_bump_items = cfg.read('auto_bump_items')
        auto_bump_items['included'].append(keyphrases)
        cfg.write('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(f"✅ Предмет с ключевыми фразами <code>{'</code>, <code>'.join(keyphrases)}</code> успешно включён в автоподнятие"), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(e), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

@router.message(states.PduBoostGrp.pdu_boost_allow_bulk, F.document.file_name.lower().endswith('.txt'))
async def rx_019(message: types.Message, state: FSMContext):
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
        auto_bump_items = cfg.read('auto_bump_items')
        auto_bump_items['included'].extend(keyphrases_list)
        cfg.write('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(f'✅ Успешно включено <b>{len(keyphrases_list)}</b> предметов из файла в автоподнятие'), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(e), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

@router.message(states.PduBoostGrp.pdu_boost_deny_line, F.text)
async def rx_016(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_bump_items = cfg.read('auto_bump_items')
        if 'excluded' not in auto_bump_items:
            auto_bump_items['excluded'] = []
        auto_bump_items['excluded'].append(keyphrases)
        cfg.write('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(
            state=state, message=message,
            text=templ.fac_090(
                f"✅ В исключения добавлено: <code>{'</code>, <code>'.join(keyphrases)}</code>",
            ),
            reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_090(e), reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()))

@router.message(states.PduBoostGrp.pdu_boost_deny_bulk, F.document.file_name.lower().endswith('.txt'))
async def rx_017(message: types.Message, state: FSMContext):
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
        auto_bump_items = cfg.read('auto_bump_items')
        if 'excluded' not in auto_bump_items:
            auto_bump_items['excluded'] = []
        auto_bump_items['excluded'].extend(keyphrases_list)
        cfg.write('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(
            state=state, message=message,
            text=templ.fac_090(f'✅ В исключения добавлено строк из файла: <b>{len(keyphrases_list)}</b>'),
            reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_090(e), reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()))

@router.message(states.PduCmdGrp.pdu_cmd_sheet, F.text)
async def rx_006(message: types.Message, state: FSMContext):
    try:
        if not message.text.strip().isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        await state.update_data(last_page=int(message.text.strip()) - 1)
        await state.set_state(None)
        await emit_overlay(state=state, message=message, text=templ.fac_067(), reply_markup=templ.fac_066(page=int(message.text) - 1))
    except Exception as e:
        data = await state.get_data()
        await emit_overlay(state=state, message=message, text=templ.fac_065(e), reply_markup=templ.fac_023(calls.PduCmdGrid(page=data.get('last_page', 0)).pack()))

@router.message(states.PduCmdGrp.pdu_cmd_body_new, F.text)
async def rx_015(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    try:
        raw = message.text.strip()
        if len(raw) < 2 or len(raw) > 64:
            raise Exception('❌ Длина команды: от 2 до 64 символов')
        if not raw.startswith('!'):
            raise Exception('❌ Команда должна начинаться с <code>!</code>')
        items = cc_get_items(cfg.read('custom_commands'))
        if cc_trigger_taken(items, raw):
            raise Exception('❌ Такая команда уже есть')
        new_item = cc_new_item(raw)
        items.append(new_item)
        cfg.write('custom_commands', cc_wrap_items(items))
        await state.update_data(custom_cmd_id=new_item['id'])
        await state.set_state(None)
        await emit_overlay(
            state=state,
            message=message,
            text=templ.fac_064(new_item['id']),
            reply_markup=templ.fac_063(new_item['id'], last_page),
        )
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_092(e), reply_markup=templ.fac_023(calls.PduCmdGrid(page=last_page).pack()))

@router.message(states.PduCmdGrp.pdu_cmd_reply, F.text)
async def rx_005(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    cmd_id = data.get('custom_cmd_id')
    try:
        if not cmd_id:
            raise Exception('❌ Сессия сброшена')
        items = cc_get_items(cfg.read('custom_commands'))
        item = cc_find_by_id(items, cmd_id)
        if not item:
            raise Exception('❌ Команда не найдена')
        raw = message.text or ''
        item['reply_lines'] = [ln.rstrip() for ln in raw.split('\n') if ln.strip()]
        cfg.write('custom_commands', cc_wrap_items(items))
        await state.set_state(None)
        await emit_overlay(
            state=state,
            message=message,
            text=templ.fac_062(f"✅ Текст ответа для <code>{item['trigger']}</code> обновлён"),
            reply_markup=templ.fac_023(calls.PduCmdOpen(cmd_id=cmd_id).pack()),
        )
    except Exception as e:
        err = str(e)
        if not cmd_id or 'Сессия сброшена' in err or 'не найдена' in err:
            await state.set_state(None)
        await emit_overlay(
            state=state,
            message=message,
            text=templ.fac_062(e),
            reply_markup=templ.fac_023(calls.PduCmdOpen(cmd_id=cmd_id).pack()) if cmd_id else templ.fac_023(calls.PduCmdGrid(page=last_page).pack()),
        )

@router.message(states.PduSealGrp.pdu_seal_phrase_line, F.text)
async def rx_020(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_complete_deals = cfg.read('auto_complete_deals')
        auto_complete_deals['included'].append(keyphrases)
        cfg.write('auto_complete_deals', auto_complete_deals)
        await emit_overlay(state=state, message=message, text=templ.fac_109('✅ Предмет успешно включён в автоподтверждение'), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_109(e), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

@router.message(states.PduSealGrp.pdu_seal_phrase_bulk, F.document.file_name.lower().endswith('.txt'))
async def rx_021(message: types.Message, state: FSMContext):
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
        auto_complete_deals = cfg.read('auto_complete_deals')
        auto_complete_deals['included'].extend(keyphrases_list)
        cfg.write('auto_complete_deals', auto_complete_deals)
        await emit_overlay(state=state, message=message, text=templ.fac_109(f'✅ Успешно включено <b>{len(keyphrases_list)} предметов</b> из файла в автоподтверждение'), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_109(e), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

@router.message(states.PduReviveGrp.pdu_revive_phrase_line, F.text)
async def rx_022(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        auto_restore_items = cfg.read('auto_restore_items')
        auto_restore_items['included'].append(keyphrases)
        cfg.write('auto_restore_items', auto_restore_items)
        await emit_overlay(state=state, message=message, text=templ.fac_096(f"✅ Предмет с ключевыми фразами <code>{'</code>, <code>'.join(keyphrases)}</code> успешно включён в автовосстановление"), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_096(e), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

@router.message(states.PduReviveGrp.pdu_revive_phrase_bulk, F.document.file_name.lower().endswith('.txt'))
async def rx_023(message: types.Message, state: FSMContext):
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
        auto_restore_items = cfg.read('auto_restore_items')
        auto_restore_items['included'].extend(keyphrases_list)
        cfg.write('auto_restore_items', auto_restore_items)
        await emit_overlay(state=state, message=message, text=templ.fac_096(f'✅ Успешно включено <b>{len(keyphrases_list)}</b> предметов из файла в автовосстановление'), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_096(e), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_sheet, F.text)
async def rx_000(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if not message.text.isdigit():
            raise Exception('❌ Вы должны ввести числовое значение')
        page = int(message.text) - 1
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.scr_delivs_float_text(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.fac_078(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.scr_delivs_float_text(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_keys_new, F.text)
async def rx_013(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',')]
        await state.update_data(new_auto_delivery_keyphrases=keyphrases)
        await state.set_state(states.PduFulfillGrp.pdu_ff_piece_edit)
        await emit_overlay(state=state, message=message, text=templ.fac_093(f'🛒 Выберите <b>тип автовыдачи</b>:'), reply_markup=templ.fac_095(last_page))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_093(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_msg_new, F.text)
async def rx_014(message: types.Message, state: FSMContext):
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
        await emit_overlay(state=state, message=message, text=templ.fac_093(f'✔️ Подтвердите <b>добавление автовыдачи</b>:\n<b>· Ключевые фразы:</b> <code>{phrases}</code>\n<b>· Тип выдачи:</b> Сообщением\n<b>· Сообщение:</b> {msg}'), reply_markup=templ.fac_024(confirm_cb=CX.ad_go, cancel_cb=calls.PduFulfillGrid(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_093(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_goods_new, F.text | F.document)
async def rx_012(message: types.Message, state: FSMContext):
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
        await emit_overlay(state=state, message=message, text=templ.fac_093(f'✔️ Подтвердите <b>добавление автовыдачи</b>:\n<b>· Ключевые фразы:</b> <code>{phrases}</code>\n<b>· Тип выдачи:</b> Поштучно\n<b>· Товары:</b> {len(goods)} шт.'), reply_markup=templ.fac_024(confirm_cb=CX.ad_go, cancel_cb=calls.PduFulfillGrid(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_093(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_keys_edit, F.text)
async def rx_002(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        index = data.get('auto_delivery_index')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        auto_deliveries = cfg.read('auto_deliveries')
        keyphrases = [phrase.strip() for phrase in message.text.split(',')]
        auto_deliveries[index]['keyphrases'] = keyphrases
        cfg.write('auto_deliveries', auto_deliveries)
        keyphrases_str = '</code>, <code>'.join(keyphrases)
        await emit_overlay(state=state, message=message, text=templ.fac_075(f'✅ <b>Ключевые фразы</b> были успешно изменены на: <code>{keyphrases_str}</code>'), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_075(e), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_msg_edit, F.text)
async def rx_003(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        index = data.get('auto_delivery_index')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткий текст')
        auto_deliveries = cfg.read('auto_deliveries')
        auto_deliveries[index]['message'] = message.text.splitlines()
        cfg.write('auto_deliveries', auto_deliveries)
        await emit_overlay(state=state, message=message, text=templ.fac_075(f'✅ <b>Сообщение автовыдачи</b> было успешно изменено на: <blockquote>{message.text}</blockquote>'), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_075(e), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_goods_add, F.text | F.document)
async def rx_001(message: types.Message, state: FSMContext):
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
        auto_deliveries = cfg.read('auto_deliveries')
        auto_deliveries[index]['goods'].extend(goods)
        cfg.write('auto_deliveries', auto_deliveries)
        await emit_overlay(state=state, message=message, text=templ.fac_094(f'✅ <b>{len(goods)} товаров</b> успешно добавлено в автовыдачу'), reply_markup=templ.fac_023(calls.PduFulfillFilesPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_094(e), reply_markup=templ.fac_023(calls.PduFulfillFilesPage(page=last_page).pack()))
