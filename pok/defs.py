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
    BLOCKED = 6
    CREATED = 7
    DATA_CHANGE_APPROVED = 8
    DATA_CHANGE_DECLINED = 9
    DEAL_FAILED = 10
    DISCONTINUED = 11
    EXPIRATION_NOTIFICATION = 12
    EXPIRED = 13
    ITEM_EDITED = 14
    ITEM_PUBLISHED = 15
    ITEM_REPUBLISHED = 16
    PENDING_MODERATION = 17
    POSTMODERATION_CHECKED = 18
    PUBLISHING_APPROVED = 19
    PUBLISHING_DECLINED = 20
    REMOVED = 21

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
    FRAGMENT_DEPOSIT = 10
    ITEM_CUSTOM_PRIORITY = 11
    ITEM_OFFICIAL_BUY = 12
    ITEM_VIP_PRIORITY = 13
    REFUND = 14

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
    BEELINE = 3
    EUR = 4
    MEGAFON = 5
    MTS = 6
    RUB = 7
    TELE2 = 8
    YOTA = 9

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
    CRYPTO = 8
    APPLE_PAY = 9
    BANK_CARD_ALL = 10
    BANK_CARD_KZ = 11
    ENOT = 12
    ERC20 = 13
    GOOGLE_PAY = 14
    MOBILE = 15
    PAYMART = 16
    PAYPAL = 17
    PROMO_CODE = 18
    QIWI = 19
    RURUPAY = 20
    TON = 21
    TRC20 = 22
    UNITPAY = 23
    WEBMONEY = 24
    TESTPAY = 25

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
    FAILED = 6

class DealFlow(Enum):
    IN = 0
    OUT = 1

class GameTypes(Enum):
    GAME = 0
    APPLICATION = 1
    MOBILE_GAME = 2

class AccountRole(Enum):
    USER = 0
    MODERATOR = 1
    BOT = 2
    ACCOUNTANT = 3
    ADMIN = 4
    ADV_DIRECTOR = 5
    ADV_MANAGER = 6
    CHECKER = 7
    DEVELOPER = 8
    GAMES_AND_APPS = 9
    MONITORING = 10
    OFFICIAL_SELLER = 11
    OFFICIAL_SELLER_ADMIN = 12
    POSTMODERATOR = 13
    POSTSECURITY = 14
    SECURITY = 15
    SUPPORT = 16
    SYSTEM_SELLER = 17

class RoomKind(Enum):
    PM = 0
    NOTIFICATIONS = 1
    SUPPORT = 2
    GROUP = 3

class RoomState(Enum):
    NEW = 0
    FINISHED = 1
    ACTIVE = 2
    RESOLVED = 3
    STARTED = 4

class ChatMessageButtonTypes(Enum):
    REDIRECT = 0
    LOTTERY = 1
    ASK_FOR_EXTERNAL_REVIEW = 2
    CURRENT_BALANCE = 3
    LOTTERY_RESULTS = 4

class ListingStage(Enum):
    PENDING_APPROVAL = 0
    PENDING_MODERATION = 1
    APPROVED = 2
    DECLINED = 3
    BLOCKED = 4
    EXPIRED = 5
    SOLD = 6
    DRAFT = 7
    DISCONTINUED = 8
    PENDING_STATUS_PAYMENT = 9
    REMOVED = 10

class ReviewState(Enum):
    APPROVED = 0
    DELETED = 1
    PENDING_APPROVAL = 2
    REJECTED = 3
    REMOVED = 4

class OrderDir(Enum):
    DESC = 0
    ASC = 1

class BoostLevel(Enum):
    DEFAULT = 0
    PREMIUM = 1
    CUSTOM = 2
    VIP = 3

class GameCategoryAgreementIconTypes(Enum):
    RESTRICTION = 0
    CONFIRMATION = 1

class OptionStyle(Enum):
    SELECTOR = 0
    SWITCH = 1
    RADIO = 2
    RANGE = 3

class FieldScope(Enum):
    ITEM_DATA = 0
    OBTAINING_DATA = 1

class GameCategoryDataFieldInputTypes(Enum):
    INPUT = 0
    TEXTAREA = 1

class GameCategoryAutoConfirmPeriods(Enum):
    SEVEN_DAYS = 0
    SEVEN_DEYS = 0
    TWO_DAYS = 1
    FIFTEEN_DAYS = 2
    THIRTY_DAYS = 3

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


class BotCheckDetectedException(Exception):
    def __init__(self, response=None):
        self.response = response
        self.status_code = getattr(response, 'status_code', None) if response is not None else None
        self.html_text = getattr(response, 'text', '') if response is not None else ''

    def __str__(self):
        extra = f'\nКод ответа: {self.status_code}' if self.status_code else ''
        return (
            'DDoS-Guard обнаружил бота: Cookie `__ddg5_` истекла или не подходит '
            'для текущего IP/UA. Обновите `account.cookies` в conf/config.json '
            '(экспортируйте полные Cookie из браузера, где вы авторизованы).' + extra
        )

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
