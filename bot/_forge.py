from __future__ import annotations
import html
from urllib.parse import urlsplit

from pok.models import ChatMessage
from pok.response import system_event_name

EVENT_LABELS: dict[str, str] = {
    'ITEM_PAID':             '💳 Оплата по сделке (заказ создан)',
    'ITEM_SENT':             '📤 Продавец отправил товар',
    'DEAL_CONFIRMED':        '✅ Покупатель подтвердил получение',
    'DEAL_ROLLED_BACK':      '↩️ Возврат / сделка отменена',
    'DEAL_HAS_PROBLEM':      '⚠️ Жалоба по сделке',
    'DEAL_PROBLEM_RESOLVED': '✔️ Жалоба снята',
    'CHAT_STARTED':          '💬 Начат чат',
}

SYS_MSG_LABELS: dict[str, str] = {f'{{{{{name}}}}}': label for name, label in EVENT_LABELS.items()}

BUTTON_LABELS: dict[str, str] = {
    'ASK_FOR_EXTERNAL_REVIEW': 'Оставить отзыв',
    'LOTTERY': 'Розыгрыш',
    'LOTTERY_RESULTS': 'Итоги розыгрыша',
    'CURRENT_BALANCE': 'Баланс',
}


def _humanize_msg(text: str | None) -> str | None:
    if not text:
        return None
    return SYS_MSG_LABELS.get(text.strip(), text)


def _event_label(message: ChatMessage) -> str | None:
    if getattr(message, 'event', None) is None and not (message.text or '').strip().startswith('{{'):
        return None
    name = system_event_name(message)
    if not name:
        return None
    return EVENT_LABELS.get(name, f'ℹ️ Событие {name}')


def _buttons(message: ChatMessage) -> list[tuple[str, str]]:
    rows = []
    for button in getattr(message, 'buttons', None) or []:
        url = getattr(button, 'url', None) or ''
        if not button or urlsplit(url).scheme not in ('http', 'https'):
            continue
        kind = getattr(getattr(button, 'type', None), 'name', None)
        rows.append(((getattr(button, 'text', None) or BUTTON_LABELS.get(kind) or 'Ссылка').strip(), url))
    return rows


def _build_plain(message: ChatMessage) -> str:
    parts: list[str] = []
    label = _event_label(message)
    if label:
        parts.append(label)
    elif message.text:
        parts.append(message.text)
    if message.file is not None:
        if getattr(message.file, 'url', None):
            parts.append(f'[файл] {message.file.filename or "файл"} | {message.file.url}')
        else:
            parts.append(f'[файл] id={message.file.id}')
    for im in (message.images or []):
        if im is None:
            continue
        parts.append(f'[изображение] {im.url}' if getattr(im, 'url', None) else f'[изображение] id={im.id}')
    for text, url in _buttons(message):
        parts.append(f'[кнопка] {text}: {url}')
    return '\n'.join(parts)


def _build_html(message: ChatMessage) -> str:
    parts: list[str] = []
    label = _event_label(message)
    if label:
        parts.append(html.escape(label))
    elif message.text:
        parts.append(html.escape(message.text))
    if message.file is not None:
        if getattr(message.file, 'url', None):
            fn = html.escape(message.file.filename or 'файл')
            u  = html.escape(message.file.url)
            parts.append(f'📎 <a href="{u}">{fn}</a>')
        else:
            parts.append(f'📎 файл (id: {html.escape(str(message.file.id))})')
    for im in (message.images or []):
        if im is None:
            continue
        if getattr(im, 'url', None):
            parts.append(f'📷 <a href="{html.escape(im.url)}">изображение</a>')
        else:
            parts.append(f'📷 изображение (id: {html.escape(str(im.id))})')
    for text, url in _buttons(message):
        parts.append(f'🔗 <a href="{html.escape(url)}">{html.escape(text)}</a>')
    return '\n'.join(parts) or '<i>нет текста</i>'


def message_body_html(message: ChatMessage) -> str:
    return _build_html(message)


def first_link_preview_url(message: ChatMessage) -> str | None:
    for im in (message.images or []):
        if im is not None and getattr(im, 'url', None):
            return im.url
    f = message.file
    return f.url if f is not None and getattr(f, 'url', None) else None
