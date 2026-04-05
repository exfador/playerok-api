import html
import math
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from lib.cfg import AppConf as cfg
from lib.custom_commands import cc_get_items, cc_find_by_id, cc_item_summary, KNOWN_EVENTS
from lib.util import proxy_http_latency_country
from .. import keys as calls
from ..cb import CX

_ON = '✅'
_OFF = '❌'
_BELL_ON = '🔔'
_BELL_OFF = '🔕'


def fac_011(v: bool) -> str:
    return f'{_ON} вкл' if v else f'{_OFF} выкл'


def fac_004(v: bool) -> str:
    return _ON if v else _OFF


def fac_012(name: str, enabled: bool) -> str:
    return f'{_ON}  {name}' if enabled else f'{_OFF}  {name}'


def fac_002(on: bool) -> str:
    return _BELL_ON if on else _BELL_OFF


def fac_006(on: bool, label: str) -> str:
    return f'{fac_002(on)} {label}'


def fac_001(master_on: bool, ev: dict, key: str, default: bool = False) -> bool:
    if not master_on:
        return False
    return bool(ev.get(key, default))


def fac_009() -> InlineKeyboardButton:
    return InlineKeyboardButton(text='⬅️ Главное меню', callback_data=calls.PduRootNav(to='default').pack())


def fac_010(page: int, total: int, pag_cls, back_cb: str) -> list:
    rows = []
    if total > 1:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=pag_cls(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data=CX.noop),
            InlineKeyboardButton(text=f'{page + 1} / {total}', callback_data=CX.noop),
            InlineKeyboardButton(text='▶', callback_data=pag_cls(page=page + 1).pack()) if page < total - 1 else InlineKeyboardButton(text='·', callback_data=CX.noop),
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


def fac_116() -> str:
    return (
        '⚙️ <b>Настройки бота</b>\n\n'
        '• <b>Авто-выдача</b> — автоматическая выдача товара после оплаты\n'
        '• <b>Авто-подтверждение</b> — авто-закрытие сделок\n'
        '• <b>Авто-поднятие</b> — поднятие объявлений по расписанию\n'
        '• <b>Авто-восстановление</b> — возврат истёкших объявлений\n'
        '• <b>Шаблоны</b> — быстрые ответы в чатах\n'
        '• <b>Команды</b> — кастомные триггер-команды\n\n'
        'Выберите раздел ниже.'
    )


def fac_080() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📦 Авто-выдача', callback_data=calls.PduFulfillGrid(page=0).pack()),
            InlineKeyboardButton(text='✅ Авто-подтверждение', callback_data=calls.PduPrefsScope(to='complete').pack()),
        ],
        [
            InlineKeyboardButton(text='🚀 Авто-поднятие', callback_data=calls.PduPrefsScope(to='bump').pack()),
            InlineKeyboardButton(text='♻️ Авто-восстановление', callback_data=calls.PduPrefsScope(to='restore').pack()),
        ],
        [
            InlineKeyboardButton(text='💬 Шаблоны', callback_data=calls.PduTplGrid(page=0).pack()),
            InlineKeyboardButton(text='⌨️ Команды', callback_data=calls.PduCmdGrid(page=0).pack()),
        ],
        [
            InlineKeyboardButton(text='🌐 Прокси', callback_data=calls.PduPrefsScope(to='proxy').pack()),
            InlineKeyboardButton(text='⚙️ Прочее', callback_data=calls.PduPrefsScope(to='other').pack()),
        ],
        [InlineKeyboardButton(text='🔑 Авторизация', callback_data=calls.PduPrefsScope(to='auth').pack())],
        [InlineKeyboardButton(text='©️ Ватермарк', callback_data=calls.PduPrefsScope(to='watermark').pack())],
        [fac_009()],
    ])


def fac_007(val: str | None) -> str:
    if not val:
        return '<i>не задан</i>'
    return f'<code>{val[:6]}···</code>'


def fac_008(val: str | None) -> str:
    if not val:
        return 'не задан'
    return f'{val[:6]}···'


def fac_052() -> str:
    config = cfg.read('config')
    token = fac_007(config['account']['token'])
    timeout = config['account']['timeout'] or '—'
    return (
        '🔑 <b>Вход на Playerok</b>\n\n'
        f'• JWT-токен аккаунта: {token}\n'
        f'• Таймаут одного запроса к сайту: <code>{timeout} с</code>\n\n'
        'Токен берётся в личном кабинете Playerok; без него бот не сможет работать с аккаунтом.'
    )


