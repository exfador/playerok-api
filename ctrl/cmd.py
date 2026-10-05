from aiogram import types, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from logging import getLogger
from tempfile import NamedTemporaryFile
import math
import os
import asyncio
import re
import html
import secrets
import shutil
import time

from lib.cfg import AppConf as cfg, hash_password, password_needs_rehash, verify_password
from lib.custom_commands import cc_get_items, cc_wrap_items, cc_new_item, cc_trigger_taken, cc_find_by_id
from lib.ext import ADDONS_DIR, all_extensions
from lib.util import token_ok, cookies_ok, parse_cookies_string, ua_ok, proxy_ok, proxy_reachable, proxy_probe_html_suffix, valid_index, plural, proxy_masked
from . import ui as templ
from . import states
from . import keys as calls
from .cb import CX
from .helpers import emit_overlay, adm_gate, msg_force_edit
from bot._kit import clean_phrases
from lib.stock import DELIVERY_LOCK


def _same_rule(rules, index, data: dict) -> bool:
    if not valid_index(rules, index):
        return False
    expected = data.get('auto_delivery_keys')
    return expected is None or rules[index].get('keyphrases') == expected

logger = getLogger('pl.ctrl')
router = Router()
MAX_ADDON_FILES = 2000
MAX_ADDON_BYTES = 50 * 1024 * 1024


def _number(text: str | None) -> int | None:
    raw = (text or '').strip()
    return int(raw) if raw.isascii() and raw.isdigit() else None


def _page(text: str | None, items: int, per_page: int = 7) -> int:
    number = _number(text)
    if number is None:
        raise Exception('❌ Вы должны ввести числовое значение')
    total_pages = max(1, math.ceil(items / per_page))
    if not 1 <= number <= total_pages:
        raise Exception(f'❌ Допустимый номер страницы: от 1 до {total_pages}')
    return number - 1


async def _retry(state: FSMContext, current, error) -> str:
    await state.set_state(current)
    return f'{error}\n\n<i>Можно сразу отправить исправленное значение или нажать «Назад».</i>'


@router.message(Command('start'))
async def on_cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    if message.from_user.id not in config['bot']['admins']:
        return await adm_gate(message, state)
    await emit_overlay(state=state, message=message, text=templ.fac_040(), reply_markup=templ.fac_039())


def _age(value: float | None) -> str:
    if value is None:
        return 'нет данных'
    seconds = max(0, int(time.monotonic() - value))
    if seconds < 60:
        return f'{seconds} с назад'
    if seconds < 3600:
        return f'{seconds // 60} мин назад'
    return f'{seconds // 3600} ч назад'


def _uptime(value) -> str:
    if value is None:
        return 'нет данных'
    try:
        import datetime
        seconds = max(0, int((datetime.datetime.now() - value).total_seconds()))
    except Exception:
        return 'нет данных'
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return f'{days} д {hours} ч {minutes} мин' if days else f'{hours} ч {minutes} мин'


def _safe_health_error(value) -> str:
    text = str(value or '')[:500]
    text = re.sub(r'(?i)(https?://)[^/@\s]+@', r'\1***@', text)
    text = re.sub(r'(?i)\b(token|cookie|authorization)=?[: ]*[^\s;,]+', r'\1=***', text)
    return html.escape(text[:180])


