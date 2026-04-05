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

from keel.shelf import ConfigShelf as cfg
from keel.aliases import (
    cc_get_items,
    cc_wrap_items,
    cc_find_by_id,
    cc_toggle_event,
    cc_delete_item,
    cc_trigger_taken,
    cc_new_item,
)
from moor.kinds import DealStage
from keel.graft import seek_graft, arm_graft, disarm_graft
from . import ui as templ
from .ui.settings import msg_vars_subset_text, template_var_keys
from . import keys as calls
from . import states
from .helpers import throw_float_message, edit_or_replace_message

logger = getLogger('trellis.face')
router = Router()


def _runtime_sync_config() -> None:
    try:
        from chamber.supervisor import active_supervisor
        r = active_supervisor()
        if r is not None:
            r.config = cfg.get('config')
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


@router.callback_query(calls.MenuNavigation.filter())
async def callback_menu_navigation(callback: CallbackQuery, callback_data: calls.MenuNavigation, state: FSMContext):
    await state.set_state(None)
    to = callback_data.to
    if to == 'default':
        await throw_float_message(state, callback.message, templ.menu_text(), templ.menu_kb(), callback)
    elif to == 'profile':
        await throw_float_message(state, callback.message, templ.profile_text(), templ.profile_kb(), callback)
    elif to == 'logs':
        await throw_float_message(state, callback.message, templ.logs_text(), templ.logs_kb(), callback)
    elif to == 'logger':
        await throw_float_message(
            state,
            callback.message,
            templ.settings_logger_text(callback.message.chat.id),
            templ.settings_logger_kb(),
            callback,
        )

@router.callback_query(calls.InstructionNavigation.filter())
async def callback_instruction_navgiation(callback: CallbackQuery, callback_data: calls.InstructionNavigation, state: FSMContext):
    await state.set_state(None)
    to = callback_data.to
    if to == 'default':
        await throw_float_message(state, callback.message, templ.instruction_text(), templ.instruction_kb(), callback)
    elif to == 'commands':
        await throw_float_message(state, callback.message, templ.instruction_comms_text(), templ.instruction_comms_kb(), callback)

@router.callback_query(calls.SettingsNavigation.filter())
async def callback_settings_navigation(callback: CallbackQuery, callback_data: calls.SettingsNavigation, state: FSMContext):
    await state.set_state(None)
    to = callback_data.to
    if to in ('index', 'default'):
        await throw_float_message(state, callback.message, templ.settings_text(), templ.settings_kb(), callback)
    elif to == 'auth':
        await throw_float_message(state, callback.message, templ.settings_auth_text(), templ.settings_auth_kb(), callback)
    elif to in ('proxy', 'conn'):
        text = await asyncio.to_thread(templ.settings_proxy_text)
        await throw_float_message(state, callback.message, text, templ.settings_proxy_kb(), callback)
    elif to == 'restore':
        await throw_float_message(state, callback.message, templ.settings_restore_text(), templ.settings_restore_kb(), callback)
    elif to == 'complete':
        await throw_float_message(state, callback.message, templ.settings_complete_text(), templ.settings_complete_kb(), callback)
    elif to == 'bump':
        await throw_float_message(state, callback.message, templ.settings_bump_text(), templ.settings_bump_kb(), callback)
    elif to == 'logger':
        await throw_float_message(
            state,
            callback.message,
            templ.settings_logger_text(callback.message.chat.id),
            templ.settings_logger_kb(),
            callback,
        )
    elif to == 'watermark':
        await throw_float_message(state, callback.message, templ.settings_watermark_text(), templ.settings_watermark_kb(), callback)
    elif to == 'other':
        await throw_float_message(state, callback.message, templ.settings_other_text(), templ.settings_other_kb(), callback)

@router.callback_query(F.data.in_(('nav_restore_included', 'nav_bump_included', 'nav_bump_excluded')))
async def callback_nav_restore_bump_lists(callback: CallbackQuery, state: FSMContext):
    d = callback.data
    if d == 'nav_restore_included':
        return await callback_included_restore_items_pagination(callback, calls.IncludedRestoreItemsPagination(page=0), state)
    if d == 'nav_bump_included':
        return await callback_included_bump_items_pagination(callback, calls.IncludedBumpItemsPagination(page=0), state)
    if d == 'nav_bump_excluded':
        return await callback_excluded_bump_items_pagination(callback, calls.ExcludedBumpItemsPagination(page=0), state)


@router.callback_query(calls.IncludedRestoreItemsPagination.filter())
async def callback_included_restore_items_pagination(callback: CallbackQuery, callback_data: calls.IncludedRestoreItemsPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_restore_included_text(), reply_markup=templ.settings_restore_included_kb(page), callback=callback)

@router.callback_query(calls.IncludedCompleteDealsPagination.filter())
async def callback_included_complete_deals_pagination(callback: CallbackQuery, callback_data: calls.IncludedCompleteDealsPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.get('config')['auto']['confirm']['enabled']:
        await state.update_data(last_page=0)
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='complete'), state)
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_complete_included_text(), reply_markup=templ.settings_complete_included_kb(page), callback=callback)

@router.callback_query(calls.IncludedBumpItemsPagination.filter())
async def callback_included_bump_items_pagination(callback: CallbackQuery, callback_data: calls.IncludedBumpItemsPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.get('config')['auto']['bump']['enabled']:
        await state.update_data(last_page=0)
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_included_text(), reply_markup=templ.settings_bump_included_kb(page), callback=callback)

@router.callback_query(calls.ExcludedBumpItemsPagination.filter())
async def callback_excluded_bump_items_pagination(callback: CallbackQuery, callback_data: calls.ExcludedBumpItemsPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.get('config')['auto']['bump']['enabled']:
        await state.update_data(last_page=0)
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_excluded_text(), reply_markup=templ.settings_bump_excluded_kb(page), callback=callback)

@router.callback_query(calls.CustomCommandsPagination.filter())
async def callback_custom_commands_pagination(callback: CallbackQuery, callback_data: calls.CustomCommandsPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.get('config')['features']['commands']:
        page = 0
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_comms_text(), reply_markup=templ.settings_comms_kb(page), callback=callback)

@router.callback_query(calls.AutoDeliveriesPagination.filter())
async def callback_auto_deliveries_pagination(callback: CallbackQuery, callback_data: calls.AutoDeliveriesPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    if not cfg.get('config')['features']['deliveries']:
        page = 0
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_delivs_text(), reply_markup=templ.settings_delivs_kb(page), callback=callback)

