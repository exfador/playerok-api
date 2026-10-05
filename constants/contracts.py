from pathlib import Path

ORIGIN = "https://playerok.com"
GRAPHQL_URL = f"{ORIGIN}/graphql"
CONTRACT_DIRECTORY = Path(__file__).resolve().parent.parent / "pok" / "contracts"
TEMPLATE_PATTERN = r"`(\s*(?:query|mutation|subscription|fragment)\s[^`]*)`"
INTERPOLATION_PATTERN = r"\$\{[^}]*\}"
DEFINITION_PATTERN = r"^\s*(fragment|query|mutation|subscription)\s+(\w+)"
SCRIPT_PATTERN = r"/_next/static/[\w./\[\]@%-]+?\.js"
CHUNK_PATTERN = r"static/chunks/[\w./\[\]@%-]+?\.js"
LAZY_CHUNK_PATTERN = r"(\d+)===e\?\"(static/chunks/[^\"]+\.js)\""
LAZY_HASH_PATTERN = r"\"static/chunks/\"\+e\+\"\.\"\+\(\{([^}]*)\}\)\[e\]\+\"\.js\""
MAX_DOCUMENT_BYTES = 262144
MAX_BUNDLE_BYTES = 16777216
MAX_CHUNK_COUNT = 600
REQUEST_TIMEOUT = 30
READ_OPERATIONS = (
    "viewer", "viewerBalance", "user", "userChats", "deals", "deal",
    "testimonials", "games", "GamePage", "GamePageCategory",
    "gameCategoryAgreements", "gameCategoryObtainingTypes",
    "gameCategoryInstructions", "gameCategoryDataFields", "chat",
    "chatMessages", "items", "item", "itemPriorityStatuses",
    "transactionProviders", "transactions", "SbpBankMembers",
    "verifiedCards", "messageTemplates",
)
WRITE_OPERATIONS = (
    "updateDeal", "markChatAsRead", "createChatMessage", "createItem",
    "updateItem", "removeItem", "publishItem", "increaseItemPriorityStatus",
    "deleteCard", "requestWithdrawal", "removeTransaction",
    "uploadChatImageIntoTemporaryStore",
)
SUBSCRIPTION_OPERATIONS = (
    "chatUpdated", "chatMarkedAsRead", "userUpdated", "chatMessageCreated",
)
REQUIRED_OPERATIONS = READ_OPERATIONS + WRITE_OPERATIONS + SUBSCRIPTION_OPERATIONS
IDEMPOTENT_OPERATIONS = frozenset({"markChatAsRead"})
