import os
import re
import sys
import html
import ctypes
import string
import logging
import textwrap
import requests
import pkg_resources
import subprocess
import shlex
import curl_cffi
import random
import time
import asyncio
import base64
from urllib.parse import urlparse
from colorlog import ColoredFormatter
from colorama import Fore, Style
from threading import Thread
from logging import getLogger
from datetime import datetime
from zoneinfo import ZoneInfo
from lib.consts import C_DIM, C_PRIMARY, C_HIGHLIGHT, C_TEXT, C_BRIGHT, C_SUCCESS, C_WARNING, C_ERROR

logger = getLogger('pl.util')


def _display_tz():
    try:
        from lib.cfg import AppConf as cfg
        name = (cfg.get('config') or {}).get('display', {}).get('timezone') or ''
        name = str(name).strip()
        if name:
            return ZoneInfo(name)
    except Exception:
        pass
    return datetime.now().astimezone().tzinfo


def iso_to_display_str(iso, fmt: str = '%d.%m.%Y · %H:%M') -> str:
    if iso is None:
        return '—'
    try:
        s = str(iso).strip().replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
    except Exception:
        return str(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    tz = _display_tz()
    try:
        return dt.astimezone(tz).strftime(fmt)
    except Exception:
        return dt.strftime(fmt)
main_loop = None
_ANSI = re.compile('\\x1b\\[[0-9;]*[A-Za-z]')


def _vlen(s: str) -> int:
    return len(_ANSI.sub('', s))


def _rpad(s: str, width: int, fill: str = ' ') -> str:
    return s + fill * max(0, width - _vlen(s))


def bind_loop(loop):
    global main_loop
    main_loop = loop


def get_loop():
    return main_loop


def halt():
    for task in asyncio.all_tasks(main_loop):
        task.cancel()
    main_loop.call_soon_threadsafe(main_loop.stop)


def clear_terminal() -> None:
    try:
        if sys.platform == 'win32':
            os.system('cls')
        else:
            os.system('clear')
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


def set_console_title(title: str):
    if sys.platform == 'win32':
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    elif sys.platform.startswith('linux'):
        sys.stdout.write(f'\x1b]2;{title}\x07')
        sys.stdout.flush()
    elif sys.platform == 'darwin':
        sys.stdout.write(f'\x1b]0;{title}\x07')
        sys.stdout.flush()


_LEVEL_BADGES = {
    'DEBUG':    (f'{Fore.LIGHTBLACK_EX}[DBG]{Fore.RESET}',   Fore.LIGHTBLACK_EX),
    'INFO':     (f'{Fore.CYAN}[INF]{Fore.RESET}',            Fore.WHITE),
    'WARNING':  (f'{Fore.YELLOW}[WRN]{Fore.RESET}',          Fore.YELLOW),
    'ERROR':    (f'{Fore.LIGHTRED_EX}[ERR]{Fore.RESET}',     Fore.LIGHTRED_EX),
    'CRITICAL': (f'{Fore.RED}[CRT]{Fore.RESET}',             Fore.RED),
}

_MODULE_TAGS = {
    'pl.conn':  ('CONN', Fore.CYAN),
    'pl.bot':   ('BOT ',  Fore.LIGHTCYAN_EX),
    'pl.feed':  ('FEED', Fore.LIGHTBLUE_EX),
    'pl.bus':   ('BUS ',  Fore.LIGHTBLACK_EX),
    'pl.ext':   ('EXT ',  Fore.LIGHTMAGENTA_EX),
    'pl.ctrl':  ('CTRL', Fore.LIGHTWHITE_EX),
    'pl.util':  ('UTIL', Fore.LIGHTBLACK_EX),
    'pl.cfg':   ('CFG ',  Fore.LIGHTBLACK_EX),
    'pl.main':  ('MAIN', Fore.LIGHTGREEN_EX),
    'pl.ui':    ('    ', Fore.LIGHTBLACK_EX),
}


def setup_logging(log_file: str = 'logs/bot.log'):

    class ConsoleFormatter(logging.Formatter):
        def format(self, record):
            from datetime import datetime as _dt
            badge, msg_color = _LEVEL_BADGES.get(record.levelname, (_LEVEL_BADGES['INFO'][0], Fore.WHITE))
            ts = _dt.now().strftime('%H:%M:%S.') + f'{_dt.now().microsecond // 1000:03d}'
            raw_tag = record.name
            tag_str, tag_color = _MODULE_TAGS.get(
                raw_tag,
                (raw_tag.split('.')[-1].upper()[:4].ljust(4), Fore.LIGHTBLACK_EX),
            )
            msg = record.getMessage()
            if record.exc_info:
                msg += '\n' + self.formatException(record.exc_info)
            return (
                f'  {Fore.LIGHTBLACK_EX}{ts}{Fore.RESET}'
                f'  {badge}'
                f'  {tag_color}{tag_str}{Fore.RESET}'
                f'  {msg_color}{msg}{Fore.RESET}'
            )

    class FileFormatter(logging.Formatter):
        def format(self, record):
            return _ANSI.sub('', super().format(record))

    os.makedirs('logs', exist_ok=True)
    console = logging.StreamHandler()
    console.setFormatter(ConsoleFormatter())
    console.setLevel(logging.INFO)
    console.name = 'pl_console'
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(FileFormatter(
        '%(asctime)s  %(levelname)-8s  %(name)-12s  %(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
    ))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(console)
    root.addHandler(fh)
    return root


_PL_LOGGERS = [
    'pl.conn', 'pl.bot', 'pl.ctrl', 'pl.bus', 'pl.ext',
    'pl.util', 'pl.feed', 'pl.cfg', 'pl.main',
]


def apply_verbose(enabled: bool) -> None:
    level = logging.DEBUG if enabled else logging.INFO
    root = logging.getLogger()
    for h in root.handlers:
        if getattr(h, 'name', '') == 'pl_console':
            h.setLevel(level)
    for name in _PL_LOGGERS:
        logging.getLogger(name).setLevel(level)
    if enabled:
        logger.info('🔍 Дебаг-лог включён — все запросы и ответы видны в консоли и файле')


_BW = 58
_LW = 18


def _b_top(title: str = '', w: int = _BW) -> str:
    if title:
        t = f' {title} '
        right = w - 4 - len(t)
        return f"{C_DIM}  ╭──{C_PRIMARY}{t}{C_DIM}{'─' * max(0, right)}╮{Fore.RESET}"
    return f"{C_DIM}  ╭{'─' * w}╮{Fore.RESET}"


def _b_sep(w: int = _BW) -> str:
    return f"{C_DIM}  ├{'─' * w}┤{Fore.RESET}"


def _b_bot(w: int = _BW) -> str:
    return f"{C_DIM}  ╰{'─' * w}╯{Fore.RESET}"


def _b_blank(w: int = _BW) -> str:
    return f"{C_DIM}  │{' ' * w}│{Fore.RESET}"


def _b_row(label: str = '', value: str = '', w: int = _BW, lw: int = _LW) -> str:
    if not label and not value:
        return _b_blank(w)
    val_w = max(1, w - lw - 4)
    lbl_plain = str(label)
    val_s = str(value)
    if len(val_s) > val_w:
        val_s = val_s[: max(0, val_w - 1)] + ('…' if val_w > 1 else '')
    lbl = f'{C_DIM}{lbl_plain:<{lw}}{Fore.RESET}'
    val_cell = f'{val_s:<{val_w}}'
    val = f'{C_HIGHLIGHT}{val_cell}{Fore.RESET}'
    return f'{C_DIM}  │{Fore.RESET}  {lbl}  {val}{C_DIM}  │{Fore.RESET}'


def _b_text(text: str, w: int = _BW, color: str = '') -> str:
    c = color or C_TEXT
    pad = w - 4
    out = []
    for chunk in textwrap.wrap(text, pad) or ['']:
        out.append(f'{C_DIM}  │{Fore.RESET}  {c}{_rpad(chunk, pad)}  {C_DIM}│{Fore.RESET}')
    return '\n'.join(out)


def draw_box(title: str, rows: list, w: int = _BW, *, lead: str = '', trail: str = '', log: logging.Logger | None = None):
    lines = [_b_top(title, w)]
    for row in rows:
        if row is None:
            lines.append(_b_blank(w))
        elif isinstance(row, tuple):
            lines.append(_b_row(str(row[0]), str(row[1]), w))
        else:
            lines.append(_b_text(str(row), w))
    lines.append(_b_bot(w))
    (log or logging.getLogger('pl.ui')).info(lead + '\n'.join(lines) + trail)


_SW = 54


def _s_rule(w: int = _SW) -> str:
    return f'  {C_DIM}{"─" * w}{Fore.RESET}'


def _s_header(step: int, total: int, title: str) -> str:
    counter = f'{C_DIM}{step}/{total}{Fore.RESET}'
    t = f'{C_BRIGHT}{title}{Fore.RESET}'
    return f'  {counter}  {t}'


def _s_line(text: str = '', color: str = '', prefix: str = '  ') -> str:
    c = color or C_TEXT
    return f'  {C_DIM}┃{Fore.RESET}{prefix}{c}{text}{Fore.RESET}'


def _s_dots(step: int, total: int) -> str:
    dots = ''.join(
        f'{C_PRIMARY}◆{Fore.RESET}' if i < step else f'{C_DIM}◇{Fore.RESET}'
        for i in range(total)
    )
    return f'  {dots}'


def setup_prompt(step: int, total: int, title: str, description: list[str], example: str = '', note: str = '', icon: str = '') -> str:
    inner = _SW - 4
    out: list[str] = ['', _s_rule(), '', _s_header(step, total, title), '']
    for line in description:
        if line == '':
            out.append('')
            continue
        for chunk in textwrap.wrap(line, inner) or ['']:
            out.append(_s_line(chunk))
    if example:
        out.extend(['', _s_line(f'e.g.  {example[:inner - 6]}', C_DIM)])
    if note:
        out.extend(['', _s_line(f'↳  {note}', C_WARNING, prefix='  ')])
    out.extend(['', _s_rule(), '', _s_dots(step, total), ''])
    logger.info('\n'.join(out))
    return input(f'  {C_PRIMARY}❯{Fore.RESET}  ').strip()


def _is_package_installed(req: str) -> bool:
    try:
        parts = shlex.split(req)
        if not parts:
            return True
        pkg_resources.require(parts[0])
        return True
    except Exception:
        return False


def check_requirements(requirements_path: str):
    try:
        if not os.path.exists(requirements_path):
            return
        with open(requirements_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('-'):
                continue
            parts = shlex.split(line)
            if parts and not _is_package_installed(parts[0]):
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', requirements_path])
                return
    except Exception as e:
        logger.error(f'Не удалось установить зависимости из «{requirements_path}»: {e}')


def monkey_patch_http():
    _orig = curl_cffi.Session.request

    def _request(self, method, url, **kwargs):
        statuses = {429: 'Too Many Requests', 500: 'Internal Server Error', 502: 'Bad Gateway', 503: 'Service Unavailable'}
        for attempt in range(6):
            resp = _orig(self, method, url, **kwargs)
            text_head = (resp.text or '')[:1200]
            for code, msg in statuses.items():
                if resp.status_code == code or msg.lower() in text_head.lower():
                    retry = resp.headers.get('Retry-After')
                    try:
                        delay = float(retry) if retry else min(120.0, 5.0 * 2 ** attempt)
                    except Exception:
                        delay = min(120.0, 5.0 * 2 ** attempt)
                    logger.debug(f'{url} — {msg}. Повтор через {delay:.1f}с.')
                    time.sleep(delay + random.uniform(0.2, 0.8))
                    break
            else:
                return resp
        return resp

    curl_cffi.Session.request = _request


def spawn_async(func: callable, args: list = [], kwargs: dict = {}):

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(func(*args, **kwargs))
        finally:
            loop.close()

    Thread(target=run, daemon=True).start()


def spawn_forever(func: callable, args: list = [], kwargs: dict = {}):

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(func(*args, **kwargs))
        try:
            loop.run_forever()
        finally:
            loop.close()

    Thread(target=run, daemon=True).start()


def token_ok(token: str) -> bool:
    if not re.match('^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$', token):
        return False
    try:
        for part in token.split('.'):
            base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))
        return True
    except Exception:
        return False


