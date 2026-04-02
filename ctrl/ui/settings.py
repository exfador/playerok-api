import html
import math
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from lib.cfg import AppConf as cfg
from lib.custom_commands import cc_get_items, cc_find_by_id, cc_item_summary, KNOWN_EVENTS
from lib.util import proxy_http_latency_country
from .. import keys as calls

_ON = '🟢'
_OFF = '⚫'
_BELL_ON = '🔔'
_BELL_OFF = '🔕'


def _sw(v: bool) -> str:
    return f'{_ON} вкл' if v else f'{_OFF} выкл'


def _e(v: bool) -> str:
    return _ON if v else _OFF


def _tog(name: str, enabled: bool) -> str:
    return f'{_ON}  {name}' if enabled else f'{_OFF}  {name}'


def _bell(on: bool) -> str:
    return _BELL_ON if on else _BELL_OFF


def _log_btn(on: bool, label: str) -> str:
    return f'{_bell(on)} {label}'


def _alert_effective(master_on: bool, ev: dict, key: str, default: bool = False) -> bool:
    if not master_on:
        return False
    return bool(ev.get(key, default))


def _mm_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton(text='⬅️ Главное меню', callback_data=calls.MenuNavigation(to='default').pack())


def _nav(page: int, total: int, pag_cls, back_cb: str) -> list:
    rows = []
    if total > 1:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=pag_cls(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data='noop'),
            InlineKeyboardButton(text=f'{page + 1} / {total}', callback_data='noop'),
            InlineKeyboardButton(text='▶', callback_data=pag_cls(page=page + 1).pack()) if page < total - 1 else InlineKeyboardButton(text='·', callback_data='noop'),
        ])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)])
    return rows


_MSG_NAMES: dict[str, str] = {
    'first_message': 'Приветствие',
    'cmd_error': 'Ошибка команды',
    'cmd_commands': 'Список команд',
    'cmd_seller': 'Вызов продавца',
    'new_deal': 'Новая сделка',
    'deal_pending': 'Ожидание отправки',
    'deal_sent': 'Товар отправлен',
    'deal_confirmed': 'Сделка завершена',
    'deal_refunded': 'Возврат',
    'new_review': 'Новый отзыв',
}


def settings_text() -> str:
    return (
        '⚙️ <b>Настройки бота</b>\n\n'
        'Автовыдача, автоподнятие, шаблоны, прокси, токен и остальное — выберите раздел ниже.'
    )


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📊 Статистика', callback_data=calls.MenuNavigation(to='stats').pack())],
        [
            InlineKeyboardButton(text='📦 Автовыдача', callback_data=calls.AutoDeliveriesPagination(page=0).pack()),
            InlineKeyboardButton(text='✅ Автоподтверждение', callback_data=calls.SettingsNavigation(to='complete').pack()),
        ],
        [
            InlineKeyboardButton(text='🚀 Автоподнятие', callback_data=calls.SettingsNavigation(to='bump').pack()),
            InlineKeyboardButton(text='♻️ Автовосстановление', callback_data=calls.SettingsNavigation(to='restore').pack()),
        ],
        [
            InlineKeyboardButton(text='💬 Шаблоны', callback_data=calls.MessagesPagination(page=0).pack()),
            InlineKeyboardButton(text='⌨️ Команды', callback_data=calls.CustomCommandsPagination(page=0).pack()),
        ],
        [
            InlineKeyboardButton(text='🔑 Авторизация', callback_data=calls.SettingsNavigation(to='auth').pack()),
            InlineKeyboardButton(text='🌐 Прокси', callback_data=calls.SettingsNavigation(to='proxy').pack()),
        ],
        [
            InlineKeyboardButton(text='©️ Ватермарк', callback_data=calls.SettingsNavigation(to='watermark').pack()),
            InlineKeyboardButton(text='⚙️ Прочее', callback_data=calls.SettingsNavigation(to='other').pack()),
        ],
        [_mm_btn()],
    ])


def _mask(val: str | None) -> str:
    if not val:
        return '<i>не задан</i>'
    return f'<code>{val[:6]}···</code>'


def _mask_btn(val: str | None) -> str:
    if not val:
        return 'не задан'
    return f'{val[:6]}···'


def settings_auth_text() -> str:
    config = cfg.get('config')
    token = _mask(config['account']['token'])
    timeout = config['account']['timeout'] or '—'
    return (
        '🔑 <b>Вход на Playerok</b>\n\n'
        f'• JWT-токен аккаунта: {token}\n'
        f'• Таймаут одного запроса к сайту: <code>{timeout} с</code>\n\n'
        'Токен берётся в личном кабинете Playerok; без него бот не сможет работать с аккаунтом.'
    )


def settings_auth_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    token = _mask_btn(config['account']['token'])
    timeout = config['account']['timeout'] or '—'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'🔑  Токен: {token}', callback_data='enter_token')],
        [InlineKeyboardButton(text=f'⏱  Таймаут: {timeout} с', callback_data='enter_playerokapi_requests_timeout')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())],
    ])