def fac_051() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    token = fac_008(config['account']['token'])
    timeout = config['account']['timeout'] or '—'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'🔑  Токен: {token}', callback_data=CX.pl_tk)],
        [InlineKeyboardButton(text=f'⏱  Таймаут: {timeout} с', callback_data=CX.pl_to)],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())],
    ])


def fac_102() -> str:
    config = cfg.read('config')
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


def fac_101() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    pl_proxy = config['account']['proxy'] or 'не задан'
    tg_proxy = config['bot']['proxy'] or 'не задан'
    rows = [
        [InlineKeyboardButton(text=f'🌐  Playerok: {pl_proxy}', callback_data=CX.pl_px)],
        [InlineKeyboardButton(text=f'✈️  Telegram: {tg_proxy}', callback_data=CX.tg_px)],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())],
    ]
    if config['account']['proxy']:
        rows[0].append(InlineKeyboardButton(text='✕ Сбросить', callback_data=CX.px0))
    if config['bot']['proxy']:
        rows[1].append(InlineKeyboardButton(text='✕ Сбросить', callback_data=CX.tx0))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_050(placeholder: str) -> str:
    return f'🔑 <b>Авторизация</b>\n\n{placeholder}'


def fac_070() -> str:
    return fac_102()


def fac_069() -> InlineKeyboardMarkup:
    return fac_101()


def fac_100(placeholder: str) -> str:
    return f'🌐 <b>Прокси</b>\n\n{placeholder}'


def fac_068(placeholder: str) -> str:
    return fac_100(placeholder)


def fac_061() -> str:
    config = cfg.read('config')
    enabled = config['auto']['bump']['enabled']
    if not enabled:
        return (
            '🔼 <b>Авто-поднятие лотов</b>\n\n'
            'Сейчас выключено. Включите переключатель ниже — бот будет периодически поднимать объявления в выдаче.'
        )
    all_mode = config['auto']['bump']['all']
    interval = config['auto']['bump']['interval'] or '—'
    d = cfg.read('auto_bump_items')
    n_exc = len(d.get('excluded') or [])
    scope = 'весь каталог' if all_mode else f"по списку ({len(d['included'])} фраз)"
    return (
        '🔼 <b>Авто-поднятие лотов</b>\n\n'
        f'• Работа: {fac_011(enabled)}\n'
        f'• Какие лоты: <b>{scope}</b>\n'
        f'• Как часто: каждые <code>{interval} с</code>\n\n'
        '<b>Как это устроено</b>\n'
        '• Поднимаются только лоты <b>в продаже</b> (APPROVED), нужен <b>PREMIUM</b>.\n'
        '• <b>Весь каталог</b> — все активные PREMIUM, <b>кроме</b> попавших в «Исключения».\n'
        '• <b>По списку</b> — только если название содержит фразу из «В списке» (буквы ё/е не различаются).\n'
        f'• Сейчас исключений: <code>{n_exc}</code>.'
    )


def fac_060() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    enabled = config['auto']['bump']['enabled']
    rows = [[InlineKeyboardButton(text=fac_012('Авто-поднятие', enabled), callback_data=CX.bm_en)]]
    if not enabled:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    all_mode = config['auto']['bump']['all']
    interval = config['auto']['bump']['interval'] or '—'
    d = cfg.read('auto_bump_items')
    n_ex = len(d.get('excluded') or [])
    scope_btn = 'Охват: весь каталог' if all_mode else 'Охват: по списку'
    rows.append([InlineKeyboardButton(text=f'↔️  {scope_btn}', callback_data=CX.bm_all)])
    rows.append([InlineKeyboardButton(text=f'⏱  Интервал: {interval} с', callback_data=CX.bm_iv)])
    rows.append([InlineKeyboardButton(text='🔼 Поднять сейчас', callback_data=CX.bm_go)])
    rows.append([
        InlineKeyboardButton(text=f'📋 В списке ({len(d["included"])})', callback_data=CX.nv_bi),
        InlineKeyboardButton(text=f'🚫 Исключения ({n_ex})', callback_data=CX.nv_bx),
    ])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_056(placeholder: str) -> str:
    return f'🔼 <b>Авто-поднятие</b>\n\n{placeholder}'


def fac_059() -> str:
    items = cfg.read('auto_bump_items').get('included')
    return (
        '📋 <b>Белый список (режим «по списку»)</b>\n\n'
        'Если в названии лота есть хотя бы одна из фраз — лот поднимается. Регистр не важен, <b>ё</b> и <b>е</b> считаются одинаково.\n\n'
        f'Сейчас записей: <code>{len(items)}</code>'
    )


