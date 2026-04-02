import math
import html as html_module
from urllib.parse import quote
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from uuid import UUID
from lib.consts import VERSION
from lib.util import iso_to_display_str
from lib.cfg import AppConf as cfg
from lib.ext import all_extensions, Extension, find_extension
from .. import keys as calls
from .settings import _tpl_label


def _brand_line() -> str:
    return f'<b>CXH Playerok</b>  <code>v{VERSION}</code>'


def error_text(placeholder: str) -> str:
    return (
        '⛔ <b>Что-то пошло не так</b>\n\n'
        f'<b>Подробности:</b>\n<blockquote>{placeholder}</blockquote>'
    )


def back_kb(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Назад', callback_data=cb)]])


def confirm_kb(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='✅  Подтвердить', callback_data=confirm_cb),
        InlineKeyboardButton(text='✕  Отмена', callback_data=cancel_cb),
    ]])


def destroy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✕  Закрыть', callback_data='destroy')]])


def do_action_text(placeholder: str) -> str:
    return f'✅ <b>Готово</b>\n\n{placeholder}'


def log_text(title: str, text: str) -> str:
    return f'{title}\n\n{text}'


def log_restore_ok_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='♻️ Автовосстановление', callback_data=calls.SettingsNavigation(to='restore').pack())],
    ])


def log_bump_ok_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔼 Автоподнятие', callback_data=calls.SettingsNavigation(to='bump').pack())],
    ])


def log_new_mess_kb(username: str, chat_id: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if chat_id:
        rows.append([
            InlineKeyboardButton(text='↗  Перейти в чат', url=f'https://playerok.com/chats/{chat_id}'),
            InlineKeyboardButton(text='📜  Больше', callback_data=calls.LogChatHistory(chat_id=chat_id, page=0).pack()),
        ])
    rows.append([
        InlineKeyboardButton(text='💬  Ответить', callback_data=calls.RememberUsername(name=username, do='send_mess').pack()),
        InlineKeyboardButton(text='📋  Шаблоны', callback_data=calls.RememberUsername(name=username, do='tpl_list').pack()),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def log_chat_only_kb(chat_id: str | None) -> InlineKeyboardMarkup | None:
    if not chat_id:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='↗  Перейти в чат', url=f'https://playerok.com/chats/{chat_id}')],
    ])


def chat_history_chunks(messages: list, our_user_id: str) -> list[str]:
    from bot.core import message_body_html
    header = (
        '📜 <b>История чата</b>\n'
        'Ниже до <b>25</b> последних сообщений: от старых к новым, время — по часовому поясу вашего ПК.\n\n'
    )
    max_chunk = 4000
    ordered = list(reversed(messages))
    blocks: list[str] = []
    for m in ordered:
        uid = getattr(getattr(m, 'user', None), 'id', None)
        un = getattr(getattr(m, 'user', None), 'username', '?')
        un_esc = html_module.escape(un)
        if uid == our_user_id:
            head = '🫡 <b>Вы</b> (продавец)'
        else:
            head = f'👤 <b>Покупатель</b> · <code>{un_esc}</code>'
        ts = ''
        ca = getattr(m, 'created_at', None)
        if ca:
            try:
                ts = iso_to_display_str(ca)
            except Exception:
                ts = ''
        body = message_body_html(m)
        lines = [head]
        if ts:
            lines.append(f'<i>🕐 {ts}</i>')
        lines.append(f'<blockquote>{body}</blockquote>')
        blocks.append('\n'.join(lines))
    if not blocks:
        return [header + 'В этом чате пока нет сообщений.']
    chunks: list[str] = []
    cur = header
    sep = '\n\n'
    for b in blocks:
        add = b if cur == header else sep + b
        if len(cur + add) <= max_chunk:
            cur += add
            continue
        if cur != header:
            chunks.append(cur)
        nb = header + b
        if len(nb) <= max_chunk:
            cur = nb
        else:
            chunks.append(nb[: max_chunk - 1] + '…')
            cur = header
    if cur != header:
        chunks.append(cur)
    return chunks