@router.callback_query(calls.DelivGoodsPagination.filter())
async def callback_deliv_goods_pagination(callback: CallbackQuery, callback_data: calls.DelivGoodsPagination, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    index = data.get('auto_delivery_index')
    page = callback_data.page
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_goods_text(index), reply_markup=templ.settings_deliv_goods_kb(index, page), callback=callback)

@router.callback_query(calls.MessagesPagination.filter())
async def callback_messages_pagination(callback: CallbackQuery, callback_data: calls.MessagesPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_mess_text(), reply_markup=templ.settings_mess_kb(page), callback=callback)

@router.callback_query(calls.PluginsPagination.filter())
async def callback_plugins_pagination(callback: CallbackQuery, callback_data: calls.PluginsPagination, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    await state.update_data(last_page=page)
    await throw_float_message(state=state, message=callback.message, text=templ.plugins_text(), reply_markup=templ.plugins_kb(page), callback=callback)

@router.callback_query(calls.CustomCommandPage.filter())
async def callback_custom_command_page(callback: CallbackQuery, callback_data: calls.CustomCommandPage, state: FSMContext):
    await state.set_state(None)
    cmd_id = callback_data.cmd_id
    await state.update_data(custom_cmd_id=cmd_id)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_comm_page_text(cmd_id), reply_markup=templ.settings_comm_page_kb(cmd_id, last_page), callback=callback)


@router.callback_query(calls.CustomCommandToggleEvent.filter())
async def callback_custom_command_toggle_event(callback: CallbackQuery, callback_data: calls.CustomCommandToggleEvent, state: FSMContext):
    await state.set_state(None)
    items = cc_get_items(cfg.get('custom_commands'))
    item = cc_find_by_id(items, callback_data.cmd_id)
    if not item:
        return await callback.answer('Команда не найдена', show_alert=True)
    cc_toggle_event(item, callback_data.kind)
    cfg.set('custom_commands', cc_wrap_items(items))
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await throw_float_message(
        state=state,
        message=callback.message,
        text=templ.settings_comm_page_text(callback_data.cmd_id),
        reply_markup=templ.settings_comm_page_kb(callback_data.cmd_id, last_page),
        callback=callback,
    )

@router.callback_query(calls.AutoDeliveryPage.filter())
async def callback_auto_delivery_page(callback: CallbackQuery, callback_data: calls.AutoDeliveryPage, state: FSMContext):
    await state.set_state(None)
    index = callback_data.index
    await state.update_data(auto_delivery_index=index)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_text(index), reply_markup=templ.settings_deliv_page_kb(index, last_page), callback=callback)

@router.callback_query(calls.MessagePage.filter())
async def callback_message_page(callback: CallbackQuery, callback_data: calls.MessagePage, state: FSMContext):
    await state.set_state(None)
    message_id = callback_data.message_id
    await state.update_data(message_id=message_id)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_mess_page_text(message_id), reply_markup=templ.settings_mess_page_kb(message_id, last_page), callback=callback)

@router.callback_query(calls.PluginPage.filter())
async def callback_plugin_page(callback: CallbackQuery, callback_data: calls.PluginPage, state: FSMContext):
    await state.set_state(None)
    plugin_uuid = callback_data.uuid
    await state.update_data(plugin_uuid=plugin_uuid)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await throw_float_message(state=state, message=callback.message, text=templ.plugin_page_text(plugin_uuid), reply_markup=templ.plugin_page_kb(plugin_uuid, last_page), callback=callback)