def settings_proxy_text() -> str:
    config = cfg.get('config')
    pl_proxy = f'<code>{config["account"]["proxy"]}</code>' if config['account']['proxy'] else '<i>без прокси</i>'
    tg_proxy = f'<code>{config["bot"]["proxy"]}</code>' if config['bot']['proxy'] else '<i>без прокси</i>'
    lines = [
        '🌐 <b>Прокси</b>',
        '',
        'Формат: <code>ip:port</code> или <code>user:pass@ip:port</code>. '
        'Для Playerok можно указать и SOCKS5: <code>socks5h://user:pass@host:port</code> — без второго раза логина после порта.',
        '',
        f'<b>Запросы к Playerok</b>\n{pl_proxy}',
    ]
    if config['account']['proxy']:
        ms, country = proxy_http_latency_country(config['account']['proxy'])
        if ms is not None:
            geo = f' · {html.escape(country)}' if country else ''
            lines.append(f'   ⚡ <b>{ms} мс</b>{geo}')
        else:
            lines.append('   <i>Задержку и страну выхода проверить не удалось (прокси недоступен или ошибка проверки).</i>')
    lines.append(f'<b>Бот Telegram</b>\n{tg_proxy}')
    if config['bot']['proxy']:
        ms, country = proxy_http_latency_country(config['bot']['proxy'])
        if ms is not None:
            geo = f' · {html.escape(country)}' if country else ''
            lines.append(f'   ⚡ <b>{ms} мс</b>{geo}')
        else:
            lines.append('   <i>Задержку и страну выхода проверить не удалось.</i>')
    return '\n'.join(lines)


def settings_proxy_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    pl_proxy = config['account']['proxy'] or 'не задан'
    tg_proxy = config['bot']['proxy'] or 'не задан'
    rows = [
        [InlineKeyboardButton(text=f'🌐  Playerok: {pl_proxy}', callback_data='enter_pl_proxy')],
        [InlineKeyboardButton(text=f'✈️  Telegram: {tg_proxy}', callback_data='enter_tg_proxy')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())],
    ]
    if config['account']['proxy']:
        rows[0].append(InlineKeyboardButton(text='✕ Сбросить', callback_data='clean_pl_proxy'))
    if config['bot']['proxy']:
        rows[1].append(InlineKeyboardButton(text='✕ Сбросить', callback_data='clean_tg_proxy'))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_auth_float_text(placeholder: str) -> str:
    return f'🔑 <b>Авторизация</b>\n\n{placeholder}'


def settings_conn_text() -> str:
    return settings_proxy_text()


def settings_conn_kb() -> InlineKeyboardMarkup:
    return settings_proxy_kb()


def settings_proxy_float_text(placeholder: str) -> str:
    return f'🌐 <b>Прокси</b>\n\n{placeholder}'


def settings_conn_float_text(placeholder: str) -> str:
    return settings_proxy_float_text(placeholder)


def settings_bump_text() -> str:
    config = cfg.get('config')
    enabled = config['auto']['bump']['enabled']
    if not enabled:
        return (
            '🔼 <b>Автоподнятие лотов</b>\n\n'
            'Сейчас выключено. Включите переключатель ниже — бот будет периодически поднимать объявления в выдаче.'
        )
    all_mode = config['auto']['bump']['all']
    interval = config['auto']['bump']['interval'] or '—'
    d = cfg.get('auto_bump_items')
    n_exc = len(d.get('excluded') or [])
    scope = 'весь каталог' if all_mode else f"по списку ({len(d['included'])} фраз)"
    return (
        '🔼 <b>Автоподнятие лотов</b>\n\n'
        f'• Работа: {_sw(enabled)}\n'
        f'• Какие лоты: <b>{scope}</b>\n'
        f'• Как часто: каждые <code>{interval} с</code>\n\n'
        '<b>Как это устроено</b>\n'
        '• Поднимаются только лоты <b>в продаже</b> (APPROVED), нужен <b>PREMIUM</b>.\n'
        '• <b>Весь каталог</b> — все активные PREMIUM, <b>кроме</b> попавших в «Исключения».\n'
        '• <b>По списку</b> — только если название содержит фразу из «В списке» (буквы ё/е не различаются).\n'
        f'• Сейчас исключений: <code>{n_exc}</code>.'
    )


def settings_bump_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    enabled = config['auto']['bump']['enabled']
    rows = [[InlineKeyboardButton(text=_tog('Автоподнятие', enabled), callback_data='switch_auto_bump_items_enabled')]]
    if not enabled:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    all_mode = config['auto']['bump']['all']
    interval = config['auto']['bump']['interval'] or '—'
    d = cfg.get('auto_bump_items')
    n_ex = len(d.get('excluded') or [])
    scope_btn = 'Охват: весь каталог' if all_mode else 'Охват: по списку'
    rows.append([InlineKeyboardButton(text=f'↔️  {scope_btn}', callback_data='switch_auto_bump_items_all')])
    rows.append([InlineKeyboardButton(text=f'⏱  Интервал: {interval} с', callback_data='enter_auto_bump_items_interval')])
    rows.append([InlineKeyboardButton(text='🔼 Поднять сейчас', callback_data='confirm_bump_items')])
    rows.append([
        InlineKeyboardButton(text=f'📋 В списке ({len(d["included"])})', callback_data='nav_bump_included'),
        InlineKeyboardButton(text=f'🚫 Исключения ({n_ex})', callback_data='nav_bump_excluded'),
    ])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_bump_float_text(placeholder: str) -> str:
    return f'🔼 <b>Автоподнятие</b>\n\n{placeholder}'


def settings_bump_included_text() -> str:
    items = cfg.get('auto_bump_items').get('included')
    return (
        '📋 <b>Белый список (режим «по списку»)</b>\n\n'
        'Если в названии лота есть хотя бы одна из фраз — лот поднимается. Регистр не важен, <b>ё</b> и <b>е</b> считаются одинаково.\n\n'
        f'Сейчас записей: <code>{len(items)}</code>'
    )