def fac_058(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.read('auto_bump_items').get('included')
    return fac_005(items, page, calls.PduBoostAllowPage, lambda i: calls.PduBoostAllowDrop(index=i).pack(), CX.in_bm_i_kw, CX.f_bm_i_txt, calls.PduPrefsScope(to='bump').pack())


def fac_057(placeholder: str) -> str:
    return f'📋 <b>Белый список</b>\n\n{placeholder}'


def fac_091(placeholder: str) -> str:
    return f'➕ <b>Новая фраза</b>\n\n{placeholder}'


def fac_055() -> str:
    items = cfg.read('auto_bump_items').get('excluded') or []
    return (
        '🚫 <b>Исключения из поднятия</b>\n\n'
        'При режиме <b>«весь каталог»</b> такие лоты <b>не</b> поднимаются (даже если PREMIUM).\n'
        'При режиме «по списку» этот список не используется.\n\n'
        f'Сейчас записей: <code>{len(items)}</code>'
    )


def fac_054(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.read('auto_bump_items').get('excluded') or []
    return fac_005(
        items, page, calls.PduBoostDenyPage,
        lambda i: calls.PduBoostDenyDrop(index=i).pack(),
        CX.in_bm_x_kw, CX.f_bm_x_txt,
        calls.PduPrefsScope(to='bump').pack(),
    )


def fac_053(placeholder: str) -> str:
    return f'🚫 <b>Исключения</b>\n\n{placeholder}'


def fac_090(placeholder: str) -> str:
    return f'➕ <b>Исключение</b>\n\n{placeholder}'


def fac_113() -> str:
    config = cfg.read('config')
    enabled = config['auto']['confirm']['enabled']
    if not enabled:
        return (
            '✅ <b>Авто-подтверждение сделок</b>\n\n'
            'Выключено. После включения бот сможет сам закрывать сделки (отправка товара подтверждена) по вашим правилам.'
        )
    all_mode = config['auto']['confirm']['all']
    d = cfg.read('auto_complete_deals')
    scope = 'любые сделки' if all_mode else f"по списку ({len(d['included'])} фраз)"
    return (
        '✅ <b>Авто-подтверждение сделок</b>\n\n'
        f'• Работа: {fac_011(enabled)}\n'
        f'• Охват: <b>{scope}</b>\n\n'
        'Бот сам нажимает «товар отправлен» / завершает этап без вашего участия.\n'
        '• <b>Любые сделки</b> — по всем подходящим товарам.\n'
        '• <b>По списку</b> — только если название товара содержит фразу из списка.'
    )


def fac_115() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    enabled = config['auto']['confirm']['enabled']
    rows = [[InlineKeyboardButton(text=fac_012('Авто-подтверждение', enabled), callback_data=CX.sh_en)]]
    if not enabled:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    all_mode = config['auto']['confirm']['all']
    d = cfg.read('auto_complete_deals')
    scope_btn = 'Охват: любые сделки' if all_mode else 'Охват: по списку'
    rows.append([InlineKeyboardButton(text=f'↔️  {scope_btn}', callback_data=CX.sh_all)])
    rows.append([InlineKeyboardButton(text=f"📋  Список ({len(d['included'])})", callback_data=calls.PduSealAllowPage(page=0).pack())])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_114(placeholder: str) -> str:
    return f'✅ <b>Авто-подтверждение</b>\n\n{placeholder}'


def fac_110() -> str:
    items = cfg.read('auto_complete_deals').get('included')
    return (
        '📋 <b>Фразы для автоподтверждения</b>\n\n'
        'Если название товара в сделке содержит одну из фраз — бот может автоматически подтвердить отправку (при режиме «по списку»).\n\n'
        f'Сейчас фраз: <code>{len(items)}</code>'
    )


def fac_112(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.read('auto_complete_deals').get('included')
    return fac_005(items, page, calls.PduSealAllowPage, lambda i: calls.PduSealAllowDrop(index=i).pack(), CX.in_sh_kw, CX.f_sh_txt, calls.PduPrefsScope(to='complete').pack())


def fac_111(placeholder: str) -> str:
    return f'📋 <b>Список фраз</b>\n\n{placeholder}'


def fac_109(placeholder: str) -> str:
    return f'➕ <b>Новая фраза</b>\n\n{placeholder}'


def fac_108() -> str:
    config = cfg.read('config')
    sold = config['auto']['restore']['sold']
    expired = config['auto']['restore']['expired']
    scope = 'весь каталог' if config['auto']['restore']['all'] else 'по списку'
    poll = config['auto']['restore'].get('poll') or {}
    poll_on = poll.get('enabled', False)
    poll_iv = poll.get('interval') or 300
    premium = config['auto']['restore'].get('premium', False)
    return (
        '♻️ <b>Авто-восстановление лотов после продажи / срока</b>\n\n'
        f'• После продажи: {fac_011(sold)}\n'
        f'• После истечения срока: {fac_011(expired)}\n'
        f'• Какие лоты трогать: <b>{scope}</b>\n'
        f'• Платное восстановление (PREMIUM): {fac_011(premium)}\n'
        f'• Доп. проверка «завершённых» на сайте: {fac_011(poll_on)} (каждые <code>{poll_iv}</code> с)\n\n'
        '<b>Зачем это</b>\n'
        'Обычно бот сразу выставляет лот снова. Если на сайте задержка или сбой, объявление может остаться в архиве.\n\n'
        '<b>Платное восстановление</b> — если у лота нет бесплатного тира, бот использует PREMIUM (списывается с баланса). '
        'Если выключено, такие лоты пропускаются.\n\n'
        '<b>Проверка завершённых</b> — периодически бот снова запрашивает список проданных/истёкших лотов и при необходимости '
        'восстанавливает их (учитываются только включённые выше типы и охват).'
    )


def fac_107() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    sold = config['auto']['restore']['sold']
    expired = config['auto']['restore']['expired']
    scope = 'весь каталог' if config['auto']['restore']['all'] else 'по списку'
    poll = config['auto']['restore'].get('poll') or {}
    poll_on = poll.get('enabled', False)
    poll_iv = poll.get('interval') or 300
    premium = config['auto']['restore'].get('premium', False)
    d = cfg.read('auto_restore_items')
    rows: list[list] = [
        [InlineKeyboardButton(text=fac_012('Продажа', sold), callback_data=CX.rs_sd)],
        [InlineKeyboardButton(text=fac_012('Истечение', expired), callback_data=CX.rs_ex)],
        [InlineKeyboardButton(text=f'↔️ Охват: {scope}', callback_data=CX.rs_all)],
        [InlineKeyboardButton(text=fac_012('💎 Платное (PREMIUM)', premium), callback_data=CX.rs_pm)],
        [InlineKeyboardButton(text=fac_012('Проверка завершённых', poll_on), callback_data=CX.rs_pol)],
    ]
    if poll_on:
        rows.append([InlineKeyboardButton(text=f'⏱ Как часто: {poll_iv} с', callback_data=CX.rs_pol_iv)])
    rows.extend([
        [InlineKeyboardButton(text=f"📋  Список ({len(d['included'])})", callback_data=CX.nv_rs)],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_103(placeholder: str) -> str:
    return f'♻️ <b>Авто-восстановление лотов</b>\n\n{placeholder}'


def fac_106() -> str:
    items = cfg.read('auto_restore_items').get('included')
    return (
        '📋 <b>Фразы для автовосстановления</b>\n\n'
        'При охвате «по списку» восстанавливаются только лоты, в названии которых есть хотя бы одна из этих фраз.\n\n'
        f'Сейчас фраз: <code>{len(items)}</code>'
    )


def fac_105(page: int = 0) -> InlineKeyboardMarkup:
    items: list = cfg.read('auto_restore_items').get('included')
    return fac_005(items, page, calls.PduReviveAllowPage, lambda i: calls.PduReviveAllowDrop(index=i).pack(), CX.in_rs_kw, CX.f_rs_txt, calls.PduPrefsScope(to='restore').pack())


def fac_104(placeholder: str) -> str:
    return f'📋 <b>Список фраз</b>\n\n{placeholder}'


def fac_096(placeholder: str) -> str:
    return f'➕ <b>Новая фраза</b>\n\n{placeholder}'


def fac_083(chat_id: int | None = None) -> str:
    config = cfg.read('config')
    enabled = config['alerts']['enabled']
    ev = config['alerts']['on'] or {}
    cid = html.escape(str(chat_id)) if chat_id is not None else '—'

    def _row(eff: bool, label: str) -> str:
        return f'{fac_006(eff, label)}'

    return (
        '🔔 <b>Уведомления в Telegram</b>\n\n'
        'Выберите, о чём присылать сообщения в этот чат. Общий переключатель должен быть включён, иначе остальные пункты не работают.\n\n'
        f'<b>ID этого чата:</b> <code>{cid}</code>\n\n'
        '<b>События</b>\n'
        f'{_row(enabled, "Все уведомления")}\n'
        f'{_row(fac_001(enabled, ev, "message", False), "Новое сообщение")}\n'
        f'{_row(fac_001(enabled, ev, "system", False), "Системный чат Playerok")}\n'
        f'{_row(fac_001(enabled, ev, "deal", False), "Новая сделка")}\n'
        f'{_row(fac_001(enabled, ev, "deal_changed", False), "Статус сделки изменился")}\n'
        f'{_row(fac_001(enabled, ev, "restore", True), "Авто-восстановление лота")}\n'
        f'{_row(fac_001(enabled, ev, "bump", True), "Авто-поднятие лота")}\n'
        f'{_row(fac_001(enabled, ev, "review", False), "Оставлен отзыв")}\n'
        f'{_row(fac_001(enabled, ev, "problem", False), "Спор по сделке")}\n'
        f'{_row(fac_001(enabled, ev, "startup", True), "Запуск бота")}'
    )


def fac_082() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    enabled = config['alerts']['enabled']
    ev = config['alerts']['on'] or {}

    rows = [
        [InlineKeyboardButton(text=fac_006(enabled, 'Все уведомления'), callback_data=CX.lg_en)],
        [
            InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'message', False), 'Новое сообщение'), callback_data=CX.lg_um),
            InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'system', False), 'Системный чат'), callback_data=CX.lg_sy),
        ],
        [
            InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'deal', False), 'Новая сделка'), callback_data=CX.lg_dl),
            InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'deal_changed', False), 'Статус сделки'), callback_data=CX.lg_st),
        ],
        [
            InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'restore', True), 'Авто-восстановление лота'), callback_data=CX.lg_rs),
            InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'bump', True), 'Авто-поднятие лота'), callback_data=CX.lg_bm),
        ],
        [InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'review', False), 'Оставлен отзыв'), callback_data=CX.lg_rv)],
        [InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'problem', False), 'Спор по сделке'), callback_data=CX.lg_sp)],
        [InlineKeyboardButton(text=fac_006(fac_001(enabled, ev, 'startup', True), 'Запуск бота'), callback_data=CX.lg_bt)],
        [fac_009()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_081(placeholder: str) -> str:
    return f'🔔 <b>Уведомления</b>\n\n{placeholder}'


def fac_099() -> str:
    config = cfg.read('config')
    read_ch = config['features']['read_chat']
    verbose = config.get('debug', {}).get('verbose', False)
    return (
        '🔧 <b>Прочее</b>\n\n'
        f'💬 <b>Помечать чат прочитанным</b> — {fac_011(read_ch)}\n'
        'Перед ответом покупателю бот отмечает переписку на Playerok как прочитанную.\n\n'
        f'🔍 <b>Подробный лог (debug)</b> — {fac_011(verbose)}\n'
        'В консоль и файл пишутся запросы, ответы API и ошибки. Включайте при отладке.'
    )


def fac_098() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    read_ch = config['features']['read_chat']
    verbose = config.get('debug', {}).get('verbose', False)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fac_012('💬  Прочитано', read_ch), callback_data=CX.rd_en)],
        [InlineKeyboardButton(text=fac_012('🔍  Подробный лог', verbose), callback_data=CX.db_v)],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())],
    ])


