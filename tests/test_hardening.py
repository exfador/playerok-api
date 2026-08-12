from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.core import MarketBridge
from ctrl.actions import _patch_deal_idempotent, _valid_index
from ctrl.cmd import _safe_health_error
from ctrl.panel import Panel
from lib import broadcast
from lib.bus import Signal
from lib.cfg import _load, hash_password, password_needs_rehash, verify_password
from lib.db import _DbFile, AppDb
from lib.db import _ALL as DB_FILES
from lib.ext import ADDONS_DIR
from lib.updater import fetch_latest_release
from lib.updater_apply import apply_update
from lib.util import cookies_from_json_list, proxy_url_for_requests
from lib.util import COOKIES_JSON_PATH
from pok.defs import PayGateway, PayMethod
from pok.feed import Feed, _parse_api_datetime
from pok.gql import decode_transaction_provider
from main import CXHBot


class SecurityHardeningTests(unittest.TestCase):
    def test_password_hash_uses_salted_kdf_and_keeps_legacy_verification(self):
        first = hash_password('secret-value')
        second = hash_password('secret-value')
        self.assertTrue(first.startswith('pbkdf2_sha256$'))
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password('secret-value', first))
        self.assertFalse(verify_password('wrong', first))

        legacy = hashlib.sha256(b'secret-value').hexdigest()
        self.assertTrue(verify_password('secret-value', legacy))
        self.assertTrue(password_needs_rehash(legacy))
        self.assertFalse(password_needs_rehash(first))
        self.assertFalse(verify_password('wrong', legacy))
        self.assertFalse(verify_password('secret-value', 'broken$hash'))

    def test_cookie_import_rejects_lookalike_domains(self):
        jar = cookies_from_json_list([
            {'name': 'good-root', 'value': '1', 'domain': 'playerok.com'},
            {'name': 'good-sub', 'value': '2', 'domain': '.www.playerok.com'},
            {'name': 'evil-prefix', 'value': '3', 'domain': 'evilplayerok.com'},
            {'name': 'evil-suffix', 'value': '4', 'domain': 'playerok.com.evil.test'},
        ])
        self.assertEqual(jar, {'good-root': '1', 'good-sub': '2'})

    def test_https_proxy_scheme_is_preserved(self):
        proxy = 'https://user:pass@proxy.example:8443'
        self.assertEqual(proxy_url_for_requests(proxy), proxy)