def account_reachable() -> bool:
    try:
        from pok.conn import Conn
        from lib.cfg import AppConf
        cfg = AppConf.get('config')['account']
        timeout = cfg.get('timeout') or 30
        Conn(token=cfg['token'], user_agent=cfg.get('user_agent') or '', requests_timeout=int(timeout), proxy=cfg.get('proxy') or None).get()
        return True
    except Exception:
        return False


def account_banned() -> bool:
    try:
        from pok.conn import Conn
        from lib.cfg import AppConf
        cfg = AppConf.get('config')['account']
        timeout = cfg.get('timeout') or 30
        acc = Conn(token=cfg['token'], user_agent=cfg.get('user_agent') or '', requests_timeout=int(timeout), proxy=cfg.get('proxy') or None).get()
        return acc.profile.is_blocked
    except Exception:
        return False


def ua_ok(ua: str) -> bool:
    if not ua or not 10 <= len(ua) <= 512:
        return False
    allowed = string.ascii_letters + string.digits + string.punctuation + ' '
    return all((c in allowed for c in ua))


def _vendor_proxy_host_port_user_pass(s: str) -> str | None:
    ip = r'(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)'
    m = re.match(rf'^({ip}\.{ip}\.{ip}\.{ip}):(\d+):([^:]+):(.+)$', (s or '').strip())
    if not m:
        return None
    host, port_s, user, password = m.group(1), m.group(2), m.group(3), m.group(4)
    port = int(port_s)
    if not 1 <= port <= 65535:
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
    scheme_user, userinfo, host_tail = m.group(1), m.group(2), m.group(3)
    if ':' not in userinfo:
        return None
    u0, p0 = userinfo.split(':', 1)
    parts = host_tail.split(':')
    if len(parts) < 4:
        return None
    if parts[-2] != u0 or parts[-1] != p0:
        return None
    host_and_port = ':'.join(parts[:-2])
    ip = r'(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)'
    if not re.match(rf'^({ip}\.){{3}}{ip}:\d+$', host_and_port):
        return None
    port_s = host_and_port.rsplit(':', 1)[1]
    try:
        pi = int(port_s)
    except ValueError:
        return None
    if not 1 <= pi <= 65535:
        return None
    return f'{scheme_user}{userinfo}@{host_and_port}'


