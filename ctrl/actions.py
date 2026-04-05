from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from pathlib import Path
from collections import deque
from logging import getLogger
import asyncio
import shutil
import os
import html

from lib.cfg import AppConf as cfg
from lib.custom_commands import (
    cc_get_items,
    cc_wrap_items,
    cc_find_by_id,
    cc_toggle_event,
    cc_delete_item,
    cc_trigger_taken,
    cc_new_item,
)
from pok.defs import DealStage
from lib.ext import find_extension, start_extension, stop_extension
from . import ui as templ
from .ui.settings import fac_042, fac_127
from . import keys as calls
from .cb import CX
from . import states
from .helpers import emit_overlay, msg_swap_surface

logger = getLogger('pl.ctrl')
router = Router()


def _runtime_sync_config() -> None:
    try:
        from bot.core import live_bridge
        r = live_bridge()
        if r is not None:
            r.config = cfg.read('config')
    except Exception:
        pass



_ALERT_ON_KEYS = ('message', 'system', 'deal', 'review', 'problem', 'deal_changed', 'restore', 'bump', 'startup')


def _alerts_all_off(on: dict) -> None:
    for k in _ALERT_ON_KEYS:
        on[k] = False


def _alerts_all_on(on: dict) -> None:
    for k in _ALERT_ON_KEYS:
        on[k] = True


def _toggle_alert_type(config: dict, key: str, default: bool = False) -> None:
    alerts = config.setdefault('alerts', {})
    on = alerts.setdefault('on', {})
    if not alerts.get('enabled'):
        alerts['enabled'] = True
        _alerts_all_off(on)
        on[key] = True
        return
    on[key] = not bool(on.get(key, default))


@router.callback_query(calls.PduRootNav.filter())
async def hx_061(callback: CallbackQuery, callback_data: calls.PduRootNav, state: FSMContext):
    await state.set_state(None)
    to = callback_data.to
    if to == 'default':
        await emit_overlay(state, callback.message, templ.fac_040(), templ.fac_039(), callback)
    elif to == 'profile':
        await emit_overlay(state, callback.message, templ.fac_049(), templ.fac_048(), callback)
    elif to == 'logs':
        await emit_overlay(state, callback.message, templ.fac_038(), templ.fac_037(), callback)
    elif to == 'logger':
        await emit_overlay(
            state,
            callback.message,
            templ.fac_083(callback.message.chat.id),
            templ.fac_082(),
            callback,
        )

@router.callback_query(calls.PduHelpNav.filter())
async def hx_057(callback: CallbackQuery, callback_data: calls.PduHelpNav, state: FSMContext):
    await state.set_state(None)
    to = callback_data.to
    if to == 'default':
        await emit_overlay(state, callback.message, templ.fac_022(), templ.fac_021(), callback)
    elif to == 'commands':
        await emit_overlay(state, callback.message, templ.fac_020(), templ.fac_019(), callback)

@router.callback_query(calls.PduPrefsScope.filter())
async def hx_079(callback: CallbackQuery, callback_data: calls.PduPrefsScope, state: FSMContext):
    await state.set_state(None)
    to = callback_data.to
    if to in ('index', 'default'):
        await emit_overlay(state, callback.message, templ.fac_116(), templ.fac_080(), callback)
    elif to == 'auth':
        await emit_overlay(state, callback.message, templ.fac_052(), templ.fac_051(), callback)
    elif to in ('proxy', 'conn'):
        text = await asyncio.to_thread(templ.fac_102)
        await emit_overlay(state, callback.message, text, templ.fac_101(), callback)
    elif to == 'restore':
        await emit_overlay(state, callback.message, templ.fac_108(), templ.fac_107(), callback)
    elif to == 'complete':
        await emit_overlay(state, callback.message, templ.fac_113(), templ.fac_115(), callback)
    elif to == 'bump':
        await emit_overlay(state, callback.message, templ.fac_061(), templ.fac_060(), callback)
    elif to == 'logger':
        await emit_overlay(
            state,
            callback.message,
            templ.fac_083(callback.message.chat.id),
            templ.fac_082(),
            callback,
        )
    elif to == 'watermark':
        await emit_overlay(state, callback.message, templ.fac_119(), templ.fac_118(), callback)
    elif to == 'other':
        await emit_overlay(state, callback.message, templ.fac_099(), templ.fac_098(), callback)

@router.callback_query(F.data.in_((CX.nv_rs, CX.nv_bi, CX.nv_bx)))
async def hx_064(callback: CallbackQuery, state: FSMContext):
    d = callback.data
    if d == CX.nv_rs:
        return await hx_056(callback, calls.PduReviveAllowPage(page=0), state)
    if d == CX.nv_bi:
        return await hx_054(callback, calls.PduBoostAllowPage(page=0), state)
    if d == CX.nv_bx:
        return await hx_053(callback, calls.PduBoostDenyPage(page=0), state)


@router.callback_query(calls.PduReviveAllowPage.filter())
async def hx_056(callback: CallbackQuery, callback_data: calls.PduReviveAllowPage, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_106(), reply_markup=templ.fac_105(page), callback=callback)

@router.callback_query(calls.PduSealAllowPage.filter())
async def hx_055(callback: CallbackQuery, callback_data: calls.PduSealAllowPage, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.read('config')['auto']['confirm']['enabled']:
        await state.update_data(last_page=0)
        return await hx_079(callback, calls.PduPrefsScope(to='complete'), state)
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_110(), reply_markup=templ.fac_112(page), callback=callback)

@router.callback_query(calls.PduBoostAllowPage.filter())
async def hx_054(callback: CallbackQuery, callback_data: calls.PduBoostAllowPage, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.read('config')['auto']['bump']['enabled']:
        await state.update_data(last_page=0)
        return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_059(), reply_markup=templ.fac_058(page), callback=callback)

@router.callback_query(calls.PduBoostDenyPage.filter())
async def hx_053(callback: CallbackQuery, callback_data: calls.PduBoostDenyPage, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.read('config')['auto']['bump']['enabled']:
        await state.update_data(last_page=0)
        return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_055(), reply_markup=templ.fac_054(page), callback=callback)

@router.callback_query(calls.PduCmdGrid.filter())
async def hx_017(callback: CallbackQuery, callback_data: calls.PduCmdGrid, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.read('config')['features']['commands']:
        page = 0
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_067(), reply_markup=templ.fac_066(page), callback=callback)