def log_chat_history_kb(chat_id: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        prev_p = max(0, page - 1)
        next_p = min(total_pages - 1, page + 1)
        rows.append([
            InlineKeyboardButton(
                text='◀️ Ранее',
                callback_data=calls.LogChatHistory(chat_id=chat_id, page=prev_p).pack(),
            ),
            InlineKeyboardButton(
                text=f'📄 {page + 1} / {total_pages}',
                callback_data=calls.LogChatHistory(chat_id=chat_id, page=page).pack(),
            ),
            InlineKeyboardButton(
                text='Далее ▶️',
                callback_data=calls.LogChatHistory(chat_id=chat_id, page=next_p).pack(),
            ),
        ])
    rows.append([InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def log_templates_text(username: str, page: int, order: list[str]) -> str:
    per_page = 7
    n = len(order)
    total_pages = max(1, math.ceil(n / per_page) if n else 1)
    page = max(0, min(page, total_pages - 1))
    head = f'📋 <b>Шаблоны для</b> <code>{html_module.escape(username)}</code>\n\n'
    if total_pages > 1:
        head += f'Страница <b>{page + 1}</b> из <b>{total_pages}</b> — листайте кнопками <b>◀ Пред.</b> / <b>След. ▶</b>.\n\n'
    head += (
        'Нажмите шаблон — бот отправит его текст в чат сделки на Playerok '
        '(переменные вроде <code>$buyer</code>, <code>$seller</code> подставятся сами).'
    )
    return head


def log_templates_kb(page: int, order: list[str]) -> InlineKeyboardMarkup:
    messages = cfg.get('messages') or {}
    per_page = 7
    n = len(order)
    total_pages = max(1, math.ceil(n / per_page) if n else 1)
    page = max(0, min(page, total_pages - 1))
    rows = []
    slice_ = order[page * per_page:(page + 1) * per_page]
    start_idx = page * per_page
    for i, mess_id in enumerate(slice_):
        msg_idx = start_idx + i
        info = messages.get(mess_id, {})
        label = _tpl_label(mess_id, info)
        display = label if len(label) <= 36 else label[:33] + '…'
        rows.append([InlineKeyboardButton(
            text=f'📄 {display}',
            callback_data=calls.LogTemplateSend(idx=msg_idx).pack(),
        )])
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text='◀ Пред.', callback_data=calls.LogTemplateMenu(page=page - 1).pack()))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text='След. ▶', callback_data=calls.LogTemplateMenu(page=page + 1).pack()))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text='⬅️ К уведомлению', callback_data='back_to_notification')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def log_new_deal_kb(username: str, deal_id: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text='💬  Ответить', callback_data=calls.RememberUsername(name=username, do='send_mess').pack()),
            InlineKeyboardButton(text='📋  Шаблоны', callback_data=calls.RememberUsername(name=username, do='tpl_list').pack()),
        ],
    ]
    rows.append([InlineKeyboardButton(text='✅  Закрыть сделку', callback_data=calls.RememberDealId(de_id=deal_id, do='complete').pack())])
    rows.append([InlineKeyboardButton(text='↩️  Возврат', callback_data=calls.RememberDealId(de_id=deal_id, do='refund').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def log_new_review_kb(username: str, deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='⭐  К отзыву', callback_data=calls.RememberDealId(de_id=deal_id, do='answer_rev').pack()),
        InlineKeyboardButton(text='💬  Написать', callback_data=calls.RememberUsername(name=username, do='send_mess').pack()),
    ]])


def sign_in_prompt_text() -> str:
    return (
        '🔐 <b>Вход в панель</b>\n\n'
        'Отправьте пароль, который вы задали при первом запуске бота.\n\n'
        '<b>Забыли пароль?</b> Остановите бота, удалите папку <code>conf/</code> и запустите снова — мастер настройки начнётся заново.'
    )


def sign_text(placeholder: str) -> str:
    return f'🔐 <b>Вход</b>\n\n{placeholder}'


def call_seller_text(calling_name: str, chat_link: str) -> str:
    return f'🔔 <b>{calling_name}</b> вызывает вас в чат\n\n{chat_link}'


def menu_text() -> str:
    return (
        '🏠 <b>Главное меню</b>\n\n'
        f'{_brand_line()}\n\n'
        'Профиль, уведомления и расширения — кнопками ниже. Настройки бота и статистика — в разделе «Настройки».'
    )


def menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='⚙️ Настройки', callback_data=calls.SettingsNavigation(to='index').pack()),
            InlineKeyboardButton(text='👤 Профиль', callback_data=calls.MenuNavigation(to='profile').pack()),
        ],
        [
            InlineKeyboardButton(text='🔔 Уведомления', callback_data=calls.MenuNavigation(to='logger').pack()),
            InlineKeyboardButton(text='🧩 Расширения', callback_data=calls.ExtPagination(page=0).pack()),
        ],
    ])


def startup_text(playerok_ok: bool = True) -> str:
    text = f'🚀 <b>Панель готова</b>\n\n{_brand_line()}'
    if not playerok_ok:
        text += '\n\n⚠️ Playerok не отвечает: проверьте токен в конфиге и прокси (если используете).'
    return text