@router.callback_query(F.data == 'enter_token')
async def callback_enter_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_token)
    config = cfg.get('config')
    golden_key = config['account']['token'] or '❌ Не задано'
    await throw_float_message(state=state, message=callback.message, text=templ.settings_auth_float_text(f'🔐 Введите новый <b>токен</b> вашего аккаунта:\n・ Текущее: <code>{golden_key}</code>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.callback_query(F.data == 'enter_user_agent')
async def callback_enter_user_agent(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_user_agent)
    config = cfg.get('config')
    user_agent = config['account']['user_agent'] or '❌ Не задано'
    await throw_float_message(state=state, message=callback.message, text=templ.settings_auth_float_text(f'🎩 Введите новый <b>User Agent</b> вашего браузера:\n・ Текущее: <code>{user_agent}</code>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.callback_query(F.data == 'enter_pl_proxy')
async def callback_enter_pl_proxy(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_pl_proxy)
    config = cfg.get('config')
    proxy = config['account']['proxy'] or '❌ Не задано'
    await throw_float_message(state=state, message=callback.message, text=templ.settings_conn_float_text(f'🌐 Введите <b>HTTP-прокси</b> для аккаунта Playerok (<code>ip:port</code> или <code>user:pass@ip:port</code>):\n・ Текущий: <code>{proxy}</code>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='proxy').pack()))

@router.callback_query(F.data == 'enter_tg_proxy')
async def callback_enter_tg_proxy(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_tg_proxy)
    config = cfg.get('config')
    proxy = config['bot']['proxy'] or '❌ Не задано'
    await throw_float_message(state=state, message=callback.message, text=templ.settings_conn_float_text(f'🌐 Введите <b>HTTP-прокси</b> для Telegram (<code>ip:port</code> или <code>user:pass@ip:port</code>):\n・ Текущий: <code>{proxy}</code>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='proxy').pack()))

@router.callback_query(F.data.in_({'enter_requests_timeout', 'enter_playerokapi_requests_timeout'}))
async def callback_enter_requests_timeout(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_requests_timeout)
    config = cfg.get('config')
    requests_timeout = config['account']['timeout'] or 'не задан'
    await throw_float_message(state=state, message=callback.message, text=templ.settings_auth_float_text(f'Введите новый <b>таймаут запросов</b> в секундах:\n・ Сейчас: <code>{requests_timeout}</code>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='auth').pack()))

@router.callback_query(F.data == 'enter_watermark_value')
async def callback_enter_watermark_value(callback: CallbackQuery, state: FSMContext):
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='watermark'), state)

@router.callback_query(F.data == 'watermark_pos_start')
async def callback_watermark_pos_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    config['features']['watermark']['position'] = 'start'
    cfg.set('config', config)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_watermark_text(), reply_markup=templ.settings_watermark_kb())

@router.callback_query(F.data == 'watermark_pos_end')
async def callback_watermark_pos_end(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    config['features']['watermark']['position'] = 'end'
    cfg.set('config', config)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_watermark_text(), reply_markup=templ.settings_watermark_kb())

@router.callback_query(F.data == 'enter_watermark_text')
async def callback_enter_watermark_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_watermark_value)
    config = cfg.get('config')
    watermark_value = config['features']['watermark']['text'] or '❌ Не задано'
    await throw_float_message(state=state, message=callback.message, text=templ.settings_watermark_float_text(f'✏️ Введите новый <b>текст водяного знака</b>:\n・ Текущий: <code>{watermark_value}</code>'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='watermark').pack()))

@router.callback_query(F.data == 'enter_new_included_restore_item_keyphrases')
async def callback_enter_new_included_restore_item_keyphrases(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.RestoreItemsStates.waiting_for_new_included_restore_item_keyphrases)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_restore_included_float_text(f'🔑 Введите <b>часть названия товара</b>, который нужно восстанавливать после продажи или истечения срока.\n\nЕсли нужно указать несколько вариантов — перечислите через запятую. Товар восстанавливается, если его название содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, Ключ Steam</code>'), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_new_included_complete_deal_keyphrases')
async def callback_enter_new_included_complete_deal_keyphrases(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.CompleteDealsStates.waiting_for_new_included_complete_deal_keyphrases)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_complete_included_float_text(f'🔑 Введите <b>часть названия товара</b>, сделки по которому нужно подтверждать автоматически.\n\nЕсли нужно несколько вариантов — перечислите через запятую. Сделка подтверждается, если название товара содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, Ключ Steam</code>'), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_auto_bump_items_interval')
async def callback_enter_auto_bump_items_interval(callback: CallbackQuery, state: FSMContext):
    if not cfg.get('config')['auto']['bump']['enabled']:
        await state.set_state(None)
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)
    try:
        await state.set_state(states.BumpItemsStates.waiting_for_bump_items_interval)
        config = cfg.get('config')
        interval = config['auto']['bump']['interval']
        await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_float_text(f'⏲️ Введите <b>интервал автоподнятия предметов</b>:\n・ Текущее: <code>{interval}</code> сек.'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='bump').pack()))
    except:
        import traceback
        traceback.print_exc()

@router.callback_query(F.data == 'enter_new_included_bump_item_keyphrases')
async def callback_enter_new_included_bump_item_keyphrases(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.BumpItemsStates.waiting_for_new_included_bump_item_keyphrases)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_bump_included_float_text(f'🔑 Введите <b>часть названия товара</b>, который нужно поднимать в топ.\n\nЕсли нужно несколько вариантов — перечислите через запятую. Товар поднимается, если его название содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, Minecraft аккаунт</code>'), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_new_excluded_bump_item_keyphrases')
async def callback_enter_new_excluded_bump_item_keyphrases(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.BumpItemsStates.waiting_for_new_excluded_bump_item_keyphrases)
    await throw_float_message(
        state=state, message=callback.message,
        text=templ.settings_new_bump_excluded_float_text(
            '🔑 Введите <b>фразу из названия</b> лота, который <b>не</b> нужно поднимать (режим «весь каталог»).\n\n'
            'Несколько вариантов через запятую. Сравнение без учёта регистра, буквы ё и е считаются одинаковыми.\n\n'
            'Например: <code>тест, черновик</code>',
        ),
        reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()),
    )

@router.callback_query(F.data == 'enter_custom_commands_page')
async def callback_enter_custom_commands_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.CustomCommandsStates.waiting_for_page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_comms_float_text(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_new_custom_command')
async def callback_enter_new_custom_command(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.CustomCommandsStates.waiting_for_new_custom_command)
    await throw_float_message(
        state=state,
        message=callback.message,
        text=templ.settings_new_comm_float_text(
            '⌨️ Введите <b>триггер команды</b> — слово с <code>!</code> в начале, как его напишет покупатель в чат.\n\n'
            'Пример: <code>!вызвать</code>\n\n'
            'После сохранения откроется карточка: там включите <b>события</b> и при необходимости текст ответа.',
        ),
        reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=last_page).pack()),
    )