def settings_bump_included_kb(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.get('auto_bump_items').get('included')
    return _list_kb(items, page, calls.IncludedBumpItemsPagination, lambda i: calls.DeleteIncludedBumpItem(index=i).pack(), 'enter_new_included_bump_item_keyphrases', 'send_new_included_bump_items_keyphrases_file', calls.SettingsNavigation(to='bump').pack())


def settings_bump_included_float_text(placeholder: str) -> str:
    return f'📋 <b>Белый список</b>\n\n{placeholder}'


def settings_new_bump_included_float_text(placeholder: str) -> str:
    return f'➕ <b>Новая фраза</b>\n\n{placeholder}'


def settings_bump_excluded_text() -> str:
    items = cfg.get('auto_bump_items').get('excluded') or []
    return (
        '🚫 <b>Исключения из поднятия</b>\n\n'
        'При режиме <b>«весь каталог»</b> такие лоты <b>не</b> поднимаются (даже если PREMIUM).\n'
        'При режиме «по списку» этот список не используется.\n\n'
        f'Сейчас записей: <code>{len(items)}</code>'
    )


def settings_bump_excluded_kb(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.get('auto_bump_items').get('excluded') or []
    return _list_kb(
        items, page, calls.ExcludedBumpItemsPagination,
        lambda i: calls.DeleteExcludedBumpItem(index=i).pack(),
        'enter_new_excluded_bump_item_keyphrases', 'send_new_excluded_bump_items_keyphrases_file',
        calls.SettingsNavigation(to='bump').pack(),
    )


def settings_bump_excluded_float_text(placeholder: str) -> str:
    return f'🚫 <b>Исключения</b>\n\n{placeholder}'


def settings_new_bump_excluded_float_text(placeholder: str) -> str:
    return f'➕ <b>Исключение</b>\n\n{placeholder}'


def settings_complete_text() -> str:
    config = cfg.get('config')
    enabled = config['auto']['confirm']['enabled']
    if not enabled:
        return (
            '✅ <b>Автоподтверждение сделок</b>\n\n'
            'Выключено. После включения бот сможет сам закрывать сделки (отправка товара подтверждена) по вашим правилам.'
        )
    all_mode = config['auto']['confirm']['all']
    d = cfg.get('auto_complete_deals')
    scope = 'любые сделки' if all_mode else f"по списку ({len(d['included'])} фраз)"
    return (
        '✅ <b>Автоподтверждение сделок</b>\n\n'
        f'• Работа: {_sw(enabled)}\n'
        f'• Охват: <b>{scope}</b>\n\n'
        'Бот сам нажимает «товар отправлен» / завершает этап без вашего участия.\n'
        '• <b>Любые сделки</b> — по всем подходящим товарам.\n'
        '• <b>По списку</b> — только если название товара содержит фразу из списка.'
    )


def settings_complete_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    enabled = config['auto']['confirm']['enabled']
    rows = [[InlineKeyboardButton(text=_tog('Автоподтверждение', enabled), callback_data='switch_auto_complete_deals_enabled')]]
    if not enabled:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    all_mode = config['auto']['confirm']['all']
    d = cfg.get('auto_complete_deals')
    scope_btn = 'Охват: любые сделки' if all_mode else 'Охват: по списку'
    rows.append([InlineKeyboardButton(text=f'↔️  {scope_btn}', callback_data='switch_auto_complete_deals_all')])
    rows.append([InlineKeyboardButton(text=f"📋  Список ({len(d['included'])})", callback_data=calls.IncludedCompleteDealsPagination(page=0).pack())])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_complete_float_text(placeholder: str) -> str:
    return f'✅ <b>Автоподтверждение</b>\n\n{placeholder}'


def settings_complete_included_text() -> str:
    items = cfg.get('auto_complete_deals').get('included')
    return (
        '📋 <b>Фразы для автоподтверждения</b>\n\n'
        'Если название товара в сделке содержит одну из фраз — бот может автоматически подтвердить отправку (при режиме «по списку»).\n\n'
        f'Сейчас фраз: <code>{len(items)}</code>'
    )


def settings_complete_included_kb(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.get('auto_complete_deals').get('included')
    return _list_kb(items, page, calls.IncludedCompleteDealsPagination, lambda i: calls.DeleteIncludedCompleteDeal(index=i).pack(), 'enter_new_included_complete_deal_keyphrases', 'send_new_included_complete_deals_keyphrases_file', calls.SettingsNavigation(to='complete').pack())


def settings_complete_included_float_text(placeholder: str) -> str:
    return f'📋 <b>Список фраз</b>\n\n{placeholder}'


def settings_new_complete_included_float_text(placeholder: str) -> str:
    return f'➕ <b>Новая фраза</b>\n\n{placeholder}'


def settings_restore_text() -> str:
    config = cfg.get('config')
    sold = config['auto']['restore']['sold']
    expired = config['auto']['restore']['expired']
    scope = 'весь каталог' if config['auto']['restore']['all'] else 'по списку'
    poll = config['auto']['restore'].get('poll') or {}
    poll_on = poll.get('enabled', False)
    poll_iv = poll.get('interval') or 300
    return (
        '♻️ <b>Автовосстановление лотов после продажи / срока</b>\n\n'
        f'• После продажи: {_sw(sold)}\n'
        f'• После истечения срока: {_sw(expired)}\n'
        f'• Какие лоты трогать: <b>{scope}</b>\n'
        f'• Доп. проверка «завершённых» на сайте: {_sw(poll_on)} (каждые <code>{poll_iv}</code> с)\n\n'
        '<b>Зачем это</b>\n'
        'Обычно бот сразу выставляет лот снова. Если на сайте задержка или сбой, объявление может остаться в архиве.\n\n'
        '<b>Проверка завершённых</b> — периодически бот снова запрашивает список проданных/истёкших лотов и при необходимости '
        'восстанавливает их (учитываются только включённые выше типы и охват).'
    )


def settings_restore_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    sold = config['auto']['restore']['sold']
    expired = config['auto']['restore']['expired']
    scope = 'весь каталог' if config['auto']['restore']['all'] else 'по списку'
    poll = config['auto']['restore'].get('poll') or {}
    poll_on = poll.get('enabled', False)
    poll_iv = poll.get('interval') or 300
    d = cfg.get('auto_restore_items')
    rows: list[list] = [
        [InlineKeyboardButton(text=_tog('Продажа', sold), callback_data='switch_auto_restore_items_sold')],
        [InlineKeyboardButton(text=_tog('Истечение', expired), callback_data='switch_auto_restore_items_expired')],
        [InlineKeyboardButton(text=f'↔️ Охват: {scope}', callback_data='switch_auto_restore_items_all')],
        [InlineKeyboardButton(text=_tog('Проверка завершённых', poll_on), callback_data='switch_auto_restore_poll')],
    ]
    if poll_on:
        rows.append([InlineKeyboardButton(text=f'⏱ Как часто: {poll_iv} с', callback_data='enter_auto_restore_poll_interval')])
    rows.extend([
        [InlineKeyboardButton(text=f"📋  Список ({len(d['included'])})", callback_data='nav_restore_included')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_restore_float_text(placeholder: str) -> str:
    return f'♻️ <b>Автовосстановление лотов</b>\n\n{placeholder}'


def settings_restore_included_text() -> str:
    items = cfg.get('auto_restore_items').get('included')
    return (
        '📋 <b>Фразы для автовосстановления</b>\n\n'
        'При охвате «по списку» восстанавливаются только лоты, в названии которых есть хотя бы одна из этих фраз.\n\n'
        f'Сейчас фраз: <code>{len(items)}</code>'
    )


def settings_restore_included_kb(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.get('auto_restore_items').get('included')
    return _list_kb(items, page, calls.IncludedRestoreItemsPagination, lambda i: calls.DeleteIncludedRestoreItem(index=i).pack(), 'enter_new_included_restore_item_keyphrases', 'send_new_included_restore_items_keyphrases_file', calls.SettingsNavigation(to='restore').pack())


def settings_restore_included_float_text(placeholder: str) -> str:
    return f'📋 <b>Список фраз</b>\n\n{placeholder}'


def settings_new_restore_included_float_text(placeholder: str) -> str:
    return f'➕ <b>Новая фраза</b>\n\n{placeholder}'


def settings_logger_text(chat_id: int | None = None) -> str:
    config = cfg.get('config')
    enabled = config['alerts']['enabled']
    ev = config['alerts']['on'] or {}
    cid = html.escape(str(chat_id)) if chat_id is not None else '—'

    def _row(eff: bool, label: str) -> str:
        return f'{_log_btn(eff, label)}'

    return (
        '🔔 <b>Уведомления в Telegram</b>\n\n'
        'Выберите, о чём присылать сообщения в этот чат. Общий переключатель должен быть включён, иначе остальные пункты не работают.\n\n'
        f'<b>ID этого чата:</b> <code>{cid}</code>\n\n'
        '<b>События</b>\n'
        f'{_row(enabled, "Все уведомления")}\n'
        f'{_row(_alert_effective(enabled, ev, "message", False), "Новое сообщение")}\n'
        f'{_row(_alert_effective(enabled, ev, "system", False), "Системный чат Playerok")}\n'
        f'{_row(_alert_effective(enabled, ev, "deal", False), "Новая сделка")}\n'
        f'{_row(_alert_effective(enabled, ev, "deal_changed", False), "Статус сделки изменился")}\n'
        f'{_row(_alert_effective(enabled, ev, "restore", True), "Автовосстановление лота")}\n'
        f'{_row(_alert_effective(enabled, ev, "bump", True), "Автоподнятие лота")}\n'
        f'{_row(_alert_effective(enabled, ev, "review", False), "Оставлен отзыв")}\n'
        f'{_row(_alert_effective(enabled, ev, "problem", False), "Спор по сделке")}'
    )


def settings_logger_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    enabled = config['alerts']['enabled']
    ev = config['alerts']['on'] or {}

    rows = [
        [InlineKeyboardButton(text=_log_btn(enabled, 'Все уведомления'), callback_data='switch_tg_logging_enabled')],
        [
            InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'message', False), 'Новое сообщение'), callback_data='switch_tg_logging_event_new_user_message'),
            InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'system', False), 'Системный чат'), callback_data='switch_tg_logging_event_new_system_message'),
        ],
        [
            InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'deal', False), 'Новая сделка'), callback_data='switch_tg_logging_event_new_deal'),
            InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'deal_changed', False), 'Статус сделки'), callback_data='switch_tg_logging_event_deal_status_changed'),
        ],
        [
            InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'restore', True), 'Автовосстановление лота'), callback_data='switch_tg_logging_event_restore_ok'),
            InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'bump', True), 'Автоподнятие лота'), callback_data='switch_tg_logging_event_bump_ok'),
        ],
        [InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'review', False), 'Оставлен отзыв'), callback_data='switch_tg_logging_event_new_review')],
        [InlineKeyboardButton(text=_log_btn(_alert_effective(enabled, ev, 'problem', False), 'Спор по сделке'), callback_data='switch_tg_logging_event_new_problem')],
        [_mm_btn()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_logger_float_text(placeholder: str) -> str:
    return f'🔔 <b>Уведомления</b>\n\n{placeholder}'


def settings_other_text() -> str:
    config = cfg.get('config')
    read_ch = config['features']['read_chat']
    verbose = config.get('debug', {}).get('verbose', False)
    return (
        '🔧 <b>Прочее</b>\n\n'
        f'💬 <b>Помечать чат прочитанным</b> — {_sw(read_ch)}\n'
        'Перед ответом покупателю бот отмечает переписку на Playerok как прочитанную.\n\n'
        f'🔍 <b>Подробный лог (debug)</b> — {_sw(verbose)}\n'
        'В консоль и файл пишутся запросы, ответы API и ошибки. Включайте при отладке.'
    )


def settings_other_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    read_ch = config['features']['read_chat']
    verbose = config.get('debug', {}).get('verbose', False)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_tog('💬  Прочитано', read_ch), callback_data='switch_read_chat_enabled')],
        [InlineKeyboardButton(text=_tog('🔍  Подробный лог', verbose), callback_data='switch_debug_verbose')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())],
    ])


