from __future__ import annotations

import base64
import json
import mimetypes
import os
import tempfile
import threading
import uuid
from contextlib import ExitStack
from urllib.parse import urlparse
from http.cookies import CookieError, SimpleCookie
from logging import getLogger
from threading import RLock
from typing import Iterator, Literal

import certifi
import curl_cffi

from constants.contracts import ORIGIN
from constants.transport import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    MAX_ATTACHMENT_BYTES,
    MAX_CLONE_ATTACHMENTS,
    MAX_MESSAGE_COUNT,
    MAX_PAGES,
    MESSAGE_PAGE_SIZE,
    VIEWER_FIELDS,
)
from lib.util import ascii_safe_ca_bundle, proxy_url_for_requests

from . import models as types
from .cookies import parse_cookies, parse_cookies_lenient
from .defs import *
from .gql import *
from .transport import GraphQLTransport, ResponseContractError, impersonation_for

PUBLISHABLE_STAGES = (ListingStage.DRAFT, ListingStage.DECLINED, ListingStage.EXPIRED, ListingStage.SOLD)
BOOSTABLE_STAGES = (ListingStage.APPROVED, ListingStage.PENDING_MODERATION, ListingStage.PENDING_APPROVAL)


def active_conn() -> Conn | None:
    from .client import get_account
    try:
        return get_account()
    except RuntimeError:
        return None


