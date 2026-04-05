import os
import re
import sys
import html
import ctypes
import string
import logging
import textwrap
import requests
import subprocess
import shlex
import curl_cffi
import random
import shutil
import time
import asyncio
import base64
from urllib.parse import urlparse
from colorama import Fore, Style
from threading import Thread
from logging import getLogger
from datetime import datetime
from zoneinfo import ZoneInfo
from lib.consts import C_BRIGHT, C_DIM, C_HIGHLIGHT, C_PRIMARY, C_TEXT


def project_root_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def get_bot_log_path() -> str:
    day = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(project_root_dir(), 'logs', day, 'bot.log')


logger = getLogger('cxh.util')


def _app_config() -> dict:
    try:
        from lib.cfg import AppConf as cfg
        return cfg.read('config') or {}
    except Exception:
        pass
    try:
        from keel.shelf import ConfigShelf as cfg
        return cfg.get('config') or {}
    except Exception:
        return {}


def _display_tz():
    try:
        name = str((_app_config().get('display') or {}).get('timezone') or '').strip()
        if name:
            return ZoneInfo(name)
    except Exception:
        pass
    return datetime.now().astimezone().tzinfo


def iso_to_display_str(iso, fmt: str = '%d.%m.%Y · %H:%M') -> str:
    if iso is None:
        return '—'
    try:
        dt = datetime.fromisoformat(str(iso).strip().replace('Z', '+00:00'))
    except Exception:
        return str(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    try:
        return dt.astimezone(_display_tz()).strftime(fmt)
    except Exception:
        return dt.strftime(fmt)


main_loop = None


def bind_loop(loop) -> None:
    global main_loop
    main_loop = loop


def get_loop():
    return main_loop


def halt() -> None:
    for task in asyncio.all_tasks(main_loop):
        task.cancel()
    main_loop.call_soon_threadsafe(main_loop.stop)


def clear_terminal() -> None:
    try:
        os.system('cls' if sys.platform == 'win32' else 'clear')
    except OSError:
        pass


def reboot() -> None:
    os.environ['CXH_QUICK_REBOOT'] = '1'
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except OSError:
        pass
    clear_terminal()
    python = sys.executable
    try:
        os.execl(python, python, *sys.argv)
    except OSError:
        subprocess.Popen([python, *sys.argv], cwd=os.getcwd(), env={**os.environ})
        os._exit(0)


def set_console_title(title: str) -> None:
    if sys.platform == 'win32':
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    elif sys.platform.startswith('linux'):
        sys.stdout.write(f'\x1b]2;{title}\x07')
        sys.stdout.flush()
    elif sys.platform == 'darwin':
        sys.stdout.write(f'\x1b]0;{title}\x07')
        sys.stdout.flush()


_LOG_DATEFMT  = '%a, %d %b %Y %H:%M:%S'
_LOG_FILE_FMT = '[%(asctime)s] | %(levelname)s | [%(filename)s.%(funcName)s:%(lineno)d] | %(message)s'
_C_LOG_TIME   = Fore.LIGHTBLUE_EX
_C_LOG_LOC    = Fore.LIGHTMAGENTA_EX

_LEVEL_COLORS = {
    'DEBUG':    Fore.LIGHTBLACK_EX,
    'INFO':     Fore.GREEN,
    'WARNING':  Fore.YELLOW,
    'ERROR':    Fore.LIGHTRED_EX,
    'CRITICAL': Style.DIM + Fore.RED,
}

_CXH_LOGGERS = (
    'cxh.conn', 'cxh.bot', 'cxh.ctrl', 'cxh.bus', 'cxh.ext',
    'cxh.util', 'cxh.feed', 'cxh.cfg', 'cxh.boot',
    'chamber.sup', 'trellis.face', 'keel.graft', 'app.boot',
)


def apply_verbose(enabled: bool) -> None:
    level = logging.DEBUG if enabled else logging.INFO
    for h in logging.getLogger().handlers:
        if getattr(h, 'name', '') == 'pl_console':
            h.setLevel(level)
    for name in _CXH_LOGGERS:
        logging.getLogger(name).setLevel(level)
    if enabled:
        logger.info('Подробный лог включён — запросы и ответы видны в консоли и в файле')


def _config_verbose() -> bool:
    try:
        return bool((_app_config() or {}).get('debug', {}).get('verbose'))
    except Exception:
        return False


def _silence_noisy_loggers() -> None:
    noisy = (
        'urllib3', 'urllib3.connectionpool', 'urllib3.util.retry',
        'tls_requests', 'aiogram', 'aiogram.event', 'aiogram.dispatcher',
        'aiohttp.client', 'aiohttp.access', 'httpcore', 'httpx', 'asyncio',
    )
    for name in noisy:
        logging.getLogger(name).setLevel(logging.WARNING)


class _DateFolderFileHandler(logging.Handler):
    def __init__(self, logs_root: str, filename: str = 'bot.log', retention_days: int = 30) -> None:
        super().__init__(level=logging.DEBUG)
        self.logs_root      = logs_root
        self.filename       = filename
        self.retention_days = max(0, int(retention_days))
        self._stream        = None
        self._current_date: str | None = None
        self._open_for_today()

    def _today(self) -> str:
        return datetime.now().strftime('%Y-%m-%d')

    def _cleanup_old(self) -> None:
        if self.retention_days <= 0:
            return
        try:
            dated = sorted(
                d for d in os.listdir(self.logs_root)
                if os.path.isdir(os.path.join(self.logs_root, d))
                and _date_folder_valid(d)
            )
            for d in dated[:-self.retention_days]:
                full = os.path.join(self.logs_root, d)
                try:
                    for fname in os.listdir(full):
                        try:
                            os.remove(os.path.join(full, fname))
                        except OSError:
                            pass
                    os.rmdir(full)
                except OSError:
                    pass
        except OSError:
            pass

    def _open_for_today(self) -> None:
        new_date = self._today()
        if self._current_date == new_date and self._stream is not None:
            return
        try:
            if self._stream is not None:
                try:
                    self._stream.flush()
                    self._stream.close()
                except OSError:
                    pass
                self._stream = None
            day_dir = os.path.join(self.logs_root, new_date)
            os.makedirs(day_dir, exist_ok=True)
            self._stream = open(os.path.join(day_dir, self.filename), mode='a', encoding='utf-8', buffering=1)
            self._current_date = new_date
            self._cleanup_old()
        except OSError:
            self._stream = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._open_for_today()
            if self._stream is not None:
                self._stream.write(self.format(record) + '\n')
        except Exception:
            pass

    def flush(self) -> None:
        try:
            if self._stream is not None:
                self._stream.flush()
        except OSError:
            pass

    def close(self) -> None:
        try:
            if self._stream is not None:
                try:
                    self._stream.flush()
                    self._stream.close()
                except OSError:
                    pass
                self._stream = None
        finally:
            super().close()


def _date_folder_valid(name: str) -> bool:
    try:
        datetime.strptime(name, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def setup_logging(log_file: str | None = None) -> logging.Logger:
    class ConsoleFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            ts    = datetime.fromtimestamp(record.created).strftime(_LOG_DATEFMT)
            level = record.levelname
            loc   = f'[{record.filename}.{record.funcName}:{record.lineno}]'
            msg   = record.getMessage()
            exc   = ''
            if record.exc_info:
                exc = '\n' + f'{Fore.LIGHTBLACK_EX}{self.formatException(record.exc_info)}{Fore.RESET}'
            bar   = f'{C_DIM} | {Fore.RESET}'
            lc    = _LEVEL_COLORS.get(level, Fore.WHITE)
            head  = (
                f'{_C_LOG_TIME}[{ts}]{Fore.RESET}{bar}'
                f'{lc}{level}{Fore.RESET}{bar}'
                f'{_C_LOG_LOC}{loc}{Fore.RESET}{bar}'
            )
            body_lines = [s for s in msg.split('\n') if s != '']
            if not body_lines:
                return head + f'{Fore.WHITE}{msg}{Fore.RESET}' + exc
            return '\n'.join(head + f'{Fore.WHITE}{s}{Fore.RESET}' for s in body_lines) + exc

    class FileFormatter(logging.Formatter):
        def __init__(self) -> None:
            super().__init__(_LOG_FILE_FMT, datefmt=_LOG_DATEFMT)

    root_dir  = project_root_dir()
    logs_root = os.path.join(root_dir, 'logs')
    os.makedirs(logs_root, exist_ok=True)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter())
    console.setLevel(logging.INFO)
    console.name = 'pl_console'

    fh = _DateFolderFileHandler(logs_root, 'bot.log', retention_days=30)
    fh.setFormatter(FileFormatter())
    fh.name = 'pl_file_dated'

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(console)
    root.addHandler(fh)

    if log_file is not None:
        lf = log_file if os.path.isabs(log_file) else os.path.join(root_dir, log_file)
        os.makedirs(os.path.dirname(lf), exist_ok=True)
        extra = logging.FileHandler(lf, encoding='utf-8')
        extra.setLevel(logging.DEBUG)
        extra.setFormatter(FileFormatter())
        extra.name = 'pl_file_extra'
        root.addHandler(extra)

    _silence_noisy_loggers()
    apply_verbose(_config_verbose())
    return root


def draw_box(title: str, rows: list, w: int = 0, *, lead: str = '', trail: str = '', log: logging.Logger | None = None) -> None:
    tw = max(40, min(shutil.get_terminal_size((96, 20)).columns - 4, 100)) if w <= 0 else w
    rule_len = min(max(len(title) + 8, 18), tw - 2)
    lines = [
        f'{Style.BRIGHT}{C_HIGHLIGHT}{title}{Style.RESET_ALL}',
        f'{C_DIM}{"─" * rule_len}{Fore.RESET}',
    ]
    for row in rows:
        if row is None:
            lines.append('')
            continue
        if isinstance(row, tuple):
            k, v = str(row[0]), str(row[1])
            indent = len(k) - len(k.lstrip(' '))
            kl     = k.lstrip(' ')
            prefix = ' ' * (2 + indent)
            if indent >= 2:
                lines.append(f'{prefix}{C_DIM}╰ {kl}{Fore.RESET}{C_DIM} · {Fore.RESET}{C_BRIGHT}{v}{Fore.RESET}')
            else:
                lines.append(f'{prefix}{C_DIM}●{Fore.RESET} {C_DIM}{kl}{Fore.RESET}{C_DIM} · {Fore.RESET}{C_BRIGHT}{v}{Fore.RESET}')
        else:
            for chunk in textwrap.wrap(str(row), tw) or ['']:
                lines.append(f'  {C_DIM}·{Fore.RESET} {C_TEXT}{chunk}{Fore.RESET}')
    (log or logging.getLogger('pl.ui')).info(lead + '\n'.join(lines) + trail)


def setup_prompt(step: int, total: int, title: str, description: list[str], example: str = '') -> str:
    chunks = [f'[{step}/{total}] {title}']
    chunks.extend(ln.strip() for ln in description if ln.strip())
    text = ' · '.join(chunks)
    if example:
        text = f'{text} · Пример: {example}'
    logger.info(text)
    return input('> ').strip()


def _ensure_packaging() -> None:
    try:
        import packaging.requirements  
    except ImportError:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '-q', 'packaging>=23'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _requirement_line_satisfied(req_line: str) -> bool:
    req_line = req_line.strip()
    if not req_line or req_line.startswith(('#', '-')):
        return True
    from packaging.requirements import Requirement
    from packaging.markers import default_environment
    from importlib.metadata import PackageNotFoundError, version
    from packaging.version import parse as parse_version
    try:
        req = Requirement(req_line)
    except Exception:
        return True
    try:
        if req.marker and not req.marker.evaluate(default_environment()):
            return True
    except Exception:
        return True
    try:
        installed_v = parse_version(version(req.name))
    except PackageNotFoundError:
        return False
    return req.specifier.contains(installed_v, prereleases=True)


def check_requirements(requirements_path: str) -> None:
    try:
        if not os.path.exists(requirements_path):
            return
        _ensure_packaging()
        with open(requirements_path, encoding='utf-8') as f:
            lines = f.readlines()
        needs_install = any(
            not _requirement_line_satisfied(ln.strip())
            for ln in lines
            if ln.strip() and not ln.strip().startswith(('#', '-'))
        )
        if needs_install:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '-r', requirements_path])
    except Exception as e:
        logger.error('Не удалось установить зависимости из «%s»: %s', requirements_path, e)