def settings_watermark_text() -> str:
    config = cfg.get('config')
    wm_en = config['features']['watermark']['enabled']
    wm_raw = (config['features']['watermark']['text'] or '').strip()
    wm_val = f'<code>{html.escape(wm_raw)}</code>' if wm_raw else '<i>строка не задана</i>'
    wm_pos = config['features']['watermark']['position']
    pos_s = 'в начале сообщения' if wm_pos == 'start' else 'в конце сообщения'
    return (
        '📎 <b>Подпись к ответам (ватермарк)</b>\n\n'
        f'• Включено: {_sw(wm_en)}\n'
        f'• Текст: <code>{wm_val}</code>\n'
        f'• Позиция: {pos_s}'
    )


def settings_watermark_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    wm_en = config['features']['watermark']['enabled']
    wm_pos = config['features']['watermark']['position']
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_tog('✏️  Подпись', wm_en), callback_data='switch_watermark_enabled')],
        [InlineKeyboardButton(text='📝  Редактировать строку', callback_data='enter_watermark_text')],
        [
            InlineKeyboardButton(text=f'{"🔘 " if wm_pos == "start" else ""}До текста', callback_data='watermark_pos_start'),
            InlineKeyboardButton(text=f'{"🔘 " if wm_pos == "end" else ""}После текста', callback_data='watermark_pos_end'),
        ],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())],
    ])


