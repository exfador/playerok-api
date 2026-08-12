from __future__ import annotations
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import requests

from lib.consts import VERSION
from lib.util import proxy_url_for_requests

logger = logging.getLogger('cxh.broadcast')

DEFAULT_SOURCE = 'https://api.github.com/gists/89e52dbb3ca81aee82b6a3d8b51b55e2'

_SEP = '␟'
_CONTAINER_KEYS = ('messages', 'items', 'posts', 'entries', 'bulletins', 'list')
_TEXT_KEYS = ('text', 'body', 'message', 'content', 'md')
_TITLE_KEYS = ('title', 'header', 'subject', 'name')
_URL_KEYS = ('url', 'link', 'href')
_ID_KEYS = ('id', 'tag', 'uid', 'slug', 'key')

_GIST_ID_RE = re.compile(r'(?:gists/|gist\.github\.com/(?:[^/]+/)?)([0-9a-fA-F]{20,})')
_BTN_RE = re.compile(r'\[\s*([^\]|]+?)\s*\|\s*([^\]\s][^\]]*?)\s*\]')
_HTML_HINT = re.compile(r'</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler|span)\b', re.I)


@dataclass
class Bulletin:
    key: str
    title: str
    text: str
    pinned: bool
    html: bool
    buttons: list = field(default_factory=list)


def _pick(raw: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = raw.get(k)
        if v:
            return str(v).strip()
    return ''


def _gist_id(src: str) -> str | None:
    m = _GIST_ID_RE.search(src or '')
    return m.group(1) if m else None


def _normalize_url(u: str) -> str:
    u = (u or '').strip()
    if not u:
        return ''
    if u.startswith(('http://', 'https://', 'tg://', 'mailto:')):
        return u
    return 'https://' + u.lstrip('/')


def _parse_markup(body: str) -> tuple[str, list]:
    buttons: list = []

    def _grab(m: re.Match) -> str:
        label = m.group(1).strip()
        url = _normalize_url(m.group(2))
        if label and url:
            buttons.append([label, url])
        return ''

    text = _BTN_RE.sub(_grab, body or '')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text, buttons


def _comment_bulletins(comments: list) -> list[Bulletin]:
    out: list[Bulletin] = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        raw_body = str(c.get('body') or '')
        text, buttons = _parse_markup(raw_body)
        if not text and not buttons:
            continue
        cid = str(c.get('id') or '').strip()
        stamp = str(c.get('updated_at') or c.get('created_at') or '').strip()
        if cid:
            key = f'c:{cid}@{stamp}' if stamp else f'c:{cid}'
        else:
            key = 'h:' + hashlib.sha256((raw_body + stamp).encode('utf-8')).hexdigest()[:24]
        out.append(Bulletin(
            key=key, title='', text=text,
            pinned=False, html=bool(_HTML_HINT.search(raw_body)), buttons=buttons,
        ))
    return out


def _coerce_items(payload: Any) -> list[dict]:
    if isinstance(payload, dict):
        for fkey in _CONTAINER_KEYS:
            seq = payload.get(fkey)
            if isinstance(seq, list):
                return [x for x in seq if isinstance(x, dict)]
        if any(k in payload for k in _TEXT_KEYS + _TITLE_KEYS):
            return [payload]
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def _digest(raw: dict, title: str, text: str, btn_sig: str) -> str:
    explicit = _pick(raw, _ID_KEYS)
    if explicit:
        return 'k:' + explicit
    basis = _SEP.join((title, text, btn_sig)).encode('utf-8')
    return 'h:' + hashlib.sha256(basis).hexdigest()[:24]


def _normalize_item(raw: dict) -> Bulletin | None:
    title = _pick(raw, _TITLE_KEYS)
    body = _pick(raw, _TEXT_KEYS)
    text, inline_buttons = _parse_markup(body)
    buttons = list(inline_buttons)
    direct = _pick(raw, _URL_KEYS)
    if direct:
        label = str(raw.get('button') or raw.get('button_text') or 'Открыть').strip() or 'Открыть'
        buttons.append([label, _normalize_url(direct)])
    extra = raw.get('buttons')
    if isinstance(extra, list):
        for e in extra:
            if isinstance(e, dict):
                lbl = str(e.get('label') or e.get('text') or 'Открыть').strip()
                url = _normalize_url(str(e.get('url') or e.get('link') or ''))
                if lbl and url:
                    buttons.append([lbl, url])
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                buttons.append([str(e[0]).strip(), _normalize_url(str(e[1]))])
    if not title and not text and not buttons:
        return None
    btn_sig = '|'.join(f'{b[0]}>{b[1]}' for b in buttons)
    pinned = bool(raw.get('pin') or raw.get('pinned') or raw.get('important'))
    html = bool(raw.get('html') or raw.get('parse_html') or _HTML_HINT.search(body))
    return Bulletin(
        key=_digest(raw, title, text, btn_sig),
        title=title, text=text, pinned=pinned, html=html, buttons=buttons,
    )


def _http_get(url: str, headers: dict, proxies: dict | None, timeout: int):
    try:
        return requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
    except requests.RequestException as e:
        logger.debug('Источник рассылки недоступен (%s): %s', url, e)
        return None


def fetch_bulletins(source: str, proxy: str | None = None, timeout: int = 12) -> list[Bulletin]:
    src = (source or '').strip()
    if not src:
        return []
    purl = proxy_url_for_requests(proxy) if proxy else None
    proxies = {'http': purl, 'https': purl} if purl else None
    base_headers = {'User-Agent': f'cxh-playerok/{VERSION}', 'Accept': '*/*'}

    gist_id = _gist_id(src)
    if gist_id:
        gh_headers = dict(base_headers)
        gh_headers['Accept'] = 'application/vnd.github+json'
        gh_headers['X-GitHub-Api-Version'] = '2022-11-28'
        meta_url = f'https://api.github.com/gists/{gist_id}'
        meta = _http_get(meta_url, gh_headers, proxies, timeout)
        if meta is None or meta.status_code != 200:
            return []
        try:
            trusted_login = str((meta.json().get('owner') or {}).get('login') or '').lower()
        except (ValueError, AttributeError):
            return []
        if not trusted_login:
            return []
        url = f'https://api.github.com/gists/{gist_id}/comments?per_page=100'
        r = _http_get(url, gh_headers, proxies, timeout)
        if r is None or r.status_code != 200:
            if r is not None:
                logger.debug('Комментарии gist вернули HTTP %s', r.status_code)
            return []
        try:
            comments = r.json()
        except ValueError:
            return []
        if not isinstance(comments, list):
            return []
        trusted_comments = [
            comment for comment in comments
            if isinstance(comment, dict)
            and str(((comment.get('user') or {}).get('login')) or '').lower() == trusted_login
        ]
        return _dedupe(_comment_bulletins(trusted_comments))

    r = _http_get(src, base_headers, proxies, timeout)
    if r is None or r.status_code != 200:
        if r is not None:
            logger.debug('Источник рассылки вернул HTTP %s', r.status_code)
        return []
    try:
        body: Any = r.json()
    except ValueError:
        body = r.text
    items = _coerce_items(body)
    if not items and isinstance(body, str) and body.strip():
        text, _ = _parse_markup(body)
        if text:
            items = [{'text': text}]
    bulletins = [b for b in (_normalize_item(x) for x in items) if b is not None]
    return _dedupe(bulletins)


def _dedupe(bulletins: list[Bulletin]) -> list[Bulletin]:
    out: list[Bulletin] = []
    local: set[str] = set()
    for b in bulletins:
        if b.key in local:
            continue
        local.add(b.key)
        out.append(b)
    return out