def monkey_patch_http() -> None:
    _orig = curl_cffi.Session.request
    _RETRY_CODES = {429: 'Too Many Requests', 500: 'Internal Server Error', 502: 'Bad Gateway', 503: 'Service Unavailable'}

    def _request(self, method, url, **kwargs):
        for attempt in range(6):
            resp = _orig(self, method, url, **kwargs)
            head = (resp.text or '')[:1200].lower()
            retry_on = next(
                (msg for code, msg in _RETRY_CODES.items()
                 if resp.status_code == code or msg.lower() in head),
                None,
            )
            if retry_on is None:
                return resp
            raw_retry = resp.headers.get('Retry-After')
            try:
                delay = float(raw_retry) if raw_retry else min(120.0, 5.0 * 2 ** attempt)
            except Exception:
                delay = min(120.0, 5.0 * 2 ** attempt)
            logger.debug('%s — %s. Повтор через %.1f с.', url, retry_on, delay)
            time.sleep(delay + random.uniform(0.2, 0.8))
        return resp

    curl_cffi.Session.request = _request


def spawn_async(func: callable, args: list | None = None, kwargs: dict | None = None) -> None:
    _args   = list(args or [])
    _kwargs = dict(kwargs or {})
    log     = logging.getLogger('cxh.util')

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(func(*_args, **_kwargs))
        except Exception:
            log.exception(
                'spawn_async: поток панели Telegram завершился с ошибкой. '
                'Опрос не работает, пока не исправите; в логах не будет [tg].'
            )
            try:
                print('[spawn_async] Ошибка в потоке Telegram — см. logs/bot.log.', file=sys.stderr, flush=True)
            except Exception:
                pass
        finally:
            try:
                loop.close()
            except Exception:
                pass

    Thread(target=_run, daemon=True, name='TelegramPanel').start()


