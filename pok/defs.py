from enum import Enum
import requests

class MarketEvent(Enum):
    CHAT_INITIALIZED = 0
    NEW_MESSAGE = 1
    NEW_DEAL = 2
    NEW_REVIEW = 3
    DEAL_CONFIRMED = 4
    DEAL_CONFIRMED_AUTOMATICALLY = 5
    DEAL_ROLLED_BACK = 6
    DEAL_HAS_PROBLEM = 7
    DEAL_PROBLEM_RESOLVED = 8
    DEAL_STATUS_CHANGED = 9
    ITEM_PAID = 10
    ITEM_SENT = 11
    REVIEW_REMOVED = 12
    REVIEW_UPDATED = 13

class ItemLogEvents(Enum):
    PAID = 0
    SENT = 1
    DEAL_CONFIRMED = 2
    DEAL_ROLLED_BACK = 3
    PROBLEM_REPORTED = 4
    PROBLEM_RESOLVED = 5

class TxKind(Enum):
    DEPOSIT = 0
    BUY = 1
    SELL = 2
    ITEM_DEFAULT_PRIORITY = 3
    ITEM_PREMIUM_PRIORITY = 4
    WITHDRAW = 5
    MANUAL_BALANCE_INCREASE = 6
    MANUAL_BALANCE_DECREASE = 7
    REFERRAL_BONUS = 8
    STEAM_DEPOSIT = 9

class TransactionDirections(Enum):
    IN = 0
    OUT = 1

class TxStage(Enum):
    PENDING = 0
    PROCESSING = 1
    CONFIRMED = 2
    ROLLED_BACK = 3
    FAILED = 4

class PayMethod(Enum):
    MIR = 0
    VISA_MASTERCARD = 1
    ERIP = 2

class TxDirection(Enum):
    IN = 0
    OUT = 1

class PayGateway(Enum):
    LOCAL = 0
    SBP = 1
    BANK_CARD_RU = 2
    BANK_CARD_BY = 3
    BANK_CARD = 4
    YMONEY = 5
    USDT = 6
    PENDING_INCOME = 7

class BankCardTypes(Enum):
    MIR = 0
    VISA = 1
    MASTERCARD = 2

class DealStage(Enum):
    PAID = 0
    PENDING = 1
    SENT = 2
    CONFIRMED = 3
    CONFIRMED_AUTOMATICALLY = 4
    ROLLED_BACK = 5

class DealFlow(Enum):
    IN = 0
    OUT = 1

class GameTypes(Enum):
    GAME = 0
    APPLICATION = 1

class AccountRole(Enum):
    USER = 0
    MODERATOR = 1
    BOT = 2

class RoomKind(Enum):
    PM = 0
    NOTIFICATIONS = 1
    SUPPORT = 2

class RoomState(Enum):
    NEW = 0
    FINISHED = 1

class ChatMessageButtonTypes(Enum):
    REDIRECT = 0
    LOTTERY = 1

class ListingStage(Enum):
    PENDING_APPROVAL = 0
    PENDING_MODERATION = 1
    APPROVED = 2
    DECLINED = 3
    BLOCKED = 4
    EXPIRED = 5
    SOLD = 6
    DRAFT = 7

class ReviewState(Enum):
    APPROVED = 0
    DELETED = 1

class OrderDir(Enum):
    DESC = 0
    ASC = 1

class BoostLevel(Enum):
    DEFAULT = 0
    PREMIUM = 1

class GameCategoryAgreementIconTypes(Enum):
    RESTRICTION = 0
    CONFIRMATION = 0

class OptionStyle(Enum):
    SELECTOR = 0
    SWITCH = 1

class FieldScope(Enum):
    ITEM_DATA = 0
    OBTAINING_DATA = 1

class GameCategoryDataFieldInputTypes(Enum):
    INPUT = 0

class GameCategoryAutoConfirmPeriods(Enum):
    SEVEN_DEYS = 0

class InstructionFor(Enum):
    FOR_SELLER = 0
    FOR_BUYER = 1

class CloudflareDetectedException(Exception):

    def __init__(self, response: requests.Response):
        self.response = response
        self.status_code = self.response.status_code
        self.html_text = self.response.text

    def __str__(self):
        msg = f'Ошибка: CloudFlare заметил подозрительную активность при отправке запроса на сайт Playerok.\nКод ошибки: {self.status_code}\nОтвет: {self.html_text}'
        return msg

class RequestFailedError(Exception):

    def __init__(self, response: requests.Response):
        self.response = response
        self.status_code = self.response.status_code
        self.html_text = self.response.text

    def __str__(self):
        msg = f'Ошибка запроса к {self.response.url}\nКод ошибки: {self.status_code}\nОтвет: {self.html_text}'
        return msg

class RequestApiError(Exception):

    def __init__(self, response: requests.Response):
        self.response = response
        self.json = response.json()
        errs = self.json.get('errors') or []
        first = errs[0] if errs else {}
        self.error_message = first.get('message') or str(first) or 'Неизвестная ошибка API'
        ext = first.get('extensions') or {}
        self.error_code = ext.get('code', 'UNKNOWN')

    def __str__(self):
        msg = f'Ошибка запроса к {self.response.url}\nКод ошибки: {self.error_code}\nСообщение: {self.error_message}'
        return self.error_message or msg

class RequestSendingError(Exception):

    def __init__(self, url: str, error: str):
        self.url = url
        self.error = error

    def __str__(self):
        msg = f'Ошибка при попытке отправить запрос к {self.url}\nТекст ошибки: {self.error}'
        return msg

class UnauthorizedError(Exception):

    def __str__(self):
        return 'Не удалось подключиться к аккаунту Playerok. Может вы указали неверный token?'

class HoneypotDetectedException(Exception):

    def __init__(self, returned_id: str, token_sub: str):
        self.returned_id = returned_id
        self.token_sub = token_sub

    def __str__(self):
        return (
            f'Обнаружен ханипот: сервер вернул чужой аккаунт (id={self.returned_id}), '
            f'не совпадающий с токеном (sub={self.token_sub}). '
            'Проверьте токен или прокси.'
        )
