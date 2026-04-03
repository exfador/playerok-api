import asyncio
import logging
import os
import sys
from colorama import Fore, init as init_colorama
from keel.netfix import apply_tls_patch
apply_tls_patch()
from keel.tone import VERSION, C_PRIMARY, C_DIM, C_BRIGHT, C_SUCCESS, C_WARNING, C_ERROR, C_TEXT
from keel.shelf import ConfigShelf as cfg, hash_password
from keel.kit import (
    clear_terminal, set_console_title, setup_logging, check_requirements, monkey_patch_http,
    bind_loop, spawn_async, setup_prompt,
    token_ok, account_reachable, account_banned,
    ua_ok, proxy_ok, proxy_reachable, tg_token_ok, tg_ok, tg_api_reachable, password_ok,
)
from keel.graft import harvest_grafts, publish_grafts, ignite_grafts
from keel.relay import broadcast

log = logging.getLogger('app.boot')

try:
    main_loop = asyncio.get_running_loop()
except RuntimeError:
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)
init_colorama()
bind_loop(main_loop)


def _blank(v) -> bool:
    return v == ''


def _need_fields(config: dict) -> int:
    fields = [
        config['bot']['token'],
        config['bot']['password_hash'],
        config['bot']['proxy'],
        config['account']['token'],
        config['account']['proxy'],
        config['account']['user_agent'],
    ]
    return max(sum(1 for f in fields if _blank(f)), 1)


async def _trim_log():
    path = 'logs/bot.log'
    while True:
        try:
            c = cfg.get('config') or {}
            max_mb = (c.get('logs') or {}).get('max_mb', 300)
            if os.path.exists(path):
                size_mb = os.path.getsize(path) / (1024 * 1024)
                if size_mb > max_mb:
                    open(path, 'w').close()
        except OSError:
            pass
        await asyncio.sleep(30)


async def _start_panel():
    from trellis.facade import Facade
    spawn_async(Facade().operate)


async def _start_engine():
    from chamber.supervisor import Supervisor
    from moor.kinds import TransportShakeError
    try:
        rt = Supervisor()
        await rt.operate()
    except TransportShakeError as e:
        log.error('  %s✗%s  Playerok недоступен (прокси или сеть).', C_ERROR, Fore.RESET)
        log.error('  %s%s', C_TEXT, str(e)[:500])
        log.error(
            '  %sПроверьте account.proxy в conf/config.json (socks5h:… для SOCKS5) или оставьте пустым; '
            'узел прокси и белый список IP у провайдера.%s',
            C_DIM,
            Fore.RESET,
        )
        raise SystemExit(1) from None


def _header() -> str:
    line = f'{C_DIM}  {"━" * 50}{Fore.RESET}'
    name = f'{C_PRIMARY}CXH Playerok{Fore.RESET}  {C_DIM}{VERSION}{Fore.RESET}'
    tagline = f'{C_DIM}автоматизация продаж на Playerok{Fore.RESET}'
    return f'\n{line}\n  {name}\n  {tagline}\n{line}\n'


def _done(msg: str):
    log.info(f'  {C_SUCCESS}✓{Fore.RESET}  {C_BRIGHT}{msg}{Fore.RESET}\n')


def _fail(msg: str):
    log.error(f'  {C_ERROR}✗{Fore.RESET}  {C_TEXT}{msg}{Fore.RESET}\n')


def _skip(msg: str):
    log.info(f'  {C_DIM}–{Fore.RESET}  {C_DIM}{msg}{Fore.RESET}\n')


def _note(msg: str):
    log.info(f'  {C_DIM}·{Fore.RESET}  {C_DIM}{msg}{Fore.RESET}\n')


def _flush_out():
    for h in logging.root.handlers:
        try:
            h.flush()
        except OSError:
            pass
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except OSError:
        pass