def spawn_forever(func: callable, args: list = [], kwargs: dict = {}) -> None:
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(func(*args, **kwargs))
        try:
            loop.run_forever()
        finally:
            loop.close()

    Thread(target=_run, daemon=True).start()


def token_ok(token: str) -> bool:
    if not re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', token):
        return False
    try:
        for part in token.split('.'):
            base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))
        return True
    except Exception:
        return False


def account_reachable() -> bool:
    for loader in (_load_conn_pok, _load_conn_moor):
        try:
            loader()
            return True
        except Exception:
            pass
    return False


def _load_conn_pok():
    from pok.conn import Conn
    from lib.cfg import AppConf
    c = AppConf.read('config')['account']
    Conn(token=c['token'], user_agent=c.get('user_agent') or '', requests_timeout=int(c.get('timeout') or 30), proxy=c.get('proxy') or None).get()


def _load_conn_moor():
    from moor.sessiongate import SessionGate
    from keel.shelf import ConfigShelf
    c = ConfigShelf.get('config')['account']
    SessionGate(token=c['token'], user_agent=c.get('user_agent') or '', requests_timeout=int(c.get('timeout') or 30), proxy=c.get('proxy') or None).get()


def account_banned() -> bool:
    for loader, getter in (
        (_load_conn_pok_acc, lambda a: a.profile.is_blocked),
        (_load_conn_moor_acc, lambda a: a.profile.is_blocked),
    ):
        try:
            return getter(loader())
        except Exception:
            pass
    return False