def settings_watermark_float_text(placeholder: str) -> str:
    return f'📎 <b>Ватермарк</b>\n\n{placeholder}'


def settings_other_float_text(placeholder: str) -> str:
    return f'🔧 <b>Прочие настройки</b>\n\n{placeholder}'


_MSG_VAR_DESC: dict[str, str] = {
    '$buyer': 'ник покупателя в чате',
    '$seller': 'ваш ник на Playerok',
    '$product': 'название товара в сделке',
    '$price': 'цена',
    '$deal_id': 'номер сделки',
    '$rating': 'оценка в отзыве (1–5)',
    '$error': 'текст ошибки команды',
    '$time': 'время (ЧЧ:ММ)',
    '$date': 'дата (ДД.ММ.ГГГГ)',
    '$datetime': 'дата и время',
}


def msg_vars_full_text() -> str:
    return '\n'.join(f'{k}  — {v}' for k, v in _MSG_VAR_DESC.items())


def msg_vars_subset_text(keys: list[str]) -> str:
    lines: list[str] = []
    for k in keys:
        desc = _MSG_VAR_DESC.get(k)
        if desc:
            lines.append(f'{k}  — {desc}')
    return '\n'.join(lines)


_KNOWN_EVENTS: dict[str, str] = {
    'first_message': 'первое сообщение покупателя',
    'cmd_error':     'ошибка при выполнении команды',
    'cmd_commands':  'команда !команды',
    'cmd_seller':    'команда !вызвать',
    'new_deal':      'новая сделка',
    'deal_pending':  'сделка ожидает отправки',
    'deal_sent':     'продавец подтвердил сделку',
    'deal_confirmed':'покупатель закрыл сделку',
    'deal_refunded': 'возврат сделки',
    'new_review':    'новый отзыв',
}


def _tpl_label(mess_id: str, info: dict) -> str:
    return (info.get('title') or '').strip() or _MSG_NAMES.get(mess_id, mess_id)


def settings_mess_text() -> str:
    messages = cfg.get('messages')
    enabled_count = sum(1 for m in messages.values() if m.get('enabled'))
    if not messages:
        hint = 'Шаблонов пока нет. Нажмите «Добавить шаблон»: сначала пришлите короткое название, затем текст.'
    else:
        hint = (
            'Бот подставляет эти тексты в чат с покупателем при сделках и командах. '
            'В тексте можно писать переменные, например: <code>Привет, $buyer!</code>'
        )
    return (
        '💬 <b>Шаблоны сообщений</b>\n\n'
        f'Шаблонов: <code>{len(messages)}</code>, из них включено: <code>{enabled_count}</code>.\n\n'
        f'{hint}\n\n'
        f'<b>Справка по переменным</b>\n{msg_vars_full_text()}'
    )