def _test_connections(config: dict, *, verbose: bool = True) -> bool:
    if config['account']['proxy']:
        if not proxy_reachable(config['account']['proxy']):
            _fail('Прокси Playerok недоступен — проверьте сеть/прокси или смените в настройках')
            return False
        if verbose:
            _done('Прокси Playerok — соединение есть')

    if not account_reachable():
        _fail('Не удалось войти в аккаунт Playerok — токен/сеть/прокси; конфиг не менялся')
        return False
    if verbose:
        _done('Playerok — аккаунт авторизован')

    if account_banned():
        _fail('Аккаунт заблокирован на платформе — конфиг не менялся')
        return False

    if config['bot']['proxy']:
        if not proxy_reachable(config['bot']['proxy'], 'https://api.telegram.org/'):
            _fail('Прокси Telegram недоступен — проверьте или отключите прокси в настройках')
            return False
        if verbose:
            _done('Прокси Telegram — соединение есть')

    if not tg_ok():
        if not tg_api_reachable(config['bot'].get('proxy')):
            _fail('Не удаётся достучаться до api.telegram.org — укажите прокси для Telegram или VPN (часто в РФ без этого Telegram API недоступен)')
            return False
        _fail('Неверный или отозванный токен бота — замените в conf/config.json или настройках; конфиг не менялся')
        return False

    if verbose:
        _done('Telegram-бот доступен')
    else:
        _done('Playerok и Telegram — всё в порядке')
    return True