def fac_119() -> str:
    config = cfg.read('config')
    wm_en = config['features']['watermark']['enabled']
    wm_raw = (config['features']['watermark']['text'] or '').strip()
    wm_val = f'<code>{html.escape(wm_raw)}</code>' if wm_raw else '<i>строка не задана</i>'
    wm_pos = config['features']['watermark']['position']
    pos_s = 'в начале сообщения' if wm_pos == 'start' else 'в конце сообщения'
    return (
        '📎 <b>Подпись к ответам (ватермарк)</b>\n\n'
        f'• Включено: {fac_011(wm_en)}\n'
        f'• Текст: <code>{wm_val}</code>\n'
        f'• Позиция: {pos_s}'
    )


def fac_118() -> InlineKeyboardMarkup:
    config = cfg.read('config')
    wm_en = config['features']['watermark']['enabled']
    wm_pos = config['features']['watermark']['position']
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fac_012('✏️  Подпись', wm_en), callback_data=CX.wm_en)],
        [InlineKeyboardButton(text='📝  Редактировать строку', callback_data=CX.wm_tx)],
        [
            InlineKeyboardButton(text=f'{"🔘 " if wm_pos == "start" else ""}До текста', callback_data=CX.wm_pre),
            InlineKeyboardButton(text=f'{"🔘 " if wm_pos == "end" else ""}После текста', callback_data=CX.wm_pst),
        ],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())],
    ])