@router.callback_query(calls.PduFulfillGrid.filter())
async def hx_001(callback: CallbackQuery, callback_data: calls.PduFulfillGrid, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.read('config')['features']['deliveries']:
        page = 0
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_079(), reply_markup=templ.fac_078(page), callback=callback)

@router.callback_query(calls.PduFulfillFilesPage.filter())
async def hx_026(callback: CallbackQuery, callback_data: calls.PduFulfillFilesPage, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    index = data.get('auto_delivery_index')
    page = callback_data.page
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_074(index), reply_markup=templ.fac_073(index, page), callback=callback)

@router.callback_query(calls.PduTplGrid.filter())
async def hx_063(callback: CallbackQuery, callback_data: calls.PduTplGrid, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_089(), reply_markup=templ.fac_085(page), callback=callback)

@router.callback_query(calls.PduAddonGrid.filter())
async def hx_066(callback: CallbackQuery, callback_data: calls.PduAddonGrid, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    await state.update_data(last_page=page)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_047(), reply_markup=templ.fac_046(page), callback=callback)

@router.callback_query(calls.PduCmdOpen.filter())
async def hx_015(callback: CallbackQuery, callback_data: calls.PduCmdOpen, state: FSMContext):
    await state.set_state(None)
    cmd_id = callback_data.cmd_id
    await state.update_data(custom_cmd_id=cmd_id)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_064(cmd_id), reply_markup=templ.fac_063(cmd_id, last_page), callback=callback)


@router.callback_query(calls.PduCmdEvtFlip.filter())
async def hx_016(callback: CallbackQuery, callback_data: calls.PduCmdEvtFlip, state: FSMContext):
    await state.set_state(None)
    items = cc_get_items(cfg.read('custom_commands'))
    item = cc_find_by_id(items, callback_data.cmd_id)
    if not item:
        return await callback.answer('Команда не найдена', show_alert=True)
    cc_toggle_event(item, callback_data.kind)
    cfg.write('custom_commands', cc_wrap_items(items))
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await emit_overlay(
        state=state,
        message=callback.message,
        text=templ.fac_064(callback_data.cmd_id),
        reply_markup=templ.fac_063(callback_data.cmd_id, last_page),
        callback=callback,
    )

@router.callback_query(calls.PduFulfillOpen.filter())
async def hx_002(callback: CallbackQuery, callback_data: calls.PduFulfillOpen, state: FSMContext):
    await state.set_state(None)
    index = callback_data.index
    await state.update_data(auto_delivery_index=index)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_077(index), reply_markup=templ.fac_076(index, last_page), callback=callback)

@router.callback_query(calls.PduTplOpen.filter())
async def hx_062(callback: CallbackQuery, callback_data: calls.PduTplOpen, state: FSMContext):
    await state.set_state(None)
    message_id = callback_data.message_id
    await state.update_data(message_id=message_id)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_088(message_id), reply_markup=templ.fac_087(message_id, last_page), callback=callback)

@router.callback_query(calls.PduAddonOpen.filter())
async def hx_065(callback: CallbackQuery, callback_data: calls.PduAddonOpen, state: FSMContext):
    await state.set_state(None)
    plugin_uuid = callback_data.uuid
    await state.update_data(plugin_uuid=plugin_uuid)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_045(plugin_uuid), reply_markup=templ.fac_044(plugin_uuid, last_page), callback=callback)