def _load_conn_pok_acc():
    from pok.conn import Conn
    from lib.cfg import AppConf
    c = AppConf.read('config')['account']
    return Conn(token=c['token'], user_agent=c.get('user_agent') or '', requests_timeout=int(c.get('timeout') or 30), proxy=c.get('proxy') or None).get()


def _load_conn_moor_acc():
    from moor.sessiongate import SessionGate
    from keel.shelf import ConfigShelf
    c = ConfigShelf.get('config')['account']
    return SessionGate(token=c['token'], user_agent=c.get('user_agent') or '', requests_timeout=int(c.get('timeout') or 30), proxy=c.get('proxy') or None).get()


def ua_ok(ua: str) -> bool:
    if not ua or not 10 <= len(ua) <= 512:
        return False
    allowed = string.ascii_letters + string.digits + string.punctuation + ' '
    return all(c in allowed for c in ua)


def _vendor_proxy_host_port_user_pass(s: str) -> str | None:
    ip = r'(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)'
    m = re.match(rf'^({ip}\.{ip}\.{ip}\.{ip}):(\d+):([^:]+):(.+)$', (s or '').strip())
    if not m:
        return None
    host, port_s, user, password = m.group(1), m.group(2), m.group(3), m.group(4)
    if not 1 <= int(port_s) <= 65535:
        return None
    return f'{user}:{password}@{host}:{port_s}'