def settings_mess_kb(page: int = 0) -> InlineKeyboardMarkup:
    messages = cfg.get('messages')
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(max(len(messages), 1) / per_page))
    page = max(0, min(page, total_pages - 1))
    for mess_id, info in list(messages.items())[page * per_page:(page + 1) * per_page]:
        mark = _ON if info['enabled'] else _OFF
        name = _tpl_label(mess_id, info)
        rows.append([InlineKeyboardButton(text=f'{mark}  {name}', callback_data=calls.MessagePage(message_id=mess_id).pack())])
    rows.append([InlineKeyboardButton(text='➕  Добавить шаблон', callback_data='enter_new_template_id')])
    rows += _nav(page, total_pages, calls.MessagesPagination, calls.SettingsNavigation(to='index').pack())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_mess_float_text(placeholder: str) -> str:
    return f'💬 <b>Шаблоны</b>\n\n{placeholder}'


_TMPL_VARS: dict[str, list[str]] = {
    'first_message': ['$buyer', '$time', '$date', '$seller'],
    'cmd_error':     ['$error', '$time'],
    'cmd_commands':  ['$seller', '$time'],
    'cmd_seller':    ['$buyer', '$time'],
    'new_deal':      ['$buyer', '$product', '$price', '$deal_id', '$time', '$date', '$seller'],
    'deal_pending':  ['$buyer', '$product', '$price', '$deal_id', '$time', '$seller'],
    'deal_sent':     ['$buyer', '$product', '$price', '$deal_id', '$time', '$seller'],
    'deal_confirmed':['$buyer', '$product', '$price', '$deal_id', '$time', '$seller'],
    'deal_refunded': ['$buyer', '$product', '$price', '$deal_id', '$time', '$seller'],
    'new_review':    ['$buyer', '$product', '$price', '$deal_id', '$rating', '$time', '$seller'],
}


def template_var_keys(message_id: str) -> list[str]:
    if message_id.startswith('t_'):
        return list(_MSG_VAR_DESC.keys())
    return _TMPL_VARS.get(message_id, list(_MSG_VAR_DESC.keys()))


def settings_mess_page_text(message_id: str) -> str:
    messages = cfg.get('messages')
    info = messages[message_id]
    name = _tpl_label(message_id, info)
    status = _sw(info['enabled'])
    if info['text']:
        raw = '\n'.join(info['text'])
        body = f'<blockquote>{html.escape(raw)}</blockquote>'
    else:
        body = '<i>Текста ещё нет — нажмите «Редактировать текст».</i>'
    available = template_var_keys(message_id)
    vars_block = msg_vars_subset_text(available)
    return (
        f'💬 <b>{html.escape(name)}</b>\n\n'
        f'<b>Отправка:</b> {status}\n\n'
        f'<b>Текст для покупателя</b>\n{body}\n\n'
        f'<b>Переменные в этом шаблоне</b>\n{vars_block}'
    )


def settings_mess_page_kb(message_id: str, page: int = 0) -> InlineKeyboardMarkup:
    messages = cfg.get('messages')
    enabled = messages[message_id]['enabled']
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_tog('Включён', enabled), callback_data='switch_message_enabled')],
        [InlineKeyboardButton(text='📝  Редактировать текст', callback_data='enter_message_text')],
        [InlineKeyboardButton(text='🗑  Удалить шаблон', callback_data='confirm_delete_message')],
        [InlineKeyboardButton(text='⬅️ К шаблонам', callback_data=calls.MessagesPagination(page=page).pack())],
    ])


def settings_mess_page_float_text(placeholder: str) -> str:
    return f'💬 <b>Шаблон</b>\n\n{placeholder}'


def settings_comms_text() -> str:
    items = cc_get_items(cfg.get('custom_commands'))
    commands = cfg.get('config')['features']['commands']
    head = (
        '⌨️ <b>Команды в чате сделки</b>\n\n'
        'Покупатель пишет в чат фразу (например <code>!вызвать</code>) — бот реагирует: может уведомить вас в Telegram '
        'и/или ответить в чат. Настройка — в карточке каждой команды.\n\n'
    )
    if not commands:
        return head + 'Сейчас команды отключены. Включите переключатель «Команды» строкой выше.'
    return head + f'Создано команд: <code>{len(items)}</code>.'


def settings_comms_kb(page: int = 0) -> InlineKeyboardMarkup:
    config = cfg.get('config')
    commands = config['features']['commands']
    rows = [[InlineKeyboardButton(text=_tog('⌨️  Команды', commands), callback_data='switch_custom_commands_enabled')]]
    if not commands:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    items = cc_get_items(cfg.get('custom_commands'))
    per_page = 7
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = max(0, min(page, total_pages - 1))
    for it in items[page * per_page:(page + 1) * per_page]:
        summ = cc_item_summary(it, 28)
        t = it['trigger'][:22] + '…' if len(it['trigger']) > 22 else it['trigger']
        rows.append([InlineKeyboardButton(text=f'{t}  ·  {summ}', callback_data=calls.CustomCommandPage(cmd_id=it['id']).pack())])
    rows.append([InlineKeyboardButton(text='➕  Добавить команду', callback_data='enter_new_custom_command')])
    rows.append([InlineKeyboardButton(text='❓  Как это работает', callback_data=calls.InstructionNavigation(to='commands').pack())])
    rows += _nav(page, total_pages, calls.CustomCommandsPagination, calls.SettingsNavigation(to='index').pack())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_comms_float_text(placeholder: str) -> str:
    return f'⌨️ <b>Команды в чате</b>\n\n{placeholder}'