@router.callback_query(F.data == 'enter_custom_command_answer')
async def callback_enter_custom_command_answer(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        cmd_id = data.get('custom_cmd_id')
        if not cmd_id:
            return await callback_custom_commands_pagination(callback, calls.CustomCommandsPagination(page=last_page), state)
        item = cc_find_by_id(cc_get_items(cfg.get('custom_commands')), cmd_id)
        if not item:
            return await callback_custom_commands_pagination(callback, calls.CustomCommandsPagination(page=last_page), state)
        await state.set_state(states.CustomCommandsStates.waiting_for_custom_command_answer)
        cur = '\n'.join(item.get('reply_lines') or []) or '❌ Не задано'
        await throw_float_message(
            state=state,
            message=callback.message,
            text=templ.settings_comm_page_float_text(
                f'💬 Текст ответа в чат для <code>{item["trigger"]}</code> '
                f'(отправляется после событий; несколько строк — несколько сообщений по смыслу одного блока):\n・ Сейчас: <blockquote>{cur}</blockquote>',
            ),
            reply_markup=templ.back_kb(calls.CustomCommandPage(cmd_id=cmd_id).pack()),
        )
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_comm_page_float_text(e), reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_auto_deliveries_page')
async def callback_enter_auto_deliveries_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.AutoDeliveriesStates.waiting_for_page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_delivs_float_text(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_new_auto_delivery_keyphrases')
async def callback_enter_new_auto_delivery_keyphrases(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.AutoDeliveriesStates.waiting_for_new_auto_delivery_keyphrases)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_float_text(f'🔑 Введите <b>часть названия товара</b>, при покупке которого бот должен автоматически отправить содержимое.\n\nЕсли нужно несколько вариантов — перечислите через запятую. Выдача срабатывает, если название товара в сделке содержит <b>хотя бы одну</b> из фраз.\n\nНапример: <code>Звёзды Telegram, 100 звёзд</code>'), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_auto_delivery_keyphrases')
async def callback_enter_auto_delivery_keyphrases(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        await state.set_state(states.AutoDeliveriesStates.waiting_for_auto_delivery_keyphrases)
        auto_deliveries = cfg.get('auto_deliveries')
        auto_delivery_message = '</code>, <code>'.join(auto_deliveries[index]['keyphrases']) or '❌ Не задано'
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text(f'🔑 Введите новые <b>ключевые фразы</b> для автовыдачи по этому товару (через запятую)\n・ Текущее: <code>{auto_delivery_message}</code>'), reply_markup=templ.back_kb(calls.AutoDeliveryPage(index=index).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_auto_delivery_message')
async def callback_enter_auto_delivery_message(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        await state.set_state(states.AutoDeliveriesStates.waiting_for_auto_delivery_message)
        auto_deliveries = cfg.get('auto_deliveries')
        auto_delivery_message = '\n'.join(auto_deliveries[index]['message']) or '❌ Не задано'
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text(f'💬 Введите новое <b>сообщение</b> после покупки\n・ Текущее: <blockquote>{auto_delivery_message}</blockquote>'), reply_markup=templ.back_kb(calls.AutoDeliveryPage(index=index).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_auto_delivery_goods_add')
async def callback_enter_auto_delivery_goods_add(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        await state.set_state(states.AutoDeliveriesStates.waiting_for_auto_delivery_goods_add)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_goods_float_text(f'📦 Отправьте <b>товары</b> для добавления в поштучную выдачу (1 строка = 1 товар, можно прислать .txt файл с товарами):'), reply_markup=templ.back_kb(calls.DelivGoodsPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_goods_float_text(e), reply_markup=templ.back_kb(calls.DelivGoodsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_messages_page')
async def callback_enter_messages_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.MessagesStates.waiting_for_page)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_mess_float_text(f'📃 Введите номер страницы для перехода:'), reply_markup=templ.back_kb(calls.MessagesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_ext_page')
async def callback_enter_plugins_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.ExtStates.waiting_for_page)
    await throw_float_message(state=state, message=callback.message, text=templ.plugin_page_float_text('📃 Введите номер страницы для перехода:'), reply_markup=templ.back_kb(calls.PluginsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'enter_message_text')
async def callback_enter_message_text(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        message_id = data.get('message_id')
        if not message_id:
            return await callback_messages_pagination(callback, calls.MessagesPagination(page=last_page), state)
        await state.set_state(states.MessagesStates.waiting_for_message_text)
        messages = cfg.get('messages')
        current = '\n'.join(messages[message_id]['text']) if messages[message_id]['text'] else '<i>пусто</i>'
        available = template_var_keys(message_id)
        vars_block = msg_vars_subset_text(available)
        body = (
            f'<b>Текущий текст:</b>\n<blockquote>{current}</blockquote>\n\n'
            f'<b>Переменные для этого шаблона:</b>\n{vars_block}\n\n'
            f'<i>Переменные вставляются прямо в текст: «Привет, $buyer!»\n'
            f'Разные строки — через перенос. Каждая строка — отдельная строка сообщения.</i>'
        )
        await throw_float_message(state=state, message=callback.message, text=templ.settings_mess_float_text(body), reply_markup=templ.back_kb(calls.MessagePage(message_id=message_id).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_mess_float_text(str(e)), reply_markup=templ.back_kb(calls.MessagePage(message_id=message_id if 'message_id' in dir() else '').pack()))

@router.callback_query(F.data == 'enter_logs_max_file_size')
async def callback_enter_logs_max_file_size(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.SettingsStates.waiting_for_logs_max_file_size)
    config = cfg.get('config')
    max_file_size = config['logs']['max_mb'] or '❌ Не указано'
    await throw_float_message(state=state, message=callback.message, text=templ.logs_float_text(f'📄 Введите новый <b>максимальный размер файла логов</b> (в мегабайтах):\n・ Текущее: <b>{max_file_size} MB</b>'), reply_markup=templ.back_kb(calls.MenuNavigation(to='logs').pack()))

@router.callback_query(F.data == 'switch_auto_restore_items_sold')
async def callback_switch_auto_restore_items_sold(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['auto']['restore']['sold'] = not config['auto']['restore']['sold']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='restore'), state)

@router.callback_query(F.data == 'switch_auto_restore_items_expired')
async def callback_switch_auto_restore_items_expired(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['auto']['restore']['expired'] = not config['auto']['restore']['expired']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='restore'), state)

@router.callback_query(F.data == 'switch_auto_restore_items_all')
async def callback_switch_auto_restore_items_all(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['auto']['restore']['all'] = not config['auto']['restore']['all']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='restore'), state)

@router.callback_query(F.data == 'switch_auto_restore_poll')
async def callback_switch_auto_restore_poll(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    r = config['auto']['restore']
    if 'poll' not in r or not isinstance(r.get('poll'), dict):
        r['poll'] = {'enabled': False, 'interval': 300}
    r['poll']['enabled'] = not r['poll'].get('enabled', False)
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='restore'), state)

@router.callback_query(F.data == 'enter_auto_restore_poll_interval')
async def callback_enter_auto_restore_poll_interval(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.RestoreItemsStates.waiting_for_restore_poll_interval)
    config = cfg.get('config')
    poll = (config['auto']['restore'].get('poll') or {})
    interval = poll.get('interval') or 300
    await throw_float_message(state=state, message=callback.message, text=templ.settings_restore_float_text(f'⏲️ Как часто проверять завершённые лоты на сайте (секунды).\n・ Минимум <code>30</code> с.\n・ Сейчас: <code>{interval}</code> с.'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='restore').pack()))

@router.callback_query(F.data == 'switch_auto_bump_items_enabled')
async def callback_switch_auto_bump_items_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['auto']['bump']['enabled'] = not config['auto']['bump']['enabled']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)

@router.callback_query(F.data == 'switch_auto_bump_items_all')
async def callback_switch_auto_bump_items_all(callback: CallbackQuery, state: FSMContext):
    if not cfg.get('config')['auto']['bump']['enabled']:
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)
    config = cfg.get('config')
    config['auto']['bump']['all'] = not config['auto']['bump']['all']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)

@router.callback_query(F.data == 'switch_read_chat_enabled')
async def callback_switch_read_chat_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['features']['read_chat'] = not config['features']['read_chat']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='other'), state)

@router.callback_query(F.data == 'switch_auto_complete_deals_enabled')
async def callback_switch_auto_complete_deals_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['auto']['confirm']['enabled'] = not config['auto']['confirm']['enabled']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='complete'), state)

@router.callback_query(F.data == 'switch_auto_complete_deals_all')
async def callback_switch_auto_complete_deals_all(callback: CallbackQuery, state: FSMContext):
    if not cfg.get('config')['auto']['confirm']['enabled']:
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='complete'), state)
    config = cfg.get('config')
    config['auto']['confirm']['all'] = not config['auto']['confirm']['all']
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='complete'), state)

@router.callback_query(F.data == 'switch_custom_commands_enabled')
async def callback_switch_custom_commands_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['features']['commands'] = not config['features']['commands']
    cfg.set('config', config)
    return await callback_custom_commands_pagination(callback, calls.CustomCommandsPagination(page=0), state)

@router.callback_query(F.data == 'switch_auto_deliveries_enabled')
async def callback_switch_auto_deliveries_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['features']['deliveries'] = not config['features']['deliveries']
    cfg.set('config', config)
    return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=0), state)