def normalize_proxy_setting(proxy: str) -> str:

    s = (proxy or '').strip()
    if not s:
        return s
    low = s.lower()
    if low.startswith(('socks5://', 'socks5h://')):
        fixed = _strip_duplicate_tail_auth_socks_url(s)
        if fixed:
            s = fixed
            low = s.lower()
    if low.startswith(('socks5://', 'socks5h://', 'http://', 'https://')):
        return s
    m = re.match(r'^(socks5h|socks5)\s*:\s*(.+)$', s, re.I)
    if m:
        inner = m.group(2).strip()
        v = _vendor_proxy_host_port_user_pass(inner)
        if v:
            return f'socks5h://{v}'
        return s
    v = _vendor_proxy_host_port_user_pass(s)
    return v if v else s


def proxy_display_parts(raw: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    if not raw or not str(raw).strip():
        return (None, None, None, None)
    s = normalize_proxy_setting(str(raw).strip())
    low = s.lower()
    if low.startswith(('socks5://', 'socks5h://', 'http://', 'https://')):
        p = urlparse(s)
        if not p.hostname:
            return (None, None, None, None)
        try:
            port = str(p.port) if p.port is not None else None
        except ValueError:
            port = None
        return (p.hostname, port, p.username or None, p.password or None)
    if '@' in s:
        auth, hostport = s.rsplit('@', 1)
        if ':' not in hostport:
            return (None, None, None, None)
        host, port = hostport.rsplit(':', 1)
        user = password = None
        if auth:
            user, _, rest = auth.partition(':')
            password = rest or None
        return (host, port, user or None, password)
    if ':' in s:
        host, port = s.rsplit(':', 1)
        return (host, port, None, None)
    return (None, None, None, None)


def proxy_url_for_requests(proxy: str) -> str | None:
    if not proxy or not str(proxy).strip():
        return None
    s = normalize_proxy_setting(str(proxy).strip())
    low = s.lower()
    if low.startswith('socks5://') or low.startswith('socks5h://'):
        try:
            u = urlparse(s)
            if u.hostname and u.port and 1 <= int(u.port) <= 65535:
                return s
        except Exception:
            pass
        return None
    if low.startswith('http://') or low.startswith('https://'):
        return s.replace('https://', 'http://', 1)
    return f"http://{s.replace('https://', '').replace('http://', '')}"


def proxy_url_for_aiogram(proxy: str) -> str | None:
    p = proxy_url_for_requests(proxy)
    if not p:
        return None
    m = re.match(r'(?i)socks5h://', p)
    if m:
        return 'socks5://' + p[m.end():]
    return p


def proxy_ok(proxy: str) -> bool:
    if not proxy or not str(proxy).strip():
        return False
    s = normalize_proxy_setting(str(proxy).strip())
    low = s.lower()
    if low.startswith('socks5://') or low.startswith('socks5h://'):
        u = urlparse(s)
        try:
            port = u.port
        except ValueError:
            return False
        return bool(u.hostname and port is not None and 1 <= int(port) <= 65535)
    ip = '(?:25[0-5]|2[0-4]\\d|1\\d{2}|[1-9]?\\d)'
    p1 = re.compile(f'^{ip}\\.{ip}\\.{ip}\\.{ip}:(\\d+)$')
    p2 = re.compile(f'^[^:@]+:[^:@]+@{ip}\\.{ip}\\.{ip}\\.{ip}:(\\d+)$')
    for p in (p1, p2):
        m = p.match(s)
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
        r = requests.get(
            'http://ip-api.com/json/?fields=status,country,query',
            proxies=prx,
            timeout=timeout,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return None, None
        data = r.json()
        if data.get('status') != 'success':
            return ms, None
        country = data.get('country')
        return ms, country if country else None
    except Exception:
        return None, None


def proxy_probe_html_suffix(proxy: str) -> str:
    ms, country = proxy_http_latency_country(proxy)
    if ms is None:
        return '\n\n<i>Не удалось измерить пинг и страну выхода (проверьте HTTP-прокси).</i>'
    cc = f'\n🌍 <b>Страна выхода:</b> {html.escape(country)}' if country else ''
    return f'\n\n⚡ <b>{ms} мс</b> (запрос к ip-api через прокси){cc}'


def tg_token_ok(token: str) -> bool:
    if not token or len(token) > 128:
        return False
    return bool(re.match('^\\d{7,12}:[A-Za-z0-9_-]{30,64}$', token))


def tg_api_reachable(proxy: str | None = None) -> bool:
    url = proxy_url_for_requests(proxy) if proxy else None
    prx = {'http': url, 'https': url} if url else None
    try:
        requests.get('https://api.telegram.org/bot123:abc/getMe', proxies=prx, timeout=15)
        return True
    except requests.RequestException:
        return False


def tg_ok() -> bool:
    try:
        from lib.cfg import AppConf
        cfg = AppConf.get('config')['bot']
        token = (cfg.get('token') or '').strip()
        if not token:
            return False
        proxy = cfg.get('proxy')
        purl = proxy_url_for_requests(proxy) if proxy else None
        prx = {'http': purl, 'https': purl} if purl else None
        resp = requests.get(
            f'https://api.telegram.org/bot{token}/getMe',
            proxies=prx,
            timeout=15,
        ).json()
        return resp.get('ok') is True and resp.get('result', {}).get('is_bot') is True
    except Exception:
        return False


def password_ok(password: str) -> bool:
    if not 6 <= len(password) <= 64:
        return False
    weak = {'123456', '1234567', '12345678', '123456789', 'password', 'qwerty', 'admin', '123123', '111111', 'abc123', 'letmein', 'welcome', 'monkey', 'login', 'root', 'pass', 'test', '000000', 'user', 'qwerty123', 'iloveyou'}
    return password.lower() not in weak


