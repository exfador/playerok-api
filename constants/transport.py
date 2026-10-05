from constants.contracts import ORIGIN

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
DEFAULT_IMPERSONATION = "chrome"
DEFAULT_TIMEOUT = 20
MAX_READ_ATTEMPTS = 3
MAX_RETRY_DELAY = 5
MAX_RESPONSE_BYTES = 8388608
MAX_ATTACHMENT_BYTES = 15728640
MUTATION_LOCK_SLOTS = 64
MAX_CLONE_ATTACHMENTS = 10
MAX_COOKIE_EXPORT_BYTES = 65536
MAX_COOKIE_COUNT = 100
MAX_MESSAGE_COUNT = 1000
MESSAGE_PAGE_SIZE = 10
MAX_PAGES = 200
COOKIE_NAME_PATTERN = r"^[!#$%&'*+.^_`|~0-9a-zA-Z-]+$"
COOKIE_DOMAIN = "playerok.com"
COOKIE_PATH = "/"
VIEWER_FIELDS = {
    "id": "id", "username": "username", "email": "email", "role": "role",
    "support_chat_id": "supportChatId", "system_chat_id": "systemChatId",
    "unread_chats_counter": "unreadChatsCounter", "is_blocked": "isBlocked",
    "is_blocked_for": "isBlockedFor", "created_at": "createdAt",
    "last_item_created_at": "lastItemCreatedAt", "has_frozen_balance": "hasFrozenBalance",
    "has_confirmed_phone_number": "hasConfirmedPhoneNumber", "can_publish_items": "canPublishItems",
}
PERSISTED_QUERY_MISSING = "PERSISTED_QUERY_NOT_FOUND"
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "ru,en;q=0.9",
    "apollographql-client-name": "web",
    "apollo-require-preflight": "true",
    "origin": ORIGIN,
    "x-timezone-offset": "-180",
}
OPERATION_PATHS = {
    "userChats": "/chats",
    "chat": "/chats/[id]",
    "chatMessages": "/chats/[id]",
    "markChatAsRead": "/chats/[id]",
    "createChatMessage": "/chats/[id]",
    "uploadChatImageIntoTemporaryStore": "/chats/[id]",
    "items": "/profile/[username]/products",
    "item": "/products/[slug]",
    "itemPriorityStatuses": "/products/[slug]",
    "publishItem": "/products/[slug]",
    "increaseItemPriorityStatus": "/products/[slug]",
    "updateItem": "/products/[slug]/edit",
    "createItem": "/sell",
    "deal": "/deal/[id]",
    "updateDeal": "/deal/[id]",
    "verifiedCards": "/profile/balance",
    "SbpBankMembers": "/profile/balance",
    "requestWithdrawal": "/profile/balance",
}