@router.callback_query(F.data == 'switch_debug_verbose')
async def callback_switch_debug_verbose(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    if 'debug' not in config:
        config['debug'] = {'verbose': False}
    config['debug']['verbose'] = not config['debug'].get('verbose', False)
    cfg.set('config', config)
    from lib.util import apply_verbose
    apply_verbose(config['debug']['verbose'])
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='other'), state)


@router.callback_query(F.data == 'switch_auto_delivery_piece')
async def callback_switch_auto_delivery_piece(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    index = data.get('auto_delivery_index', 0)
    auto_deliveries = cfg.get('auto_deliveries')
    auto_deliveries[index]['piece'] = not auto_deliveries[index].get('piece', False)
    cfg.set('auto_deliveries', auto_deliveries)
    return await callback_auto_delivery_page(callback, calls.AutoDeliveryPage(index=index), state)

@router.callback_query(F.data == 'switch_watermark_enabled')
async def callback_switch_watermark_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    config['features']['watermark']['enabled'] = not config['features']['watermark']['enabled']
    cfg.set('config', config)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_watermark_text(), reply_markup=templ.settings_watermark_kb())

@router.callback_query(F.data == 'switch_tg_logging_enabled')
async def callback_switch_tg_logging_enabled(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    alerts = config.setdefault('alerts', {})
    on = alerts.setdefault('on', {})
    alerts['enabled'] = not alerts.get('enabled', False)
    if not alerts['enabled']:
        _alerts_all_off(on)
    else:
        _alerts_all_on(on)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_new_user_message')
async def callback_switch_tg_logging_event_new_user_message(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'message', False)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_new_system_message')
async def callback_switch_tg_logging_event_new_system_message(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'system', False)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_new_deal')
async def callback_switch_tg_logging_event_new_deal(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'deal', False)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_new_review')
async def callback_switch_tg_logging_event_new_review(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'review', False)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_new_problem')
async def callback_switch_tg_logging_event_new_problem(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'problem', False)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_deal_status_changed')
async def callback_switch_tg_logging_event_deal_status_changed(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'deal_changed', False)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_restore_ok')
async def callback_switch_tg_logging_event_restore_ok(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'restore', True)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_bump_ok')
async def callback_switch_tg_logging_event_bump_ok(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'bump', True)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'switch_tg_logging_event_bot_startup')
async def callback_switch_tg_logging_event_bot_startup(callback: CallbackQuery, state: FSMContext):
    config = cfg.get('config')
    _toggle_alert_type(config, 'startup', True)
    cfg.set('config', config)
    _runtime_sync_config()
    return await callback_menu_navigation(callback, calls.MenuNavigation(to='logger'), state)

@router.callback_query(F.data == 'enter_new_template_id')
async def callback_enter_new_template_id(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.MessagesStates.waiting_for_new_template_name)
    await state.update_data(new_template_title=None)
    await throw_float_message(
        state=state, message=callback.message,
        text=templ.settings_mess_float_text(
            'Введите <b>название шаблона</b> — так оно будет показано в списке.\n\n'
            '<i>Например: «Приветствие» или «После оплаты».</i>'
        ),
        reply_markup=templ.back_kb(calls.MessagesPagination(page=0).pack()),
        callback=callback,
    )