def settings_new_comm_float_text(placeholder: str) -> str:
    return f'➕ <b>Новая команда</b>\n\n{placeholder}'


def settings_comm_page_text(cmd_id: str) -> str:
    items = cc_get_items(cfg.get('custom_commands'))
    item = cc_find_by_id(items, cmd_id)
    if not item:
        return '⌨️ Команда не найдена. Вернитесь к списку и выберите снова.'
    trig = html.escape(item['trigger'])
    evs = item.get('events') or []
    ev_lines = [f'• {KNOWN_EVENTS[e]}' for e in evs if e in KNOWN_EVENTS]
    ev_block = '\n'.join(ev_lines) if ev_lines else '<i>Ничего не выбрано — отметьте строки кнопками ниже.</i>'
    rl = item.get('reply_lines') or []
    if rl:
        reply_body = '<blockquote>' + html.escape('\n'.join(rl)) + '</blockquote>'
    else:
        reply_body = '<i>Ответ в чат не задан — можно только уведомление в Telegram.</i>'
    return (
        f'⌨️ <b>Команда</b> <code>{trig}</code>\n\n'
        f'<b>Что делать при срабатывании</b>\n{ev_block}\n\n'
        f'<b>Текст ответа покупателю в чат Playerok</b>\n{reply_body}'
    )


def settings_comm_page_kb(cmd_id: str, page: int = 0) -> InlineKeyboardMarkup:
    items = cc_get_items(cfg.get('custom_commands'))
    item = cc_find_by_id(items, cmd_id)
    if not item:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ К списку', callback_data=calls.CustomCommandsPagination(page=page).pack())]])
    rows: list[list] = []
    for ev_id, label in KNOWN_EVENTS.items():
        on = ev_id in (item.get('events') or [])
        lab = label if len(label) <= 30 else label[:28] + '…'
        rows.append([InlineKeyboardButton(
            text=f'{_e(on)}  {lab}',
            callback_data=calls.CustomCommandToggleEvent(cmd_id=cmd_id, kind=ev_id).pack(),
        )])
    rows.append([InlineKeyboardButton(text='📝  Текст ответа', callback_data='enter_custom_command_answer')])
    rows.append([InlineKeyboardButton(text='🗑  Удалить команду', callback_data='confirm_deleting_custom_command')])
    rows.append([InlineKeyboardButton(text='⬅️ К списку', callback_data=calls.CustomCommandsPagination(page=page).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_comm_page_float_text(placeholder: str) -> str:
    return f'⌨️ <b>Команда</b>\n\n{placeholder}'


def settings_delivs_text() -> str:
    auto_deliveries = cfg.get('auto_deliveries')
    if not cfg.get('config')['features']['deliveries']:
        return (
            '📦 <b>Автовыдача товара</b>\n\n'
            'Функция выключена. Включите переключатель «Автовыдача» вверху экрана.'
        )
    return (
        '📦 <b>Автовыдача товара</b>\n\n'
        'Когда покупатель оплатил сделку и название товара содержит вашу фразу, бот сам отправит в чат ключ, текст или файлы.\n\n'
        f'Настроено правил: <code>{len(auto_deliveries)}</code>'
    )


def settings_delivs_kb(page: int = 0) -> InlineKeyboardMarkup:
    config = cfg.get('config')
    delivs = config['features']['deliveries']
    rows = [[InlineKeyboardButton(text=_tog('📦  Автовыдача', delivs), callback_data='switch_auto_deliveries_enabled')]]
    if not delivs:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.SettingsNavigation(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    auto_deliveries: list = cfg.get('auto_deliveries')
    per_page = 7
    total_pages = max(1, math.ceil(len(auto_deliveries) / per_page))
    page = max(0, min(page, total_pages - 1))
    for deliv in auto_deliveries[page * per_page:(page + 1) * per_page]:
        piece = deliv.get('piece')
        kp = ', '.join(deliv.get('keyphrases', [])) or 'нет фраз'
        kp_short = kp[:28] + '…' if len(kp) > 28 else kp
        count = f"{len(deliv.get('goods', []))} шт." if piece else 'текст'
        rows.append([InlineKeyboardButton(text=f'{kp_short}  →  {count}', callback_data=calls.AutoDeliveryPage(index=auto_deliveries.index(deliv)).pack())])
    rows.append([InlineKeyboardButton(text='➕  Добавить выдачу', callback_data='enter_new_auto_delivery_keyphrases')])
    rows += _nav(page, total_pages, calls.AutoDeliveriesPagination, calls.SettingsNavigation(to='index').pack())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_deliv_float_text(placeholder: str) -> str:
    return f'📦 <b>Автовыдача</b>\n\n{placeholder}'


def settings_new_deliv_float_text(placeholder: str) -> str:
    return f'➕ <b>Новая автовыдача</b>\n\n{placeholder}'


def settings_new_deliv_piece_kb(last_page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📁  Пакет файлов', callback_data=calls.SetNewDelivPiece(val=True).pack())],
        [InlineKeyboardButton(text='💬  Один текст', callback_data=calls.SetNewDelivPiece(val=False).pack())],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.AutoDeliveriesPagination(page=last_page).pack())],
    ])


def settings_deliv_page_text(index: int) -> str:
    auto_deliveries = cfg.get('auto_deliveries')
    deliv = auto_deliveries[index]
    piece = deliv.get('piece')
    kp_joined = ', '.join(deliv.get('keyphrases', []))
    keyphrases = html.escape(kp_joined) if kp_joined else '<i>фразы не заданы</i>'
    if piece:
        content = f'<b>Что выдаётся:</b> файлы из списка (<code>{len(deliv.get("goods", []))} шт.</code>)'
    else:
        raw_msg = '\n'.join(deliv.get('message', []))
        if raw_msg:
            content = f'<b>Текст покупателю</b>\n<blockquote>{html.escape(raw_msg)}</blockquote>'
        else:
            content = '<b>Текст покупателю</b>\n<i>Пока пусто — задайте в кнопке «Текст».</i>'
    return (
        f'📦 <b>Правило автовыдачи</b>\n\n'
        f'<b>Тип:</b> {"несколько файлов (пакет)" if piece else "одно текстовое сообщение"}\n'
        f'<b>Фразы в названии товара:</b> <code>{keyphrases}</code>\n\n'
        f'{content}'
    )


def settings_deliv_page_kb(index: int, page: int = 0) -> InlineKeyboardMarkup:
    auto_deliveries = cfg.get('auto_deliveries')
    deliv = auto_deliveries[index]
    piece = deliv.get('piece')
    kp = ', '.join(deliv.get('keyphrases', [])) or 'нет'
    n_goods = len(deliv.get('goods', []))
    message = '\n'.join(deliv.get('message', [])) or ''
    msg_btn = message[:22] + '…' if len(message) > 22 else message
    content_btn = (
        InlineKeyboardButton(text=f'📁  Файлы ({n_goods})', callback_data=calls.DelivGoodsPagination(page=0).pack())
        if piece else
        InlineKeyboardButton(text=f'💬  Текст: {msg_btn}', callback_data='enter_auto_delivery_message')
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'Тип: {"пакет" if piece else "текст"}', callback_data='switch_auto_delivery_piece')],
        [InlineKeyboardButton(text=f'🔑  Фразы: {kp[:32]}', callback_data='enter_auto_delivery_keyphrases')],
        [content_btn],
        [InlineKeyboardButton(text='🗑  Удалить выдачу', callback_data='confirm_deleting_auto_delivery')],
        [InlineKeyboardButton(text='⬅️ К выдачам', callback_data=calls.AutoDeliveriesPagination(page=page).pack())],
    ])


