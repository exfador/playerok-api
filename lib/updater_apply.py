from __future__ import annotations

import logging
import os
import shutil
import stat
import threading
import time
import tempfile
import zipfile
from typing import Callable

import requests

from lib.consts import VERSION
from lib.util import proxy_url_for_requests

logger = logging.getLogger('cxh.updater.apply')

_PRESERVE = {
    '.git', '.github', '.venv', 'venv', '.idea', '.vscode', 'node_modules',
    '__pycache__',
    'conf', 'db', 'logs',
    'requirements.txt.local',
    'cookies.json', 'config.json',
}
_PRESERVE_FILES = {'.env', '.envrc', 'playerok_state.json'}


def download_to_file(url: str, dest_path: str, proxy: str | None = None,
                     progress_cb: Callable[[int, int], None] | None = None,
                     timeout: int = 60) -> None:
    purl = proxy_url_for_requests(proxy) if proxy else None
    proxies = {'http': purl, 'https': purl} if purl else None
    headers = {'User-Agent': f'cxh-playerok/{VERSION}', 'Accept': 'application/octet-stream'}
    with requests.get(url, stream=True, proxies=proxies, headers=headers, timeout=timeout, allow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get('Content-Length') or 0)
        os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
        done = 0
        last_report = 0.0
        with open(dest_path, 'wb') as fh:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                fh.write(chunk)
                done += len(chunk)
                if progress_cb:
                    now = time.time()
                    if now - last_report >= 0.5 or (total and done == total):
                        last_report = now
                        try:
                            progress_cb(done, total)
                        except Exception:
                            pass
    if total and done < total:
        raise IOError(f'Скачано {done} из {total} байт — обрыв соединения')


def extract_zip(zip_path: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for name in names:
            if name.startswith(('/', '..', '\\')) or '..' in name.replace('\\', '/').split('/'):
                raise ValueError(f'Опасный путь в архиве: {name!r}')
        zf.extractall(out_dir)
    entries = [e for e in os.listdir(out_dir) if not e.startswith('.')]
    if len(entries) == 1 and os.path.isdir(os.path.join(out_dir, entries[0])):
        return os.path.join(out_dir, entries[0])
    return out_dir


def _iter_tree(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRESERVE]
        for f in filenames:
            yield os.path.join(dirpath, f)


def _rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace('\\', '/')


def _should_skip_src(rel: str) -> bool:
    parts = rel.split('/')
    if parts[0] in _PRESERVE:
        return True
    if parts[-1] in _PRESERVE_FILES:
        return True
    return False


def apply_update(src_root: str, live_root: str, logger_cb: Callable[[str], None] | None = None) -> dict:
    log = logger_cb or (lambda m: logger.info(m))
    skipped = 0
    errors: list[str] = []
    sources: list[tuple[str, str]] = []
    for src_path in _iter_tree(src_root):
        rel = _rel(src_root, src_path)
        if _should_skip_src(rel):
            skipped += 1
            continue
        sources.append((src_path, rel))

    live_parent = os.path.dirname(os.path.abspath(live_root)) or '.'
    os.makedirs(live_parent, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cxh-update-', dir=live_parent) as work_dir:
        staged_root = os.path.join(work_dir, 'staged')
        backup_root = os.path.join(work_dir, 'backup')
        for src_path, rel in sources:
            staged_path = os.path.join(staged_root, rel)
            os.makedirs(os.path.dirname(staged_path), exist_ok=True)
            try:
                shutil.copy2(src_path, staged_path)
            except OSError as e:
                errors.append(f'{rel}: {e}')
                log(f'Ошибка подготовки {rel}: {e}')
        if errors:
            log(f'Обновление отменено до изменения рабочей копии: ошибок {len(errors)}')
            return {'copied': 0, 'skipped': skipped, 'errors': errors}

        applied: list[tuple[str, str | None]] = []
        try:
            for _, rel in sources:
                staged_path = os.path.join(staged_root, rel)
                dst_path = os.path.join(live_root, rel)
                os.makedirs(os.path.dirname(dst_path) or '.', exist_ok=True)
                backup_path = None
                if os.path.exists(dst_path):
                    try:
                        os.chmod(dst_path, stat.S_IWRITE | stat.S_IREAD)
                    except OSError:
                        pass
                    backup_path = os.path.join(backup_root, rel)
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(dst_path, backup_path)
                os.replace(staged_path, dst_path)
                applied.append((dst_path, backup_path))
        except OSError as e:
            errors.append(str(e))
            for dst_path, backup_path in reversed(applied):
                try:
                    if backup_path is None:
                        os.unlink(dst_path)
                    else:
                        os.replace(backup_path, dst_path)
                except OSError as rollback_error:
                    errors.append(f'rollback {dst_path}: {rollback_error}')
            log(f'Обновление отменено и откачено: ошибок {len(errors)}')
            return {'copied': 0, 'skipped': skipped, 'errors': errors}

    copied = len(sources)
    log(f'Обновление: скопировано {copied}, пропущено {skipped}, ошибок 0')
    return {'copied': copied, 'skipped': skipped, 'errors': []}


def schedule_reboot(delay_sec: float = 3.0) -> None:
    def _do():
        time.sleep(delay_sec)
        try:
            from lib.util import reboot
            reboot()
        except Exception:
            logger.exception('Не удалось перезапустить процесс')
            os._exit(1)
    threading.Thread(target=_do, daemon=True, name='cxh-reboot').start()


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