@router.callback_query(F.data == 'confirm_delete_message')
async def callback_confirm_delete_message(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    message_id = data.get('message_id')
    last_page = data.get('last_page', 0)
    if not message_id:
        return await callback_messages_pagination(callback, calls.MessagesPagination(page=last_page), state)
    messages = cfg.get('messages')
    info = messages.get(message_id, {})
    label = (info.get('title') or '').strip() or message_id
    await throw_float_message(
        state=state, message=callback.message,
        text=templ.settings_mess_float_text(f'Удалить шаблон «{html.escape(label)}»? Отменить нельзя.'),
        reply_markup=templ.confirm_kb('delete_message', calls.MessagePage(message_id=message_id).pack()),
        callback=callback,
    )


@router.callback_query(F.data == 'delete_message')
async def callback_delete_message(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    message_id = data.get('message_id')
    last_page = data.get('last_page', 0)
    messages = cfg.get('messages')
    if message_id and message_id in messages:
        del messages[message_id]
        cfg.set('messages', messages)
        logger.info(f'[tg] шаблон удалён  id={message_id}')
    return await callback_messages_pagination(callback, calls.MessagesPagination(page=last_page), state)


@router.callback_query(F.data == 'switch_message_enabled')
async def callback_switch_message_enabled(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        message_id = data.get('message_id')
        if not message_id:
            return await callback_messages_pagination(callback, calls.MessagesPagination(page=last_page), state)
        messages = cfg.get('messages')
        messages[message_id]['enabled'] = not messages[message_id]['enabled']
        cfg.set('messages', messages)
        return await callback_message_page(callback, calls.MessagePage(message_id=message_id), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_mess_float_text(e), reply_markup=templ.back_kb(calls.MessagesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'toggle_ext_state')
async def callback_switch_plugin_enabled(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        plugin_uuid = data.get('plugin_uuid')
        mod = seek_graft(plugin_uuid)
        if not all((plugin_uuid, mod)):
            return await callback_plugins_pagination(callback, calls.PluginsPagination(page=last_page), state)
        if mod.enabled:
            await disarm_graft(plugin_uuid)
        else:
            await arm_graft(plugin_uuid)
        return await callback_plugin_page(callback, calls.PluginPage(uuid=plugin_uuid), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.plugin_page_float_text(e), reply_markup=templ.back_kb(calls.PluginsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'destroy')
async def callback_back(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    try:
        await callback.bot.answer_callback_query(callback.id, cache_time=0)
    except Exception:
        pass
    try:
        await callback.message.delete()
    except Exception:
        pass

@router.callback_query(calls.DeleteIncludedRestoreItem.filter())
async def callback_delete_included_restore_item(callback: CallbackQuery, callback_data: calls.DeleteIncludedRestoreItem, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await callback_included_restore_items_pagination(callback, calls.IncludedRestoreItemsPagination(page=last_page), state)
        auto_restore_items = cfg.get('auto_restore_items')
        auto_restore_items['included'].pop(index)
        cfg.set('auto_restore_items', auto_restore_items)
        return await callback_included_restore_items_pagination(callback, calls.IncludedRestoreItemsPagination(page=last_page), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_restore_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))

@router.callback_query(calls.DeleteIncludedCompleteDeal.filter())
async def callback_delete_included_complete_deal(callback: CallbackQuery, callback_data: calls.DeleteIncludedCompleteDeal, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await callback_included_complete_deals_pagination(callback, calls.IncludedCompleteDealsPagination(page=last_page), state)
        auto_complete_deals = cfg.get('auto_complete_deals')
        auto_complete_deals['included'].pop(index)
        cfg.set('auto_complete_deals', auto_complete_deals)
        return await callback_included_complete_deals_pagination(callback, calls.IncludedCompleteDealsPagination(page=last_page), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_complete_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))

@router.callback_query(calls.DeleteIncludedBumpItem.filter())
async def callback_delete_included_bump_item(callback: CallbackQuery, callback_data: calls.DeleteIncludedBumpItem, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await callback_included_bump_items_pagination(callback, calls.IncludedBumpItemsPagination(page=last_page), state)
        auto_bump_items = cfg.get('auto_bump_items')
        auto_bump_items['included'].pop(index)
        cfg.set('auto_bump_items', auto_bump_items)
        return await callback_included_bump_items_pagination(callback, calls.IncludedBumpItemsPagination(page=last_page), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_included_float_text(e), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))

@router.callback_query(calls.DeleteExcludedBumpItem.filter())
async def callback_delete_excluded_bump_item(callback: CallbackQuery, callback_data: calls.DeleteExcludedBumpItem, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = callback_data.index
        if index is None:
            return await callback_excluded_bump_items_pagination(callback, calls.ExcludedBumpItemsPagination(page=last_page), state)
        auto_bump_items = cfg.get('auto_bump_items')
        if 'excluded' not in auto_bump_items:
            auto_bump_items['excluded'] = []
        auto_bump_items['excluded'].pop(index)
        cfg.set('auto_bump_items', auto_bump_items)
        return await callback_excluded_bump_items_pagination(callback, calls.ExcludedBumpItemsPagination(page=last_page), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_excluded_float_text(e), reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()))

def _save_notification(message) -> dict:
    try:
        kb = message.reply_markup.model_dump() if message.reply_markup else None
    except Exception:
        kb = None
    return {'text': message.html_text or message.text or '', 'kb': kb}


@router.callback_query(F.data == 'back_to_notification')
async def callback_back_to_notification(callback: CallbackQuery, state: FSMContext):
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
        m = await edit_or_replace_message(callback.message, text, kb)
        if m is not None and getattr(m, 'message_id', None):
            await state.update_data(accent_message_id=m.message_id)
    except Exception:
        pass


@router.callback_query(calls.LogChatHistory.filter())
async def callback_log_chat_history(callback: CallbackQuery, callback_data: calls.LogChatHistory, state: FSMContext):
    page_req = callback_data.page
    await callback.answer()
    await state.set_state(None)
    chat_id = callback_data.chat_id
    from chamber.supervisor import active_supervisor, first_link_preview_url
    eng = active_supervisor()
    if not eng:
        await callback.message.answer('❌ Движок не запущен')
        return
    msgs: list = []
    from_cache = False
    try:
        lst = await asyncio.to_thread(eng.account.load_messages, chat_id, 25)
        msgs = lst.messages
    except Exception:
        msgs = eng.get_recent_chat_messages(chat_id)
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
    parts = templ.chat_history_chunks(msgs, eng.account.id)
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
    kb = templ.log_chat_history_kb(chat_id, page, total)
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


@router.callback_query(calls.RememberUsername.filter())
async def callback_remember_username(callback: CallbackQuery, callback_data: calls.RememberUsername, state: FSMContext):
    await state.set_state(None)
    username = callback_data.name
    do = callback_data.do
    await state.update_data(username=username, notification_orig=_save_notification(callback.message))
    if do == 'send_mess':
        logger.info(f'[tg] ручной ответ  →  {username}')
        await state.set_state(states.ActionsStates.waiting_for_message_content)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_notification')]
        ])
        await throw_float_message(
            state=state, message=callback.message,
            text=f'💬 Введите сообщение для <b>{username}</b>:\n<i>Поддерживается текст и изображения.</i>',
            reply_markup=back_kb, callback=callback,
        )
    elif do == 'tpl_list':
        messages = cfg.get('messages') or {}
        if not messages:
            await callback.answer('Нет сохранённых шаблонов', show_alert=True)
            return
        order = list(messages.keys())
        await state.update_data(tpl_pick_order=order)
        await callback.answer()
        await throw_float_message(
            state=state, message=callback.message,
            text=templ.log_templates_text(username, 0, order),
            reply_markup=templ.log_templates_kb(0, order),
            callback=callback,
        )


@router.callback_query(calls.LogTemplateMenu.filter())
async def callback_log_template_menu(callback: CallbackQuery, callback_data: calls.LogTemplateMenu, state: FSMContext):
    await state.set_state(None)
    page = callback_data.page
    data = await state.get_data()
    username = data.get('username')
    order = data.get('tpl_pick_order') or []
    if not username or not order:
        await callback.answer('Сессия устарела — откройте уведомление снова', show_alert=True)
        return
    await callback.answer()
    await throw_float_message(
        state=state, message=callback.message,
        text=templ.log_templates_text(username, page, order),
        reply_markup=templ.log_templates_kb(page, order),
        callback=callback,
    )


@router.callback_query(calls.LogTemplateSend.filter())
async def callback_log_template_send(callback: CallbackQuery, callback_data: calls.LogTemplateSend, state: FSMContext):
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
    from chamber.supervisor import active_supervisor
    eng = active_supervisor()
    text = eng.render_template_for_manual(mess_id, username)
    if not text or not str(text).strip():
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_notification')],
        ])
        await throw_float_message(
            state=state, message=callback.message,
            text='❌ В шаблоне нет текста',
            reply_markup=kb, callback=callback,
        )
        return
    try:
        chat = eng.find_chat_by_name(username)
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
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')],
            [InlineKeyboardButton(text='Закрыть', callback_data='destroy')],
        ])
        logger.info(f'[tg] шаблон из уведомления  →  {username}  id={mess_id}  «{preview[:60]}»')
        await throw_float_message(state=state, message=callback.message, text=result_text, reply_markup=kb, callback=callback)
    except Exception as e:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')],
        ])
        await throw_float_message(
            state=state, message=callback.message,
            text=f'❌ Ошибка отправки: {html.escape(str(e))}',
            reply_markup=kb, callback=callback,
        )


@router.callback_query(calls.RememberDealId.filter())
async def callback_remember_deal_id(callback: CallbackQuery, callback_data: calls.RememberDealId, state: FSMContext):
    await state.set_state(None)
    deal_id = callback_data.de_id
    do = callback_data.do
    await state.update_data(deal_id=deal_id, notification_orig=_save_notification(callback.message))
    if do == 'refund':
        await throw_float_message(
            state=state, message=callback.message,
            text=f'↩️ Подтвердите <b>возврат</b> по <a href="https://playerok.com/deal/{deal_id}">сделке</a>:',
            reply_markup=templ.confirm_kb(confirm_cb='refund_deal', cancel_cb='back_to_notification'),
            callback=callback,
        )
    elif do == 'complete':
        await throw_float_message(
            state=state, message=callback.message,
            text=f'✅ Подтвердите <b>выполнение</b> <a href="https://playerok.com/deal/{deal_id}">сделки</a>:',
            reply_markup=templ.confirm_kb(confirm_cb='complete_deal', cancel_cb='back_to_notification'),
            callback=callback,
        )

