from __future__ import annotations
import html
from pok.models import ChatMessage

SYS_MSG_LABELS: dict[str, str] = {
    '{{ITEM_PAID}}':             '💳 Оплата по сделке (заказ создан)',
    '{{ITEM_SENT}}':             '📤 Продавец отправил товар',
    '{{DEAL_CONFIRMED}}':        '✅ Покупатель подтвердил получение',
    '{{DEAL_ROLLED_BACK}}':      '↩️ Возврат / сделка отменена',
    '{{DEAL_HAS_PROBLEM}}':      '⚠️ Жалоба по сделке',
    '{{DEAL_PROBLEM_RESOLVED}}': '✔️ Жалоба снята',
}


def _humanize_msg(text: str | None) -> str | None:
    if not text:
        return None
    return SYS_MSG_LABELS.get(text.strip(), text)


def _build_plain(message: ChatMessage) -> str:
    parts: list[str] = []
    if message.text:
        parts.append(_humanize_msg(message.text) or '')
    if message.file is not None:
        if getattr(message.file, 'url', None):
            parts.append(f'[файл] {message.file.filename or "файл"} | {message.file.url}')
        else:
            parts.append(f'[файл] id={message.file.id}')
    for im in (message.images or []):
        if im is None:
            continue
        parts.append(f'[изображение] {im.url}' if getattr(im, 'url', None) else f'[изображение] id={im.id}')
    return '\n'.join(parts)


def _build_html(message: ChatMessage) -> str:
    parts: list[str] = []
    if message.text:
        shown = _humanize_msg(message.text)
        raw   = (message.text or '').strip()
        parts.append(html.escape(shown if shown and shown != raw else message.text))
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
    return '\n'.join(parts) or '<i>нет текста</i>'


def message_body_html(message: ChatMessage) -> str:
    return _build_html(message)


def first_link_preview_url(message: ChatMessage) -> str | None:
    for im in (message.images or []):
        if im is not None and getattr(im, 'url', None):
            return im.url
    f = message.file
    return f.url if f is not None and getattr(f, 'url', None) else None