class Conn:
    def __init__(self, token=None, user_agent="", proxy=None,
                 requests_timeout=DEFAULT_TIMEOUT, request_max_retries=2,
                 cookies=None, ddg5="", anonymous=False, **kwargs):
        self.anonymous = bool(anonymous)
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.requests_timeout = int(requests_timeout or DEFAULT_TIMEOUT)
        self.request_max_retries = request_max_retries
        self.proxy = proxy
        self.base_url = ORIGIN
        self.logger = getLogger("pl.conn")
        self._cookies_lock = RLock()
        self._sessions_lock = RLock()
        self._configure_credentials(token, cookies, ddg5)
        self._ca_bundle = ascii_safe_ca_bundle() or certifi.where()
        self.profile = None
        for attribute in VIEWER_FIELDS:
            setattr(self, attribute, None)
        self._configure_transport()

    def _configure_credentials(self, token, cookies, ddg5):
        self.cookies = parse_cookies_lenient(cookies)
        if token and self.cookies.get("token", token) != token:
            raise ValueError("Токен в account.token не совпадает с Cookie token")
        if token:
            self.cookies.update(parse_cookies({"token": token}))
        if ddg5:
            self.cookies.update(parse_cookies({"__ddg5_": ddg5}))
        self.token = self.cookies.get("token", "")
        self.ddg5 = self.cookies.get("__ddg5_", "")
        if not self.token and not self.anonymous:
            raise ValueError("Нужен token или Cookie с полем token=... от playerok.com")

    def _configure_transport(self):
        self.impersonate = impersonation_for(self.user_agent)
        self._local = threading.local()
        self._sessions: list = []
        self._session = None
        self._transport = GraphQLTransport(None, self)

    def _thread_session(self):
        if self._session is not None:
            return self._session
        session = getattr(self._local, "session", None)
        if session is None:
            proxy = proxy_url_for_requests(self.proxy) if self.proxy else None
            session = curl_cffi.Session(impersonate=self.impersonate, proxy=proxy,
                                        verify=self._ca_bundle, timeout=self.requests_timeout)
            self._local.session = session
            with self._sessions_lock:
                self._sessions.append(session)
        return session

    @property
    def proxy_url(self) -> str | None:
        return proxy_url_for_requests(self.proxy) if self.proxy else None

    @staticmethod
    def _build_cookie_jar(cookies):
        return parse_cookies(cookies)

    def _cookie_header(self):
        with self._cookies_lock:
            return "; ".join(f"{key}={value}" for key, value in self.cookies.items() if value)

    def _ingest_set_cookie(self, response):
        headers = getattr(response, "headers", None)
        get_list = getattr(headers, "get_list", None)
        if not callable(get_list):
            return
        for value in get_list("set-cookie") or []:
            self._ingest_cookie_header(value)

    def _ingest_cookie_header(self, value):
        parsed = SimpleCookie()
        try:
            parsed.load(value)
        except CookieError:
            self.logger.warning("Отклонён некорректный Set-Cookie")
            return
        for name, cookie in parsed.items():
            if cookie["domain"] and cookie["domain"].lstrip(".").lower() != "playerok.com":
                continue
            if cookie["path"] not in ("", "/"):
                continue
            self._update_cookie(name, cookie)

    def replace_cookies(self, cookies) -> None:
        parsed = parse_cookies_lenient(cookies)
        if not parsed.get("token"):
            raise ValueError("В новых Cookie нет token")
        with self._cookies_lock:
            self.cookies = parsed
            self.token = parsed.get("token", "")
            self.ddg5 = parsed.get("__ddg5_", "")

    def _update_cookie(self, name, cookie):
        with self._cookies_lock:
            if cookie["max-age"] == "0" or not cookie.value:
                self.cookies.pop(name, None)
            else:
                try:
                    self.cookies.update(parse_cookies({name: cookie.value}))
                except (TypeError, ValueError):
                    self.logger.warning("Отклонено значение Cookie %s", name)
                    return
            self.token = self.cookies.get("token", "")

    @property
    def _timeout(self):
        return self.requests_timeout

    def request(self, method, url, headers, payload=None, files=None):
        return self._transport.send(method, url, headers, payload, files)

    def forget_uncertain(self, prefix=None):
        self._transport.forget_uncertain(prefix)

    def close(self):
        with self._sessions_lock:
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass
        self._local = threading.local()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def _graphql(self, operation: str, variables: dict) -> dict:
        payload = {"operationName": operation, "variables": variables}
        response = self.request("post", f"{self.base_url}/graphql", {"accept": "*/*"}, payload)
        return response.json()["data"]

    @staticmethod
    def _decode_jwt_sub(token: str) -> str | None:
        try:
            payload_part = token.split('.')[1]
            padding = (4 - len(payload_part) % 4) % 4
            decoded = base64.urlsafe_b64decode(payload_part + '=' * padding)
            return json.loads(decoded).get('sub')
        except (ValueError, TypeError, IndexError, KeyError, AttributeError):
            return None

    def get(self) -> Conn:
        self._apply_viewer(self._graphql("viewer", {}).get("viewer"))
        data = self._graphql("user", {"id": self.id, "hasSupportAccess": False}).get("user")
        if not isinstance(data, dict) or data.get("id") != self.id:
            raise ResponseContractError("Профиль аккаунта не получен или не совпадает")
        self.profile = account_profile(data)
        return self

    def _apply_viewer(self, data):
        if data is None:
            raise UnauthorizedError()
        if not isinstance(data, dict) or not data.get("id"):
            raise ResponseContractError("Playerok не вернул id аккаунта")
        token_subject = self._decode_jwt_sub(self.token)
        if token_subject and data["id"] != token_subject:
            raise HoneypotDetectedException(returned_id=data["id"], token_sub=token_subject)
        for attribute, field in VIEWER_FIELDS.items():
            setattr(self, attribute, data.get(field))

    def load_balance(self) -> types.AccountBalance | None:
        data = self._graphql("viewerBalance", {}).get("viewer") or {}
        return account_balance(data.get("balance"))

    def load_user(self, id: str | None = None, username: str | None = None) -> types.UserProfile | None:
        if not any([id, username]):
            raise TypeError('Не был передан ни один из обязательных аргументов: id, username')
        data = self._graphql("user", {"id": id, "username": username, "hasSupportAccess": False}).get("user")
        if data is None:
            return None
        if data.get('__typename') == 'UserFragment':
            profile = data
        elif data.get('__typename') == 'User':
            profile = data.get('profile') or data
        else:
            profile = None
        user = user_profile(profile)
        if user is not None:
            user.account = self
        return user

    def load_deals(self, count: int = 24, statuses: list[DealStage] | None = None, direction: DealFlow | None = None, after_cursor: str | None = None) -> types.ItemDealList:
        variables = {
            "pagination": {"first": count, "after": after_cursor},
            "filter": {"userId": self.id, "direction": direction.name if direction else None,
                       "status": [status.name for status in statuses] if statuses else None},
            "showForbiddenImage": True,
        }
        return item_deal_list(self._graphql("deals", variables)["deals"])

    def load_deal(self, deal_id: str) -> types.ItemDeal:
        data = self._graphql("deal", {"id": deal_id, "hasSupportAccess": False, "showForbiddenImage": True})
        return item_deal(data["deal"])

    def patch_deal(self, deal_id: str, new_status: DealStage) -> types.ItemDeal:
        data = self._graphql("updateDeal", {"input": {"id": deal_id, "status": new_status.name}, "showForbiddenImage": True})
        return item_deal(data["updateDeal"])

    def load_games(self, count: int = 24, type: GameTypes | None = None, after_cursor: str | None = None) -> types.GameList:
        variables = {"pagination": {"first": count, "after": after_cursor}, "filter": {"type": type.name if type else None}}
        return game_list(self._graphql("games", variables)["games"])

    def load_game(self, id: str | None = None, slug: str | None = None) -> types.Game:
        if not any([id, slug]):
            raise TypeError('Не был передан ни один из обязательных аргументов: id, slug')
        return game(self._graphql("GamePage", {"id": id, "slug": slug})["game"])

    def load_category(self, id: str | None = None, game_id: str | None = None, slug: str | None = None) -> types.GameCategory:
        if not id and not all([game_id, slug]):
            if game_id or slug:
                raise TypeError('Связка аргументов game_id, slug была передана не полностью')
            raise TypeError('Не был передан ни один из обязательных аргументов: id, game_id, slug')
        if not id:
            game_data = self.load_game(id=game_id)
            category = next((row for row in (game_data.categories if game_data else []) if row.slug == slug), None)
            if category is None:
                raise ValueError('Категория не найдена в указанной игре')
            id = category.id
        return game_category(self._graphql("GamePageCategory", {"id": id})["gameCategory"])

    def load_agreements(self, game_category_id: str, user_id: str | None = None, count: int = 24, after_cursor: str | None = None) -> types.GameCategoryAgreementList:
        variables = {"pagination": {"first": count, "after": after_cursor},
                     "filter": {"gameCategoryId": game_category_id, "userId": user_id or self.id}}
        return game_category_agreement_list(self._graphql("gameCategoryAgreements", variables)["gameCategoryAgreements"])

    def load_obtain_types(self, game_category_id: str, count: int = 24, after_cursor: str | None = None) -> types.GameCategoryObtainingTypeList:
        variables = {"pagination": {"first": count, "after": after_cursor}, "filter": {"gameCategoryId": game_category_id}}
        return game_category_obtaining_type_list(self._graphql("gameCategoryObtainingTypes", variables)["gameCategoryObtainingTypes"])

    def load_instructions(self, game_category_id: str, obtaining_type_id: str, count: int = 24, type: InstructionFor | None = None, after_cursor: str | None = None) -> types.GameCategoryInstructionList:
        variables = {"pagination": {"first": count, "after": after_cursor},
                     "filter": {"gameCategoryId": game_category_id, "obtainingTypeId": obtaining_type_id,
                                "type": type.name if type else None}}
        return game_category_instruction_list(self._graphql("gameCategoryInstructions", variables)["gameCategoryInstructions"])

    def load_data_fields(self, game_category_id: str, obtaining_type_id: str, count: int = 24, type: FieldScope | None = None, after_cursor: str | None = None) -> types.GameCategoryDataFieldList:
        variables = {"pagination": {"first": count, "after": after_cursor},
                     "filter": {"gameCategoryId": game_category_id, "obtainingTypeId": obtaining_type_id,
                                "type": type.name if type else None}}
        return game_category_data_field_list(self._graphql("gameCategoryDataFields", variables)["gameCategoryDataFields"])

    def load_chats(self, count: int = 24, type: RoomKind | None = None, status: RoomState | None = None, after_cursor: str | None = None) -> types.ChatList:
        pagination: dict = {"first": count}
        if after_cursor is not None:
            pagination["after"] = after_cursor
        filters: dict = {"userId": self.id}
        if type is not None:
            filters["type"] = type.name
        if status is not None:
            filters["status"] = status.name
        return chat_list(self._graphql("userChats", {"pagination": pagination, "filter": filters})["chats"])

    def load_chat(self, chat_id: str) -> types.Chat:
        return chat(self._graphql("chat", {"id": chat_id, "hasSupportAccess": False})["chat"])

    def find_chat_by_name(self, username: str) -> types.Chat | None:
        next_cursor = None
        visited = set()
        wanted = (username or "").lower()
        for _ in range(MAX_PAGES):
            chats = self.load_chats(count=24, after_cursor=next_cursor)
            for chat_item in chats.chats:
                if any(user for user in chat_item.users if user and (user.username or "").lower() == wanted):
                    return chat_item
            if not chats.page_info or not chats.page_info.has_next_page:
                return None
            next_cursor = chats.page_info.end_cursor
            if not next_cursor or next_cursor in visited:
                raise ResponseContractError('Курсор списка чатов не сдвинулся')
            visited.add(next_cursor)
        return None

    _CHAT_MESSAGES_PAGE = MESSAGE_PAGE_SIZE

    def _chat_messages_one_page(self, chat_id: str, pag: dict, show_forbidden: bool, method: Literal['get', 'post']) -> dict:
        variables = {'pagination': pag, 'filter': {'chatId': chat_id}, 'hasSupportAccess': False,
                     'showForbiddenImage': show_forbidden}
        payload = {'operationName': 'chatMessages', 'variables': json.dumps(variables)}
        return self.request('get', f'{self.base_url}/graphql', {'accept': '*/*'}, payload).json()

    def load_messages(self, chat_id: str, count: int = 25, after_cursor: str | None = None) -> types.ChatMessageList:
        if type(count) is not int or not 1 <= count <= MAX_MESSAGE_COUNT:
            raise ValueError("Некорректное количество сообщений")
        collected, seen_ids, visited = [], set(), {after_cursor}
        cursor = after_cursor
        info = None
        total = None
        while len(collected) < count:
            pagination = {"first": min(MESSAGE_PAGE_SIZE, count - len(collected))}
            if cursor is not None:
                pagination["after"] = cursor
            response = self._chat_messages_one_page(chat_id, pagination, True, "get")
            page = chat_message_list(response["data"]["chatMessages"])
            if page is None:
                raise ResponseContractError("Playerok не вернул список сообщений")
            total = page.total_count
            for message in page.messages:
                if message and message.id not in seen_ids:
                    collected.append(message)
                    seen_ids.add(message.id)
            info = page.page_info
            if not info or not info.has_next_page or len(collected) >= count:
                break
            cursor = info.end_cursor
            if not cursor or cursor in visited or not page.messages:
                raise ResponseContractError("Курсор сообщений не сдвинулся")
            visited.add(cursor)
        return types.ChatMessageList(collected, info, total)

    def read_chat(self, chat_id: str) -> types.Chat:
        return chat(self._graphql("markChatAsRead", {"input": {"chatId": chat_id}})["markChatAsRead"])

    def upload_chat_image(self, photo_file_path: str, chat_id: str) -> types.TemporaryAttachmentUploadOutput:
        operations = {
            'operationName': 'uploadChatImageIntoTemporaryStore',
            'variables': {'file': None, 'input': {'chatId': chat_id, 'clientAttachmentId': str(uuid.uuid4())}},
        }
        with open(photo_file_path, 'rb') as fh:
            payload = {'operations': json.dumps(operations), 'map': json.dumps({'1': ['variables.file']})}
            r = self.request('post', f'{self.base_url}/graphql', {'accept': '*/*'}, payload, {'1': fh}).json()
        return temporary_attachment_upload_output(r['data']['uploadChatImageIntoTemporaryStore'])

    def send_message(self, chat_id: str, text: str | None = None, photo_file_path: str | list[str] | None = None, read_chat: bool = False) -> types.ChatMessage:
        if not text and not photo_file_path:
            raise TypeError('Не был передан ни один из обязательных аргументов: text, photo_file_path')
        if read_chat:
            try:
                self.read_chat(chat_id=chat_id)
            except Exception as error:
                self.logger.debug('markChatAsRead %s не выполнен: %s', chat_id, error)
        if photo_file_path is None:
            image_paths: list[str] = []
        elif isinstance(photo_file_path, str):
            image_paths = [photo_file_path]
        else:
            image_paths = list(photo_file_path)
        images_ids: list[str] = []
        for path in image_paths:
            uploaded = self.upload_chat_image(path, chat_id)
            if uploaded and getattr(uploaded, 'id', None):
                images_ids.append(uploaded.id)
        variables = {'input': {'chatId': chat_id, 'imagesIds': images_ids, 'text': text or ''}, 'showForbiddenImage': True}
        return chat_message(self._graphql('createChatMessage', variables)['createChatMessage'])

    def _upload_listing(self, operation, variables, paths, variable_name):
        operations = {"operationName": operation, "variables": {**variables, variable_name: [None] * len(paths)}}
        with ExitStack() as stack:
            files = {str(index): stack.enter_context(open(path, "rb")) for index, path in enumerate(paths, start=1)}
            if files:
                mapping = {str(index): [f"variables.{variable_name}.{index - 1}"] for index in range(1, len(paths) + 1)}
                payload = {"operations": json.dumps(operations), "map": json.dumps(mapping)}
                response = self.request("post", f"{self.base_url}/graphql", {}, payload, files).json()
            else:
                response = self.request("post", f"{self.base_url}/graphql", {}, operations).json()
        data = response["data"][operation]
        return my_item(data) if data.get("__typename") == "MyItem" else item(data)

    def new_listing(self, game_category_id: str, obtaining_type_id: str | None, name: str, price: int,
                    description: str, options: list[GameCategoryOption] | None = None,
                    data_fields: list[GameCategoryDataField] | None = None, attachments: list[str] | None = None,
                    attachment_ids: list[str] | None = None, comment: str | None = None,
                    attributes: dict | None = None) -> types.Item:
        fields = {"gameCategoryId": game_category_id, "name": name, "price": int(price), "description": description}
        if obtaining_type_id:
            fields["obtainingTypeId"] = obtaining_type_id
        if attributes is not None:
            fields["attributes"] = attributes
        elif options:
            fields["attributes"] = {option.field: option.value for option in options}
        if data_fields:
            fields["dataFields"] = [{"fieldId": field.id, "value": field.value} for field in data_fields if field and field.value is not None]
        if comment:
            fields["comment"] = comment
        if attachment_ids:
            fields["attachmentIds"] = list(attachment_ids)
            return self._upload_listing("createItem", {"input": fields, "showForbiddenImage": True}, [], "attachments")
        return self._upload_listing("createItem", {"input": fields, "showForbiddenImage": True}, attachments or [], "attachments")

    def edit_listing(self, id: str, name: str | None = None, price: int | None = None,
                     description: str | None = None, options: list[GameCategoryOption] | None = None,
                     data_fields: list[GameCategoryDataField] | None = None,
                     remove_attachments: list[str] | None = None,
                     add_attachments: list[str] | None = None, keep_in_sale: bool | None = None,
                     comment: str | None = None) -> types.Item:
        candidates = {
            "name": name, "price": int(price) if price is not None else None,
            "description": description, "removedAttachments": remove_attachments,
            "attributes": {option.field: option.value for option in options} if options is not None else None,
            "dataFields": [{"fieldId": field.id, "value": field.value} for field in data_fields] if data_fields is not None else None,
            "keepInSale": keep_in_sale, "comment": comment,
        }
        fields = {"id": id, **{key: value for key, value in candidates.items() if value is not None}}
        return self._upload_listing("updateItem", {"input": fields, "showForbiddenImage": True}, add_attachments or [], "addedAttachments")

    def set_keep_in_sale(self, item_id: str, keep_in_sale: bool) -> types.Item:
        return self.edit_listing(item_id, keep_in_sale=bool(keep_in_sale))

    def download_attachment(self, url: str, folder: str) -> str:
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "playerok.com" or host.endswith(".playerok.com")):
            raise ValueError("Картинка лота размещена не на playerok.com")
        headers = {"user-agent": self.user_agent, "accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                   "referer": f"{ORIGIN}/"}
        response = self._thread_session().get(url, headers=headers, timeout=self._timeout,
                                              allow_redirects=False, discard_cookies=True)
        if response.status_code != 200:
            raise RequestFailedError(response)
        content = response.content or b""
        kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not kind.startswith("image/") or not content or len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError("Не удалось скачать картинку лота")
        path = os.path.join(folder, f"{uuid.uuid4().hex}{mimetypes.guess_extension(kind) or '.jpg'}")
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def clone_listing(self, source: types.MyItem | types.Item, price: int | None = None, name: str | None = None,
                      obtaining_type_id: str | None = None) -> types.Item:
        category = getattr(source, "category", None)
        obtaining = getattr(source, "obtaining_type", None)
        if category is None or not category.id:
            raise ValueError("У исходного лота нет категории")
        source_type = obtaining.id if obtaining else None
        target_type = obtaining_type_id or source_type
        urls = [file.url for file in (getattr(source, "attachments", None) or []) if file and file.url]
        if not urls:
            raise ValueError("У исходного лота нет картинок, а без них Playerok не создаст лот")
        same_type = target_type == source_type
        data_fields = [field for field in (getattr(source, "data_fields", None) or []) if field and field.value] if same_type else []
        with tempfile.TemporaryDirectory(prefix="pok-clone-") as folder:
            paths = [self.download_attachment(url, folder) for url in urls[:MAX_CLONE_ATTACHMENTS]]
            return self.new_listing(
                game_category_id=category.id,
                obtaining_type_id=target_type,
                name=name or source.name,
                price=int(price if price is not None else (getattr(source, "raw_price", None) or source.price)),
                description=getattr(source, "description", "") or "",
                data_fields=data_fields,
                attachments=paths,
                comment=getattr(source, "comment", None),
                attributes=getattr(source, "attributes", None) or None,
            )

    def delete_listing(self, id: str) -> bool:
        self._graphql("removeItem", {"id": id, "showForbiddenImage": True})
        return True

    def activate_listing(self, item_id: str, priority_status_id: str | None = None,
                         transaction_provider_id: PayGateway = PayGateway.LOCAL,
                         keep_in_sale: bool | None = None) -> types.Item:
        statuses = [priority_status_id] if priority_status_id else []
        payload = {"itemId": item_id, "priorityStatuses": statuses, "transactionProviderId": transaction_provider_id.name}
        if keep_in_sale is not None:
            payload["keepInSale"] = bool(keep_in_sale)
        return item(self._graphql("publishItem", {"input": payload, "showForbiddenImage": True})["publishItem"])

    def load_listings(self, game_id: str | None = None, category_id: str | None = None, count: int = 24, status: ListingStage = ListingStage.APPROVED, after_cursor: str | None = None) -> types.ItemProfileList:
        if not any([game_id, category_id]):
            raise TypeError('Не был передан ни один из обязательных аргументов: game_id, category_id')
        filters = {'gameCategoryId': category_id} if category_id else {'gameId': game_id}
        filters['status'] = [status.name] if status else None
        variables = {'pagination': {'first': count, 'after': after_cursor}, 'filter': filters, 'showForbiddenImage': True}
        return item_profile_list(self._graphql('items', variables)['items'])

    def load_my_items(self, statuses: list[ListingStage] | None = None, count: int = 24, after_cursor: str | None = None) -> types.ItemProfileList:
        filters = {'userId': self.id}
        if statuses:
            filters['status'] = [status.name for status in statuses]
        variables = {'pagination': {'first': count, 'after': after_cursor}, 'filter': filters, 'showForbiddenImage': True}
        return item_profile_list(self._graphql('items', variables)['items'])

    def iter_my_items(self, statuses: list[ListingStage] | None = None, page_size: int = 24) -> Iterator[types.ItemProfile]:
        cursor, visited = None, set()
        for _ in range(MAX_PAGES):
            page = self.load_my_items(statuses=statuses, count=page_size, after_cursor=cursor)
            if page is None:
                return
            for entry in page.items:
                if entry is not None:
                    yield entry
            info = page.page_info
            if not info or not info.has_next_page:
                return
            cursor = info.end_cursor
            if not cursor or cursor in visited:
                raise ResponseContractError('Курсор списка лотов не сдвинулся')
            visited.add(cursor)

    def load_listing(self, id: str | None = None, slug: str | None = None) -> types.MyItem | types.Item | types.ItemProfile | None:
        if not any([id, slug]):
            raise TypeError('Не был передан ни один из обязательных аргументов: id, slug')
        try:
            data = self._graphql('item', {'id': id, 'slug': slug, 'hasSupportAccess': False, 'showForbiddenImage': True})['item']
        except RequestApiError as error:
            if error.error_code == 'NOT_FOUND':
                return None
            raise
        if data is None:
            return None
        kind = data.get('__typename')
        if kind == 'MyItem':
            return my_item(data)
        if kind in ('ItemProfile', 'MyItemProfile', 'ForeignItemProfile'):
            return item_profile(data)
        if kind in ('Item', 'ForeignItem'):
            return item(data)
        return None

    def load_boost_tiers(self, item_id: str, item_price: int) -> list[types.ItemPriorityStatus]:
        data = self._graphql('itemPriorityStatuses', {'itemId': item_id, 'price': int(item_price)})
        rows = data.get('itemPriorityStatuses') or []
        return [item_priority_status(row) for row in rows if isinstance(row, dict)]

    def apply_boost(self, item_id: str, priority_status_id: str, payment_method_id: PayMethod | None = None,
                    transaction_provider_id: PayGateway = PayGateway.LOCAL,
                    keep_in_sale: bool | None = None) -> types.Item:
        payload = {'itemId': item_id, 'priorityStatuses': [priority_status_id],
                   'transactionProviderId': transaction_provider_id.name}
        if payment_method_id:
            payload['transactionProviderData'] = {'paymentMethodId': payment_method_id.name}
        if keep_in_sale is not None:
            payload['keepInSale'] = bool(keep_in_sale)
        data = self._graphql('increaseItemPriorityStatus', {'input': payload, 'showForbiddenImage': True})
        return item(data['increaseItemPriorityStatus'])

    def load_providers(self, direction: TxDirection = TxDirection.IN) -> list[types.TransactionProvider]:
        data = self._graphql('transactionProviders', {'filter': {'direction': direction.name if direction else None}})
        return [transaction_provider(provider) for provider in data['transactionProviders'] or []]

    def load_txs(self, count: int = 24, operation: TxKind | None = None, min_value: int | None = None, max_value: int | None = None, provider_id: PayGateway | None = None, status: TxStage | None = None, after_cursor: str | None = None) -> TransactionList:
        filters: dict = {'userId': self.id}
        if operation:
            filters['operation'] = [operation.name]
        if min_value is not None or max_value is not None:
            filters['value'] = {}
            if min_value is not None:
                filters['value']['min'] = str(min_value)
            if max_value is not None:
                filters['value']['max'] = str(max_value)
        if provider_id:
            filters['providerId'] = [provider_id.name]
        if status:
            filters['status'] = [status.name]
        variables = {'pagination': {'first': count, 'after': after_cursor}, 'filter': filters, 'hasSupportAccess': False}
        return transaction_list(self._graphql('transactions', variables)['transactions'])

    def cancel_tx(self, transaction_id: str) -> types.Transaction:
        return transaction(self._graphql('removeTransaction', {'id': transaction_id})['removeTransaction'])