def fac_117(placeholder: str) -> str:
    return f'📎 <b>Ватермарк</b>\n\n{placeholder}'


def fac_097(placeholder: str) -> str:
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


def fac_041() -> str:
    return '\n'.join(f'<code>{k}</code>  — {v}' for k, v in _MSG_VAR_DESC.items())


def fac_042(keys: list[str]) -> str:
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


def fac_013(mess_id: str, info: dict) -> str:
    return (info.get('title') or '').strip() or _MSG_NAMES.get(mess_id, mess_id)


def fac_089() -> str:
    messages = cfg.read('messages')
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
        f'<b>Справка по переменным</b>\n{fac_041()}'
    )


def fac_085(page: int = 0) -> InlineKeyboardMarkup:
    messages = cfg.read('messages')
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(max(len(messages), 1) / per_page))
    page = max(0, min(page, total_pages - 1))
    for mess_id, info in list(messages.items())[page * per_page:(page + 1) * per_page]:
        mark = _ON if info['enabled'] else _OFF
        name = fac_013(mess_id, info)
        rows.append([InlineKeyboardButton(text=f'{mark}  {name}', callback_data=calls.PduTplOpen(message_id=mess_id).pack())])
    rows.append([InlineKeyboardButton(text='➕  Добавить шаблон', callback_data=CX.tpl_nid)])
    rows += fac_010(page, total_pages, calls.PduTplGrid, calls.PduPrefsScope(to='index').pack())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_084(placeholder: str) -> str:
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