@router.callback_query(F.data == CX.pl_tk)
async def hx_049(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_golden_key)
    config = cfg.read('config')
    golden_key = config['account']['token'] or '❌ Не задано'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_050(f'🔐 Введите новый <b>токен</b> вашего аккаунта:\n・ Текущее: <code>{golden_key}</code>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.callback_query(F.data == CX.pl_ua)
async def hx_050(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_browser_ua)
    config = cfg.read('config')
    user_agent = config['account']['user_agent'] or '❌ Не задано'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_050(f'🎩 Введите новый <b>User Agent</b> вашего браузера:\n・ Текущее: <code>{user_agent}</code>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.callback_query(F.data == CX.pl_px)
async def hx_045(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_pl_proxy_line)
    config = cfg.read('config')
    proxy = config['account']['proxy'] or '❌ Не задано'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_068(f'🌐 Введите <b>HTTP-прокси</b> для аккаунта Playerok (<code>ip:port</code> или <code>user:pass@ip:port</code>):\n・ Текущий: <code>{proxy}</code>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))

@router.callback_query(F.data == CX.tg_px)
async def hx_048(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_tg_proxy_line)
    config = cfg.read('config')
    proxy = config['bot']['proxy'] or '❌ Не задано'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_068(f'🌐 Введите <b>HTTP-прокси</b> для Telegram (<code>ip:port</code> или <code>user:pass@ip:port</code>):\n・ Текущий: <code>{proxy}</code>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='proxy').pack()))

@router.callback_query(F.data == CX.pl_to)
async def hx_047(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_http_timeout)
    config = cfg.read('config')
    requests_timeout = config['account']['timeout'] or 'не задан'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_050(f'Введите новый <b>таймаут запросов</b> в секундах:\n・ Сейчас: <code>{requests_timeout}</code>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='auth').pack()))

@router.callback_query(F.data == CX.wm_vl)
async def hx_052(callback: CallbackQuery, state: FSMContext):
    return await hx_079(callback, calls.PduPrefsScope(to='watermark'), state)

@router.callback_query(F.data == CX.wm_pre)
async def hx_106(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    config['features']['watermark']['position'] = 'start'
    cfg.write('config', config)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_119(), reply_markup=templ.fac_118())

@router.callback_query(F.data == CX.wm_pst)
async def hx_105(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    config['features']['watermark']['position'] = 'end'
    cfg.write('config', config)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_119(), reply_markup=templ.fac_118())

@router.callback_query(F.data == CX.wm_tx)
async def hx_051(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_wm_text)
    config = cfg.read('config')
    watermark_value = config['features']['watermark']['text'] or '❌ Не задано'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_117(f'✏️ Введите новый <b>текст водяного знака</b>:\n・ Текущий: <code>{watermark_value}</code>'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='watermark').pack()))

@router.callback_query(F.data == CX.in_rs_kw)
async def hx_043(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduReviveGrp.pdu_revive_phrase_line)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_096(f'🔑 Введите <b>часть названия товара</b>, который нужно восстанавливать после продажи или истечения срока.\n\nЕсли нужно указать несколько вариантов — перечислите через запятую. Товар восстанавливается, если его название содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, Ключ Steam</code>'), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

@router.callback_query(F.data == CX.in_sh_kw)
async def hx_042(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduSealGrp.pdu_seal_phrase_line)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_109(f'🔑 Введите <b>часть названия товара</b>, сделки по которому нужно подтверждать автоматически.\n\nЕсли нужно несколько вариантов — перечислите через запятую. Сделка подтверждается, если название товара содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, Ключ Steam</code>'), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

@router.callback_query(F.data == CX.bm_iv)
async def hx_027(callback: CallbackQuery, state: FSMContext):
    if not cfg.read('config')['auto']['bump']['enabled']:
        await state.set_state(None)
        return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)
    try:
        await state.set_state(states.PduBoostGrp.pdu_boost_interval_sec)
        config = cfg.read('config')
        interval = config['auto']['bump']['interval']
        await emit_overlay(state=state, message=callback.message, text=templ.fac_056(f'⏲️ Введите <b>интервал автоподнятия предметов</b>:\n・ Текущее: <code>{interval}</code> сек.'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))
    except:
        import traceback
        traceback.print_exc()

@router.callback_query(F.data == CX.in_bm_i_kw)
async def hx_041(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduBoostGrp.pdu_boost_allow_line)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_091(f'🔑 Введите <b>часть названия товара</b>, который нужно поднимать в топ.\n\nЕсли нужно несколько вариантов — перечислите через запятую. Товар поднимается, если его название содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, Minecraft аккаунт</code>'), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

@router.callback_query(F.data == CX.in_bm_x_kw)
async def hx_040(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduBoostGrp.pdu_boost_deny_line)
    await emit_overlay(
        state=state, message=callback.message,
        text=templ.fac_090(
            '🔑 Введите <b>фразу из названия</b> лота, который <b>не</b> нужно поднимать (режим «весь каталог»).\n\n'
            'Несколько вариантов через запятую. Сравнение без учёта регистра, буквы ё и е считаются одинаковыми.\n\n'
            'Например: <code>тест, черновик</code>',
        ),
        reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()),
    )

@router.callback_query(F.data == CX.cc_pg)
async def hx_034(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduCmdGrp.pdu_cmd_sheet)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_065(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.fac_023(calls.PduCmdGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.cc_new)
async def hx_039(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduCmdGrp.pdu_cmd_body_new)
    await emit_overlay(
        state=state,
        message=callback.message,
        text=templ.fac_092(
            '⌨️ Введите <b>триггер команды</b> — слово с <code>!</code> в начале, как его напишет покупатель в чат.\n\n'
            'Пример: <code>!вызвать</code>\n\n'
            'После сохранения откроется карточка: там включите <b>события</b> и при необходимости текст ответа.',
        ),
        reply_markup=templ.fac_023(calls.PduCmdGrid(page=last_page).pack()),
    )

@router.callback_query(F.data == CX.cc_ans)
async def hx_033(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        cmd_id = data.get('custom_cmd_id')
        if not cmd_id:
            return await hx_017(callback, calls.PduCmdGrid(page=last_page), state)
        item = cc_find_by_id(cc_get_items(cfg.read('custom_commands')), cmd_id)
        if not item:
            return await hx_017(callback, calls.PduCmdGrid(page=last_page), state)
        await state.set_state(states.PduCmdGrp.pdu_cmd_reply)
        cur = '\n'.join(item.get('reply_lines') or []) or '❌ Не задано'
        await emit_overlay(
            state=state,
            message=callback.message,
            text=templ.fac_062(
                f'💬 Текст ответа в чат для <code>{item["trigger"]}</code> '
                f'(отправляется после событий; несколько строк — несколько сообщений по смыслу одного блока):\n・ Сейчас: <blockquote>{cur}</blockquote>',
            ),
            reply_markup=templ.fac_023(calls.PduCmdOpen(cmd_id=cmd_id).pack()),
        )
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_062(e), reply_markup=templ.fac_023(calls.PduCmdGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_pg)
async def hx_028(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduFulfillGrp.pdu_ff_sheet)
    await emit_overlay(state=state, message=callback.message, text=templ.scr_delivs_float_text(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_kw_n)
async def hx_038(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduFulfillGrp.pdu_ff_keys_new)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_093(f'🔑 Введите <b>часть названия товара</b>, при покупке которого бот должен автоматически отправить содержимое.\n\nЕсли нужно несколько вариантов — перечислите через запятую. Выдача срабатывает, если название товара в сделке содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, 100 звёзд</code>'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_kw_e)
async def hx_030(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        await state.set_state(states.PduFulfillGrp.pdu_ff_keys_edit)
        auto_deliveries = cfg.read('auto_deliveries')
        auto_delivery_message = '</code>, <code>'.join(auto_deliveries[index]['keyphrases']) or '❌ Не задано'
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075(f'🔑 Введите новые <b>ключевые фразы</b> для автовыдачи по этому товару (через запятую)\n・ Текущее: <code>{auto_delivery_message}</code>'), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_msg)
async def hx_031(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        await state.set_state(states.PduFulfillGrp.pdu_ff_msg_edit)
        auto_deliveries = cfg.read('auto_deliveries')
        auto_delivery_message = '\n'.join(auto_deliveries[index]['message']) or '❌ Не задано'
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075(f'💬 Введите новое <b>сообщение</b> после покупки\n・ Текущее: <blockquote>{auto_delivery_message}</blockquote>'), reply_markup=templ.fac_023(calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_g_add)
async def hx_029(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        await state.set_state(states.PduFulfillGrp.pdu_ff_goods_add)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_094(f'📦 Отправьте <b>товары</b> для добавления в поштучную выдачу (1 строка = 1 товар, можно прислать .txt файл с товарами):'), reply_markup=templ.fac_023(calls.PduFulfillFilesPage(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_094(e), reply_markup=templ.fac_023(calls.PduFulfillFilesPage(page=last_page).pack()))

@router.callback_query(F.data == CX.tpl_pg)
async def hx_037(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduTplGrp.pdu_tpl_sheet)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_084(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.fac_023(calls.PduTplGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.xt_pg)
async def hx_046(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduAddonGrp.pdu_addon_sheet)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_043('📃 Введите номер страницы для перехода:'), reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.tpl_tx)
async def hx_036(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        message_id = data.get('message_id')
        if not message_id:
            return await hx_063(callback, calls.PduTplGrid(page=last_page), state)
        await state.set_state(states.PduTplGrp.pdu_tpl_body)
        messages = cfg.read('messages')
        current = '\n'.join(messages[message_id]['text']) if messages[message_id]['text'] else '<i>пусто</i>'
        available = fac_127(message_id)
        vars_block = fac_042(available)
        body = (
            f'<b>Текущий текст:</b>\n<blockquote>{current}</blockquote>\n\n'
            f'<b>Переменные для этого шаблона:</b>\n{vars_block}\n\n'
            f'<i>Переменные вставляются прямо в текст: «Привет, $buyer!»\n'
            f'Разные строки — через перенос. Каждая строка — отдельная строка сообщения.</i>'
        )
        await emit_overlay(state=state, message=callback.message, text=templ.fac_084(body), reply_markup=templ.fac_023(calls.PduTplOpen(message_id=message_id).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_084(str(e)), reply_markup=templ.fac_023(calls.PduTplOpen(message_id=message_id if 'message_id' in dir() else '').pack()))

@router.callback_query(F.data == CX.log_mb)
async def hx_035(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduConnGrp.pdu_log_tail)
    config = cfg.read('config')
    max_file_size = config['logs']['max_mb'] or '❌ Не указано'
    await emit_overlay(state=state, message=callback.message, text=templ.fac_036(f'📄 Введите новый <b>максимальный размер файла логов</b> (в мегабайтах):\n・ Текущее: <b>{max_file_size} MB</b>'), reply_markup=templ.fac_023(calls.PduRootNav(to='logs').pack()))

@router.callback_query(F.data == CX.rs_sd)
async def hx_088(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['auto']['restore']['sold'] = not config['auto']['restore']['sold']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='restore'), state)

@router.callback_query(F.data == CX.rs_ex)
async def hx_087(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['auto']['restore']['expired'] = not config['auto']['restore']['expired']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='restore'), state)

@router.callback_query(F.data == CX.rs_all)
async def hx_086(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['auto']['restore']['all'] = not config['auto']['restore']['all']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='restore'), state)

@router.callback_query(F.data == CX.rs_pm)
async def hx_098(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['auto']['restore']['premium'] = not config['auto']['restore'].get('premium', False)
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='restore'), state)

@router.callback_query(F.data == CX.rs_pol)
async def hx_089(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    r = config['auto']['restore']
    if 'poll' not in r or not isinstance(r.get('poll'), dict):
        r['poll'] = {'enabled': False, 'interval': 300}
    r['poll']['enabled'] = not r['poll'].get('enabled', False)
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='restore'), state)

@router.callback_query(F.data == CX.rs_pol_iv)
async def hx_032(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduReviveGrp.pdu_revive_poll_sec)
    config = cfg.read('config')
    poll = (config['auto']['restore'].get('poll') or {})
    interval = poll.get('interval') or 300
    await emit_overlay(state=state, message=callback.message, text=templ.fac_103(f'⏲️ Как часто проверять завершённые лоты на сайте (секунды).\n・ Минимум <code>30</code> с.\n・ Сейчас: <code>{interval}</code> с.'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='restore').pack()))

@router.callback_query(F.data == CX.bm_en)
async def hx_081(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['auto']['bump']['enabled'] = not config['auto']['bump']['enabled']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)

@router.callback_query(F.data == CX.bm_all)
async def hx_080(callback: CallbackQuery, state: FSMContext):
    if not cfg.read('config')['auto']['bump']['enabled']:
        return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)
    config = cfg.read('config')
    config['auto']['bump']['all'] = not config['auto']['bump']['all']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)

@router.callback_query(F.data == CX.rd_en)
async def hx_094(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['features']['read_chat'] = not config['features']['read_chat']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='other'), state)