def settings_deliv_page_float_text(placeholder: str) -> str:
    return f'📦 <b>Автовыдача</b>\n\n{placeholder}'


def settings_deliv_goods_text(index: int = 0) -> str:
    goods = cfg.get('auto_deliveries')[index].get('goods', [])
    return (
        f'📁 <b>Файлы для выдачи</b>\n\n'
        f'Каждая строка — отдельный товар (ключ, ссылка и т.д.). Всего: <code>{len(goods)}</code>.'
    )


def settings_deliv_goods_kb(index: int = 0, page: int = 0) -> InlineKeyboardMarkup:
    goods = cfg.get('auto_deliveries')[index].get('goods', [])
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(len(goods) / per_page))
    page = max(0, min(page, total_pages - 1))
    for good in goods[page * per_page:(page + 1) * per_page]:
        rows.append([
            InlineKeyboardButton(text=str(good), callback_data='noop'),
            InlineKeyboardButton(text='✕', callback_data=calls.DeleteDelivGood(index=goods.index(good)).pack()),
        ])
    if total_pages > 1:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=calls.DelivGoodsPagination(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data='noop'),
            InlineKeyboardButton(text=f'{page + 1} / {total_pages}', callback_data='enter_auto_delivery_goods_page'),
            InlineKeyboardButton(text='▶', callback_data=calls.DelivGoodsPagination(page=page + 1).pack()) if page < total_pages - 1 else InlineKeyboardButton(text='·', callback_data='noop'),
        ])
    rows.append([InlineKeyboardButton(text='➕  Добавить файл', callback_data='enter_auto_delivery_goods_add')])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.AutoDeliveryPage(index=index).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_deliv_goods_float_text(placeholder: str) -> str:
    return f'📁 <b>Файлы пакета</b>\n\n{placeholder}'


def settings_new_deliv_goods_float_text(placeholder: str) -> str:
    return f'➕ <b>Добавить файл</b>\n\n{placeholder}'


def _list_kb(items: list, page: int, pagination_cls, delete_cb_fn, add_cb: str, bulk_add_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = max(0, min(page, total_pages - 1))
    for kp in items[page * per_page:(page + 1) * per_page]:
        label = ', '.join(kp) if kp else '(пусто)'
        rows.append([
            InlineKeyboardButton(text=label, callback_data='noop'),
            InlineKeyboardButton(text='✕', callback_data=delete_cb_fn(items.index(kp))),
        ])
    if total_pages > 1 and pagination_cls is not None:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=pagination_cls(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data='noop'),
            InlineKeyboardButton(text=f'{page + 1} / {total_pages}', callback_data='noop'),
            InlineKeyboardButton(text='▶', callback_data=pagination_cls(page=page + 1).pack()) if page < total_pages - 1 else InlineKeyboardButton(text='·', callback_data='noop'),
        ])
    rows.append([
        InlineKeyboardButton(text='➕  Одна фраза', callback_data=add_cb),
        InlineKeyboardButton(text='➕  Из .txt', callback_data=bulk_add_cb),
    ])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
