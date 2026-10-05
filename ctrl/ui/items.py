import html
import math

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pok.conn import BOOSTABLE_STAGES, PUBLISHABLE_STAGES
from pok.defs import BoostLevel, ListingStage
from .. import keys as calls
from ..cb import CX

ITEMS_PER_PAGE = 7

STATUS_LABELS = {
    ListingStage.APPROVED: ('🟢', 'в продаже'),
    ListingStage.PENDING_APPROVAL: ('🕓', 'на проверке'),
    ListingStage.PENDING_MODERATION: ('🕓', 'на модерации'),
    ListingStage.PENDING_STATUS_PAYMENT: ('💳', 'ожидает оплаты статуса'),
    ListingStage.SOLD: ('💰', 'продан'),
    ListingStage.EXPIRED: ('⌛', 'истёк'),
    ListingStage.DRAFT: ('📝', 'черновик'),
    ListingStage.DECLINED: ('⛔', 'отклонён'),
    ListingStage.BLOCKED: ('🚫', 'заблокирован'),
    ListingStage.DISCONTINUED: ('⏸', 'снят'),
    ListingStage.REMOVED: ('🗑', 'удалён'),
}

PRIORITY_LABELS = {
    BoostLevel.DEFAULT: 'обычный',
    BoostLevel.PREMIUM: 'премиум',
    BoostLevel.CUSTOM: 'свой',
    BoostLevel.VIP: 'VIP',
}

ORDER = [
    ListingStage.APPROVED, ListingStage.PENDING_APPROVAL, ListingStage.PENDING_MODERATION,
    ListingStage.PENDING_STATUS_PAYMENT, ListingStage.SOLD, ListingStage.EXPIRED, ListingStage.DRAFT,
    ListingStage.DECLINED, ListingStage.DISCONTINUED, ListingStage.BLOCKED, ListingStage.REMOVED,
]


def status_label(status) -> str:
    icon, label = STATUS_LABELS.get(status, ('❔', getattr(status, 'name', 'неизвестно')))
    return f'{icon} {label}'


def sort_items(items: list) -> list:
    def key(item):
        status = getattr(item, 'status', None)
        return (ORDER.index(status) if status in ORDER else len(ORDER), (getattr(item, 'name', '') or '').lower())
    return sorted([i for i in items if i is not None], key=key)


def keep_in_sale_editable(item) -> bool:
    return bool(item.keep_in_sale_available and item.status in BOOSTABLE_STAGES and item.priority == BoostLevel.PREMIUM)


def items_text(items: list, page: int) -> str:
    total = len(items)
    active = sum(1 for i in items if i.status in BOOSTABLE_STAGES)
    stopped = [i for i in items if i.status in PUBLISHABLE_STAGES]
    restorable = sum(1 for i in stopped if not i.lacks_seller_reviews)
    blocked = len(stopped) - restorable
    if not total:
        return '📦 <b>Мои лоты</b>\n\nНа аккаунте пока нет лотов.'
    pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    blocked_note = f' · ждут отзывов: <b>{blocked}</b>' if blocked else ''
    return (
        '📦 <b>Мои лоты</b>\n\n'
        f'Всего: <b>{total}</b> · в продаже: <b>{active}</b> · можно выставить: <b>{restorable}</b>{blocked_note}\n'
        f'Страница {min(page, pages - 1) + 1} из {pages}. Нажмите на лот, чтобы открыть действия.'
    )