@router.callback_query(F.data == CX.sh_en)
async def hx_083(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['auto']['confirm']['enabled'] = not config['auto']['confirm']['enabled']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='complete'), state)

@router.callback_query(F.data == CX.sh_all)
async def hx_082(callback: CallbackQuery, state: FSMContext):
    if not cfg.read('config')['auto']['confirm']['enabled']:
        return await hx_079(callback, calls.PduPrefsScope(to='complete'), state)
    config = cfg.read('config')
    config['auto']['confirm']['all'] = not config['auto']['confirm']['all']
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='complete'), state)

@router.callback_query(F.data == CX.cc_en)
async def hx_090(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['features']['commands'] = not config['features']['commands']
    cfg.write('config', config)
    return await hx_017(callback, calls.PduCmdGrid(page=0), state)

@router.callback_query(F.data == CX.ad_en)
async def hx_084(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['features']['deliveries'] = not config['features']['deliveries']
    cfg.write('config', config)
    return await hx_001(callback, calls.PduFulfillGrid(page=0), state)

@router.callback_query(F.data == CX.db_v)
async def hx_091(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    if 'debug' not in config:
        config['debug'] = {'verbose': False}
    config['debug']['verbose'] = not config['debug'].get('verbose', False)
    cfg.write('config', config)
    from lib.util import apply_verbose
    apply_verbose(config['debug']['verbose'])
    return await hx_079(callback, calls.PduPrefsScope(to='other'), state)


@router.callback_query(F.data == CX.ad_pc)
async def hx_085(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    index = data.get('auto_delivery_index', 0)
    auto_deliveries = cfg.read('auto_deliveries')
    auto_deliveries[index]['piece'] = not auto_deliveries[index].get('piece', False)
    cfg.write('auto_deliveries', auto_deliveries)
    return await hx_002(callback, calls.PduFulfillOpen(index=index), state)

@router.callback_query(F.data == CX.wm_en)
async def hx_104(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    config['features']['watermark']['enabled'] = not config['features']['watermark']['enabled']
    cfg.write('config', config)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_119(), reply_markup=templ.fac_118())

@router.callback_query(F.data == CX.lg_en)
async def hx_095(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    alerts = config.setdefault('alerts', {})
    on = alerts.setdefault('on', {})
    alerts['enabled'] = not alerts.get('enabled', False)
    if not alerts['enabled']:

        _alerts_all_off(on)
    else:

        _alerts_all_on(on)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_um)
async def hx_102(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'message', False)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_sy)
async def hx_101(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'system', False)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_dl)
async def hx_098(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'deal', False)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_rv)
async def hx_100(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'review', False)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_sp)
async def hx_099(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'problem', False)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_st)
async def hx_097(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'deal_changed', False)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_rs)
async def hx_103(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'restore', True)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_bm)
async def hx_096(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'bump', True)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.lg_bt)
async def hx_097(callback: CallbackQuery, state: FSMContext):
    config = cfg.read('config')
    _toggle_alert_type(config, 'startup', True)
    cfg.write('config', config)
    _runtime_sync_config()
    return await hx_061(callback, calls.PduRootNav(to='logger'), state)

