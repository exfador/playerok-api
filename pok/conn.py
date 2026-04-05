from __future__ import annotations
from typing import *
from logging import getLogger
from typing import Literal
import json
import os
import ssl
import time
import base64
import certifi
import tls_requests
import curl_cffi
from lib.util import proxy_url_for_requests
from . import models as types
from .defs import *
from .gql import *


def active_conn() -> Conn | None:
    if hasattr(Conn, 'instance'):
        return getattr(Conn, 'instance')


def _is_transport_recoverable(exc: BaseException) -> bool:
    if isinstance(exc, (ssl.SSLError, TimeoutError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    if isinstance(exc, OSError):
        err_no = getattr(exc, 'errno', None)
        if err_no is not None and err_no in (
            10054, 10053, 10060,
            104, 110, 111, 113,
        ):
            return True
    blob = f'{type(exc).__name__} {exc}'.lower()
    for needle in (
        'ssl', 'tls', 'handshake', 'certificate', 'eof occurred',
        'connection reset', 'broken pipe', 'curl: (', 'recv failure', 'send failure',
        'wrong version number', 'unexpected eof',
    ):
        if needle in blob:
            return True
    return False


def _is_proxy_dial_failure_message(msg: str) -> bool:
    m = (msg or '').lower()
    if any(x in m for x in ('curl: (7)', 'curl: (56)')):
        return True
    if any(x in m for x in ('failed to connect', 'could not connect', 'connection refused')):
        return True
    if any(x in m for x in ('no route to host', 'network is unreachable', 'name or service not known')):
        return True
    return False


def _proxy_dial_failure_hint(err: str) -> str:
    e = (err or '').lower()
    if 'curl: (28)' in e:
        return (
            ' | Таймаут запроса (0 байт — часто сеть/фильтр/прокси): проверьте '
            'доступ к playerok.com с этого хоста, account.proxy, account.timeout в config, фаервол и DNS.'
        )
    if 'curl: (7)' in e:
        return ' | Нет соединения с прокси: закрыт порт, неверный адрес или блокировка.'
    return ' | Проверьте account.proxy / bot.proxy в conf/config.json.'


class Conn:

    def __new__(cls, *args, **kwargs) -> Conn:
        if not hasattr(cls, 'instance'):
            cls.instance = super(Conn, cls).__new__(cls)
        return getattr(cls, 'instance')

    def __init__(self, token: str, user_agent: str = '', proxy: str = None, requests_timeout: int = 15, request_max_retries: int = 5, **kwargs):
        self.token = token
        self.user_agent = user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
        self.requests_timeout = requests_timeout
        self.proxy = proxy
        self.__proxy_string = proxy_url_for_requests(self.proxy) if self.proxy else None
        self.request_max_retries = request_max_retries
        self.base_url = 'https://playerok.com'
        self.id: str | None = None
        self.username: str | None = None
        self.email: str | None = None
        self.role: str | None = None
        self.support_chat_id: str | None = None
        self.system_chat_id: str | None = None
        self.unread_chats_counter: int | None = None
        self.is_blocked: bool | None = None
        self.is_blocked_for: str | None = None
        self.created_at: str | None = None
        self.last_item_created_at: str | None = None
        self.has_frozen_balance: bool | None = None
        self.has_confirmed_phone_number: bool | None = None
        self.can_publish_items: bool | None = None
        self.profile: AccountProfile | None = None
        self._ca_bundle = certifi.where()
        self._refresh_clients()
        self.logger = getLogger('pl.conn')

    _IMPERSONATE_PROFILES = [
        'chrome124', 'chrome131', 'chrome120', 'chrome123', 'chrome116',
        'chrome119', 'chrome107', 'chrome110', 'chrome104',
    ]
    _profile_index: int = 0

    def _refresh_clients(self):
        profile = self._IMPERSONATE_PROFILES[
            Conn._profile_index % len(self._IMPERSONATE_PROFILES)
        ]
        Conn._profile_index += 1
        self.__tls_requests = tls_requests.Client(proxy=self.__proxy_string)
        self.__curl_session = curl_cffi.Session(impersonate=profile, timeout=10, proxy=self.__proxy_string, verify=self._ca_bundle)

    @property
    def _timeout(self) -> int:
        try:
            from lib.cfg import AppConf
            t = AppConf.read('config').get('account', {}).get('timeout')
            return int(t) if t else self.requests_timeout
        except Exception:
            return self.requests_timeout

    @property
    def _verbose(self) -> bool:
        try:
            from lib.cfg import AppConf
            return bool(AppConf.read('config').get('debug', {}).get('verbose', False))
        except Exception:
            return False

    def request(self, method: Literal['get', 'post'], url: str, headers: dict[str, str], payload: dict[str, str] | None = None, files: dict | None = None) -> requests.Response:
        caller_hdr = dict(headers or {})
        try:
            x_gql_op = payload.get('operationName', 'viewer')
        except Exception:
            x_gql_op = 'viewer'
        x_gql_path = '/'
        referer = 'https://playerok.com/'
        if x_gql_op == 'chatMessages' and isinstance(payload, dict) and payload.get('variables'):
            try:
                vars_ = json.loads(payload['variables'])
                cid = (vars_.get('filter') or {}).get('chatId')
                if cid:
                    x_gql_path = '/chats/[id]'
                    referer = f'https://playerok.com/chats/{cid}'
            except Exception:
                pass
        wallet_ops = ('verifiedCards', 'SbpBankMembers', 'requestWithdrawal')

        if x_gql_op in wallet_ops:
            path_attempts = [
                ('/wallet', 'https://playerok.com/wallet'),
                ('/profile/wallet', 'https://playerok.com/profile/wallet'),
                ('/wallet/add', 'https://playerok.com/wallet/add'),
                ('/profile', 'https://playerok.com/profile'),
            ]
        else:
            path_attempts = [(x_gql_path, referer)]
        verbose = self._verbose

        if verbose:
            safe_payload = {k: v for k, v in (payload or {}).items() if k != 'query'} if isinstance(payload, dict) else payload
            self.logger.debug(f'→ {method.upper()} {url}  op={x_gql_op}  payload={safe_payload}')

        def make_req(req_headers: dict[str, str]):
            err = ''
            max_try = 8
            for attempt in range(max_try):
                try:
                    if method == 'get':
                        r = self.__curl_session.get(url=url, params=payload, headers=req_headers, timeout=self._timeout)
                    elif method == 'post':
                        if files:
                            r = self.__tls_requests.post(url=url, json=payload if not files else None, data=payload if files else None, headers=req_headers, files=files, timeout=self._timeout)
                        else:
                            r = self.__curl_session.post(url=url, json=payload, headers=req_headers, timeout=self._timeout)
                    return r
                except Exception as e:
                    err = str(e)
                    if _is_transport_recoverable(e):
                        if _is_proxy_dial_failure_message(err):
                            self.logger.warning(
                                'Прокси/сеть op=%s (без повторов curl-профиля): %s%s',
                                x_gql_op,
                                err[:800],
                                _proxy_dial_failure_hint(err),
                            )
                            raise RequestSendingError(url, err)
                        self.logger.warning(
                            'Транспорт/TLS op=%s попытка %s/%s (без перезапуска процесса): %s',
                            x_gql_op,
                            attempt + 1,
                            max_try,
                            err[:800],
                        )
                        self._refresh_clients()
                        continue
                    self.logger.debug('Ошибка при отправке запроса: %s', e)
                    self.logger.debug('Отправляю запрос повторно…')
            if err and 'curl: (28)' in err.lower():
                err = f'{err}{_proxy_dial_failure_hint(err)}'
            raise RequestSendingError(url, err)

        cf_sigs = ['<title>Just a moment...</title>', 'window._cf_chl_opt', 'Enable JavaScript and cookies to continue', 'Checking your browser before accessing', 'cf-browser-verification', 'Cloudflare Ray ID']
        max_cf_retries = 4

        for attempt_i, (pth, ref) in enumerate(path_attempts):
            _headers = {'accept': '*/*', 'accept-language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7', 'access-control-allow-headers': 'sentry-trace, baggage', 'apollo-require-preflight': 'true', 'apollographql-client-name': 'web', 'content-type': 'application/json', 'cookie': f'token={self.token}', 'origin': 'https://playerok.com', 'priority': 'u=1, i', 'referer': ref, 'sec-ch-ua': '"Chromium";v="144", "Google Chrome";v="144", "Not_A Brand";v="99"', 'sec-ch-ua-arch': '"x86"', 'sec-ch-ua-bitness': '"64"', 'sec-ch-ua-full-version': '"144.0.7559.110"', 'sec-ch-ua-full-version-list': 'Not(A:Brand";v="8.0.0.0", "Chromium";v="144.0.7559.110", "Google Chrome";v="144.0.7559.110"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-model': '""', 'sec-ch-ua-platform': '"Windows"', 'sec-ch-ua-platform-version': '"19.0.0"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin', 'user-agent': self.user_agent, 'x-gql-op': x_gql_op, 'x-gql-path': pth, 'x-timezone-offset': '-180'}
            req_headers = {k: v for k, v in _headers.items() if k not in caller_hdr.keys()}
            resp = None
            for cf_i in range(max_cf_retries):
                resp = make_req(req_headers)
                if not any((sig in resp.text for sig in cf_sigs)):
                    break
                snippet = (resp.text or '')[:240].replace('\n', ' ').replace('\r', '')
                self.logger.warning(
                    'Ответ похож на Cloudflare challenge op=%s path=%s — новая TLS-сессия, повтор %s/%s (без перезапуска). Начало тела: %s',
                    x_gql_op,
                    pth,
                    cf_i + 1,
                    max_cf_retries,
                    snippet,
                )
                self._refresh_clients()
            else:
                if resp is not None and any((sig in resp.text for sig in cf_sigs)):
                    raise CloudflareDetectedException(resp)

            json_data = {}
            try:
                json_data = resp.json()
            except Exception:
                pass

            if verbose:
                self.logger.debug(f'← {resp.status_code}  op={x_gql_op}  path={pth}  json={json.dumps(json_data, ensure_ascii=False)[:800]}')

            if 'errors' in json_data:
                msg = str((json_data.get('errors') or [{}])[0].get('message', '')).lower()
                permissionish = any(x in msg for x in ('доступ', 'access denied', 'permission', 'forbidden'))
                last_attempt = attempt_i >= len(path_attempts) - 1
                if x_gql_op not in wallet_ops or not permissionish or last_attempt:
                    if verbose:
                        self.logger.debug(f'⚠ API error  op={x_gql_op}  errors={json_data["errors"]}')
                    try:
                        err_txt = json.dumps(json_data.get('errors'), ensure_ascii=False)
                    except Exception:
                        err_txt = str(json_data.get('errors'))
                    self.logger.warning(
                        'GraphQL ошибка op=%s x-gql-path=%s referer=%s http=%s errors=%s',
                        x_gql_op,
                        pth,
                        ref,
                        resp.status_code,
                        err_txt[:2000],
                    )
                    raise RequestApiError(resp)
                self.logger.debug(
                    'GraphQL op=%s: отказ по доступу на path=%s — следующий referer/path…',
                    x_gql_op,
                    pth,
                )
                continue

            if resp.status_code != 200:
                if verbose:
                    self.logger.debug(f'⚠ HTTP {resp.status_code}  op={x_gql_op}  body={resp.text[:400]}')
                raise RequestFailedError(resp)
            return resp

    @staticmethod
    def _decode_jwt_sub(token: str) -> str | None:
        try:
            payload_part = token.split('.')[1]
            padding = (4 - len(payload_part) % 4) % 4
            decoded = base64.urlsafe_b64decode(payload_part + '=' * padding)
            return json.loads(decoded).get('sub')
        except Exception:
            return None

    def get(self) -> Conn:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'viewer', 'query': QUERIES.get('viewer'), 'variables': {}}
        url = f'{self.base_url}/graphql'
        last_err: BaseException | None = None
        for attempt in range(1, 4):
            try:
                r = self.request('post', url, headers, payload).json()
                break
            except RequestSendingError as e:
                last_err = e
                if attempt < 3:
                    self.logger.warning(
                        'viewer: сеть/прокси (%s/%s) — %s; повтор через 2 с…',
                        attempt,
                        3,
                        str(e)[:200],
                    )
                    time.sleep(2)
                continue
        else:
            raise last_err
        data: dict = r['data']['viewer']
        if data is None:
            raise UnauthorizedError()
        self.id = data.get('id')
        jwt_sub = self._decode_jwt_sub(self.token)
        if jwt_sub and self.id and jwt_sub != self.id:
            self.logger.warning(f'Ханипот: токен sub={jwt_sub}, вернули id={self.id}')
            raise HoneypotDetectedException(returned_id=self.id, token_sub=jwt_sub)
        self.username = data.get('username')
        self.email = data.get('email')
        self.role = data.get('role')
        self.has_frozen_balance = data.get('hasFrozenBalance')
        self.support_chat_id = data.get('supportChatId')
        self.system_chat_id = data.get('systemChatId')
        self.unread_chats_counter = data.get('unreadChatsCounter')
        self.is_blocked = data.get('isBlocked')
        self.is_blocked_for = data.get('isBlockedFor')
        self.created_at = data.get('createdAt')
        self.last_item_created_at = data.get('lastItemCreatedAt')
        self.has_confirmed_phone_number = data.get('hasConfirmedPhoneNumber')
        self.can_publish_items = data.get('canPublishItems')
        self.unread_chats_counter = data.get('unreadChatsCounter')
        headers = {'accept': '*/*'}
        payload = {'operationName': 'user', 'variables': json.dumps({'username': self.username, 'hasSupportAccess': False}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('user')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        data: dict = r['data']['user']
        if data.get('__typename') == 'User':
            self.profile = account_profile(data)
        return self

    def load_user(self, id: str | None = None, username: str | None = None) -> types.UserProfile:
        if not any([id, username]):
            raise TypeError('Не был передан ни один из обязательных аргументов: id, username')
        headers = {'accept': '*/*'}
        payload = {'operationName': 'user', 'variables': json.dumps({'id': id, 'username': username, 'hasSupportAccess': False}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('user')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        data: dict = r['data']['user']
        if data.get('__typename') == 'UserFragment':
            profile = data
        elif data.get('__typename') == 'User':
            profile = data.get('profile')
        else:
            profile = None
        return user_profile(profile)

    def load_deals(self, count: int = 24, statuses: list[DealStage] | None = None, direction: DealFlow | None = None, after_cursor: str = None) -> types.ItemDealList:
        str_statuses = [status.name for status in statuses] if statuses else None
        str_direction = direction.name if direction else None
        headers = {'accept': '*/*'}
        payload = {'operationName': 'deals', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'userId': self.id, 'direction': str_direction, 'status': str_statuses}, 'showForbiddenImage': True}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('deals')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return item_deal_list(r['data']['deals'])

    def load_deal(self, deal_id: str) -> types.ItemDeal:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'deal', 'variables': json.dumps({'id': deal_id, 'hasSupportAccess': False, 'showForbiddenImage': True}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('deal')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return item_deal(r['data']['deal'])

    def patch_deal(self, deal_id: str, new_status: DealStage) -> types.ItemDeal:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'updateDeal', 'variables': {'input': {'id': deal_id, 'status': new_status.name}}, 'query': QUERIES.get('updateDeal')}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload).json()
        return item_deal(r['data']['updateDeal'])

    def load_games(self, count: int = 24, type: GameTypes | None = None, after_cursor: str = None) -> types.GameList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'games', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'type': type.name if type else None}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('games')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game_list(r['data']['games'])

    def load_game(self, id: str | None = None, slug: str | None = None) -> types.Game:
        if not any([id, slug]):
            raise TypeError('Не был передан ни один из обязательных аргументов: id, slug')
        headers = {'accept': '*/*'}
        payload = {'operationName': 'GamePage', 'variables': json.dumps({'id': id, 'slug': slug}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('GamePage')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game(r['data']['game'])

    def load_category(self, id: str | None = None, game_id: str | None = None, slug: str | None = None) -> types.GameCategory:
        if not id and (not all([game_id, slug])):
            if not id and (game_id or slug):
                raise TypeError('Связка аргументов game_id, slug была передана не полностью')
            raise TypeError('Не был передан ни один из обязательных аргументов: id, game_id, slug')
        headers = {'accept': '*/*'}
        payload = {'operationName': 'GamePageCategory', 'variables': json.dumps({'id': id, 'gameId': game_id, 'slug': slug}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('GamePageCategory')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game_category(r['data']['gameCategory'])

    def load_agreements(self, game_category_id: str, user_id: str | None = None, count: int = 24, after_cursor: str | None = None) -> types.GameCategoryAgreementList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'gameCategoryAgreements', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'gameCategoryId': game_category_id, 'userId': user_id if user_id else self.id}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('gameCategoryAgreements')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game_category_agreement_list(r['data']['gameCategoryAgreements'])

    def load_obtain_types(self, game_category_id: str, count: int = 24, after_cursor: str | None = None) -> types.GameCategoryObtainingTypeList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'gameCategoryObtainingTypes', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'gameCategoryId': game_category_id}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('gameCategoryObtainingTypes')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game_category_obtaining_type_list(r['data']['gameCategoryObtainingTypes'])

    def load_instructions(self, game_category_id: str, obtaining_type_id: str, count: int = 24, type: InstructionFor | None = None, after_cursor: str | None = None) -> types.GameCategoryInstructionList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'gameCategoryInstructions', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'gameCategoryId': game_category_id, 'obtainingTypeId': obtaining_type_id, 'type': type.name if type else None}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('gameCategoryInstructions')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game_category_instruction_list(r['data']['gameCategoryInstructions'])

    def load_data_fields(self, game_category_id: str, obtaining_type_id: str, count: int = 24, type: FieldScope | None = None, after_cursor: str | None = None) -> types.GameCategoryDataFieldList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'gameCategoryDataFields', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'gameCategoryId': game_category_id, 'obtainingTypeId': obtaining_type_id, 'type': type.name if type else None}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('gameCategoryDataFields')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return game_category_data_field_list(r['data']['gameCategoryDataFields'])

    def load_chats(self, count: int = 24, type: RoomKind | None = None, status: RoomState | None = None, after_cursor: str | None = None) -> types.ChatList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'userChats', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': {'userId': self.id, 'type': type.name if type else None, 'status': status.name if status else None}, 'hasSupportAccess': False}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('userChats')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return chat_list(r['data']['chats'])

    def load_chat(self, chat_id: str) -> types.Chat:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'chat', 'variables': json.dumps({'id': chat_id, 'hasSupportAccess': False}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('chat')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return chat(r['data']['chat'])

    def find_chat_by_name(self, username: str) -> types.Chat | None:
        next_cursor = None
        while True:
            chats = self.load_chats(count=24, after_cursor=next_cursor)
            for chat_item in chats.chats:
                if any((user for user in chat_item.users if user.username.lower() == username.lower())):
                    return chat_item
            if not chats.page_info.has_next_page:
                break
            next_cursor = chats.page_info.end_cursor

    _CHAT_MESSAGES_PAGE = 10

    def load_messages(self, chat_id: str, count: int = 25, after_cursor: str | None = None) -> types.ChatMessageList:
        headers = {'accept': '*/*'}
        collected: list = []
        cursor = after_cursor
        last_list: types.ChatMessageList | None = None
        while len(collected) < count:
            batch = min(self._CHAT_MESSAGES_PAGE, count - len(collected))
            pag: dict = {'first': batch}
            if cursor is not None:
                pag['after'] = cursor
            payload = {'operationName': 'chatMessages', 'variables': json.dumps({'pagination': pag, 'filter': {'chatId': chat_id}, 'hasSupportAccess': False, 'showForbiddenImage': True}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('chatMessages')}})}
            r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
            lst = chat_message_list(r['data']['chatMessages'])
            last_list = lst
            collected.extend(lst.messages)
            pi = lst.page_info
            if not pi or not pi.has_next_page or not pi.end_cursor:
                break
            cursor = pi.end_cursor
        total = last_list.total_count if last_list else len(collected)
        pi = last_list.page_info if last_list else None
        return types.ChatMessageList(messages=collected[:count], page_info=pi, total_count=total)

    def read_chat(self, chat_id: str) -> types.Chat:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'markChatAsRead', 'query': QUERIES.get('markChatAsRead'), 'variables': {'input': {'chatId': chat_id}}}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload).json()
        return chat(r['data']['markChatAsRead'])

    def send_message(self, chat_id: str, text: str | None = None, photo_file_path: str | None = None, read_chat: bool = False) -> types.ChatMessage:
        if not any([text, photo_file_path]):
            raise TypeError('Не был передан ни один из обязательных аргументов: text, photo_file_path')
        if read_chat:
            self.read_chat(chat_id=chat_id)
        headers = {'accept': '*/*'}
        operations = {'operationName': 'createChatMessage', 'query': QUERIES.get('createChatMessageWithFile') if photo_file_path else QUERIES.get('createChatMessage'), 'variables': {'input': {'chatId': chat_id}}}
        if photo_file_path:
            operations['variables']['file'] = None
        elif text:
            operations['variables']['input']['text'] = text
        files = {'1': open(photo_file_path, 'rb')} if photo_file_path else None
        map_data = {'1': ['variables.file']} if photo_file_path else None
        payload = operations if not files else {'operations': json.dumps(operations), 'map': json.dumps(map_data)}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload, files).json()
        return chat_message(r['data']['createChatMessage'])

    def new_listing(self, game_category_id: str, obtaining_type_id: str, name: str, price: int, description: str, options: list[GameCategoryOption], data_fields: list[GameCategoryDataField], attachments: list[str]) -> types.Item:
        payload_attributes = {option.field: option.value for option in options}
        payload_data_fields = [{'fieldId': field.id, 'value': field.value} for field in data_fields]
        headers = {'accept': '*/*'}
        operations = {'operationName': 'createItem', 'query': QUERIES.get('createItem'), 'variables': {'input': {'gameCategoryId': game_category_id, 'obtainingTypeId': obtaining_type_id, 'name': name, 'price': int(price), 'description': description, 'attributes': payload_attributes, 'dataFields': payload_data_fields}, 'attachments': [None] * len(attachments)}}
        map_data = {}
        files = {}
        for i, att in enumerate(attachments, start=1):
            map_data[str(i)] = [f'variables.attachments.{i - 1}']
            files[str(i)] = open(att, 'rb')
        payload = {'operations': json.dumps(operations), 'map': json.dumps(map_data)}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload, files).json()
        return item(r['data']['createItem'])

    def edit_listing(self, id: str, name: str | None = None, price: int | None = None, description: str | None = None, options: list[GameCategoryOption] | None = None, data_fields: list[GameCategoryDataField] | None = None, remove_attachments: list[str] | None = None, add_attachments: list[str] | None = None) -> types.Item:
        payload_attributes = {option.field: option.value for option in options} if options is not None else None
        payload_data_fields = [{'fieldId': field.id, 'value': field.value} for field in data_fields] if data_fields is not None else None
        headers = {'accept': '*/*'}
        operations = {'operationName': 'updateItem', 'query': QUERIES.get('updateItem'), 'variables': {'input': {'id': id}, 'addedAttachments': [None] * len(add_attachments) if add_attachments else None}}
        if name:
            operations['variables']['input']['name'] = name
        if price:
            operations['variables']['input']['price'] = int(price)
        if description:
            operations['variables']['input']['description'] = description
        if options:
            operations['variables']['input']['attributes'] = payload_attributes
        if data_fields:
            operations['variables']['input']['dataFields'] = payload_data_fields
        if remove_attachments:
            operations['variables']['input']['removedAttachments'] = remove_attachments
        map_data = {}
        files = {}
        if add_attachments:
            for i, att in enumerate(add_attachments, start=1):
                map_data[str(i)] = [f'variables.addedAttachments.{i - 1}']
                files[str(i)] = open(att, 'rb')
        payload = {'operations': json.dumps(operations), 'map': json.dumps(map_data)}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload if files else operations, files if files else None).json()
        return item(r['data']['updateItem'])

    def delete_listing(self, id: str) -> bool:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'removeItem', 'query': QUERIES.get('removeItem'), 'variables': {'id': id}}
        self.request('post', f'{self.base_url}/graphql', headers, payload)
        return True

    def activate_listing(self, item_id: str, priority_status_id: str | None = None, transaction_provider_id: PayGateway = PayGateway.LOCAL) -> types.Item:
        headers = {'accept': '*/*'}
        statuses = [priority_status_id] if priority_status_id else []
        payload = {'operationName': 'publishItem', 'query': QUERIES.get('publishItem'), 'variables': {'input': {'transactionProviderId': transaction_provider_id.name, 'priorityStatuses': statuses, 'itemId': item_id}}}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload).json()
        return item(r['data']['publishItem'])

    def load_listings(self, game_id: str | None = None, category_id: str | None = None, count: int = 24, status: ListingStage = ListingStage.APPROVED, after_cursor: str | None = None) -> types.ItemProfileList:
        if not any([game_id, category_id]):
            raise TypeError('Не был передан ни один из обязательных аргументов: game_id, category_id')
        headers = {'accept': '*/*'}
        filter_data = {'gameId': game_id, 'status': [status.name] if status else None} if not category_id else {'gameCategoryId': category_id, 'status': [status.name] if status else None}
        payload = {'operationName': 'items', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': filter_data}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('items')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return item_profile_list(r['data']['items'])

    def load_listing(self, id: str | None = None, slug: str | None = None) -> types.MyItem | types.Item | types.ItemProfile:
        if not any([id, slug]):
            raise TypeError('Не был передан ни один из обязательных аргументов: id, slug')
        headers = {'accept': '*/*'}
        payload = {'operationName': 'item', 'variables': json.dumps({'id': id, 'slug': slug, 'hasSupportAccess': False, 'showForbiddenImage': True}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('item')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        data: dict = r['data']['item']
        if data['__typename'] == 'MyItem':
            _item = my_item(data)
        elif data['__typename'] == 'ItemProfile':
            _item = item_profile(data)
        elif data['__typename'] in ['Item', 'ForeignItem']:
            _item = item(data)
        else:
            _item = None
        return _item

    def load_boost_tiers(self, item_id: str, item_price: int) -> list[types.ItemPriorityStatus]:
        headers = {'accept': '*/*'}
        price = int(item_price)
        payload = {'operationName': 'itemPriorityStatuses', 'variables': json.dumps({'itemId': item_id, 'price': price}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('itemPriorityStatuses')}})}
        resp = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        tiers_raw = resp.get('data', {}).get('itemPriorityStatuses', [])
        self.logger.debug('itemPriorityStatuses[itemId=%s price=%s] → %s', item_id, price, tiers_raw)
        return [item_priority_status(r) if isinstance(r, dict) else r for r in tiers_raw]

    def apply_boost(self, item_id: str, priority_status_id: str, payment_method_id: PayMethod | None = None, transaction_provider_id: PayGateway = PayGateway.LOCAL) -> types.Item:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'increaseItemPriorityStatus', 'query': QUERIES.get('increaseItemPriorityStatus'), 'variables': {'input': {'itemId': item_id, 'priorityStatuses': [priority_status_id], 'transactionProviderData': {'paymentMethodId': payment_method_id.name if payment_method_id else None}, 'transactionProviderId': transaction_provider_id.name}}}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload).json()
        return item(r['data']['increaseItemPriorityStatus'])

    def load_providers(self, direction: TxDirection = TxDirection.IN) -> list[types.TransactionProvider]:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'transactionProviders', 'variables': json.dumps({'filter': {'direction': direction.name if direction else None}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('transactionProviders')}})}
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return [transaction_provider(provider) for provider in r['data']['transactionProviders']]

    def load_txs(self, count: int = 24, operation: TxKind | None = None, min_value: int | None = None, max_value: int | None = None, provider_id: PayGateway | None = None, status: TxStage | None = None, after_cursor: str | None = None) -> TransactionList:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'transactions', 'variables': {'pagination': {'first': count, 'after': after_cursor}, 'filter': {'userId': self.id}, 'hasSupportAccess': False}, 'extensions': {'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('transactions')}}}
        if operation:
            payload['variables']['filter']['operation'] = [operation.name]
        if min_value or max_value:
            payload['variables']['filter']['value'] = {}
            if min_value:
                payload['variables']['filter']['value']['min'] = str(min_value)
            if max_value:
                payload['variables']['filter']['value']['max'] = str(max_value)
        if provider_id:
            payload['variables']['filter']['providerId'] = [provider_id.name]
        if status:
            payload['variables']['filter']['status'] = [status.name]
        payload['variables'] = json.dumps(payload['variables'])
        payload['extensions'] = json.dumps(payload['extensions'])
        r = self.request('get', f'{self.base_url}/graphql', headers, payload).json()
        return transaction_list(r['data']['transactions'])

    def cancel_tx(self, transaction_id: str) -> types.Transaction:
        headers = {'accept': '*/*'}
        payload = {'operationName': 'removeTransaction', 'query': QUERIES.get('removeTransaction'), 'variables': {'id': transaction_id}}
        r = self.request('post', f'{self.base_url}/graphql', headers, payload).json()
        return transaction(r['data']['removeTransaction'])