def items_kb(items: list, page: int) -> InlineKeyboardMarkup:
    total = len(items)
    pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page, pages - 1))
    rows = []
    for item in items[page * ITEMS_PER_PAGE:(page + 1) * ITEMS_PER_PAGE]:
        icon = STATUS_LABELS.get(item.status, ('❔', ''))[0]
        name = (item.name or '—')
        name = name if len(name) <= 34 else name[:33] + '…'
        rows.append([InlineKeyboardButton(text=f'{icon} {name} · {item.price}₽', callback_data=calls.PduItemOpen(id=item.id).pack())])
    if pages > 1:
        rows.append([
            InlineKeyboardButton(text='◀', callback_data=calls.PduItemsGrid(page=page - 1).pack()) if page > 0 else InlineKeyboardButton(text='·', callback_data=CX.noop),
            InlineKeyboardButton(text=f'{page + 1} / {pages}', callback_data=CX.noop),
            InlineKeyboardButton(text='▶', callback_data=calls.PduItemsGrid(page=page + 1).pack()) if page < pages - 1 else InlineKeyboardButton(text='·', callback_data=CX.noop),
        ])
    rows.append([InlineKeyboardButton(text='🔄 Обновить', callback_data=calls.PduItemsGrid(page=page).pack())])
    rows.append([InlineKeyboardButton(text='⬅️ Меню', callback_data=calls.PduRootNav(to='default').pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def item_text(item, note: str | None = None) -> str:
    name = html.escape(item.name or '—')
    priority = PRIORITY_LABELS.get(item.priority, getattr(item.priority, 'name', '—'))
    lines = [
        f'📦 <b>{name}</b>',
        '',
        f'Статус: {status_label(item.status)}',
        f'Цена: <b>{item.price} ₽</b>' + (f' (покупатель платит {item.raw_price} ₽)' if item.raw_price and item.raw_price != item.price else ''),
        f'Приоритет: {html.escape(str(priority))}',
    ]
    if item.views_counter is not None:
        lines.append(f'Просмотры: {item.views_counter}' + (f' · продаж: {item.deals_counter}' if item.deals_counter is not None else ''))
    if keep_in_sale_editable(item):
        lines.append(f'Оставлять в продаже после покупки: {"✅" if item.keep_in_sale else "❌"}')
    if item.status_description:
        lines.append(f'Комментарий Playerok: <i>{html.escape(item.status_description)}</i>')
    if item.status in PUBLISHABLE_STAGES and item.lacks_seller_reviews:
        obtaining = getattr(getattr(item, 'obtaining_type', None), 'name', None)
        where = f' со способом «{html.escape(obtaining)}»' if obtaining else ''
        lines.append(f'⚠️ Playerok разрешает выставлять лоты{where} от {item.required_seller_reviews} отзывов, '
                     f'у аккаунта {item.seller_reviews}. Создайте копию с другим способом получения.')
    if note:
        lines.extend(['', note])
    return '\n'.join(lines)


def item_kb(item, page: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if item.status in PUBLISHABLE_STAGES and not item.lacks_seller_reviews:
        rows.append([InlineKeyboardButton(text='♻️ Выставить на продажу', callback_data=calls.PduItemAct(do='tiers').pack())])
    elif item.status in BOOSTABLE_STAGES:
        rows.append([InlineKeyboardButton(text='⬆️ Поднять в топ', callback_data=calls.PduItemAct(do='tiers').pack())])
    if keep_in_sale_editable(item):
        mark = '✅' if item.keep_in_sale else '❌'
        rows.append([InlineKeyboardButton(text=f'📌 Оставлять в продаже: {mark}', callback_data=calls.PduItemAct(do='keep').pack())])
    rows.append([
        InlineKeyboardButton(text='📄 Создать копию', callback_data=calls.PduItemAct(do='clone').pack()),
        InlineKeyboardButton(text='🗑 Удалить', callback_data=calls.PduItemAct(do='remove').pack()),
    ])
    if item.slug:
        rows.append([InlineKeyboardButton(text='↗ Открыть на Playerok', url=f'https://playerok.com/products/{item.slug}')])
    rows.append([
        InlineKeyboardButton(text='🔄', callback_data=calls.PduItemOpen(id=item.id).pack()),
        InlineKeyboardButton(text='⬅️ К лотам', callback_data=calls.PduItemsGrid(page=page).pack()),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tiers_text(item, tiers: list) -> str:
    action = 'выставления' if item.status in PUBLISHABLE_STAGES else 'поднятия'
    if not tiers:
        return f'📦 <b>{html.escape(item.name or "—")}</b>\n\nPlayerok не предложил тарифов для {action}.'
    lines = [f'📦 <b>{html.escape(item.name or "—")}</b>', '', f'Выберите тариф для {action}:']
    for tier in tiers:
        period = f', {tier.period} дн.' if tier.period else ''
        price = 'бесплатно' if not tier.price else f'{tier.price} ₽'
        lines.append(f'• {html.escape(tier.name or "—")} — <b>{price}</b>{period}')
    return '\n'.join(lines)


def tiers_kb(tiers: list, item_id: str) -> InlineKeyboardMarkup:
    rows = []
    for index, tier in enumerate(tiers):
        price = 'бесплатно' if not tier.price else f'{tier.price} ₽'
        rows.append([InlineKeyboardButton(text=f'{tier.name or "—"} · {price}', callback_data=calls.PduItemTier(i=index).pack())])
    rows.append([InlineKeyboardButton(text='⬅️ К лоту', callback_data=calls.PduItemOpen(id=item_id).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_text(item, tier: dict, keep: bool) -> str:
    action = 'Выставить' if item.status in PUBLISHABLE_STAGES else 'Поднять'
    price = tier.get('price') or 0
    lines = [
        f'{action} <b>{html.escape(item.name or "—")}</b>',
        f'Тариф: <b>{html.escape(tier.get("name") or "—")}</b>',
        f'Стоимость: <b>{"бесплатно" if not price else f"{price} ₽ с баланса Playerok"}</b>',
    ]
    if tier.get('type') == BoostLevel.PREMIUM.name and item.keep_in_sale_available:
        lines.append(f'Оставлять в продаже после покупки: {"✅" if keep else "❌"}')
    lines.extend(['', 'Подтвердите действие.'])
    return '\n'.join(lines)


def confirm_kb(item, tier: dict, keep: bool) -> InlineKeyboardMarkup:
    rows = []
    if tier.get('type') == BoostLevel.PREMIUM.name and item.keep_in_sale_available:
        rows.append([InlineKeyboardButton(text=f'📌 Оставлять в продаже: {"✅" if keep else "❌"}', callback_data=calls.PduItemAct(do='kis').pack())])
    price = tier.get('price') or 0
    rows.append([
        InlineKeyboardButton(text=f'✅ Подтвердить{f" · {price} ₽" if price else ""}', callback_data=calls.PduItemAct(do='go').pack()),
        InlineKeyboardButton(text='✕ Отмена', callback_data=calls.PduItemOpen(id=item.id).pack()),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def clone_text(item, options: list[dict]) -> str:
    lines = [f'📄 Копия лота <b>{html.escape(item.name or "—")}</b>', '',
             'Будут скопированы название, описание, цена, параметры и фото. Копия появится как черновик, '
             'её можно выставить из карточки.']
    if options:
        lines.extend(['', 'Выберите способ получения для копии:'])
        for option in options:
            mark = ' · сейчас у лота' if option['current'] else ''
            lock = f' · 🔒 нужно {option["required"]}+ отзывов' if option['locked'] else ''
            lines.append(f'• {html.escape(option["name"] or "—")}{mark}{lock}')
    return '\n'.join(lines)


def clone_kb(options: list[dict], item_id: str) -> InlineKeyboardMarkup:
    rows = []
    for index, option in enumerate(options):
        icon = '🔒' if option['locked'] else ('✅' if option['current'] else '▫️')
        rows.append([InlineKeyboardButton(text=f'{icon} {option["name"] or "—"}', callback_data=calls.PduItemObtain(i=index).pack())])
    if not options:
        rows.append([InlineKeyboardButton(text='✅ Создать копию', callback_data=calls.PduItemAct(do='clone_go').pack())])
    rows.append([InlineKeyboardButton(text='⬅️ К лоту', callback_data=calls.PduItemOpen(id=item_id).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no_kb(do: str, item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='✅ Да', callback_data=calls.PduItemAct(do=do).pack()),
        InlineKeyboardButton(text='✕ Нет', callback_data=calls.PduItemOpen(id=item_id).pack()),
    ]])


def uncertain_kb(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔓 Я проверил — снять блокировку', callback_data=calls.PduItemAct(do='unlock').pack())],
        [InlineKeyboardButton(text='⬅️ К лоту', callback_data=calls.PduItemOpen(id=item_id).pack())],
    ])