def profile_text() -> str:
    from bot.core import active_engine
    acc = active_engine().account.get()
    p = acc.profile
    bal = p.balance
    bal_total = f'{bal.value} ₽' if bal else '—'
    bal_avail = f'{bal.available} ₽' if bal else '—'
    bal_pending = f'{bal.pending_income} ₽' if bal else '—'
    bal_frozen = f'{bal.frozen} ₽' if bal else '—'
    items_active = p.stats.items.total - p.stats.items.finished
    sells_active = p.stats.deals.outgoing.total - p.stats.deals.outgoing.finished
    buys_active = p.stats.deals.incoming.total - p.stats.deals.incoming.finished
    reg_date = iso_to_display_str(p.created_at, fmt='%d.%m.%Y')
    uname = (p.username or '').strip().lstrip('@')
    if uname:
        profile_url = f'https://playerok.com/profile/{quote(uname, safe="")}/products'
        nick_line = (
            f'<a href="{html_module.escape(profile_url, quote=True)}">'
            f'{html_module.escape(uname)}'
            f'</a>'
        )
    else:
        nick_line = '—'
    return (
        f'👤 <b>Профиль на Playerok</b>\n\n'
        f'Ник: {nick_line}\n'
        f'Рейтинг <code>{p.rating}</code> · отзывов <code>{p.reviews_count}</code> · на сайте с <code>{reg_date}</code>\n\n'
        f'💰 <b>Баланс</b>\n'
        f'• Всего: <code>{bal_total}</code>\n'
        f'• Доступно: <code>{bal_avail}</code>\n'
        f'• В ожидании: <code>{bal_pending}</code>\n'
        f'• Заморожено: <code>{bal_frozen}</code>\n\n'
        f'📊 <b>Сейчас активно</b>\n'
        f'• Лотов: <code>{items_active}</code>\n'
        f'• Продаж (сделок): <code>{sells_active}</code>\n'
        f'• Покупок: <code>{buys_active}</code>'
    )


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Меню', callback_data=calls.MenuNavigation(to='default').pack())]])


def stats_text() -> str:
    from bot.core import get_stats
    s = get_stats()
    launch = iso_to_display_str(s.bot_launch_time.isoformat(), fmt='%d.%m.%Y  %H:%M:%S') if s.bot_launch_time else '—'
    return (
        f'📊 <b>Статистика бота</b>\n\n'
        f'Сессия запущена: <code>{launch}</code>\n\n'
        f'<b>Счётчики за всё время работы</b>\n'
        f'• Успешно закрытых сделок: <code>{s.deals_completed}</code>\n'
        f'• Возвратов: <code>{s.deals_refunded}</code>\n'
        f'• Заработано (по данным бота): <code>{s.earned_money} ₽</code>'
    )


def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🗑 Сбросить счётчики', callback_data='confirm_reset_stats')],
        [
            InlineKeyboardButton(text='⬅️ Настройки', callback_data=calls.SettingsNavigation(to='index').pack())
        ],
    ])


def stats_reset_confirm_text() -> str:
    return (
        '⚠️ <b>Сбросить статистику?</b>\n\n'
        'Обнулятся счётчики сделок, возвратов и заработка, которые ведёт бот. '
        'Восстановить их будет нельзя.'
    )


def stats_reset_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='✅  Да, сбросить', callback_data='reset_stats'),
        InlineKeyboardButton(text='✕  Отмена', callback_data='back_to_stats'),
    ]])


def logs_text() -> str:
    config = cfg.get('config')
    max_mb = config['logs'].get('max_mb') or '—'
    return (
        '🗂 <b>Логи работы</b>\n\n'
        f'Максимальный размер файла: <code>{max_mb} МБ</code>.\n'
        'Когда файл вырастет до лимита, он обнуляется и пишется заново.'
    )


def logs_kb() -> InlineKeyboardMarkup:
    config = cfg.get('config')
    max_mb = config['logs'].get('max_mb') or '—'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'📏  Лимит: {max_mb} МБ', callback_data='enter_logs_max_file_size')],
        [InlineKeyboardButton(text='📥  Скачать фрагмент', callback_data='select_logs_file_lines')],
        [InlineKeyboardButton(text='⬅️ Меню', callback_data=calls.MenuNavigation(to='default').pack())],
    ])