@router.callback_query(calls.SetNewDelivPiece.filter())
async def callback_set_new_deliv_piece(callback: CallbackQuery, callback_data: calls.SetNewDelivPiece, state: FSMContext):
    await state.set_state(None)
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    value = callback_data.val
    await state.update_data(new_auto_delivery_piece=value)
    if value:
        await state.set_state(states.AutoDeliveriesStates.waiting_for_new_auto_delivery_goods)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_float_text(f'📦 Отправьте <b>товары</b> для поштучной выдачи (1 строка = 1 товар, можно прислать .txt файл с товарами):'), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()), callback=callback)
    else:
        await state.set_state(states.AutoDeliveriesStates.waiting_for_new_auto_delivery_message)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_float_text(f'💬 Введите <b>сообщение автовыдачи</b>, которое будет отправляться после покупки товара:'), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()), callback=callback)

@router.callback_query(F.data == 'refund_deal')
async def callback_refund_deal(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    from chamber.supervisor import active_supervisor as get_runtime
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    eng = get_runtime()
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
        [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')],
        [InlineKeyboardButton(text='Закрыть', callback_data='destroy')],
    ])
    await throw_float_message(state=state, message=callback.message, text=text, reply_markup=kb, callback=callback)


@router.callback_query(F.data == 'complete_deal')
async def callback_complete_deal(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    from chamber.supervisor import active_supervisor as get_runtime
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    eng = get_runtime()
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
        [InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')],
        [InlineKeyboardButton(text='Закрыть', callback_data='destroy')],
    ])
    await throw_float_message(state=state, message=callback.message, text=text, reply_markup=kb, callback=callback)

@router.callback_query(F.data == 'bump_items')
async def callback_bump_items(callback: CallbackQuery, state: FSMContext):
    if not cfg.get('config')['auto']['bump']['enabled']:
        await state.set_state(None)
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)
    try:
        await state.set_state(None)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_float_text(f'🔝 Идёт <b>обновление позиций</b> — смотрите консоль…'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='bump').pack()))
        from chamber.supervisor import active_supervisor as get_runtime
        get_runtime().bump_items()
        await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_float_text(f'✅ <b>Позиции</b> обновлены'), reply_markup=templ.back_kb(calls.SettingsNavigation(to='bump').pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_float_text(e), reply_markup=templ.back_kb(calls.SettingsNavigation(to='bump').pack()))


@router.callback_query(F.data == 'clean_fp_proxy')
async def callback_clean_fp_proxy(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    config['account']['proxy'] = ''
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='proxy'), state)

@router.callback_query(F.data == 'clean_tg_proxy')
async def callback_clean_tg_proxy(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    config['bot']['proxy'] = ''
    cfg.set('config', config)
    return await callback_settings_navigation(callback, calls.SettingsNavigation(to='proxy'), state)

@router.callback_query(F.data == 'send_new_included_restore_items_keyphrases_file')
async def callback_send_new_included_restore_items_keyphrases_file(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.RestoreItemsStates.waiting_for_new_included_restore_items_keyphrases_file)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_restore_included_float_text('📄 Отправьте <b>.txt файл</b> со списком товаров для <b>автовосстановления</b>.\n\nКаждая строка — отдельный товар. Если для одного товара нужно несколько фраз — перечислите через запятую.\n\nПример содержимого файла:\n<code>Звёзды Telegram, 100 звёзд\nКлюч Steam, steam key\nMinecraft аккаунт</code>'), reply_markup=templ.back_kb(calls.IncludedRestoreItemsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'send_new_included_complete_deals_keyphrases_file')
async def callback_send_new_included_complete_deals_keyphrases_file(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.CompleteDealsStates.waiting_for_new_included_complete_deals_keyphrases_file)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_complete_included_float_text('📄 Отправьте <b>.txt файл</b> со списком товаров, сделки по которым нужно подтверждать автоматически.\n\nКаждая строка — отдельный товар. Если для одного товара нужно несколько фраз — перечислите через запятую.\n\nПример содержимого файла:\n<code>Звёзды Telegram, 100 звёзд\nКлюч Steam, steam key</code>'), reply_markup=templ.back_kb(calls.IncludedCompleteDealsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'send_new_included_bump_items_keyphrases_file')
async def callback_send_new_included_bump_items_keyphrases_file(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.BumpItemsStates.waiting_for_new_included_bump_items_keyphrases_file)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_new_bump_included_float_text('📄 Отправьте <b>.txt файл</b> со списком товаров, которые нужно поднимать в топ.\n\nКаждая строка — отдельный товар. Если для одного товара нужно несколько фраз — перечислите через запятую.\n\nПример содержимого файла:\n<code>Звёзды Telegram, 100 звёзд\nMinecraft аккаунт\nКлюч Steam</code>'), reply_markup=templ.back_kb(calls.IncludedBumpItemsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'send_new_excluded_bump_items_keyphrases_file')
async def callback_send_new_excluded_bump_items_keyphrases_file(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_page = data.get('last_page', 0)
    await state.set_state(states.BumpItemsStates.waiting_for_new_excluded_bump_items_keyphrases_file)
    await throw_float_message(
        state=state, message=callback.message,
        text=templ.settings_new_bump_excluded_float_text(
            '📄 <b>.txt</b> с фразами исключений (по одной строке на набор фраз через запятую, как для белого списка).',
        ),
        reply_markup=templ.back_kb(calls.ExcludedBumpItemsPagination(page=last_page).pack()),
    )

@router.callback_query(F.data == 'confirm_deleting_custom_command')
async def callback_confirm_deleting_custom_command(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        cmd_id = data.get('custom_cmd_id')
        item = cc_find_by_id(cc_get_items(cfg.get('custom_commands')), cmd_id) if cmd_id else None
        if not item:
            return await callback_custom_commands_pagination(callback, calls.CustomCommandsPagination(page=last_page), state)
        trig = item['trigger']
        await throw_float_message(
            state=state,
            message=callback.message,
            text=templ.settings_comm_page_float_text(f'🗑 Удалить команду <code>{trig}</code>?'),
            reply_markup=templ.confirm_kb(confirm_cb='delete_custom_command', cancel_cb=calls.CustomCommandPage(cmd_id=cmd_id).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        lp = data.get('last_page', 0)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_comm_page_float_text(e), reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=lp).pack()))

@router.callback_query(F.data == 'delete_custom_command')
async def callback_delete_custom_command(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        cmd_id = data.get('custom_cmd_id')
        if not cmd_id:
            return await callback_custom_commands_pagination(callback, calls.CustomCommandsPagination(page=last_page), state)
        items = cc_get_items(cfg.get('custom_commands'))
        trig = (cc_find_by_id(items, cmd_id) or {}).get('trigger', cmd_id)
        if not cc_delete_item(items, cmd_id):
            return await callback_custom_commands_pagination(callback, calls.CustomCommandsPagination(page=last_page), state)
        cfg.set('custom_commands', cc_wrap_items(items))
        await throw_float_message(
            state=state,
            message=callback.message,
            text=templ.settings_comm_page_float_text(f'✅ Команда <code>{trig}</code> удалена'),
            reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=last_page).pack()),
        )
    except Exception as e:
        data = await state.get_data()
        lp = data.get('last_page', 0)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_comm_page_float_text(e), reply_markup=templ.back_kb(calls.CustomCommandsPagination(page=lp).pack()))

