
import asyncio
import logging
import os
import signal
import sys
from typing import Dict, Any, Optional, List

from colorama import Fore, init as colorama_init

from lib.tls_patch import apply_tls_patch

apply_tls_patch()

import lib.consts as const
import lib.cfg as cfgmod
import lib.util as ut
import lib.ext as extmod
import lib.bus as busmod

LOG = logging.getLogger('cxh.boot')
COLOR_MAP = {
    'primary': const.C_PRIMARY,
    'success': const.C_SUCCESS,
    'warning': const.C_WARNING,
    'error': const.C_ERROR,
    'text': const.C_TEXT,
    'dim': const.C_DIM,
    'bright': const.C_BRIGHT,
}


class CXHBot:

    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_flag = False

    @staticmethod
    def _log_status(level: str, msg: str, *, icon: str = '', newline: bool = True) -> None:
        color = COLOR_MAP.get(level, Fore.RESET)
        icon_map = {
            'success': f'{const.C_SUCCESS}✓{Fore.RESET}',
            'error': f'{const.C_ERROR}✗{Fore.RESET}',
            'skip': f'{const.C_DIM}–{Fore.RESET}',
            'note': f'{const.C_DIM}·{Fore.RESET}',
            'warn': f'{const.C_WARNING}⚠{Fore.RESET}',
        }
        used_icon = icon or icon_map.get(level, '')
        if used_icon:
            line = f'{used_icon} {color}{msg}{Fore.RESET}'
        else:
            line = f'{color}{msg}{Fore.RESET}'
        LOG.info(line + ('\n' if newline else ''))

    @staticmethod
    def _flush_output() -> None:
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

    def _is_field_empty(self, cfg: Dict[str, Any], *keys: str) -> bool:
        for key in keys:
            val = cfg
            for part in key.split('.'):
                val = val.get(part, '')
                if val is None:
                    break
            if not val:
                return True
        return False

    async def _test_all_connections(self, cfg: Dict[str, Any], quiet: bool = False) -> bool:
        if cfg['account']['proxy']:
            if not ut.proxy_reachable(cfg['account']['proxy']):
                if not quiet:
                    self._log_status('error', 'Прокси Playerok недоступен')
                return False
            if not quiet:
                self._log_status('success', 'Прокси Playerok в порядке')

        if not ut.account_reachable():
            self._log_status('error', 'Playerok: аккаунт, токен или сеть — ошибка')
            return False
        if not quiet:
            self._log_status('success', 'Аккаунт Playerok доступен')
        if ut.account_banned():
            self._log_status('error', 'Аккаунт заблокирован на Playerok')
            return False

        if cfg['bot']['proxy']:
            if not ut.proxy_reachable(cfg['bot']['proxy'], 'https://api.telegram.org/'):
                if not quiet:
                    self._log_status('error', 'Прокси Telegram недоступен')
                return False
            if not quiet:
                self._log_status('success', 'Прокси Telegram в порядке')

        if not ut.tg_ok():
            if not ut.tg_api_reachable(cfg['bot'].get('proxy')):
                self._log_status('error', 'api.telegram.org недоступен — нужны прокси или VPN')
                return False
            self._log_status('error', 'Неверный токен бота Telegram')
            return False
        if not quiet:
            self._log_status('success', 'Бот Telegram в порядке')

        if not quiet:
            self._log_status('success', 'Все проверки связи пройдены')
        return True

    async def _interactive_config(self) -> None:
        config = cfgmod.AppConf.read('config')

        if config['bot'].get('token') and config['bot'].get('password_hash') and config['account'].get('token'):
            patched = False
            if not (config['bot'].get('proxy') or '') and not config['bot'].get('proxy_prompt_ok'):
                config['bot']['proxy_prompt_ok'] = True
                patched = True
            if not (config['account'].get('proxy') or '') and not config['account'].get('proxy_prompt_ok'):
                config['account']['proxy_prompt_ok'] = True
                patched = True
            if not (config['account'].get('user_agent') or '') and not config['account'].get('user_agent_prompt_ok'):
                config['account']['user_agent_prompt_ok'] = True
                patched = True
            if patched:
                cfgmod.AppConf.write('config', config)

        def _wizard_step_count(c: Dict[str, Any]) -> int:
            n = 0
            if not c['bot']['token']:
                n += 1
            if not c['bot']['password_hash']:
                n += 1
            if not (c['bot'].get('proxy') or '') and not c['bot'].get('proxy_prompt_ok'):
                n += 1
            if not c['account']['token']:
                n += 1
            if not (c['account'].get('proxy') or '') and not c['account'].get('proxy_prompt_ok'):
                n += 1
            if not (c['account'].get('user_agent') or '') and not c['account'].get('user_agent_prompt_ok'):
                n += 1
            return max(n, 1)

        total_fields = _wizard_step_count(config)
        step = 0
        prompted = False

        def ask_step(label: str, desc: List[str], example: str = '', skip_allowed: bool = False) -> Optional[str]:
            nonlocal step
            step += 1
            raw = ut.setup_prompt(step, total_fields, label, desc, example)
            if skip_allowed and raw == '':
                return None
            return raw

        while not config['bot']['token']:
            val = ask_step(
                'Токен бота Telegram',
                ['В @BotFather выполните /newbot и скопируйте токен'],
                example='123456789:AA...',
            )
            if ut.tg_token_ok(val):
                config['bot']['token'] = val
                cfgmod.AppConf.write('config', config)
                self._log_status('success', 'Токен Telegram сохранён')
                prompted = True
            else:
                step -= 1
                self._log_status('error', 'Неверный формат токена (ожидается id:hash)')

        while not config['bot']['password_hash']:
            val = ask_step(
                'Пароль панели управления',
                ['6–64 символа, надёжный, не из простых словарей'],
            )
            if ut.password_ok(val):
                config['bot']['password_hash'] = cfgmod.hash_password(val)
                cfgmod.AppConf.write('config', config)
                self._log_status('success', 'Пароль сохранён')
                prompted = True
            else:
                step -= 1
                self._log_status('error', 'Слабый или недопустимый пароль')

        if not (config['bot'].get('proxy') or '') and not config['bot'].get('proxy_prompt_ok'):
            val = ask_step(
                'Прокси для Telegram (Enter — пропустить)',
                [
                    'Форматы: user:pass@host:port, socks5h:host:port:user:pass',
                    'Из РФ часто нужен прокси или VPN до api.telegram.org',
                ],
                example='user:pass@1.2.3.4:8080',
                skip_allowed=True,
            )
            if val is None:
                config['bot']['proxy'] = ''
                config['bot']['proxy_prompt_ok'] = True
                cfgmod.AppConf.write('config', config)
                self._log_status('skip', 'Прокси Telegram не задан')
                prompted = True
            elif val:
                if ut.proxy_ok(val):
                    config['bot']['proxy'] = val
                    config['bot']['proxy_prompt_ok'] = True
                    cfgmod.AppConf.write('config', config)
                    self._log_status('success', 'Прокси Telegram сохранён')
                    prompted = True
                else:
                    self._log_status('error', 'Некорректный формат прокси')
                    config['bot']['proxy'] = ''

        while not config['account']['token']:
            val = ask_step(
                'JWT Playerok (из cookie)',
                [
                    'playerok.com → расширение Cookie-Editor → поле «token»',
                ],
                example='eyJ...',
            )
            if ut.token_ok(val):
                config['account']['token'] = val
                cfgmod.AppConf.write('config', config)
                self._log_status('success', 'Токен Playerok сохранён')
                prompted = True
            else:
                step -= 1
                self._log_status('error', 'Строка не похожа на корректный JWT')

        if not (config['account'].get('proxy') or '') and not config['account'].get('proxy_prompt_ok'):
            val = ask_step(
                'Прокси Playerok (Enter — пропустить)',
                [
                    'Те же форматы, что и для Telegram — HTTP/SOCKS5 до playerok.com',
                ],
                example='socks5h:host:port:user:pass',
                skip_allowed=True,
            )
            if val is None:
                config['account']['proxy'] = ''
                config['account']['proxy_prompt_ok'] = True
                cfgmod.AppConf.write('config', config)
                self._log_status('skip', 'Прокси Playerok не задан')
                prompted = True
            elif val:
                if ut.proxy_ok(val):
                    config['account']['proxy'] = val
                    config['account']['proxy_prompt_ok'] = True
                    cfgmod.AppConf.write('config', config)
                    self._log_status('success', 'Прокси Playerok сохранён')
                    prompted = True
                else:
                    self._log_status('error', 'Некорректный формат прокси')
                    config['account']['proxy'] = ''

        if not (config['account'].get('user_agent') or '') and not config['account'].get('user_agent_prompt_ok'):
            val = ask_step(
                'User-Agent браузера для Playerok (Enter — пропустить, нежелательно)',
                [
                    'whatmyuseragent.com — скопируйте полную строку',
                ],
                example='Mozilla/5.0 … Chrome/144',
                skip_allowed=True,
            )
            if val is None:
                config['account']['user_agent'] = ''
                config['account']['user_agent_prompt_ok'] = True
                cfgmod.AppConf.write('config', config)
                self._log_status('skip', 'User-Agent не задан — возможны сбои запросов')
                prompted = True
            elif val:
                if ut.ua_ok(val):
                    config['account']['user_agent'] = val
                    config['account']['user_agent_prompt_ok'] = True
                    cfgmod.AppConf.write('config', config)
                    self._log_status('success', 'User-Agent сохранён')
                    prompted = True
                else:
                    self._log_status('error', 'Некорректный User-Agent')
                    config['account']['user_agent'] = ''

        config = cfgmod.AppConf.read('config')
        self._log_status('note', 'Проверка сети и токенов…')
        self._flush_output()
        if await self._test_all_connections(config, quiet=not prompted):
            return
        self._log_status('warn', 'Проверка связи не пройдена — конфигурация не изменена')
        self._log_status(
            'dim',
            'Исправьте токены, прокси или сеть. Enter — повторить, Ctrl+C — выход',
        )
        try:
            await asyncio.get_event_loop().run_in_executor(None, input)
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(1) from None
        await self._interactive_config()

    async def _auto_maintenance(self) -> None:
        while not self._shutdown_flag:
            await asyncio.sleep(45)
            try:
                log_path = ut.get_bot_log_path()
                conf = cfgmod.AppConf.read('config') or {}
                max_mb = (conf.get('logs') or {}).get('max_mb', 300)
                if os.path.exists(log_path):
                    sz_mb = os.path.getsize(log_path) / (1024 * 1024)
                    if sz_mb > max_mb:
                        open(log_path, 'w').close()
            except OSError:
                pass

    async def _launch_telegram_panel(self) -> None:
        from ctrl.panel import Panel
        panel = Panel()
        try:
            async def _panel_poll():
                await panel.run_bot()
            asyncio.create_task(_panel_poll(), name='tg_panel')
        except TypeError:
            asyncio.create_task(_panel_poll())
        LOG.debug('Панель Telegram запущена — лог: %s', ut.get_bot_log_path())

    async def _launch_market_engine(self) -> None:
        from bot.core import make_bridge
        from pok.defs import RequestSendingError
        try:
            bridge = make_bridge()
            await bridge.start()
        except RequestSendingError as exc:
            LOG.error('  %s✗%s  Playerok недоступен: проверьте прокси и сеть.', const.C_ERROR, Fore.RESET)
            LOG.error('  %s%s', const.C_TEXT, str(exc)[:500])
            LOG.error('  %sПроверьте account.proxy в conf/config.json%s', const.C_DIM, Fore.RESET)
            raise SystemExit(1) from None

    async def _run(self) -> None:
        ut.clear_terminal()
        quick_restart = os.environ.pop('CXH_FAST_REBOOT', None) == '1'
        ut.check_requirements('requirements.txt')
        ut.monkey_patch_http()
        ut.setup_logging()
        ut.set_console_title(f'CXH Playerok {const.VERSION}')

        if quick_restart:
            LOG.info('%s↻ Перезапуск%s %s%s', const.C_DIM, Fore.RESET, const.VERSION, Fore.RESET)
        else:
            LOG.info(
                '%sCXH Playerok%s %s%s · автоматизация%s',
                const.C_PRIMARY,
                Fore.RESET,
                const.C_DIM,
                const.VERSION,
                Fore.RESET,
            )

        await self._interactive_config()

        extensions = extmod.discover_extensions()
        extmod.register_extensions(extensions)
        await extmod.activate_extensions(extensions)

        engine_task = asyncio.create_task(self._launch_market_engine(), name='engine')
        panel_task = asyncio.create_task(self._launch_telegram_panel(), name='panel')
        maint_task = asyncio.create_task(self._auto_maintenance(), name='maintenance')

        await busmod.fire('BOOT')

        try:
            await asyncio.gather(engine_task, panel_task, maint_task)
        except asyncio.CancelledError:
            pass
        finally:
            self._shutdown_flag = True

    def run(self) -> None:
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        colorama_init()
        ut.bind_loop(self.loop)

        def _shutdown_handler():
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            self.loop.stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, _shutdown_handler)
            except NotImplementedError:
                pass

        try:
            self.loop.run_until_complete(self._run())
            self.loop.run_forever()
        except KeyboardInterrupt:
            LOG.info('%sЗавершение по Ctrl+C%s', const.C_WARNING, Fore.RESET)
        finally:
            self.loop.close()


if __name__ == '__main__':
    bot = CXHBot()
    bot.run()