def fac_127(message_id: str) -> list[str]:
    if message_id.startswith('t_'):
        return list(_MSG_VAR_DESC.keys())
    return _TMPL_VARS.get(message_id, list(_MSG_VAR_DESC.keys()))


def fac_088(message_id: str) -> str:
    messages = cfg.read('messages')
    info = messages[message_id]
    name = fac_013(message_id, info)
    status = fac_011(info['enabled'])
    if info['text']:
        raw = '\n'.join(info['text'])
        body = f'<blockquote>{html.escape(raw)}</blockquote>'
    else:
        body = '<i>Текста ещё нет — нажмите «Редактировать текст».</i>'
    available = fac_127(message_id)
    vars_block = fac_042(available)
    return (
        f'💬 <b>{html.escape(name)}</b>\n\n'
        f'<b>Отправка:</b> {status}\n\n'
        f'<b>Текст для покупателя</b>\n{body}\n\n'
        f'<b>Переменные в этом шаблоне</b>\n{vars_block}'
    )


def fac_087(message_id: str, page: int = 0) -> InlineKeyboardMarkup:
    messages = cfg.read('messages')
    enabled = messages[message_id]['enabled']
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fac_012('Включён', enabled), callback_data=CX.tpl_en)],
        [InlineKeyboardButton(text='📝  Редактировать текст', callback_data=CX.tpl_tx)],
        [InlineKeyboardButton(text='🗑  Удалить шаблон', callback_data=CX.tpl_dq)],
        [InlineKeyboardButton(text='⬅️ К шаблонам', callback_data=calls.PduTplGrid(page=page).pack())],
    ])


def fac_086(placeholder: str) -> str:
    return f'💬 <b>Шаблон</b>\n\n{placeholder}'


def fac_067() -> str:
    items = cc_get_items(cfg.read('custom_commands'))
    commands = cfg.read('config')['features']['commands']
    head = (
        '⌨️ <b>Команды в чате сделки</b>\n\n'
        'Покупатель пишет в чат фразу (например <code>!вызвать</code>) — бот реагирует: может уведомить вас в Telegram '
        'и/или ответить в чат. Настройка — в карточке каждой команды.\n\n'
    )
    if not commands:
        return head + 'Сейчас команды отключены. Включите переключатель «Команды» строкой выше.'
    return head + f'Создано команд: <code>{len(items)}</code>.'


