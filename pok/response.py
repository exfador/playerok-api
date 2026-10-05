from urllib.parse import urlsplit

from constants.response import OPTIONAL_RESPONSE_FIELDS
from constants.stream import SYSTEM_EVENT_ALIASES


def enrich_response(model, data):
    for attribute, source in OPTIONAL_RESPONSE_FIELDS.items():
        if hasattr(model, attribute) and source in data:
            setattr(model, attribute, data[source])
    return model


def image_rows(data):
    rows = [dict(row) for row in data.get("images") or [] if isinstance(row, dict)]
    links = data.get("imageLinks") or []
    if not isinstance(links, list):
        return rows
    known_urls = {row.get("url") for row in rows}
    for link in links:
        if not isinstance(link, str) or urlsplit(link).scheme != "https":
            continue
        if link not in known_urls:
            rows.append({"id": None, "url": link})
            known_urls.add(link)
    return rows


def merge_chat_update(existing, incoming):
    if existing is None:
        return incoming
    for key, value in vars(incoming).items():
        if value is None or key in ("users", "deals") and not value:
            continue
        setattr(existing, key, value)
    return existing


def message_event(value):
    return value if isinstance(value, str) else None


def system_event_name(message):
    event = message.event
    text = (message.text or "").strip()
    if not event and text.startswith("{{") and text.endswith("}}"):
        event = text[2:-2]
    return SYSTEM_EVENT_ALIASES.get(event, event)