@router.message(Command('status', 'online'))
async def on_cmd_status(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    if message.from_user.id not in config['bot']['admins']:
        return await adm_gate(message, state)

    from bot.core import live_bridge
    from ctrl.panel import get_panel

    bridge = live_bridge()
    panel = get_panel()
    market = bridge.health() if bridge is not None else {}
    telegram = panel.health() if panel is not None else {}
    feed = market.get('feed') or {}
    workers = market.get('workers') or {}
    worker_alive = sum(bool(value) for value in workers.values())
    worker_total = len(workers)
    workers_ok = worker_total > 0 and worker_alive == worker_total
    ws_ok = bool(feed.get('connected'))
    tg_success_at = telegram.get('last_api_success_at')
    tg_fresh = tg_success_at is not None and (time.monotonic() - tg_success_at) < 180
    tg_ok = bool(telegram.get('polling_active')) and tg_fresh
    supervisor_ok = bool(market.get('feed_supervisor_alive'))
    overall = ws_ok and tg_ok and supervisor_ok and workers_ok and not market.get('stopping')
    last_seen = max((v for v in (feed.get('last_pong_at'), feed.get('last_message_at')) if v is not None), default=None)
    error = feed.get('last_error') or telegram.get('last_error')
    error_line = ''
    if error:
        error_line = f'\n⚠️ Последняя ошибка: <code>{_safe_health_error(error)}</code>'
    text = (
        f'{"🟢" if overall else "🟡"} <b>Состояние CXH 24/7</b>\n\n'
        f'⏱ Аптайм: {_uptime(market.get("started_at"))}\n\n'
        f'{"🟢" if ws_ok else "🔴"} Playerok онлайн: <b>{"да" if ws_ok else "нет"}</b>\n'
        f'├ Последний сигнал от сервера: {_age(last_seen)}\n'
        f'├ Переподключений: {int(feed.get("reconnect_count") or 0)}\n'
        f'└ Активных чат-подписок: {int(feed.get("subscriptions") or 0)}\n\n'
        f'{"🟢" if tg_ok else "🔴"} Telegram polling/API: <b>{"работает" if tg_ok else "требует внимания"}</b>\n'
        f'├ API Telegram: {_age(telegram.get("last_api_success_at"))}\n'
        f'├ Получено обновлений: {int(telegram.get("updates_received") or 0)}\n'
        f'└ Сбоев polling подряд: {int(telegram.get("poll_failures") or 0)}\n\n'
        f'{"🟢" if workers_ok else "🔴"} Фоновые циклы: {worker_alive}/{worker_total}\n'
        f'{"🟢" if supervisor_ok else "🔴"} Supervisor Playerok\n'
        f'♻️ Перезапусков Feed: {int(market.get("feed_restarts") or 0)}'
        f'{error_line}'
    )
    await message.answer(text, parse_mode='HTML')


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
        await message.answer(f'❌ Неверный формат даты. Используйте <code>ДД.ММ.ГГГГ</code>, например: <code>{datetime.datetime.now():%d.%m.%Y}</code>', parse_mode='HTML')
        return

    log_path = os.path.join(project_root_dir(), 'logs', dt.strftime('%Y-%m-%d'), 'bot.log')
    if not os.path.exists(log_path):
        await message.answer(f'❌ Лог за <b>{date_str}</b> не найден.', parse_mode='HTML')
        return

    name = f'log_{dt.strftime("%d-%m-%Y")}'
    payload, filename, size, line_count, err_count, trimmed = await asyncio.to_thread(_pack_log, log_path, name)
    caption = (f'📋 Лог за <b>{date_str}</b>\n{line_count} строк · {size / 1024:.1f} KB · ошибок: {err_count}'
               + ('\n✂️ Лог большой — отправлен только конец.' if trimmed else ''))
    await message.answer_document(BufferedInputFile(payload, filename=filename), caption=caption, parse_mode='HTML')


_LOG_PLAIN_LIMIT = 5 * 1024 * 1024
_LOG_SEND_LIMIT = 45 * 1024 * 1024


def _pack_log(log_path: str, name: str) -> tuple[bytes, str, int, int, int, bool]:
    import io
    import zipfile
    size = os.path.getsize(log_path)
    with open(log_path, 'rb') as log_file:
        content = log_file.read()
    line_count = content.count(b'\n')
    err_count = content.count(b'| ERROR |')
    if len(content) <= _LOG_PLAIN_LIMIT:
        return content, f'{name}.txt', size, line_count, err_count, False
    trimmed = False
    window = len(content)
    while True:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(f'{name}.txt', content[-window:])
        packed = buffer.getvalue()
        if len(packed) <= _LOG_SEND_LIMIT or window <= _LOG_PLAIN_LIMIT:
            return packed, f'{name}.zip', size, line_count, err_count, trimmed
        window //= 2
        trimmed = True

_GATE_FAILURES: dict[int, tuple[int, float]] = {}
_GATE_FREE_ATTEMPTS = 5


def _gate_locked_for(user_id: int) -> int:
    failures, until = _GATE_FAILURES.get(user_id, (0, 0.0))
    return max(0, int(until - time.monotonic()))


def _gate_register_failure(user_id: int) -> None:
    failures, _ = _GATE_FAILURES.get(user_id, (0, 0.0))
    failures += 1
    lock = 0.0
    if failures >= _GATE_FREE_ATTEMPTS:
        lock = min(3600.0, 60.0 * 2 ** (failures - _GATE_FREE_ATTEMPTS))
    _GATE_FAILURES[user_id] = (failures, time.monotonic() + lock)
    logger.warning('[tg] неверный пароль панели user_id=%s, попытка %s', user_id, failures)


@router.message(states.PduGateGrp.pdu_gate_secret, F.text)
async def rx_026(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        user_id = message.from_user.id
        plain_password = message.text.strip()
        try:
            await message.delete()
        except Exception:
            pass
        wait = _gate_locked_for(user_id)
        if wait:
            raise Exception(f'⏳ Слишком много попыток. Повторите через {wait} с.')
        config = cfg.read('config')
        stored_hash = config['bot']['password_hash']
        if not await asyncio.to_thread(verify_password, plain_password, stored_hash):
            _gate_register_failure(user_id)
            raise Exception('❌ Неверный пароль.')
        _GATE_FAILURES.pop(user_id, None)
        if password_needs_rehash(stored_hash):
            config['bot']['password_hash'] = hash_password(plain_password)
        if message.from_user.id not in config['bot']['admins']:
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
        if eng is None:
            raise Exception('Движок Playerok ещё не запущен')
        if not username:
            raise Exception('Получатель не выбран — откройте уведомление снова')
        chat = await asyncio.to_thread(eng._room_by_alias, username)
        if chat is None:
            raise Exception(f'Чат с {html.escape(username)} не найден на Playerok')
        if message.text:
            if not message.text.strip():
                raise Exception('Пустое сообщение')
            last_sent = await asyncio.to_thread(eng._push, chat.id, message.text.strip())
            if not last_sent:
                raise Exception('Playerok не принял сообщение')
            sent_msg = message.text
        elif message.photo:
            photo = message.photo[-1]
            with NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                tmp_path = tmp.name
            try:
                await message.bot.download(photo, destination=tmp_path)
                if caption_raw:
                    await asyncio.to_thread(eng._push, chat.id, caption_raw)
                    sent_msg += caption_raw + ' '
                    await asyncio.sleep(1)
                last_sent = await asyncio.to_thread(eng._push, chat.id, None, tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            if not last_sent:
                raise Exception('Playerok не принял изображение')
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

async def _apply_cookie_jar_from_bot(jar: dict, state: FSMContext, message: types.Message, source: str) -> None:
    config = cfg.read('config')
    config['account']['cookies'] = '; '.join(f'{k}={v}' for k, v in jar.items() if v)
    config['account']['token'] = jar.get('token', '')
    config['account']['ddg5'] = jar.get('__ddg5_', '')
    config['account']['cookies_prompt_ok'] = True
    cfg.write('config', config)
    pretty = f"{source} · всего Cookie: {len(jar)} · __ddg5_ {'✓' if jar.get('__ddg5_') else '—'}"
    await emit_overlay(
        state=state, message=message,
        text=templ.fac_050(f'✅ <b>Cookie</b> Playerok сохранены ({pretty})'),
        reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()),
    )


async def _forget_secret_message(message: types.Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


@router.message(states.PduConnGrp.pdu_golden_key, F.document)
async def rx_032_doc(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        from lib.util import cookies_from_json_list, _extract_cookie_list
        from tempfile import NamedTemporaryFile
        import json as _json
        with NamedTemporaryFile(delete=False, suffix='.json') as tmp:
            await message.bot.download(message.document, destination=tmp.name)
            tmp_path = tmp.name
        try:
            with open(tmp_path, encoding='utf-8-sig') as fh:
                data = _json.load(fh)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            await _forget_secret_message(message)
        items = _extract_cookie_list(data)
        jar = cookies_from_json_list(items)
        if not jar.get('token') or not token_ok(jar['token']):
            raise Exception('В документе не найден валидный Cookie `token=` для playerok.com')
        await _apply_cookie_jar_from_bot(jar, state, message, source='из документа')
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(await _retry(state, states.PduConnGrp.pdu_golden_key, f'❌ {e}')), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))


@router.message(states.PduConnGrp.pdu_golden_key, F.text)
async def rx_032(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        from lib.util import cookies_from_json_list, _extract_cookie_list, load_cookies_json, COOKIES_JSON_PATH
        import json as _json
        raw = (message.text or '').strip()
        low = raw.lower()
        if low not in ('true', 'да', 'y', 'yes', 'ok', '1'):
            await _forget_secret_message(message)
        if low in ('true', 'да', 'y', 'yes', 'ok', '1'):
            jar, err = load_cookies_json(COOKIES_JSON_PATH)
            if err:
                raise Exception(err)
            await _apply_cookie_jar_from_bot(jar, state, message, source=f'из «{COOKIES_JSON_PATH}»')
            return
        if raw.startswith('[') or raw.startswith('{'):
            try:
                data = _json.loads(raw)
            except _json.JSONDecodeError as e:
                raise Exception(f'Некорректный JSON: {e.msg} (строка {e.lineno})')
            items = _extract_cookie_list(data)
            jar = cookies_from_json_list(items)
            if not jar.get('token') or not token_ok(jar['token']):
                raise Exception('В JSON не найден валидный Cookie `token=` для playerok.com')
            await _apply_cookie_jar_from_bot(jar, state, message, source='из JSON-текста')
            return
        if cookies_ok(raw):
            jar = parse_cookies_string(raw)
            await _apply_cookie_jar_from_bot(jar, state, message, source='из Header String')
            return
        if not token_ok(raw):
            raise Exception(
                f'Варианты:\n'
                f'• вставьте Cookie в <code>{COOKIES_JSON_PATH}</code> (Cookie-Editor → Export → JSON) и отправьте сюда <code>true</code>\n'
                f'• или пришлите JSON-файл документом\n'
                f'• или вставьте JSON-массив прямо в сообщение\n'
                f'• или Header String (<code>token=...; __ddg5_=...</code>)'
            )
        config = cfg.read('config')
        jar = parse_cookies_string(config['account'].get('cookies') or '')
        jar['token'] = raw
        config['account']['token'] = raw
        config['account']['cookies'] = '; '.join(f'{k}={v}' for k, v in jar.items() if v)
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050('✅ <b>Токен</b> сохранён (без Cookie — возможны блокировки DDoS-Guard)'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(await _retry(state, states.PduConnGrp.pdu_golden_key, f'❌ {e}')), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.message(states.PduConnGrp.pdu_browser_ua, F.text)
async def rx_033(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        user_agent = (message.text or '').strip()
        if not ua_ok(user_agent):
            raise Exception('❌ Неверный формат User Agent. Пример: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36')
        config = cfg.read('config')
        config['account']['user_agent'] = user_agent
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050(
            f'✅ <b>User Agent</b> сохранён: <code>{html.escape(user_agent)}</code>\n\n♻️ Применится после перезапуска бота (/restart).'
        ), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(await _retry(state, states.PduConnGrp.pdu_browser_ua, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.message(states.PduConnGrp.pdu_pl_proxy_line, F.text)
async def rx_027(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        proxy = message.text.strip()
        if len(proxy) <= 3:
            raise Exception('❌ Слишком короткое значение')
        if not proxy_ok(proxy):
            raise Exception(f'❌ Неверный формат прокси. Подходит: {templ.PROXY_FORMATS}')
        if not await asyncio.to_thread(proxy_reachable, proxy):
            raise Exception('❌ Указанный вами прокси не работает. Нет подключения к playerok.com')
        config = cfg.read('config')
        config['account']['proxy'] = proxy
        cfg.write('config', config)
        probe = await asyncio.to_thread(proxy_probe_html_suffix, proxy)
        await emit_overlay(state=state, message=message, text=templ.fac_068(f'✅ <b>Прокси для Playerok</b> сохранён: <code>{html.escape(proxy_masked(proxy))}</code>{probe}\n\n♻️ Применится после перезапуска бота (/restart).'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_068(await _retry(state, states.PduConnGrp.pdu_pl_proxy_line, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))

@router.message(states.PduConnGrp.pdu_tg_proxy_line, F.text)
async def rx_031(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        proxy = message.text.strip()
        if len(proxy) <= 3:
            raise Exception('❌ Слишком короткое значение')
        if not proxy_ok(proxy):
            raise Exception(f'❌ Неверный формат прокси. Подходит: {templ.PROXY_FORMATS}')
        if not await asyncio.to_thread(proxy_reachable, proxy, 'https://api.telegram.org/'):
            raise Exception('❌ Указанный вами прокси не работает. Нет подключения к api.telegram.org')
        config = cfg.read('config')
        config['bot']['proxy'] = proxy
        cfg.write('config', config)
        probe = await asyncio.to_thread(proxy_probe_html_suffix, proxy)
        await emit_overlay(state=state, message=message, text=templ.fac_068(f'✅ <b>Прокси для Telegram</b> сохранён: <code>{html.escape(proxy_masked(proxy))}</code>{probe}\n\n♻️ Применится после перезапуска бота (/restart).'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_068(await _retry(state, states.PduConnGrp.pdu_tg_proxy_line, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))

@router.message(states.PduConnGrp.pdu_http_timeout, F.text)
async def rx_029(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        raw = (message.text or '').strip()
        if not raw.isascii() or not raw.isdigit():
            raise Exception('❌ Введите целое число секунд, например 30')
        timeout = int(raw)
        if not 5 <= timeout <= 300:
            raise Exception('❌ Допустимо от 5 до 300 секунд')
        config = cfg.read('config')
        config['account']['timeout'] = timeout
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_050(f'✅ Таймаут запросов изменён на <b>{timeout} с</b> — применяется сразу.'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_050(await _retry(state, states.PduConnGrp.pdu_http_timeout, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

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
        await emit_overlay(state=state, message=message, text=templ.fac_117(await _retry(state, states.PduConnGrp.pdu_wm_text, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='watermark').pack()))

@router.message(states.PduConnGrp.pdu_log_tail, F.text)
async def rx_008(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        max_size_int = _number(message.text)
        if max_size_int is None:
            raise Exception('❌ Вы должны ввести числовое значение')
        if not 1 <= max_size_int <= 10240:
            raise Exception('❌ Допустимо от 1 до 10240 МБ')
        config = cfg.read('config')
        config['logs']['max_mb'] = max_size_int
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_036(f'✅ <b>Максимальный размер файла логов</b> был успешно изменён на <b>{max_size_int} MB</b>'), reply_markup=templ.fac_023(calls.PduRootNav(to='logs').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_036(await _retry(state, states.PduConnGrp.pdu_log_tail, e)), reply_markup=templ.fac_023(calls.PduRootNav(to='logs').pack()))

@router.message(states.PduTplGrp.pdu_tpl_sheet, F.text)
async def rx_011(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        page = _page(message.text, len(cfg.read('messages')))
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.fac_089(), reply_markup=templ.fac_085(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_084(await _retry(state, states.PduTplGrp.pdu_tpl_sheet, e)), reply_markup=templ.fac_023(calls.PduTplGrid(page=last_page).pack()))

@router.message(states.PduAddonGrp.pdu_addon_sheet, F.text)
async def rx_028(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        page = _page(message.text, len(all_extensions()))
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.fac_047(), reply_markup=templ.fac_046(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_043(await _retry(state, states.PduAddonGrp.pdu_addon_sheet, e)), reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()))

@router.message(states.PduTplGrp.pdu_tpl_body, F.text)
async def rx_010(message: types.Message, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    message_id = data.get('message_id')
    messages = cfg.read('messages') or {}
    known = message_id in messages
    back = (calls.PduTplOpen(message_id=message_id) if known else calls.PduTplGrid(page=data.get('last_page', 0))).pack()
    try:
        if not known:
            raise Exception('❌ Шаблон не найден — откройте его заново')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткий текст')
        messages[message_id]['text'] = message.text.split('\n')
        cfg.write('messages', messages)
        title = html.escape(templ.fac_013(message_id, messages[message_id]))
        await emit_overlay(state=state, message=message, text=templ.fac_086(f'✅ Текст шаблона <b>«{title}»</b> изменён:\n<blockquote>{html.escape(message.text)}</blockquote>'), reply_markup=templ.fac_023(back))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_086(await _retry(state, states.PduTplGrp.pdu_tpl_body, e)), reply_markup=templ.fac_023(back))

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
            text=templ.fac_084(await _retry(state, states.PduTplGrp.pdu_tpl_name_new, e)),
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
            text=templ.fac_084(await _retry(state, states.PduTplGrp.pdu_tpl_text_new, e)),
            reply_markup=templ.fac_023(calls.PduTplGrid(page=0).pack()),
        )


@router.message(states.PduReviveGrp.pdu_revive_poll_sec, F.text)
async def rx_030(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        raw = (message.text or '').strip()
        if not raw.isascii() or not raw.isdigit():
            raise Exception('❌ Введите целое число секунд, например 300')
        interval = int(raw)
        if not 30 <= interval <= 86400:
            raise Exception('❌ Допустимо от 30 до 86400 секунд')
        config = cfg.read('config')
        if 'poll' not in config['auto']['restore'] or not isinstance(config['auto']['restore'].get('poll'), dict):
            config['auto']['restore']['poll'] = {'enabled': False, 'interval': 300}
        config['auto']['restore']['poll']['interval'] = interval
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_103(f'✅ Проверка завершённых раз в <b>{interval}</b> с'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='restore').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_103(await _retry(state, states.PduReviveGrp.pdu_revive_poll_sec, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='restore').pack()))


async def _save_price_limit(message: types.Message, state: FSMContext, section: str | None, key: str, back: str, render, current) -> None:
    try:
        await state.set_state(None)
        raw = (message.text or '').strip().replace(',', '.')
        try:
            value = float(raw)
        except ValueError:
            raise Exception('❌ Введите число, например <code>50</code>')
        if not math.isfinite(value) or value < 0 or value > 100000:
            raise Exception('❌ Допустимо от 0 до 100000')
        config = cfg.read('config')
        target = config['auto'] if section is None else config['auto'][section]
        target[key] = int(value) if value.is_integer() else round(value, 2)
        cfg.write('config', config)
        shown = 'без лимита' if not value else f'{target[key]} ₽'
        await emit_overlay(state=state, message=message, text=render(f'✅ Лимит сохранён: <b>{shown}</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to=back).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=render(await _retry(state, current, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to=back).pack()))


@router.message(states.PduReviveGrp.pdu_revive_limit, F.text)
async def rx_revive_limit(message: types.Message, state: FSMContext):
    await _save_price_limit(message, state, 'restore', 'premium_max_price', 'restore', templ.fac_103, states.PduReviveGrp.pdu_revive_limit)


@router.message(states.PduBoostGrp.pdu_boost_limit, F.text)
async def rx_boost_limit(message: types.Message, state: FSMContext):
    await _save_price_limit(message, state, 'bump', 'max_price', 'bump', templ.fac_056, states.PduBoostGrp.pdu_boost_limit)


@router.message(states.PduBoostGrp.pdu_daily_limit, F.text)
async def rx_daily_limit(message: types.Message, state: FSMContext):
    origin = 'restore' if (await state.get_data()).get('daily_limit_origin') == 'restore' else 'bump'
    render = templ.fac_103 if origin == 'restore' else templ.fac_056
    await _save_price_limit(message, state, None, 'daily_limit', origin, render, states.PduBoostGrp.pdu_daily_limit)


@router.message(states.PduBoostGrp.pdu_boost_interval_sec, F.text)
async def rx_004(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        raw = (message.text or '').strip()
        if not raw.isascii() or not raw.isdigit():
            raise Exception('❌ Введите целое число секунд, например 3600')
        interval = int(raw)
        if not 600 <= interval <= 604800:
            raise Exception('❌ Допустимо от 600 секунд (10 минут) до 604800 (7 дней): каждое поднятие платное')
        config = cfg.read('config')
        config['auto']['bump']['interval'] = interval
        cfg.write('config', config)
        await emit_overlay(state=state, message=message, text=templ.fac_056(f'✅ Интервал автоподнятия: <b>{interval} с</b>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_056(await _retry(state, states.PduBoostGrp.pdu_boost_interval_sec, e)), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))

@router.message(states.PduBoostGrp.pdu_boost_allow_line, F.text)
async def rx_018(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        if not keyphrases:
            raise Exception('❌ Укажите хотя бы одну непустую фразу')
        auto_bump_items = cfg.read('auto_bump_items')
        auto_bump_items['included'].append(keyphrases)
        cfg.write('auto_bump_items', auto_bump_items)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(f"✅ В автоподнятие добавлено: <code>{'</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)}</code>"), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(await _retry(state, states.PduBoostGrp.pdu_boost_allow_line, e)), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

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
        await emit_overlay(state=state, message=message, text=templ.fac_091(f'✅ Из файла в автоподнятие добавлено <b>{len(keyphrases_list)}</b> {plural(len(keyphrases_list), "строка", "строки", "строк")}'), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_091(await _retry(state, states.PduBoostGrp.pdu_boost_allow_bulk, e)), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

@router.message(states.PduBoostGrp.pdu_boost_deny_line, F.text)
async def rx_016(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        if not keyphrases:
            raise Exception('❌ Укажите хотя бы одну непустую фразу')
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
                f"✅ В исключения добавлено: <code>{'</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)}</code>",
            ),
            reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_090(await _retry(state, states.PduBoostGrp.pdu_boost_deny_line, e)), reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()))

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
        await emit_overlay(state=state, message=message, text=templ.fac_090(await _retry(state, states.PduBoostGrp.pdu_boost_deny_bulk, e)), reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()))

@router.message(states.PduCmdGrp.pdu_cmd_sheet, F.text)
async def rx_006(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        page = _page(message.text, len(cc_get_items(cfg.read('custom_commands'))))
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.fac_067(), reply_markup=templ.fac_066(page=page))
    except Exception as e:
        data = await state.get_data()
        await emit_overlay(state=state, message=message, text=templ.fac_065(await _retry(state, states.PduCmdGrp.pdu_cmd_sheet, e)), reply_markup=templ.fac_023(calls.PduCmdGrid(page=data.get('last_page', 0)).pack()))

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
        await emit_overlay(state=state, message=message, text=templ.fac_092(await _retry(state, states.PduCmdGrp.pdu_cmd_body_new, e)), reply_markup=templ.fac_023(calls.PduCmdGrid(page=last_page).pack()))

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
            text=templ.fac_062(await _retry(state, states.PduCmdGrp.pdu_cmd_reply, e)),
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
        if not keyphrases:
            raise Exception('❌ Укажите хотя бы одну непустую фразу')
        auto_complete_deals = cfg.read('auto_complete_deals')
        auto_complete_deals['included'].append(keyphrases)
        cfg.write('auto_complete_deals', auto_complete_deals)
        await emit_overlay(state=state, message=message, text=templ.fac_109(f"✅ В автоподтверждение добавлено: <code>{'</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)}</code>"), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_109(await _retry(state, states.PduSealGrp.pdu_seal_phrase_line, e)), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

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
        await emit_overlay(state=state, message=message, text=templ.fac_109(f'✅ Из файла в автоподтверждение добавлено <b>{len(keyphrases_list)}</b> {plural(len(keyphrases_list), "строка", "строки", "строк")}'), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_109(await _retry(state, states.PduSealGrp.pdu_seal_phrase_bulk, e)), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

@router.message(states.PduReviveGrp.pdu_revive_phrase_line, F.text)
async def rx_022(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = [phrase.strip() for phrase in message.text.split(',') if phrase.strip()]
        if not keyphrases:
            raise Exception('❌ Укажите хотя бы одну непустую фразу')
        auto_restore_items = cfg.read('auto_restore_items')
        auto_restore_items['included'].append(keyphrases)
        cfg.write('auto_restore_items', auto_restore_items)
        await emit_overlay(state=state, message=message, text=templ.fac_096(f"✅ В автовосстановление добавлено: <code>{'</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)}</code>"), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_096(await _retry(state, states.PduReviveGrp.pdu_revive_phrase_line, e)), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

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
        await emit_overlay(state=state, message=message, text=templ.fac_096(f'✅ Из файла в автовосстановление добавлено <b>{len(keyphrases_list)}</b> {plural(len(keyphrases_list), "строка", "строки", "строк")}'), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_096(await _retry(state, states.PduReviveGrp.pdu_revive_phrase_bulk, e)), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_sheet, F.text)
async def rx_000(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        page = _page(message.text, len(cfg.read('auto_deliveries')))
        await state.update_data(last_page=page)
        await emit_overlay(state=state, message=message, text=templ.fac_079(), reply_markup=templ.fac_078(page))
    except Exception as e:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        await emit_overlay(state=state, message=message, text=templ.fac_071(await _retry(state, states.PduFulfillGrp.pdu_ff_sheet, e)), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_keys_new, F.text)
async def rx_013(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        keyphrases = clean_phrases(message.text)
        if not keyphrases:
            raise Exception('❌ Укажите хотя бы одну непустую фразу')
        await state.update_data(new_auto_delivery_keyphrases=keyphrases)
        await state.set_state(states.PduFulfillGrp.pdu_ff_piece_edit)
        await emit_overlay(state=state, message=message, text=templ.fac_093(
            '🛒 Выберите <b>тип автовыдачи</b>:\n\n'
            '🔑 <b>Поштучно</b> — каждому покупателю по одному ключу/ссылке из вашего списка.\n'
            '💬 <b>Один текст</b> — всем покупателям одно и то же сообщение.'
        ), reply_markup=templ.fac_095(last_page))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_093(await _retry(state, states.PduFulfillGrp.pdu_ff_keys_new, e)), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

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
        phrases = '</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)
        msg = message.text
        await emit_overlay(state=state, message=message, text=templ.fac_093(f'✔️ Подтвердите <b>добавление автовыдачи</b>:\n<b>· Ключевые фразы:</b> <code>{phrases}</code>\n<b>· Тип выдачи:</b> Сообщением\n<b>· Сообщение:</b> {html.escape(msg)}'), reply_markup=templ.fac_024(confirm_cb=CX.ad_go, cancel_cb=calls.PduFulfillGrid(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_093(await _retry(state, states.PduFulfillGrp.pdu_ff_msg_new, e)), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

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
        phrases = '</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)
        await emit_overlay(state=state, message=message, text=templ.fac_093(f'✔️ Подтвердите <b>добавление автовыдачи</b>:\n<b>· Ключевые фразы:</b> <code>{phrases}</code>\n<b>· Тип выдачи:</b> Поштучно\n<b>· Товары:</b> {len(goods)} шт.'), reply_markup=templ.fac_024(confirm_cb=CX.ad_go, cancel_cb=calls.PduFulfillGrid(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_093(await _retry(state, states.PduFulfillGrp.pdu_ff_goods_new, e)), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_keys_edit, F.text)
async def rx_002(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        index = data.get('auto_delivery_index')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткое значение')
        keyphrases = clean_phrases(message.text)
        if not keyphrases:
            raise Exception('❌ Укажите хотя бы одну непустую фразу')
        with DELIVERY_LOCK:
            auto_deliveries = cfg.read('auto_deliveries')
            if not _same_rule(auto_deliveries, index, data):
                return await emit_overlay(state=state, message=message, text=templ.fac_075('⚠️ Автовыдача изменилась или была удалена.'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=data.get('last_page', 0)).pack()))
            auto_deliveries[index]['keyphrases'] = keyphrases
            cfg.write('auto_deliveries', auto_deliveries)
        await state.update_data(auto_delivery_keys=keyphrases)
        keyphrases_str = '</code>, <code>'.join(html.escape(str(k)) for k in keyphrases)
        await emit_overlay(state=state, message=message, text=templ.fac_075(f'✅ <b>Ключевые фразы</b> были успешно изменены на: <code>{keyphrases_str}</code>'), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_075(await _retry(state, states.PduFulfillGrp.pdu_ff_keys_edit, e)), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))

@router.message(states.PduFulfillGrp.pdu_ff_msg_edit, F.text)
async def rx_003(message: types.Message, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        index = data.get('auto_delivery_index')
        if len(message.text) <= 0:
            raise Exception('❌ Слишком короткий текст')
        with DELIVERY_LOCK:
            auto_deliveries = cfg.read('auto_deliveries')
            if not _same_rule(auto_deliveries, index, data):
                return await emit_overlay(state=state, message=message, text=templ.fac_075('⚠️ Автовыдача изменилась или была удалена.'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=data.get('last_page', 0)).pack()))
            auto_deliveries[index]['message'] = message.text.splitlines()
            cfg.write('auto_deliveries', auto_deliveries)
        await emit_overlay(state=state, message=message, text=templ.fac_075(f'✅ <b>Сообщение автовыдачи</b> было успешно изменено на: <blockquote>{html.escape(message.text)}</blockquote>'), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_075(await _retry(state, states.PduFulfillGrp.pdu_ff_msg_edit, e)), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))

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
        with DELIVERY_LOCK:
            auto_deliveries = cfg.read('auto_deliveries')
            if not _same_rule(auto_deliveries, index, data):
                return await emit_overlay(state=state, message=message, text=templ.fac_094('⚠️ Автовыдача изменилась или была удалена.'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))
            auto_deliveries[index].setdefault('goods', []).extend(goods)
            cfg.write('auto_deliveries', auto_deliveries)
        await emit_overlay(state=state, message=message, text=templ.fac_094(f'✅ В автовыдачу {plural(len(goods), "добавлен", "добавлено", "добавлено")} <b>{len(goods)}</b> {plural(len(goods), "товар", "товара", "товаров")}'), reply_markup=templ.fac_023(calls.PduFulfillFilesPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=message, text=templ.fac_094(await _retry(state, states.PduFulfillGrp.pdu_ff_goods_add, e)), reply_markup=templ.fac_023(calls.PduFulfillFilesPage(page=last_page).pack()))


@router.message(
    states.PduAddonGrp.pdu_addon_import_file,
    F.document.file_name.lower().endswith('.zip'),
)
async def rx_addon_import(message: types.Message, state: FSMContext):
    import zipfile
    import tempfile

    last_page = 0
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)

        file_name = message.document.file_name or 'extension.zip'
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            await message.bot.download(message.document, destination=tmp_path)

            try:
                zf = zipfile.ZipFile(tmp_path)
            except zipfile.BadZipFile:
                raise Exception('❌ Архив повреждён или не является zip-файлом.')

            with zf:
                names = [n for n in zf.namelist() if not n.startswith('__MACOSX/')]
                for n in names:
                    if n.startswith(('/', '..', '\\')) or '..' in n.replace('\\', '/').split('/') or re.match(r'^[A-Za-z]:', n):
                        raise Exception(f'❌ Опасный путь в архиве: <code>{html.escape(n)}</code>')
                unpacked = sum(info.file_size for info in zf.infolist())
                if len(names) > MAX_ADDON_FILES or unpacked > MAX_ADDON_BYTES:
                    raise Exception(f'❌ Архив слишком большой: допустимо до {MAX_ADDON_FILES} файлов и {MAX_ADDON_BYTES // (1024 * 1024)} МБ после распаковки.')

                os.makedirs(ADDONS_DIR, exist_ok=True)

                root_files = [n for n in names if '/' not in n.rstrip('/') and n]
                has_root_init = any(n == '__init__.py' for n in root_files)

                if has_root_init:
                    module_name = re.sub(r'[^A-Za-z0-9_]+', '_', os.path.splitext(file_name)[0]).strip('_') or 'extension'
                    dest = os.path.join(ADDONS_DIR, module_name)
                    if os.path.isdir(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                    os.makedirs(dest, exist_ok=True)
                    zf.extractall(dest)
                    added = [module_name]
                else:
                    root_dirs = {n.rstrip('/').split('/', 1)[0] for n in names if '/' in n}
                    valid_dirs = []
                    for d in root_dirs:
                        if any(n == f'{d}/__init__.py' or n.startswith(f'{d}/') and n.endswith('/__init__.py') and n.count('/') == 1 for n in names):
                            valid_dirs.append(d)
                    if not valid_dirs:
                        valid_dirs = [d for d in root_dirs if any(n == f'{d}/__init__.py' for n in names)]
                    if not valid_dirs:
                        raise Exception(
                            '❌ В архиве не найдено ни одной папки расширения с <code>__init__.py</code> внутри.'
                        )
                    with tempfile.TemporaryDirectory(prefix='cxh_ext_') as extract_tmp:
                        zf.extractall(extract_tmp)
                        added = []
                        for d in valid_dirs:
                            src = os.path.join(extract_tmp, d)
                            dst = os.path.join(ADDONS_DIR, d)
                            if os.path.isdir(dst):
                                shutil.rmtree(dst, ignore_errors=True)
                            shutil.move(src, dst)
                            added.append(d)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if len(added) == 1:
            body = f'✅ Расширение <b>{html.escape(added[0])}</b> распаковано в <code>ext/</code>.'
        else:
            list_html = '\n'.join(f'• <b>{html.escape(n)}</b>' for n in added)
            body = f'✅ Импортировано расширений: <b>{len(added)}</b>:\n\n{list_html}'
        await emit_overlay(
            state=state,
            message=message,
            text=templ.fac_043(
                f'{body}\n\n❗ Для подключения <b>необходим перезапуск</b> бота.'
            ),
            reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()),
        )
    except Exception as e:
        await emit_overlay(
            state=state,
            message=message,
            text=templ.fac_043(await _retry(state, states.PduAddonGrp.pdu_addon_import_file, e)),
            reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()),
        )


@router.message(StateFilter(
    states.PduAddonGrp.pdu_addon_import_file,
    states.PduBoostGrp.pdu_boost_allow_bulk,
    states.PduBoostGrp.pdu_boost_deny_bulk,
    states.PduSealGrp.pdu_seal_phrase_bulk,
    states.PduReviveGrp.pdu_revive_phrase_bulk,
))
async def rx_expect_file(message: types.Message, state: FSMContext):
    extension = '.zip' if await state.get_state() == states.PduAddonGrp.pdu_addon_import_file.state else '.txt'
    await message.answer(f'📎 Здесь нужен файл <b>{extension}</b> — пришлите его документом. Чтобы выйти, нажмите «Назад» на экране выше.', parse_mode='HTML')


@router.message(StateFilter(states.PduFulfillGrp.pdu_ff_piece_new, states.PduFulfillGrp.pdu_ff_piece_edit))
async def rx_expect_choice(message: types.Message):
    await message.answer('👆 Выберите тип выдачи кнопкой на экране выше.')