def fac_066(page: int = 0) -> InlineKeyboardMarkup:
    config = cfg.read('config')
    commands = config['features']['commands']
    rows = [[InlineKeyboardButton(text=fac_012('⌨️  Команды', commands), callback_data=CX.cc_en)]]
    if not commands:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    items = cc_get_items(cfg.read('custom_commands'))
    per_page = 7
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = max(0, min(page, total_pages - 1))
    for it in items[page * per_page:(page + 1) * per_page]:
        summ = cc_item_summary(it, 28)
        t = it['trigger'][:22] + '…' if len(it['trigger']) > 22 else it['trigger']
        rows.append([InlineKeyboardButton(text=f'{t}  ·  {summ}', callback_data=calls.PduCmdOpen(cmd_id=it['id']).pack())])
    rows.append([InlineKeyboardButton(text='➕  Добавить команду', callback_data=CX.cc_new)])
    rows += fac_010(page, total_pages, calls.PduCmdGrid, calls.PduPrefsScope(to='index').pack())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_065(placeholder: str) -> str:
    return f'⌨️ <b>Команды в чате</b>\n\n{placeholder}'


def fac_092(placeholder: str) -> str:
    return f'➕ <b>Новая команда</b>\n\n{placeholder}'


def fac_064(cmd_id: str) -> str:
    items = cc_get_items(cfg.read('custom_commands'))
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


def fac_063(cmd_id: str, page: int = 0) -> InlineKeyboardMarkup:
    items = cc_get_items(cfg.read('custom_commands'))
    item = cc_find_by_id(items, cmd_id)
    if not item:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ К списку', callback_data=calls.PduCmdGrid(page=page).pack())]])
    rows: list[list] = []
    for ev_id, label in KNOWN_EVENTS.items():
        on = ev_id in (item.get('events') or [])
        lab = label if len(label) <= 30 else label[:28] + '…'
        rows.append([InlineKeyboardButton(
            text=f'{fac_004(on)}  {lab}',
            callback_data=calls.PduCmdEvtFlip(cmd_id=cmd_id, kind=ev_id).pack(),
        )])
    rows.append([InlineKeyboardButton(text='📝  Текст ответа', callback_data=CX.cc_ans)])
    rows.append([InlineKeyboardButton(text='🗑  Удалить команду', callback_data=CX.cc_dok)])
    rows.append([InlineKeyboardButton(text='⬅️ К списку', callback_data=calls.PduCmdGrid(page=page).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_062(placeholder: str) -> str:
    return f'⌨️ <b>Команда</b>\n\n{placeholder}'


def fac_079() -> str:
    auto_deliveries = cfg.read('auto_deliveries')
    if not cfg.read('config')['features']['deliveries']:
        return (
            '📦 <b>Авто-выдача товара</b>\n\n'
            'Функция выключена. Включите переключатель «Авто-выдача» вверху экрана.'
        )
    return (
        '📦 <b>Авто-выдача товара</b>\n\n'
        'Когда покупатель оплатил сделку и название товара содержит вашу фразу, бот сам отправит в чат ключ, текст или файлы.\n\n'
        f'Настроено правил: <code>{len(auto_deliveries)}</code>'
    )


def fac_078(page: int = 0) -> InlineKeyboardMarkup:
    config = cfg.read('config')
    delivs = config['features']['deliveries']
    rows = [[InlineKeyboardButton(text=fac_012('📦  Авто-выдача', delivs), callback_data=CX.ad_en)]]
    if not delivs:
        rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduPrefsScope(to='index').pack())])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    auto_deliveries: list = cfg.read('auto_deliveries')
    per_page = 7
    total_pages = max(1, math.ceil(len(auto_deliveries) / per_page))
    page = max(0, min(page, total_pages - 1))
    for deliv in auto_deliveries[page * per_page:(page + 1) * per_page]:
        piece = deliv.get('piece')
        kp = ', '.join(deliv.get('keyphrases', [])) or 'нет фраз'
        kp_short = kp[:28] + '…' if len(kp) > 28 else kp
        count = f"{len(deliv.get('goods', []))} шт." if piece else 'текст'
        rows.append([InlineKeyboardButton(text=f'{kp_short}  →  {count}', callback_data=calls.PduFulfillOpen(index=auto_deliveries.index(deliv)).pack())])
    rows.append([InlineKeyboardButton(text='➕  Добавить выдачу', callback_data=CX.ad_kw_n)])
    rows += fac_010(page, total_pages, calls.PduFulfillGrid, calls.PduPrefsScope(to='index').pack())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_071(placeholder: str) -> str:
    return f'📦 <b>Авто-выдача</b>\n\n{placeholder}'


def fac_093(placeholder: str) -> str:
    return f'➕ <b>Новая автовыдача</b>\n\n{placeholder}'