@router.callback_query(F.data == CX.tpl_nid)
async def hx_044(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.PduTplGrp.pdu_tpl_name_new)
    await state.update_data(new_template_title=None)
    await emit_overlay(
        state=state, message=callback.message,
        text=templ.fac_084(
            'Введите <b>название шаблона</b> — так оно будет показано в списке.\n\n'
            '<i>Например: «Приветствие» или «После оплаты».</i>'
        ),
        reply_markup=templ.fac_023(calls.PduTplGrid(page=0).pack()),
        callback=callback,
    )


@router.callback_query(F.data == CX.tpl_dq)
async def hx_011(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    message_id = data.get('message_id')
    last_page = data.get('last_page', 0)
    if not message_id:
        return await hx_063(callback, calls.PduTplGrid(page=last_page), state)
    messages = cfg.read('messages')
    info = messages.get(message_id, {})
    label = (info.get('title') or '').strip() or message_id
    await emit_overlay(
        state=state, message=callback.message,
        text=templ.fac_084(f'Удалить шаблон «{html.escape(label)}»? Отменить нельзя.'),
        reply_markup=templ.fac_024(CX.tpl_del, calls.PduTplOpen(message_id=message_id).pack()),
        callback=callback,
    )


@router.callback_query(F.data == CX.tpl_del)
async def hx_025(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    message_id = data.get('message_id')
    last_page = data.get('last_page', 0)
    messages = cfg.read('messages')
    if message_id and message_id in messages:
        del messages[message_id]
        cfg.write('messages', messages)
        logger.info(f'[tg] шаблон удалён  id={message_id}')
    return await hx_063(callback, calls.PduTplGrid(page=last_page), state)


@router.callback_query(F.data == CX.tpl_en)
async def hx_092(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        message_id = data.get('message_id')
        if not message_id:
            return await hx_063(callback, calls.PduTplGrid(page=last_page), state)
        messages = cfg.read('messages')
        messages[message_id]['enabled'] = not messages[message_id]['enabled']
        cfg.write('messages', messages)
        return await hx_062(callback, calls.PduTplOpen(message_id=message_id), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_084(e), reply_markup=templ.fac_023(calls.PduTplGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.xt_on)
async def hx_093(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        plugin_uuid = data.get('plugin_uuid')
        mod = find_extension(plugin_uuid)
        if not all((plugin_uuid, mod)):
            return await hx_066(callback, calls.PduAddonGrid(page=last_page), state)
        if mod.enabled:
            await stop_extension(plugin_uuid)
        else:
            await start_extension(plugin_uuid)
        return await hx_065(callback, calls.PduAddonOpen(uuid=plugin_uuid), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_043(e), reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.dismiss)
async def hx_003(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    try:
        await callback.bot.answer_callback_query(callback.id, cache_time=0)
    except Exception:
        pass
    try:
        await callback.message.delete()
    except Exception:
        pass

@router.callback_query(calls.PduReviveAllowDrop.filter())
async def hx_024(callback: CallbackQuery, callback_data: calls.PduReviveAllowDrop, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await hx_056(callback, calls.PduReviveAllowPage(page=last_page), state)
        auto_restore_items = cfg.read('auto_restore_items')
        auto_restore_items['included'].pop(index)
        cfg.write('auto_restore_items', auto_restore_items)
        return await hx_056(callback, calls.PduReviveAllowPage(page=last_page), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_104(e), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

@router.callback_query(calls.PduSealAllowDrop.filter())
async def hx_023(callback: CallbackQuery, callback_data: calls.PduSealAllowDrop, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await hx_055(callback, calls.PduSealAllowPage(page=last_page), state)
        auto_complete_deals = cfg.read('auto_complete_deals')
        auto_complete_deals['included'].pop(index)
        cfg.write('auto_complete_deals', auto_complete_deals)
        return await hx_055(callback, calls.PduSealAllowPage(page=last_page), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_111(e), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

@router.callback_query(calls.PduBoostAllowDrop.filter())
async def hx_022(callback: CallbackQuery, callback_data: calls.PduBoostAllowDrop, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await hx_054(callback, calls.PduBoostAllowPage(page=last_page), state)
        auto_bump_items = cfg.read('auto_bump_items')
        auto_bump_items['included'].pop(index)
        cfg.write('auto_bump_items', auto_bump_items)
        return await hx_054(callback, calls.PduBoostAllowPage(page=last_page), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_057(e), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

@router.callback_query(calls.PduBoostDenyDrop.filter())
async def hx_021(callback: CallbackQuery, callback_data: calls.PduBoostDenyDrop, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await hx_053(callback, calls.PduBoostDenyPage(page=last_page), state)
        auto_bump_items = cfg.read('auto_bump_items')
        if 'excluded' not in auto_bump_items:
            auto_bump_items['excluded'] = []
        auto_bump_items['excluded'].pop(index)
        cfg.write('auto_bump_items', auto_bump_items)
        return await hx_053(callback, calls.PduBoostDenyPage(page=last_page), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_053(e), reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()))

def _save_notification(message) -> dict:
    try:
        kb = message.reply_markup.model_dump() if message.reply_markup else None
    except Exception:
        kb = None
    return {'text': message.html_text or message.text or '', 'kb': kb}


@router.callback_query(F.data == CX.evt_back)
async def hx_004(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    orig = data.get('notification_orig', {})
    text = orig.get('text', '')
    kb_dict = orig.get('kb')
    from aiogram.types import InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(**kb_dict) if kb_dict else None
    try:
        await callback.bot.answer_callback_query(callback.id, cache_time=0)
    except Exception:
        pass
    try:
        m = await msg_swap_surface(callback.message, text, kb)
        if m is not None and getattr(m, 'message_id', None):
            await state.update_data(accent_message_id=m.message_id)
    except Exception:
        pass


@router.callback_query(calls.PduLogChatScroll.filter())
async def hx_058(callback: CallbackQuery, callback_data: calls.PduLogChatScroll, state: FSMContext):
    page_req = callback_data.page
    await callback.answer()
    await state.set_state(None)
    chat_id = callback_data.chat_id
    from bot.core import live_bridge, first_link_preview_url
    eng = live_bridge()
    if not eng:
        await callback.message.answer('❌ Движок не запущен')
        return
    msgs: list = []
    from_cache = False
    try:
        lst = await asyncio.to_thread(eng.account.load_messages, chat_id, 25)
        msgs = lst.messages
    except Exception:
        msgs = eng._recent_msgs(chat_id)
        from_cache = True
    if not msgs:
        await callback.message.answer(
            '❌ История пуста. Запрос списка сообщений на Playerok для этого клиента запрещён (403), '
            'а в памяти бота ещё нет сообщений по этому чату. Отправьте или получите сообщение после перезапуска — '
            'бот накапливает последние 25 сообщений из WebSocket.',
            parse_mode='HTML',
        )
        return
    preview = None
    for m in msgs:
        preview = first_link_preview_url(m)
        if preview:
            break
    parts = templ.fac_015(msgs, eng.account.id)
    total = len(parts)
    page = max(0, min(page_req, total - 1))
    if page == 0:
        await state.update_data(notification_orig=_save_notification(callback.message))
    text = parts[page]
    if from_cache and page == 0:
        text = '💾 <i>Кэш сессии (API недоступен).</i>\n\n' + text
    from aiogram.types import LinkPreviewOptions
    lp0 = None
    if preview and page == 0:
        lp0 = LinkPreviewOptions(is_disabled=False, url=preview, prefer_large_media=True, show_above_text=True)
    elif total > 1:
        lp0 = LinkPreviewOptions(is_disabled=True)
    kb = templ.fac_026(chat_id, page, total)
    try:
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=kb,
            link_preview_options=lp0,
        )
    except Exception:
        if page == 0:
            await callback.message.answer(text, parse_mode='HTML', link_preview_options=lp0, reply_markup=kb)


@router.callback_query(calls.PduNickMemo.filter())
async def hx_070(callback: CallbackQuery, callback_data: calls.PduNickMemo, state: FSMContext):
    await state.set_state(None)
    username = callback_data.name
    do = callback_data.do
    await state.update_data(username=username, notification_orig=_save_notification(callback.message))
    if do == 'send_mess':
        logger.info(f'[tg] ручной ответ  →  {username}')
        await state.set_state(states.PduReplyDraftGrp.pdu_reply_body)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data=CX.evt_back)]
        ])
        await emit_overlay(
            state=state, message=callback.message,
            text=f'💬 Введите сообщение для <b>{username}</b>:\n<i>Поддерживается текст и изображения.</i>',
            reply_markup=back_kb, callback=callback,
        )
    elif do == 'tpl_list':
        messages = cfg.read('messages') or {}
        if not messages:
            await callback.answer('Нет сохранённых шаблонов', show_alert=True)
            return
        order = list(messages.keys())
        await state.update_data(tpl_pick_order=order)
        await callback.answer()
        await emit_overlay(
            state=state, message=callback.message,
            text=templ.fac_033(username, 0, order),
            reply_markup=templ.fac_032(0, order),
            callback=callback,
        )


@router.callback_query(calls.PduLogTplMenu.filter())
async def hx_059(callback: CallbackQuery, callback_data: calls.PduLogTplMenu, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    data = await state.get_data()
    username = data.get('username')
    order = data.get('tpl_pick_order') or []
    if not username or not order:
        await callback.answer('Сессия устарела — откройте уведомление снова', show_alert=True)
        return
    await callback.answer()
    await emit_overlay(
        state=state, message=callback.message,
        text=templ.fac_033(username, page, order),
        reply_markup=templ.fac_032(page, order),
        callback=callback,
    )


@router.callback_query(calls.PduLogTplFire.filter())
async def hx_060(callback: CallbackQuery, callback_data: calls.PduLogTplFire, state: FSMContext):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await state.set_state(None)
    idx = callback_data.idx
    data = await state.get_data()
    username = data.get('username')
    order = data.get('tpl_pick_order') or []
    if not username or idx < 0 or idx >= len(order):
        await callback.answer('Сессия устарела — откройте «Шаблоны» снова', show_alert=True)
        return
    mess_id = order[idx]
    await callback.answer()
    from bot.core import live_bridge
    eng = live_bridge()
    text = eng._render_tpl(mess_id, username)
    if not text or not str(text).strip():
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data=CX.evt_back)],
        ])
        await emit_overlay(
            state=state, message=callback.message,
            text='❌ В шаблоне нет текста',
            reply_markup=kb, callback=callback,
        )
        return
    try:
        chat = eng._room_by_alias(username)
        last_sent = eng._push(chat.id, text)
        if not last_sent:
            raise Exception('Не удалось отправить в чат Playerok')
        preview = text[:120].replace('\n', ' ')
        po_url = last_sent.file.url if getattr(last_sent, 'file', None) else None
        result_lines = [f'✅ Шаблон отправлен <b>{html.escape(username)}</b>', f'<blockquote>{html.escape(preview)}</blockquote>']
        if po_url:
            result_lines.append(f'<a href="{html.escape(po_url)}">Просмотр на Playerok</a>')
        result_text = '\n'.join(result_lines)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data=CX.evt_back)],
            [InlineKeyboardButton(text='Закрыть', callback_data=CX.dismiss)],
        ])
        logger.info(f'[tg] шаблон из уведомления  →  {username}  id={mess_id}  «{preview[:60]}»')
        await emit_overlay(state=state, message=callback.message, text=result_text, reply_markup=kb, callback=callback)
    except Exception as e:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data=CX.evt_back)],
        ])
        await emit_overlay(
            state=state, message=callback.message,
            text=f'❌ Ошибка отправки: {html.escape(str(e))}',
            reply_markup=kb, callback=callback,
        )


