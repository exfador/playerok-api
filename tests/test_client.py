import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pok.conn import Conn
from pok.gql import game_profile, item_deal, item_profile, my_item, user_profile
from pok.transport import MutationOutcomeUnknown, ResponseContractError


@pytest.fixture
def client():
    with Conn(token="fixture") as connection:
        yield connection


def test_independent_clients_do_not_overwrite_credentials():
    with Conn(token="first") as first, Conn(token="second") as second:
        assert first is not second
        assert first._cookie_header() == "token=first"
        assert second._cookie_header() == "token=second"


def test_conflicting_credentials_fail_closed():
    with pytest.raises(ValueError, match="не совпадает"):
        Conn(token="first", cookies={"token": "second"})


def test_repeated_message_cursor_cannot_loop_forever(client):
    body = {"data": {"chatMessages": {"edges": [{"node": {"id": "message"}}],
            "pageInfo": {"endCursor": "same", "hasNextPage": True}, "totalCount": 9}}}
    client._chat_messages_one_page = Mock(return_value=body)
    with pytest.raises(ResponseContractError, match="Курсор"):
        client.load_messages("chat", count=9)
    assert client._chat_messages_one_page.call_count == 2


def test_overlapping_message_pages_are_deduplicated(client):
    first = {"data": {"chatMessages": {"edges": [{"node": {"id": "first"}}],
             "pageInfo": {"endCursor": "cursor", "hasNextPage": True}, "totalCount": 2}}}
    second = {"data": {"chatMessages": {"edges": [{"node": {"id": "first"}}, {"node": {"id": "second"}}],
              "pageInfo": {"hasNextPage": False}, "totalCount": 2}}}
    client._chat_messages_one_page = Mock(side_effect=[first, second])
    assert [message.id for message in client.load_messages("chat", count=2).messages] == ["first", "second"]


def test_missing_listing_is_not_a_key_error(client):
    client.request = Mock(return_value=SimpleNamespace(json=lambda: {"data": {"item": None}}))
    assert client.load_listing(id="missing") is None


def test_category_is_resolved_within_the_requested_game(client):
    client.load_game = Mock(return_value=SimpleNamespace(categories=[SimpleNamespace(id="category", slug="subscription")]))
    client.request = Mock(return_value=SimpleNamespace(json=lambda: {"data": {"gameCategory": {"id": "category"}}}))
    assert client.load_category(game_id="game", slug="subscription").id == "category"
    variables = client.request.call_args.args[3]["variables"]
    assert (json.loads(variables) if isinstance(variables, str) else variables) == {"id": "category"}


def test_editing_can_clear_optional_fields(client):
    client._upload_listing = Mock()
    client.edit_listing("item", description="", options=[], data_fields=[])
    fields = client._upload_listing.call_args.args[1]["input"]
    assert fields == {"id": "item", "description": "", "attributes": {}, "dataFields": []}


def test_listing_files_close_when_upload_fails(client, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"fixture")
    opened = []
    def fail_request(method, url, headers, payload, files):
        opened.extend(files.values())
        raise MutationOutcomeUnknown("createItem")
    client.request = fail_request
    with pytest.raises(MutationOutcomeUnknown):
        client.new_listing("category", "obtaining", "fixture", 1, "description", [], [], [str(image)])
    assert opened and all(file.closed for file in opened)


def test_review_query_includes_required_access_flag(client):
    user = user_profile({"id": "user"})
    user.account = client
    client.request = Mock(return_value=SimpleNamespace(json=lambda: {"data": {"testimonials": {"edges": []}}}))
    user.get_reviews()
    assert json.loads(client.request.call_args.args[3]["variables"])["hasSupportAccess"] is False


def test_new_listing_and_deal_response_fields_are_available():
    listing = my_item({"id": "item", "status": "DISCONTINUED", "keepInSale": True,
                       "republishAvailable": False, "isAutomated": True})
    assert listing.keep_in_sale and listing.is_automated
    assert listing.republish_available is False
    assert listing.status.name == "DISCONTINUED"
    deal = item_deal({"id": "deal", "status": "FAILED", "prevStatus": "PAID", "isAutomated": True})
    assert deal.status.name == "FAILED" and deal.previous_status.name == "PAID"
    assert deal.is_automated


def test_vip_priority_does_not_decode_as_none():
    listing = item_profile({"id": "item", "priority": "VIP"})
    assert listing.priority.name == "VIP"


def test_game_profile_uses_type_instead_of_identity():
    profile = game_profile({"id": "game", "type": "MOBILE_GAME"})
    assert profile.type.name == "MOBILE_GAME"