class PersistenceHardeningTests(unittest.TestCase):
    def test_all_runtime_state_paths_are_project_anchored(self):
        project_root = Path(__file__).resolve().parents[1]
        for entry in DB_FILES:
            self.assertTrue(Path(entry.path).is_absolute())
            self.assertTrue(Path(entry.path).is_relative_to(project_root))
        self.assertTrue(Path(ADDONS_DIR).is_relative_to(project_root))
        self.assertTrue(Path(COOKIES_JSON_PATH).is_relative_to(project_root))

    def test_config_invalid_json_is_backed_up_and_permissions_are_private(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'config.json'
            path.write_text('{invalid', encoding='utf-8')
            loaded = _load(str(path), {'safe': True})
            self.assertEqual(loaded, {'safe': True})
            self.assertEqual(Path(str(path) + '.corrupt.bak').read_text(), '{invalid')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_db_invalid_json_is_backed_up_and_default_is_not_shared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'state.json'
            path.write_text('{invalid', encoding='utf-8')
            entry = _DbFile('temporary', str(path), [])
            first = AppDb.get('temporary', [entry])
            first.append('local mutation')
            self.assertEqual(Path(str(path) + '.corrupt.bak').read_text(), '{invalid')
            self.assertEqual(AppDb.get('temporary', [entry]), [])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ApiContractHardeningTests(unittest.TestCase):
    def test_transaction_provider_account_keeps_all_graphql_fields(self):
        provider = decode_transaction_provider({
            'id': 'CRYPTO',
            'name': 'Crypto',
            'fee': 1,
            'account': {
                'id': 'account-id',
                'value': 'wallet-value',
                'userId': 'user-id',
                'providerId': 'CRYPTO',
                'paymentMethodId': 'MIR',
            },
            'paymentMethods': [],
        })
        self.assertEqual(provider.account.id, 'account-id')
        self.assertEqual(provider.account.value, 'wallet-value')
        self.assertEqual(provider.account.user_id, 'user-id')
        self.assertIs(provider.account.provider_id, PayGateway.CRYPTO)
        self.assertIs(provider.account.payment_method_id, PayMethod.MIR)

    def test_api_timestamp_parser_accepts_z_and_normalizes_to_utc(self):
        parsed = _parse_api_datetime('2026-08-12T15:10:00Z')
        self.assertEqual(parsed.isoformat(), '2026-08-12T15:10:00+00:00')


class FeedHardeningTests(unittest.TestCase):
    def _feed(self):
        conn = SimpleNamespace(id='user-id')
        return Feed(conn)

    def test_connection_ack_resets_stale_subscriptions_and_subscribes_read_events(self):
        feed = self._feed()
        feed.q = SimpleNamespace(put=lambda value: None)
        feed.chats = []
        feed.chat_subscriptions = {'stale-id': 'chat-id'}
        operations = []
        feed._send_ws = lambda payload, *args: operations.append(payload['payload']['operationName']) or True
        feed.process_ws_message(json.dumps({'type': 'connection_ack'}))
        self.assertEqual(feed.chat_subscriptions, {})
        self.assertEqual(operations, ['chatUpdated', 'chatMarkedAsRead', 'userUpdated'])

    def test_stale_websocket_generation_is_ignored(self):
        feed = self._feed()
        feed._ws_generation = 2
        feed.ws = feed._ws_generation_socket = object()
        called = []
        feed._subscribe_chat_updated = lambda: called.append(True)
        feed.process_ws_message(json.dumps({'type': 'connection_ack'}), generation=1)
        self.assertEqual(called, [])

    def test_reconnect_during_hydration_drops_old_generation_state(self):
        feed = self._feed()
        feed._ws_generation = 1
        feed.ws = feed._ws_generation_socket = object()
        feed.chats = []
        feed._hydrate_message_if_needed = lambda message, chat_id: setattr(feed, '_ws_generation', 2) or message
        events = feed._process_new_chat_message(
            SimpleNamespace(id='chat-id'), SimpleNamespace(id='message-id'), generation=1,
        )
        self.assertEqual(events, [])
        self.assertEqual(feed.chats, [])

    def test_saturated_websocket_queue_closes_instead_of_blocking_recv(self):
        feed = self._feed()
        feed._ws_generation = 1
        closed = []
        feed.ws = SimpleNamespace(close=lambda: closed.append(True))
        feed._ws_generation_socket = feed.ws
        feed._ws_capacity = SimpleNamespace(acquire=lambda **kwargs: False)
        self.assertFalse(feed._dispatch_ws_message('{}', 1))
        self.assertEqual(closed, [True])

    def test_generation_is_invalid_during_socket_replacement_gap(self):
        feed = self._feed()
        old_ws = object()
        feed._ws_generation = 5
        feed.ws = old_ws
        feed._ws_generation_socket = old_ws
        self.assertTrue(feed._generation_is_current(5))

        with feed._ws_generation_lock:
            feed._ws_generation += 1
            feed._ws_generation_socket = None
            feed.ws = object()

        self.assertFalse(feed._generation_is_current(5))
        self.assertFalse(feed._generation_is_current(6))

    def test_connection_init_uses_browser_compatible_presence_parameters(self):
        feed = Feed(SimpleNamespace(id='user-id'), ws_path='/chats')
        sent = []
        feed._send_ws = lambda payload, *args: sent.append(payload) or True
        feed._send_connection_init()
        self.assertEqual(sent[0]['type'], 'connection_init')
        self.assertEqual(sent[0]['payload']['x-gql-path'], '/chats')
        self.assertIsInstance(sent[0]['payload']['x-timezone-offset'], int)

    def test_graphql_ping_gets_immediate_pong_outside_saturated_event_queue(self):
        feed = self._feed()
        sent = []
        closed = []
        ws = SimpleNamespace(
            send=lambda value: sent.append(json.loads(value)),
            close=lambda: closed.append(True),
        )
        feed._ws_generation = 1
        feed.ws = feed._ws_generation_socket = ws
        feed._ws_capacity = SimpleNamespace(acquire=lambda **kwargs: False)
        handled = feed._dispatch_incoming_ws_message(
            json.dumps({'type': 'ping', 'payload': {'server': 'alive'}}), 1,
        )
        self.assertTrue(handled)
        self.assertEqual(sent, [{'type': 'pong', 'payload': {'server': 'alive'}}])
        self.assertEqual(closed, [])

    def test_connection_ack_is_reflected_in_health(self):
        feed = self._feed()
        feed.chats = []
        feed._send_ws = lambda *args: True
        feed.process_ws_message(json.dumps({'type': 'connection_ack'}))
        health = feed.health()
        self.assertTrue(health['connected'])
        self.assertIsNotNone(health['connected_at'])
        self.assertIsNone(health['last_error'])

    def test_partial_subscribe_failure_is_not_reported_connected(self):
        feed = self._feed()
        feed.chats = []
        closed = []
        feed.ws = feed._ws_generation_socket = SimpleNamespace(close=lambda: closed.append(True))
        feed._ws_generation = 1
        calls = []

        def fail_second(payload, *args):
            calls.append(payload)
            if len(calls) == 2:
                raise BrokenPipeError('subscribe failed')
            return True

        feed._send_ws = fail_second
        feed.process_ws_message(json.dumps({'type': 'connection_ack'}), generation=1)
        self.assertFalse(feed.health()['connected'])
        self.assertIn('subscribe', feed.health()['last_error'])
        self.assertEqual(closed, [True])

    def test_stop_invalidates_and_closes_current_socket(self):
        feed = self._feed()
        closed = []
        ws = SimpleNamespace(close=lambda: closed.append(True))
        feed._ws_generation = 3
        feed.ws = feed._ws_generation_socket = ws
        feed.stop()
        self.assertEqual(closed, [True])
        self.assertIsNone(feed.ws)
        self.assertTrue(feed.health()['stopping'])

    def test_only_matching_pong_clears_pending_heartbeat(self):
        feed = self._feed()
        feed._pending_ping_nonce = 'expected'
        feed.process_ws_message(json.dumps({'type': 'pong', 'payload': {'nonce': 'stale'}}))
        self.assertEqual(feed._pending_ping_nonce, 'expected')
        feed.process_ws_message(json.dumps({'type': 'pong', 'payload': {'nonce': 'expected'}}))
        self.assertIsNone(feed._pending_ping_nonce)

    def test_non_pong_traffic_does_not_cancel_pending_heartbeat(self):
        feed = self._feed()
        sent = []
        ws = SimpleNamespace(send=lambda value: sent.append(json.loads(value)))
        feed._ws_generation = 1
        feed.ws = feed._ws_generation_socket = ws
        feed._pending_ping_nonce = 'expected'
        feed._dispatch_incoming_ws_message(
            json.dumps({'type': 'ping', 'payload': {'server': 'busy'}}), 1,
        )
        self.assertEqual(feed._pending_ping_nonce, 'expected')
        self.assertEqual(sent, [{'type': 'pong', 'payload': {'server': 'busy'}}])

    def test_stop_interrupts_socket_while_connecting(self):
        feed = Feed(SimpleNamespace(
            id='user-id', user_agent='ua', token='token', _ca_bundle=None,
            _cookie_header=lambda: 'token=hidden', load_chats=lambda **kwargs: SimpleNamespace(chats=[]),
        ))
        entered = threading.Event()
        released = threading.Event()

        class ConnectingSocket:
            def __init__(self, **kwargs):
                pass

            def settimeout(self, value):
                pass

            def connect(self, **kwargs):
                entered.set()
                released.wait(timeout=2)
                raise __import__('websocket').WebSocketException('closed')

            def close(self):
                released.set()

        generator = feed.listen_new_messages()
        worker = threading.Thread(target=lambda: next(generator, None), daemon=True)
        with patch('pok.feed.websocket.WebSocket', ConnectingSocket):
            worker.start()
            self.assertTrue(entered.wait(timeout=1))
            feed.stop()
            worker.join(timeout=1)
        self.assertFalse(worker.is_alive())


class BotHardeningTests(unittest.TestCase):
    def test_stop_signals_and_joins_market_workers(self):
        bridge = object.__new__(MarketBridge)
        bridge._stop_event = threading.Event()
        feed_stopped = []
        bridge._feed = SimpleNamespace(stop=lambda: feed_stopped.append(True))
        bridge._feed_thread = None
        worker = threading.Thread(target=bridge._stop_event.wait, daemon=True)
        bridge._worker_threads = [worker]
        worker.start()
        bridge.stop(join_timeout=1)
        self.assertEqual(feed_stopped, [True])
        self.assertFalse(worker.is_alive())

    def test_repeated_alive_event_does_not_duplicate_workers(self):
        bridge = object.__new__(MarketBridge)
        bridge._alive_lock = threading.Lock()
        bridge._alive_started = False
        bridge._worker_threads = []
        bridge._started_worker_names = set()
        bridge.stats = SimpleNamespace(bot_launch_time=None)
        created = []

        class FakeThread:
            def __init__(self, **kwargs):
                created.append(kwargs.get('target'))

            def start(self):
                return None

        with patch('bot.core.Thread', FakeThread):
            asyncio.run(bridge._on_alive())
            asyncio.run(bridge._on_alive())
        self.assertEqual(len(created), 8)

    def test_alive_retry_starts_only_worker_that_failed(self):
        bridge = object.__new__(MarketBridge)
        bridge._alive_lock = threading.Lock()
        bridge._alive_started = False
        bridge._worker_threads = []
        bridge._started_worker_names = set()
        bridge.stats = SimpleNamespace(bot_launch_time=None)
        attempts = {}

        class FlakyThread:
            def __init__(self, **kwargs):
                self.name = kwargs['name']

            def start(self):
                attempts[self.name] = attempts.get(self.name, 0) + 1
                if self.name == 'cxh-sync_loop' and attempts[self.name] == 1:
                    raise RuntimeError('temporary thread failure')

        with patch('bot.core.Thread', FlakyThread):
            asyncio.run(bridge._on_alive())
            self.assertFalse(bridge._alive_started)
            asyncio.run(bridge._on_alive())
        self.assertTrue(bridge._alive_started)
        self.assertEqual(attempts['cxh-sync_loop'], 2)
        self.assertTrue(all(count == 1 for name, count in attempts.items() if name != 'cxh-sync_loop'))

    def test_reactivation_of_same_item_is_single_flight(self):
        bridge = object.__new__(MarketBridge)
        bridge._mutation_guard = threading.Lock()
        bridge._reactivating_items = set()
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def once(item, retry_delays):
            calls.append(item.id)
            entered.set()
            release.wait(timeout=2)

        bridge._reactivate_once = once
        item = SimpleNamespace(id='item-id')
        first = threading.Thread(target=bridge._reactivate, args=(item, []))
        first.start()
        self.assertTrue(entered.wait(timeout=1))
        second = threading.Thread(target=bridge._reactivate, args=(item, []))
        second.start()
        second.join(timeout=1)
        release.set()
        first.join(timeout=1)
        self.assertEqual(calls, ['item-id'])

    def test_listing_pagination_rejects_repeated_cursor(self):
        bridge = object.__new__(MarketBridge)
        bridge.saved_items = []
        page = SimpleNamespace(
            items=[],
            page_info=SimpleNamespace(has_next_page=True, end_cursor='same-cursor'),
        )
        user = SimpleNamespace(load_listings=lambda **kwargs: page)
        bridge.account = SimpleNamespace(id='user-id', load_user=lambda user_id: user)
        with patch('bot.core.time.sleep', return_value=None):
            with self.assertRaises(RuntimeError):
                bridge._listings()

    def test_signal_registration_is_idempotent(self):
        signal = Signal('test')

        async def handler():
            return None

        signal.connect(handler)
        signal.connect(handler)
        self.assertEqual(signal.receivers(), [handler])
        asyncio.run(signal.send())

    def test_stale_callback_indexes_are_rejected(self):
        values = ['only']
        self.assertTrue(_valid_index(values, 0))
        self.assertFalse(_valid_index(values, -1))
        self.assertFalse(_valid_index(values, 1))
        self.assertFalse(_valid_index(values, True))

    def test_deal_mutation_verifies_state_after_ambiguous_failure(self):
        calls = []
        states = iter([
            SimpleNamespace(status=None),
            SimpleNamespace(status=__import__('pok.defs', fromlist=['DealStage']).DealStage.SENT),
        ])

        class Account:
            def load_deal(self, deal_id):
                return next(states)

            def patch_deal(self, deal_id, target):
                calls.append((deal_id, target))
                raise TimeoutError('response lost')

        result = _patch_deal_idempotent(
            Account(), 'deal-id', __import__('pok.defs', fromlist=['DealStage']).DealStage.SENT,
        )
        self.assertEqual(result.status.name, 'SENT')
        self.assertEqual(len(calls), 1)


class TelegramLifecycleTests(unittest.TestCase):
    def test_status_error_redacts_credentials(self):
        safe = _safe_health_error(
            'ProxyError https://alice:secret@proxy.example token=topsecret authorization: BearerSecret'
        )
        self.assertNotIn('secret', safe)
        self.assertNotIn('topsecret', safe)
        self.assertNotIn('BearerSecret', safe)

    def test_polling_recovers_after_transient_failures(self):
        panel = SimpleNamespace(
            loop=None,
            proxy='',
            _stop_event=threading.Event(),
            _polling_active=False,
            _started_at=None,
            _last_api_success_at=None,
            _last_update_at=None,
            _last_error=None,
            _poll_failures=0,
            _updates_received=0,
            _set_main_menu=AsyncMock(),
            _set_short_description=AsyncMock(),
            _set_description=AsyncMock(),
            _send_startup_message=AsyncMock(),
        )
        panel.bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username='health_bot', id=1)),
        )
        panel._health_probe = lambda: Panel._health_probe(panel)
        attempts = []

        async def start_polling(*args, **kwargs):
            attempts.append(True)
            if len(attempts) < 3:
                raise RuntimeError('temporary Telegram outage')
            panel._stop_event.set()

        panel.dp = SimpleNamespace(start_polling=start_polling)
        with patch('ctrl.panel.dispatch', AsyncMock()), patch('ctrl.panel.asyncio.sleep', AsyncMock()):
            asyncio.run(Panel.run_bot(panel))
        self.assertEqual(len(attempts), 3)
        self.assertEqual(panel._poll_failures, 2)
        self.assertFalse(panel._polling_active)
        self.assertIsNotNone(panel._last_api_success_at)

    def test_panel_stop_stops_polling_and_closes_session_once(self):
        calls = []

        class Dispatcher:
            async def stop_polling(self):
                calls.append('polling')

        class Session:
            async def close(self):
                calls.append('session')

        panel = SimpleNamespace(
            _stop_event=threading.Event(),
            dp=Dispatcher(),
            bot=SimpleNamespace(session=Session()),
            _session_closed=False,
        )
        asyncio.run(Panel.stop(panel))
        asyncio.run(Panel.stop(panel))
        self.assertTrue(panel._stop_event.is_set())
        self.assertEqual(calls, ['polling', 'session', 'polling'])

    def test_panel_health_contains_no_credentials(self):
        panel = SimpleNamespace(
            _polling_active=True,
            _started_at=1.0,
            _last_api_success_at=2.0,
            _last_update_at=3.0,
            _last_error=None,
            _poll_failures=0,
            _updates_received=4,
            _stop_event=threading.Event(),
            token='must-not-leak',
            proxy='must-not-leak',
        )
        snapshot = Panel.health(panel)
        self.assertTrue(snapshot['polling_active'])
        self.assertNotIn('token', snapshot)
        self.assertNotIn('proxy', snapshot)