def fac_095(last_page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📁  Пакет файлов', callback_data=calls.PduFulfillModePick(val=True).pack())],
        [InlineKeyboardButton(text='💬  Один текст', callback_data=calls.PduFulfillModePick(val=False).pack())],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduFulfillGrid(page=last_page).pack())],
    ])


def fac_077(index: int) -> str:
    auto_deliveries = cfg.read('auto_deliveries')
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


def fac_076(index: int, page: int = 0) -> InlineKeyboardMarkup:
    auto_deliveries = cfg.read('auto_deliveries')
    deliv = auto_deliveries[index]
    piece = deliv.get('piece')
    kp = ', '.join(deliv.get('keyphrases', [])) or 'нет'
    n_goods = len(deliv.get('goods', []))
    message = '\n'.join(deliv.get('message', [])) or ''
    msg_btn = message[:22] + '…' if len(message) > 22 else message
    content_btn = (
        InlineKeyboardButton(text=f'📁  Файлы ({n_goods})', callback_data=calls.PduFulfillFilesPage(page=0).pack())
        if piece else
        InlineKeyboardButton(text=f'💬  Текст: {msg_btn}', callback_data=CX.ad_msg)
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'Тип: {"пакет" if piece else "текст"}', callback_data=CX.ad_pc)],
        [InlineKeyboardButton(text=f'🔑  Фразы: {kp[:32]}', callback_data=CX.ad_kw_e)],
        [content_btn],
        [InlineKeyboardButton(text='🗑  Удалить выдачу', callback_data=CX.ad_dok)],
        [InlineKeyboardButton(text='⬅️ К выдачам', callback_data=calls.PduFulfillGrid(page=page).pack())],
    ])


def fac_075(placeholder: str) -> str:
    return f'📦 <b>Авто-выдача</b>\n\n{placeholder}'


def fac_074(index: int = 0) -> str:
    goods = cfg.read('auto_deliveries')[index].get('goods', [])
    return (
        f'📁 <b>Файлы для выдачи</b>\n\n'
        f'Каждая строка — отдельный товар (ключ, ссылка и т.д.). Всего: <code>{len(goods)}</code>.'
    )


def fac_073(index: int = 0, page: int = 0) -> InlineKeyboardMarkup:
    goods = cfg.read('auto_deliveries')[index].get('goods', [])
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(len(goods) / per_page))
    page = max(0, min(page, total_pages - 1))
    for good in goods[page * per_page:(page + 1) * per_page]:
        rows.append([
            InlineKeyboardButton(text=str(good), callback_data=CX.noop),
            InlineKeyboardButton(text='✕', callback_data=calls.PduFulfillFileDrop(index=goods.index(good)).pack()),
        ])
    if total_pages > 1:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=calls.PduFulfillFilesPage(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data=CX.noop),
            InlineKeyboardButton(text=f'{page + 1} / {total_pages}', callback_data=CX.ad_g_pg),
            InlineKeyboardButton(text='▶', callback_data=calls.PduFulfillFilesPage(page=page + 1).pack()) if page < total_pages - 1 else InlineKeyboardButton(text='·', callback_data=CX.noop),
        ])
    rows.append([InlineKeyboardButton(text='➕  Добавить файл', callback_data=CX.ad_g_add)])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=calls.PduFulfillOpen(index=index).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fac_072(placeholder: str) -> str:
    return f'📁 <b>Файлы пакета</b>\n\n{placeholder}'


def fac_094(placeholder: str) -> str:
    return f'➕ <b>Добавить файл</b>\n\n{placeholder}'


def fac_005(items: list, page: int, pagination_cls, delete_cb_fn, add_cb: str, bulk_add_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = max(0, min(page, total_pages - 1))
    for kp in items[page * per_page:(page + 1) * per_page]:
        label = ', '.join(kp) if kp else '(пусто)'
        rows.append([
            InlineKeyboardButton(text=label, callback_data=CX.noop),
            InlineKeyboardButton(text='✕', callback_data=delete_cb_fn(items.index(kp))),
        ])
    if total_pages > 1 and pagination_cls is not None:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=pagination_cls(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data=CX.noop),
            InlineKeyboardButton(text=f'{page + 1} / {total_pages}', callback_data=CX.noop),
            InlineKeyboardButton(text='▶', callback_data=pagination_cls(page=page + 1).pack()) if page < total_pages - 1 else InlineKeyboardButton(text='·', callback_data=CX.noop),
        ])
    rows.append([
        InlineKeyboardButton(text='➕  Одна фраза', callback_data=add_cb),
        InlineKeyboardButton(text='➕  Из .txt', callback_data=bulk_add_cb),
    ])
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