@router.callback_query(calls.PduDealMemo.filter())
async def hx_069(callback: CallbackQuery, callback_data: calls.PduDealMemo, state: FSMContext):
    await state.set_state(None)
    deal_id = callback_data.de_id
    do = callback_data.do
    await state.update_data(deal_id=deal_id, notification_orig=_save_notification(callback.message))
    if do == 'refund':
        await emit_overlay(
            state=state, message=callback.message,
            text=f'↩️ Подтвердите <b>возврат</b> по <a href="https://playerok.com/deal/{deal_id}">сделке</a>:',
            reply_markup=templ.fac_024(confirm_cb=CX.dl_rf, cancel_cb=CX.evt_back),
            callback=callback,
        )
    elif do == 'complete':
        await emit_overlay(
            state=state, message=callback.message,
            text=f'✅ Подтвердите <b>выполнение</b> <a href="https://playerok.com/deal/{deal_id}">сделки</a>:',
            reply_markup=templ.fac_024(confirm_cb=CX.dl_ok, cancel_cb=CX.evt_back),
            callback=callback,
        )

@router.callback_query(calls.PduFulfillModePick.filter())
async def hx_078(callback: CallbackQuery, callback_data: calls.PduFulfillModePick, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    value = callback_data.val
    await state.update_data(new_auto_delivery_piece=value)
    if value:
        await state.set_state(states.PduFulfillGrp.pdu_ff_goods_new)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_093(f'📦 Отправьте <b>товары</b> для поштучной выдачи (1 строка = 1 товар, можно прислать .txt файл с товарами):'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()), callback=callback)
    else:
        await state.set_state(states.PduFulfillGrp.pdu_ff_msg_new)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_093(f'💬 Введите <b>сообщение автовыдачи</b>, которое будет отправляться после покупки товара:'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()), callback=callback)