class MainLifecycleTests(unittest.TestCase):
    def test_maintenance_exits_immediately_on_shutdown(self):
        bot = CXHBot()

        async def run():
            bot._shutdown_event = asyncio.Event()
            bot._shutdown_event.set()
            await asyncio.wait_for(bot._auto_maintenance(), timeout=0.2)

        asyncio.run(run())

    def test_panel_launcher_awaits_owned_polling_task(self):
        bot = CXHBot()
        calls = []

        class FakePanel:
            async def run_bot(self):
                calls.append('run')

        with patch('ctrl.panel.Panel', return_value=FakePanel()):
            asyncio.run(bot._launch_telegram_panel())
        self.assertEqual(calls, ['run'])
        self.assertIsNotNone(bot._panel)


class UpdaterHardeningTests(unittest.TestCase):
    def test_release_selection_ignores_unsupported_archives(self):
        class Response:
            status_code = 200
            text = ''

            def json(self):
                return {
                    'tag_name': 'v9.0.0',
                    'html_url': 'https://example/release',
                    'zipball_url': 'https://example/zipball',
                    'assets': [
                        {'name': 'release.tar.gz', 'browser_download_url': 'https://example/tar'},
                        {'name': 'release.zip', 'browser_download_url': 'https://example/zip'},
                    ],
                }

        with patch('lib.updater.requests.get', return_value=Response()):
            release = fetch_latest_release()
        self.assertEqual(release.asset_name, 'release.zip')
        self.assertEqual(release.download_url, 'https://example/zip')

    def test_staging_failure_does_not_modify_live_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src = root / 'src'
            live = root / 'live'
            src.mkdir()
            live.mkdir()
            (src / 'app.py').write_text('new', encoding='utf-8')
            (live / 'app.py').write_text('old', encoding='utf-8')

            with patch('lib.updater_apply.shutil.copy2', side_effect=OSError('disk full')):
                result = apply_update(str(src), str(live))

            self.assertTrue(result['errors'])
            self.assertEqual(result['copied'], 0)
            self.assertEqual((live / 'app.py').read_text(encoding='utf-8'), 'old')

    def test_activation_failure_rolls_back_already_replaced_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src = root / 'src'
            live = root / 'live'
            src.mkdir()
            live.mkdir()
            for name in ('a.py', 'b.py'):
                (src / name).write_text(f'new-{name}', encoding='utf-8')
                (live / name).write_text(f'old-{name}', encoding='utf-8')

            real_replace = os.replace

            def fail_second_activation(source, destination):
                normalized = str(source).replace('\\', '/')
                if normalized.endswith('/staged/b.py'):
                    raise OSError('activation failed')
                return real_replace(source, destination)

            with patch('lib.updater_apply.os.replace', side_effect=fail_second_activation):
                result = apply_update(str(src), str(live))

            self.assertTrue(result['errors'])
            self.assertEqual((live / 'a.py').read_text(encoding='utf-8'), 'old-a.py')
            self.assertEqual((live / 'b.py').read_text(encoding='utf-8'), 'old-b.py')


class BroadcastHardeningTests(unittest.TestCase):
    def test_gist_comments_are_limited_to_owner(self):
        class Response:
            status_code = 200

            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        responses = [
            Response({'owner': {'login': 'trusted-owner'}}),
            Response([
                {'id': 1, 'body': 'trusted', 'user': {'login': 'trusted-owner'}},
                {'id': 2, 'body': '<b>evil</b>', 'user': {'login': 'attacker'}},
            ]),
        ]
        with patch('lib.broadcast._http_get', side_effect=responses):
            items = broadcast.fetch_bulletins(
                'https://api.github.com/gists/89e52dbb3ca81aee82b6a3d8b51b55e2'
            )
        self.assertEqual([item.text for item in items], ['trusted'])


if __name__ == '__main__':
    unittest.main()