def _strip_duplicate_tail_auth_socks_url(s: str) -> str | None:
    low = (s or '').strip().lower()
    if not low.startswith(('socks5://', 'socks5h://')):
        return None
    try:
        u = urlparse(s.strip())
        if u.port is not None and 1 <= u.port <= 65535:
            return None
    except ValueError:
        pass
    m = re.match(r'^(socks5h?://)([^@]+)@(.+)$', s.strip(), re.I)
    if not m:
        return None
    scheme, userinfo, host_tail = m.group(1), m.group(2), m.group(3)
    if ':' not in userinfo:
        return None
    u0, p0 = userinfo.split(':', 1)
    parts = host_tail.split(':')
    if len(parts) < 4 or parts[-2] != u0 or parts[-1] != p0:
        return None
    host_and_port = ':'.join(parts[:-2])
    ip = r'(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)'
    if not re.match(rf'^({ip}\.){{3}}{ip}:\d+$', host_and_port):
        return None
    port_s = host_and_port.rsplit(':', 1)[1]
    try:
        if not 1 <= int(port_s) <= 65535:
            return None
    except ValueError:
        return None
    return f'{scheme}{userinfo}@{host_and_port}'


def normalize_proxy_setting(proxy: str) -> str:
    s = (proxy or '').strip()
    if not s:
        return s
    low = s.lower()
    if low.startswith(('socks5://', 'socks5h://')):
        fixed = _strip_duplicate_tail_auth_socks_url(s)
        if fixed:
            s, low = fixed, fixed.lower()
    if low.startswith(('socks5://', 'socks5h://', 'http://', 'https://')):
        return s
    m = re.match(r'^(socks5h|socks5)\s*:\s*(.+)$', s, re.I)
    if m:
        inner = m.group(2).strip()
        v = _vendor_proxy_host_port_user_pass(inner)
        return f'socks5h://{v}' if v else s
    v = _vendor_proxy_host_port_user_pass(s)
    return v if v else s