def first_launch():
    while True:
        config = cfg.get('config')
        total = _need_fields(config)
        step = 0
        was_prompted = False

        def _field(label: str, hints: list[str], ex: str = '', note: str = '') -> str:
            nonlocal step, was_prompted
            was_prompted = True
            step += 1
            return setup_prompt(step, total, label, hints, ex, note)

        while not config['bot']['token']:
            val = _field(
                'Токен Telegram-бота',
                [
                    'Используется для управления ботом через Telegram.',
                    '',
                    'Как получить:',
                    '  1. Откройте @BotFather в Telegram',
                    '  2. Отправьте команду /newbot',
                    '  3. Скопируйте выданный токен',
                ],
                ex='123456789:abcdefghijklmnopqrstuvwxyz123456789',
            )
            if tg_token_ok(val):
                config['bot']['token'] = val
                cfg.set('config', config)
                _done('Токен сохранён')
            else:
                step -= 1
                _fail('Формат не распознан — ожидается ID:hash')

        while not config['bot']['password_hash']:
            val = _field(
                'Пароль панели управления',
                [
                    'Вводится при каждом входе в Telegram-бот.',
                    '',
                    'Требования:',
                    '  от 6 до 64 символов',
                    '  не должен быть тривиальным',
                ],
            )
            if password_ok(val):
                config['bot']['password_hash'] = hash_password(val)
                cfg.set('config', config)
                _done('Пароль установлен')
            else:
                step -= 1
                _fail('Пароль слишком простой')

        if _blank(config['bot']['proxy']):
            val = _field(
                'Прокси для Telegram',
                [
                    'Нужен если Telegram заблокирован в вашей сети.',
                    '',
                    'Формат:',
                    '  user:pass@host:port',
                    '  socks5h:host:port:user:pass  (резидентский SOCKS5)',
                    '  host:port:user:pass  (только HTTP CONNECT, не SOCKS)',
                    '  socks5h://user:pass@host:port',
                    '  host:port  (без авторизации)',
                    '',
                    '→ Enter, чтобы пропустить',
                ],
                ex='user:pass@185.10.20.30:8080',
                note='Обязателен для РФ без VPN.',
            )
            if not val:
                config['bot']['proxy'] = None
                cfg.set('config', config)
                _skip('Прокси не задан')
            elif proxy_ok(val):
                config['bot']['proxy'] = val
                cfg.set('config', config)
                _done('Прокси сохранён')
            else:
                _fail('Неверный формат адреса')
                config['bot']['proxy'] = ''

        while not config['account']['token']:
            val = _field(
                'JWT токен Playerok (cookie «token»)',
                [
                    'JWT авторизованной сессии на playerok.com.',
                    '',
                    'Как получить:',
                    '  1. Войдите на playerok.com в браузере',
                    '  2. Откройте инструменты разработчика (F12) → вкладка Application / Хранилище',
                    '  3. В разделе Cookies для playerok.com скопируйте значение cookie с именем token',
                ],
                ex='eyJhbGci...eyJzdWIi...signature',
            )
            if token_ok(val):
                config['account']['token'] = val
                cfg.set('config', config)
                _done('Токен принят')
            else:
                step -= 1
                _fail('Не похоже на JWT — должен содержать три части через точку')

        if _blank(config['account']['proxy']):
            val = _field(
                'Прокси для Playerok (JWT / запросы к площадке)',
                [
                    'HTTP или SOCKS5 к playerok.com.',
                    '',
                    'Формат:',
                    '  user:pass@host:port',
                    '  socks5h:host:port:user:pass  (резидентский SOCKS5)',
                    '  host:port:user:pass  (только HTTP, не SOCKS)',
                    '  socks5h://user:pass@host:port',
                    '  host:port  (без авторизации)',
                    '',
                    '→ Enter, чтобы пропустить',
                ],
                ex='user:pass@185.10.20.30:8080',
            )
            if not val:
                config['account']['proxy'] = None
                cfg.set('config', config)
                _skip('Прокси не задан')
            elif proxy_ok(val):
                config['account']['proxy'] = val
                cfg.set('config', config)
                _done('Прокси сохранён')
            else:
                _fail('Неверный формат адреса')
                config['account']['proxy'] = ''

        if _blank(config['account']['user_agent']):
            val = _field(
                'User-Agent браузера (Playerok)',
                [
                    'Идентифицирует ваш клиент при запросах к Playerok.',
                    'Без него авторизация может не пройти.',
                    '',
                    'Скопируйте заголовок User-Agent из того же браузера, где вы вошли на сайт:',
                    '  Chrome / Edge: F12 → Network → любой запрос к playerok.com → Request Headers',
                    '  Firefox: about:support → «Копировать данные» и найдите строку user agent',
                    '',
                    '→ Enter, чтобы пропустить (не рекомендуется)',
                ],
                ex='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/144',
            )
            if not val:
                config['account']['user_agent'] = None
                cfg.set('config', config)
                _skip('User-Agent не задан')
            elif ua_ok(val):
                config['account']['user_agent'] = val
                cfg.set('config', config)
                _done('User-Agent сохранён')
            else:
                _fail('Строка слишком короткая или содержит недопустимые символы')
                config['account']['user_agent'] = ''

        config = cfg.get('config')
        if was_prompted:
            log.info(f'  {C_DIM}{"─" * 44}{Fore.RESET}\n')
        _note('Проверяю соединения (Playerok, Telegram — до ~1 мин. при медленной сети)…')
        _flush_out()
        if _test_connections(config, verbose=was_prompted):
            break
        log.warning(
            f'  {C_WARNING}↻  Проверка не прошла{Fore.RESET} {C_DIM}— сохранённый conf/config.json не изменён.{Fore.RESET}\n'
        )
        log.info(
            f'  {C_DIM}Исправьте сеть, токены или прокси в conf/config.json и нажмите Enter для повторной проверки '
            f'(Ctrl+C — выход).{Fore.RESET}\n'
        )
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(1) from None


if __name__ == '__main__':
    try:
        clear_terminal()
        _reboot = os.environ.pop('CXH_QUICK_REBOOT', None) == '1' or os.environ.pop('CHX_QUICK_REBOOT', None) == '1'
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
        logging.getLogger('tls_requests').setLevel(logging.WARNING)
        check_requirements('requirements.txt')
        monkey_patch_http()
        setup_logging()
        set_console_title(f'CXH Playerok {VERSION}')
        if _reboot:
            log.info(f'\n  {C_DIM}↻  CXH Playerok  {VERSION}  перезапуск{Fore.RESET}\n')
        else:
            log.info(_header())
        first_launch()
        extensions = harvest_grafts()
        publish_grafts(extensions)
        main_loop.run_until_complete(ignite_grafts(extensions))

        main_loop.run_until_complete(_start_engine())
        main_loop.run_until_complete(_start_panel())
        main_loop.create_task(_trim_log())
        main_loop.run_until_complete(broadcast('BOOT_TAIL'))
        main_loop.run_forever()
    except Exception:
        log.exception('Критическая ошибка. Проверьте конфигурацию и перезапустите.')
