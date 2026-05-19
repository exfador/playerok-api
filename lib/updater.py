from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests

from lib.consts import VERSION
from lib.util import proxy_url_for_requests

logger = logging.getLogger('cxh.updater')

GITHUB_REPO = 'exfador/playerok-api'
_RELEASES_API = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
_RELEASES_HTML = f'https://github.com/{GITHUB_REPO}/releases'


@dataclass
class ReleaseInfo:
    tag: str
    name: str
    html_url: str
    body: str
    published_at: str
    zipball_url: str
    asset_url: Optional[str]
    asset_name: Optional[str]

    @property
    def archive_url(self) -> str:
        tag = (self.tag or '').strip()
        return f'https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.zip' if tag else ''

    @property
    def download_url(self) -> str:
        return self.asset_url or self.archive_url or self.zipball_url or self.html_url


def _normalize_tag(tag: str) -> str:
    t = (tag or '').strip()
    if t.lower().startswith('v'):
        t = t[1:]
    return t


def _parse_version(tag: str) -> tuple[int, ...]:
    nums = re.findall(r'\d+', _normalize_tag(tag))
    return tuple(int(n) for n in nums) if nums else (0,)


def is_newer(remote_tag: str, local_version: str = VERSION) -> bool:
    return _parse_version(remote_tag) > _parse_version(local_version)


def fetch_latest_release(proxy: str | None = None, timeout: int = 15) -> ReleaseInfo | None:
    purl = proxy_url_for_requests(proxy) if proxy else None
    proxies = {'http': purl, 'https': purl} if purl else None
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': f'cxh-playerok/{VERSION}',
    }
    try:
        r = requests.get(_RELEASES_API, headers=headers, proxies=proxies, timeout=timeout)
    except requests.RequestException as e:
        logger.debug('GitHub releases недоступен: %s', e)
        return None
    if r.status_code != 200:
        logger.debug('GitHub releases HTTP %s: %s', r.status_code, (r.text or '')[:200])
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    asset_url, asset_name = None, None
    for a in data.get('assets') or []:
        if not isinstance(a, dict):
            continue
        nm = str(a.get('name') or '')
        url = a.get('browser_download_url')
        if not url:
            continue
        if nm.lower().endswith(('.zip', '.tar.gz', '.tgz', '.7z')):
            asset_url, asset_name = url, nm
            break

    return ReleaseInfo(
        tag=str(data.get('tag_name') or ''),
        name=str(data.get('name') or data.get('tag_name') or ''),
        html_url=str(data.get('html_url') or _RELEASES_HTML),
        body=str(data.get('body') or ''),
        published_at=str(data.get('published_at') or ''),
        zipball_url=str(data.get('zipball_url') or ''),
        asset_url=asset_url,
        asset_name=asset_name,
    )