def proxy_display_parts(raw: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    if not raw or not str(raw).strip():
        return None, None, None, None
    s = normalize_proxy_setting(str(raw).strip())
    if s.lower().startswith(('socks5://', 'socks5h://', 'http://', 'https://')):
        p = urlparse(s)
        if not p.hostname:
            return None, None, None, None
        try:
            port = str(p.port) if p.port is not None else None
        except ValueError:
            port = None
        return p.hostname, port, p.username or None, p.password or None
    if '@' in s:
        auth, hostport = s.rsplit('@', 1)
        if ':' not in hostport:
            return None, None, None, None
        host, port = hostport.rsplit(':', 1)
        user, _, rest = auth.partition(':')
        return host, port, user or None, rest or None
    if ':' in s:
        host, port = s.rsplit(':', 1)
        return host, port, None, None
    return None, None, None, None


def proxy_url_for_requests(proxy: str) -> str | None:
    if not proxy or not str(proxy).strip():
        return None
    s = normalize_proxy_setting(str(proxy).strip())
    low = s.lower()
    if low.startswith(('socks5://', 'socks5h://')):
        try:
            u = urlparse(s)
            if u.hostname and u.port and 1 <= int(u.port) <= 65535:
                return s
        except Exception:
            pass
        return None
    if low.startswith(('http://', 'https://')):
        return s.replace('https://', 'http://', 1)
    return f"http://{s.replace('https://', '').replace('http://', '')}"


def proxy_url_for_aiogram(proxy: str) -> str | None:
    p = proxy_url_for_requests(proxy)
    if not p:
        return None
    m = re.match(r'(?i)socks5h://', p)
    return ('socks5://' + p[m.end():]) if m else p


def proxy_ok(proxy: str) -> bool:
    if not proxy or not str(proxy).strip():
        return False
    s = normalize_proxy_setting(str(proxy).strip())
    low = s.lower()
    if low.startswith(('socks5://', 'socks5h://')):
        u = urlparse(s)
        try:
            port = u.port
        except ValueError:
            return False
        return bool(u.hostname and port is not None and 1 <= int(port) <= 65535)
    ip = r'(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)'
    for pattern in (
        re.compile(rf'^{ip}\.{ip}\.{ip}\.{ip}:(\d+)$'),
        re.compile(rf'^[^:@]+:[^:@]+@{ip}\.{ip}\.{ip}\.{ip}:(\d+)$'),
    ):
        m = pattern.match(s)
        if m:
            return 1 <= int(m.group(1)) <= 65535
    return False


def proxy_reachable(proxy: str, test_url: str = 'https://playerok.com', timeout: int = 10) -> bool:
    url = proxy_url_for_requests(proxy)
    if not url:
        return False
    prx = {'http': url, 'https': url}
    try:
        return requests.get(test_url, proxies=prx, timeout=timeout).status_code < 404
    except Exception:
        return False


def proxy_http_latency_country(proxy: str, timeout: float = 10.0) -> tuple[int | None, str | None]:
    url = proxy_url_for_requests(proxy)
    if not url:
        return None, None
    prx = {'http': url, 'https': url}
    t0 = time.perf_counter()
    try:
        r = requests.get('http://ip-api.com/json/?fields=status,country,query', proxies=prx, timeout=timeout)
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return None, None
        data = r.json()
        if data.get('status') != 'success':
            return ms, None
        country = data.get('country')
        return ms, country or None
    except Exception:
        return None, None


def proxy_probe_html_suffix(proxy: str) -> str:
    ms, country = proxy_http_latency_country(proxy)
    if ms is None:
        return '\n\n<i>Не удалось измерить задержку и страну выхода (проверьте HTTP-прокси).</i>'
    cc = f'\n🌍 <b>Страна выхода:</b> {html.escape(country)}' if country else ''
    return f'\n\n⚡ <b>{ms} мс</b> (запрос к ip-api через прокси){cc}'


def tg_token_ok(token: str) -> bool:
    return bool(token and len(token) <= 128 and re.match(r'^\d{7,12}:[A-Za-z0-9_-]{30,64}$', token))


def tg_api_reachable(proxy: str | None = None) -> bool:
    url = proxy_url_for_requests(proxy) if proxy else None
    prx = {'http': url, 'https': url} if url else None
    try:
        requests.get('https://api.telegram.org/bot123:abc/getMe', proxies=prx, timeout=15)
        return True
    except requests.RequestException:
        return False


def _check_tg_token_via_api(token: str, proxy: str | None) -> bool:
    purl = proxy_url_for_requests(proxy) if proxy else None
    prx  = {'http': purl, 'https': purl} if purl else None
    resp = requests.get(f'https://api.telegram.org/bot{token}/getMe', proxies=prx, timeout=15).json()
    return resp.get('ok') is True and resp.get('result', {}).get('is_bot') is True


def tg_ok() -> bool:
    for config_getter in (_get_tg_config_pok, _get_tg_config_keel):
        try:
            token, proxy = config_getter()
            if not token:
                continue
            return _check_tg_token_via_api(token, proxy)
        except Exception:
            pass
    return False


def _get_tg_config_pok() -> tuple[str, str | None]:
    from lib.cfg import AppConf
    cfg = AppConf.read('config')['bot']
    return (cfg.get('token') or '').strip(), cfg.get('proxy')


def _get_tg_config_keel() -> tuple[str, str | None]:
    from keel.shelf import ConfigShelf
    cfg = ConfigShelf.get('config')['bot']
    return (cfg.get('token') or '').strip(), cfg.get('proxy')


def _password_has_simple_sequence(s: str, window: int = 4) -> bool:
    low = s.lower()
    for i in range(len(low) - window + 1):
        vals = [ord(low[i + k]) for k in range(window)]
        if all(vals[k] == vals[k - 1] + 1 for k in range(1, window)):
            return True
        if all(vals[k] == vals[k - 1] - 1 for k in range(1, window)):
            return True
    return False


def password_ok(password: str) -> bool:
    if not isinstance(password, str):
        return False
    if not 6 <= len(password) <= 64:
        return False
    if password.strip() != password or any(ord(c) < 32 for c in password):
        return False
    if len(set(password)) < 3 or password.isdigit():
        return False
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(c in string.punctuation for c in password),
    ])
    if classes < 2:
        return False
    if len(password) <= 10 and classes < 3:
        return False
    if re.search(r'(.)\1{3,}', password):
        return False
    if _password_has_simple_sequence(password, 4):
        return False
    return True