@router.callback_query(F.data == 'add_new_auto_delivery')
async def callback_add_new_auto_delivery(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        keyphrases = data.get('new_auto_delivery_keyphrases')
        piece = data.get('new_auto_delivery_piece')
        message = data.get('new_auto_delivery_message')
        goods = data.get('new_auto_delivery_goods')
        if not keyphrases or piece is None or (piece is True and (not goods)) or (piece is False and (not message)):
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        auto_deliveries = cfg.get('auto_deliveries')
        auto_deliveries.append({'piece': piece, 'keyphrases': keyphrases, 'message': message.splitlines() if message and (not piece) else '', 'goods': goods if goods and piece else []})
        cfg.set('auto_deliveries', auto_deliveries)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_float_text(f'✅ <b>Авто-выдача</b> была успешно добавлена'), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_new_deliv_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'confirm_deleting_auto_delivery')
async def callback_confirm_deleting_auto_delivery(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text('🗑️ Подтвердите <b>удаление автовыдачи</b>:'), reply_markup=templ.confirm_kb(confirm_cb='delete_auto_delivery', cancel_cb=calls.AutoDeliveryPage(index=index).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'delete_auto_delivery')
async def callback_delete_auto_delivery(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        index = data.get('auto_delivery_index')
        if index is None:
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        auto_deliveries = cfg.get('auto_deliveries')
        del auto_deliveries[index]
        cfg.set('auto_deliveries', auto_deliveries)
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text('✅ <b>Авто-выдача</b> удалена'), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_page_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(calls.DeleteDelivGood.filter())
async def callback_delete_deliv_good(callback: CallbackQuery, callback_data: calls.DeleteDelivGood, state: FSMContext):
    try:
        await state.set_state(None)
        index = callback_data.index
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        deliv_index = data.get('auto_delivery_index')
        if deliv_index is None:
            return await callback_auto_deliveries_pagination(callback, calls.AutoDeliveriesPagination(page=last_page), state)
        auto_deliveries = cfg.get('auto_deliveries')
        auto_deliveries[deliv_index]['goods'].pop(index)
        cfg.set('auto_deliveries', auto_deliveries)
        return await callback_deliv_goods_pagination(callback, calls.DelivGoodsPagination(page=last_page), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.settings_deliv_goods_float_text(e), reply_markup=templ.back_kb(calls.AutoDeliveriesPagination(page=last_page).pack()))

@router.callback_query(F.data == 'rearm_graft')
async def callback_reload_ext(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(None)
        data = await state.get_data()
        last_page = data.get('last_page', 0)
        uuid = data.get('plugin_uuid')
        if not uuid:
            return await callback_plugins_pagination(callback, calls.PluginsPagination(page=last_page), state)
        from keel.graft import rearm_graft
        await rearm_graft(uuid)
        return await callback_plugin_page(callback, calls.PluginPage(uuid=uuid), state)
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.plugin_page_float_text(e), reply_markup=templ.back_kb(calls.PluginsPagination(page=last_page).pack()))

@router.callback_query(F.data == 'select_logs_file_lines')
async def callback_select_logs_file_lines(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await throw_float_message(state=state, message=callback.message, text=templ.logs_float_text('Выберите объём файла:'), reply_markup=templ.logs_file_lines_kb())

@router.callback_query(calls.SendLogsFile.filter())
async def callback_send_logs_file(callback: CallbackQuery, callback_data: calls.SendLogsFile, state: FSMContext):
    await state.set_state(None)
    lines = callback_data.lines
    src_dir = Path(__file__).resolve().parents[1]
    logs_file = os.path.join(src_dir, 'logs', 'bot.log')
    txt_file = os.path.join(src_dir, 'logs', 'Лог работы.txt')
    try:
        if not os.path.exists(logs_file):
            return await throw_float_message(state=state, message=callback.message, text=templ.logs_float_text('❌ Файл логов не найден'), reply_markup=templ.logs_kb(), callback=callback)
        if lines > 0:
            with open(logs_file, 'r', encoding='utf-8') as f:
                last_lines = deque(f, lines)
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.writelines(last_lines)
        else:
            shutil.copy(logs_file, txt_file)
        await callback.message.answer_document(document=FSInputFile(txt_file), reply_markup=templ.destroy_kb())
        try:
            await callback.bot.answer_callback_query(callback.id, cache_time=0)
        except Exception:
            pass
        await throw_float_message(state=state, message=callback.message, text=templ.logs_text(), reply_markup=templ.logs_kb())
    except Exception as e:
        await throw_float_message(state=state, message=callback.message, text=templ.logs_float_text(f'❌ Ошибка: {e}'), reply_markup=templ.logs_kb(), callback=callback)
    finally:
        try:
            os.remove(txt_file)
        except Exception:
            pass

@router.callback_query(F.data == 'confirm_bump_items')
async def callback_confirm_bump_items(callback: CallbackQuery, state: FSMContext):
    if not cfg.get('config')['auto']['bump']['enabled']:
        await state.set_state(None)
        return await callback_settings_navigation(callback, calls.SettingsNavigation(to='bump'), state)
    await state.set_state(None)
    await throw_float_message(state=state, message=callback.message, text=templ.settings_bump_float_text('Подтвердите <b>обновление позиций</b> ↓'), reply_markup=templ.confirm_kb('bump_items', calls.SettingsNavigation(to='bump').pack()))