def logs_file_lines_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='100 строк', callback_data=calls.SendLogsFile(lines=100).pack()),
            InlineKeyboardButton(text='250 строк', callback_data=calls.SendLogsFile(lines=250).pack()),
        ],
        [
            InlineKeyboardButton(text='1000 строк', callback_data=calls.SendLogsFile(lines=1000).pack()),
            InlineKeyboardButton(text='Весь файл', callback_data=calls.SendLogsFile(lines=-1).pack()),
        ],
        [InlineKeyboardButton(text='⬅️ К логам', callback_data=calls.MenuNavigation(to='logs').pack())],
    ])


def logs_float_text(placeholder: str) -> str:
    return f'🗂 <b>Логи</b>\n\n{placeholder}'


def instruction_text() -> str:
    return '📖 <b>Справка</b>\n\nКратко о возможностях. Выберите тему ниже:'


def instruction_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⌨️  Команды покупателя', callback_data=calls.InstructionNavigation(to='commands').pack())],
        [InlineKeyboardButton(text='⬅️ Меню', callback_data=calls.MenuNavigation(to='default').pack())],
    ])


def instruction_comms_text() -> str:
    return (
        '⌨️ <b>Команды в чате сделки</b>\n\n'
        '1. В <b>Настройки → Команды</b> добавьте триггер, например <code>!вызвать</code>.\n'
        '2. В карточке команды отметьте нужные <b>события</b> (например, уведомление вам в Telegram).\n'
        '3. По желанию укажите <b>текст ответа</b> — бот отправит его покупателю в чат на Playerok.'
    )


def instruction_comms_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ К командам', callback_data=calls.CustomCommandsPagination(page=0).pack())]])


def plugins_text() -> str:
    loaded = all_extensions()
    n = len(loaded)
    if n:
        hint = f'Папка <code>ext/</code>: загружено расширений — <code>{n}</code>. Нажмите на название, чтобы включить или выключить.'
    else:
        hint = 'Список пуст. Положите модуль в папку <code>ext/</code> и перезапустите бота — оно появится здесь.'
    return f'🧩 <b>Расширения</b>\n\n{hint}'


def plugins_kb(page: int = 0) -> InlineKeyboardMarkup:
    loaded = all_extensions()
    rows = []
    per_page = 7
    total_pages = max(1, math.ceil(len(loaded) / per_page))
    page = max(0, min(page, total_pages - 1))
    for ext in list(loaded)[page * per_page:(page + 1) * per_page]:
        status = '🟢' if ext.enabled else '⚫'
        rows.append([InlineKeyboardButton(text=f'{status}  {ext.meta.name}  {ext.meta.version}', callback_data=calls.ExtPage(uuid=ext.uuid).pack())])
    if total_pages > 1:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=calls.ExtPagination(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data='noop'),
            InlineKeyboardButton(text=f'{page + 1} / {total_pages}', callback_data='enter_plugins_page'),
            InlineKeyboardButton(text='▶', callback_data=calls.ExtPagination(page=page + 1).pack()) if page < total_pages - 1 else InlineKeyboardButton(text='·', callback_data='noop'),
        ])
    rows.append([InlineKeyboardButton(text='⬅️ Меню', callback_data=calls.MenuNavigation(to='default').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plugin_page_text(plugin_uuid: UUID) -> str:
    ext: Extension = find_extension(plugin_uuid)
    if not ext:
        raise Exception('Расширение не найдено')
    status = '🟢 работает' if ext.enabled else '⚫ остановлено'
    desc = html_module.escape(ext.meta.description or 'Описание не указано.')
    return (
        f'🧩 <b>{ext.meta.name}</b>  <code>{ext.meta.version}</code>\n\n'
        f'Состояние: {status}\n'
        f'ID: <code>{ext.uuid}</code>\n\n'
        f'<b>Описание</b>\n<blockquote>{desc}</blockquote>\n\n'
        f'<b>Автор:</b> {ext.meta.authors}\n'
        f'{ext.meta.links}'
    )


def plugin_page_kb(plugin_uuid: UUID, page: int = 0) -> InlineKeyboardMarkup:
    ext: Extension = find_extension(plugin_uuid)
    if not ext:
        raise Exception('Расширение не найдено')
    toggle = '⚫  Остановить' if ext.enabled else '🟢  Запустить'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle, callback_data='toggle_ext_state')],
        [InlineKeyboardButton(text='🔄  Перезапустить', callback_data='refresh_extension')],
        [InlineKeyboardButton(text='⬅️ К расширениям', callback_data=calls.ExtPagination(page=page).pack())],
    ])


def plugin_page_float_text(placeholder: str) -> str:
    return f'🧩 <b>Расширение</b>\n\n{placeholder}'