@router.callback_query(F.data == CX.dl_rf)
async def hx_067(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    from bot.core import live_bridge as _bridge
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    eng = _bridge()
    data = await state.get_data()
    deal_id = data.get('deal_id')
    try:
        eng.bot_account.patch_deal(deal_id, DealStage.ROLLED_BACK)
        logger.info(f'[tg] возврат  deal={deal_id}')
        text = f'↩️ Возврат по <a href="https://playerok.com/deal/{deal_id}">сделке</a> оформлен.'
    except Exception as e:
        logger.error(f'[tg] ошибка возврата  deal={deal_id}  {e}')
        text = f'❌ Не удалось оформить возврат: {e}'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data=CX.evt_back)],
        [InlineKeyboardButton(text='Закрыть', callback_data=CX.dismiss)],
    ])
    await emit_overlay(state=state, message=callback.message, text=text, reply_markup=kb, callback=callback)


@router.callback_query(F.data == CX.dl_ok)
async def hx_009(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    from bot.core import live_bridge as _bridge
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    eng = _bridge()
    data = await state.get_data()
    deal_id = data.get('deal_id')
    try:
        eng.bot_account.patch_deal(deal_id, DealStage.SENT)
        logger.info(f'[tg] сделка закрыта вручную  deal={deal_id}')
        text = f'✅ Сделка <a href="https://playerok.com/deal/{deal_id}">отмечена выполненной</a>.'
    except Exception as e:
        logger.error(f'[tg] ошибка закрытия сделки  deal={deal_id}  {e}')
        text = f'❌ Не удалось закрыть сделку: {e}'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data=CX.evt_back)],
        [InlineKeyboardButton(text='Закрыть', callback_data=CX.dismiss)],
    ])
    await emit_overlay(state=state, message=callback.message, text=text, reply_markup=kb, callback=callback)

@router.callback_query(F.data == CX.bm_run)
async def hx_006(callback: CallbackQuery, state: FSMContext):
    if not cfg.read('config')['auto']['bump']['enabled']:
        await state.set_state(None)
        return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)
    try:
        await state.set_state(None)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_056(f'🔝 Идёт <b>обновление позиций</b> — смотрите консоль…'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))
        from bot.core import live_bridge as _bridge
        _bridge().bump_items()
        await emit_overlay(state=state, message=callback.message, text=templ.fac_056(f'✅ <b>Позиции</b> обновлены'), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_056(e), reply_markup=templ.fac_023(calls.PduPrefsScope(to='bump').pack()))


@router.callback_query(F.data == CX.px0)
async def hx_007(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    config['account']['proxy'] = ''
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='proxy'), state)

@router.callback_query(F.data == CX.tx0)
async def hx_008(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.read('config')
    config['bot']['proxy'] = ''
    cfg.write('config', config)
    return await hx_079(callback, calls.PduPrefsScope(to='proxy'), state)

@router.callback_query(F.data == CX.f_rs_txt)
async def hx_077(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduReviveGrp.pdu_revive_phrase_bulk)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_096('📄 Отправьте <b>.txt файл</b> со списком товаров для <b>автовосстановления</b>.\n\nКаждая строка — отдельный товар. Если для одного товара нужно несколько фраз — перечислите через запятую.\n\nПример содержимого файла:\n<code>Звёзды Telegram, 100 звёзд\nКлюч Steam, steam key\nMinecraft аккаунт</code>'), reply_markup=templ.fac_023(calls.PduReviveAllowPage(page=last_page).pack()))

@router.callback_query(F.data == CX.f_sh_txt)
async def hx_076(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduSealGrp.pdu_seal_phrase_bulk)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_109('📄 Отправьте <b>.txt файл</b> со списком товаров, сделки по которым нужно подтверждать автоматически.\n\nКаждая строка — отдельный товар. Если для одного товара нужно несколько фраз — перечислите через запятую.\n\nПример содержимого файла:\n<code>Звёзды Telegram, 100 звёзд\nКлюч Steam, steam key</code>'), reply_markup=templ.fac_023(calls.PduSealAllowPage(page=last_page).pack()))

@router.callback_query(F.data == CX.f_bm_i_txt)
async def hx_075(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduBoostGrp.pdu_boost_allow_bulk)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_091('📄 Отправьте <b>.txt файл</b> со списком товаров, которые нужно поднимать в топ.\n\nКаждая строка — отдельный товар. Если для одного товара нужно несколько фраз — перечислите через запятую.\n\nПример содержимого файла:\n<code>Звёзды Telegram, 100 звёзд\nMinecraft аккаунт\nКлюч Steam</code>'), reply_markup=templ.fac_023(calls.PduBoostAllowPage(page=last_page).pack()))

@router.callback_query(F.data == CX.f_bm_x_txt)
async def hx_074(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.PduBoostGrp.pdu_boost_deny_bulk)
    await emit_overlay(
        state=state, message=callback.message,
        text=templ.fac_090(
            '📄 <b>.txt</b> с фразами исключений (по одной строке на набор фраз через запятую, как для белого списка).',
        ),
        reply_markup=templ.fac_023(calls.PduBoostDenyPage(page=last_page).pack()),
    )

