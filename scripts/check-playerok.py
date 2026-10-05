import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constants.contracts import READ_OPERATIONS
from pok.conn import Conn
from pok.cookies import load_cookie_file
from pok.defs import (
    HoneypotDetectedException,
    RequestApiError,
    RequestFailedError,
    RequestSendingError,
    UnauthorizedError,
)


class Audit:
    def __init__(self, client):
        self.client = client
        self.results = []

    def run(self, name, operation, allow_restricted=False):
        try:
            result = operation()
            if result is None:
                raise ValueError("Missing result")
            self.results.append({"check": name, "status": "passed"})
            print(json.dumps(self.results[-1]), flush=True)
            return result
        except (ValueError, TypeError, KeyError, AttributeError, RequestApiError,
                RequestFailedError, RequestSendingError, UnauthorizedError,
                HoneypotDetectedException) as error:
            denied = isinstance(error, RequestApiError) and error.error_message == 'У вас нет доступа на выполнение данной операции'
            status = 'restricted' if allow_restricted and denied else 'failed'
            self.results.append({"check": name, "status": status,
                                 "error": type(error).__name__,
                                 "code": getattr(error, "error_code", None)})
            print(json.dumps(self.results[-1]), flush=True)
            return None

    def query(self, name, variables):
        if name not in READ_OPERATIONS:
            raise ValueError("Live audit permits read operations only")
        payload = {"operationName": name, "variables": variables}
        return self.client.request("get", f"{self.client.base_url}/graphql", {}, payload).json()["data"]


def check_account(audit):
    client = audit.client
    if not audit.run("authenticate-and-profile", client.get):
        return
    audit.run("viewerBalance", lambda: audit.query("viewerBalance", {}))
    user = audit.run("user", lambda: client.load_user(id=client.id))
    if user:
        audit.run("testimonials", lambda: user.get_reviews(count=1))
        own = audit.run("own-items", lambda: user.load_listings(count=1))
        if own and own.items:
            audit.run("own-item", lambda: client.load_listing(id=own.items[0].id))
    deals = audit.run("deals", lambda: client.load_deals(count=1))
    if deals and deals.deals:
        audit.run("deal", lambda: client.load_deal(deals.deals[0].id))
    audit.run("transactions", lambda: client.load_txs(count=1))
    audit.run("transactionProviders", client.load_providers)
    audit.run("verifiedCards", lambda: audit.query("verifiedCards", {"pagination": {"first": 1}}))
    audit.run("SbpBankMembers", lambda: audit.query("SbpBankMembers", {}))
    audit.run("messageTemplates", lambda: audit.query("messageTemplates", {
        "pagination": {"first": 1}, "filter": {"type": "SUPPORT"},
    }), allow_restricted=True)


def check_chats(audit):
    client = audit.client
    chats = audit.run("userChats", lambda: client.load_chats(count=2))
    if not chats or not chats.chats:
        return
    first = chats.chats[0]
    audit.run("chat", lambda: client.load_chat(first.id))
    audit.run("chatMessages", lambda: client.load_messages(first.id, count=2))
    page = chats.page_info
    if page and page.has_next_page:
        audit.run("chat-pagination", lambda: client.load_chats(count=1, after_cursor=page.end_cursor))


def check_catalog(audit):
    client = audit.client
    audit.run("games", lambda: client.load_games(count=2))
    game = audit.run("GamePage", lambda: client.load_game(slug="cgpt"))
    if not game or not game.categories:
        return
    category = next((entry for entry in game.categories if entry.slug == "subscription"), game.categories[0])
    audit.run("GamePageCategory", lambda: client.load_category(id=category.id))
    audit.run("category-by-game-and-slug", lambda: client.load_category(game_id=game.id, slug=category.slug))
    if client.id:
        audit.run("gameCategoryAgreements", lambda: client.load_agreements(category.id, count=1))
    obtaining = audit.run("gameCategoryObtainingTypes", lambda: client.load_obtain_types(category.id, count=1))
    if obtaining and obtaining.obtaining_types:
        obtaining_id = obtaining.obtaining_types[0].id
        audit.run("gameCategoryInstructions", lambda: client.load_instructions(category.id, obtaining_id, count=1))
        audit.run("gameCategoryDataFields", lambda: client.load_data_fields(category.id, obtaining_id, count=1))
    listings = audit.run("items", lambda: client.load_listings(category_id=category.id, count=1))
    if listings and listings.items:
        item = audit.run("item", lambda: client.load_listing(id=listings.items[0].id))
        if item:
            audit.run("itemPriorityStatuses", lambda: client.load_boost_tiers(item.id, item.price))


def main():
    parser = argparse.ArgumentParser(description="Проверка чтения API Playerok без изменений на аккаунте")
    parser.add_argument("--cookies", type=Path, help="экспорт Cookie; без него проверяется только публичный каталог")
    parser.add_argument("--user-agent", default="", help="User-Agent браузера, из которого экспортированы Cookie")
    parser.add_argument("--proxy", default=None, help="прокси в формате conf/config.json")
    args = parser.parse_args()
    cookies = load_cookie_file(args.cookies) if args.cookies else None
    with Conn(cookies=cookies, user_agent=args.user_agent, proxy=args.proxy, anonymous=cookies is None,
              requests_timeout=20, request_max_retries=1) as client:
        audit = Audit(client)
        if cookies is None:
            check_catalog(audit)
        else:
            check_account(audit)
            if client.id:
                check_chats(audit)
                check_catalog(audit)
    passed = sum(result["status"] == "passed" for result in audit.results)
    failed = sum(result["status"] == "failed" for result in audit.results)
    restricted = sum(result["status"] == "restricted" for result in audit.results)
    print(json.dumps({"passed": passed, "failed": failed, "restricted": restricted}))
    raise SystemExit(bool(failed))


if __name__ == "__main__":
    main()