@router.callback_query(F.data == CX.cc_dok)
async def hx_013(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        cmd_id = data.get('custom_cmd_id')
        item = cc_find_by_id(cc_get_items(cfg.read('custom_commands')), cmd_id) if cmd_id else None
        if not item:
            return await hx_017(callback, calls.PduCmdGrid(page=last_page), state)
        trig = item['trigger']
        await emit_overlay(
            state=state,
            message=callback.message,
            text=templ.fac_062(f'🗑 Удалить команду <code>{trig}</code>?'),
            reply_markup=templ.fac_024(confirm_cb=CX.cc_del, cancel_cb=calls.PduCmdOpen(cmd_id=cmd_id).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        lp = data.get('last_page', 0)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_062(e), reply_markup=templ.fac_023(calls.PduCmdGrid(page=lp).pack()))

@router.callback_query(F.data == CX.cc_del)
async def hx_019(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        cmd_id = data.get('custom_cmd_id')
        if not cmd_id:
            return await hx_017(callback, calls.PduCmdGrid(page=last_page), state)
        items = cc_get_items(cfg.read('custom_commands'))
        trig = (cc_find_by_id(items, cmd_id) or {}).get('trigger', cmd_id)
        if not cc_delete_item(items, cmd_id):
            return await hx_017(callback, calls.PduCmdGrid(page=last_page), state)
        cfg.write('custom_commands', cc_wrap_items(items))
        await emit_overlay(
            state=state,
            message=callback.message,
            text=templ.fac_062(f'✅ Команда <code>{trig}</code> удалена'),
            reply_markup=templ.fac_023(calls.PduCmdGrid(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        lp = data.get('last_page', 0)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_062(e), reply_markup=templ.fac_023(calls.PduCmdGrid(page=lp).pack()))

@router.callback_query(F.data == CX.ad_go)
async def hx_000(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        keyphrases = data.get('new_auto_delivery_keyphrases')
        piece = data.get('new_auto_delivery_piece')
        message = data.get('new_auto_delivery_message')
        goods = data.get('new_auto_delivery_goods')
        if not keyphrases or piece is None or (piece is True and (not goods)) or (piece is False and (not message)):
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        auto_deliveries = cfg.read('auto_deliveries')
        auto_deliveries.append({'piece': piece, 'keyphrases': keyphrases, 'message': message.splitlines() if message and (not piece) else '', 'goods': goods if goods and piece else []})
        cfg.write('auto_deliveries', auto_deliveries)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_093(f'✅ <b>Авто-выдача</b> была успешно добавлена'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_093(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_dok)
async def hx_012(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075('🗑️ Подтвердите <b>удаление автовыдачи</b>:'), reply_markup=templ.fac_024(confirm_cb=CX.ad_del, cancel_cb=calls.PduFulfillOpen(index=index).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.ad_del)
async def hx_018(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        auto_deliveries = cfg.read('auto_deliveries')
        del auto_deliveries[index]
        cfg.write('auto_deliveries', auto_deliveries)
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075('✅ <b>Авто-выдача</b> удалена'), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_075(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(calls.PduFulfillFileDrop.filter())
async def hx_020(callback: CallbackQuery, callback_data: calls.PduFulfillFileDrop, state: FSMContext):
    try:
        await state.set_state(None)
        index = callback_data.index
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        deliv_index = data.get('auto_delivery_index')
        if deliv_index is None:
            return await hx_001(callback, calls.PduFulfillGrid(page=last_page), state)
        auto_deliveries = cfg.read('auto_deliveries')
        auto_deliveries[deliv_index]['goods'].pop(index)
        cfg.write('auto_deliveries', auto_deliveries)
        return await hx_026(callback, calls.PduFulfillFilesPage(page=last_page), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_072(e), reply_markup=templ.fac_023(calls.PduFulfillGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.xt_rf)
async def hx_068(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        uuid = data.get('plugin_uuid')
        if not uuid:
            return await hx_066(callback, calls.PduAddonGrid(page=last_page), state)
        from lib.ext import refresh_extension
        await refresh_extension(uuid)
        return await hx_065(callback, calls.PduAddonOpen(uuid=uuid), state)
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_043(e), reply_markup=templ.fac_023(calls.PduAddonGrid(page=last_page).pack()))

@router.callback_query(F.data == CX.log_sn)
async def hx_072(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    from lib.util import get_bot_log_path
    from aiogram.types import BufferedInputFile
    import datetime
    log_path = get_bot_log_path()
    try:
        if not os.path.exists(log_path):
            return await emit_overlay(state=state, message=callback.message, text=templ.fac_036('❌ Файл логов не найден'), reply_markup=templ.fac_037(), callback=callback)
        content = open(log_path, 'rb').read()
        today = datetime.datetime.now().strftime('%d-%m-%Y')
        filename = f'log_{today}.txt'
        line_count = content.count(b'\n')
        size_kb = len(content) / 1024
        err_count = content.count(b'| ERROR |')
        await callback.message.answer_document(
            document=BufferedInputFile(content, filename=filename),
            caption=f'📋 Лог за <b>{datetime.datetime.now().strftime("%d.%m.%Y")}</b>\n{line_count} строк · {size_kb:.1f} KB · ошибок: {err_count}',
            parse_mode='HTML',
            reply_markup=templ.fac_016(),
        )
        try:
            await callback.bot.answer_callback_query(callback.id, cache_time=0)
        except Exception:
            pass
        await emit_overlay(state=state, message=callback.message, text=templ.fac_038(), reply_markup=templ.fac_037())
    except Exception as e:
        await emit_overlay(state=state, message=callback.message, text=templ.fac_036(f'❌ Ошибка: {e}'), reply_markup=templ.fac_037(), callback=callback)

@router.callback_query(F.data == CX.bm_go)
async def hx_010(callback: CallbackQuery, state: FSMContext):
    if not cfg.read('config')['auto']['bump']['enabled']:
        await state.set_state(None)
        return await hx_079(callback, calls.PduPrefsScope(to='bump'), state)
    await state.set_state(None)
    await emit_overlay(state=state, message=callback.message, text=templ.fac_056('Подтвердите <b>обновление позиций</b> ↓'), reply_markup=templ.fac_024(CX.bm_run, calls.PduPrefsScope(to='bump').pack()))


