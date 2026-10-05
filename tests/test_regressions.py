from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pok.conn import Conn
from pok.defs import (
    GameCategoryAgreementIconTypes,
    GameCategoryAutoConfirmPeriods,
    GameCategoryDataFieldInputTypes,
    GameTypes,
    ListingStage,
    OptionStyle,
    PayGateway,
    PayMethod,
    RoomKind,
    TxKind,
    RequestApiError,
    RequestSendingError,
)
from pok.models import GameProfile
from pok.models import UserProfile
from pok.gql import decode_transaction
from pok.client import get_account
from pok.transport import ResponseContractError
from lib.cfg import FILES


class _Response:
    def __init__(self, data=None):
        self.status_code = 200
        self.text = "{}"
        self.headers = {}
        self.url = "https://playerok.com/graphql"
        self._data = {} if data is None else data

    def json(self):
        return self._data


def _conn(*, retries: int = 2) -> Conn:
    conn = object.__new__(Conn)
    Conn.__init__(
        conn,
        cookies={"token": "test-token"},
        request_max_retries=retries,
    )
    return conn


class ModelsRegressionTests(unittest.TestCase):
    def test_game_profile_keeps_api_type(self):
        profile = GameProfile(
            id="game-id",
            slug="game",
            name="Game",
            type=GameTypes.GAME,
            logo=None,
        )

        self.assertIs(profile.type, GameTypes.GAME)

    def test_current_enum_names_are_not_aliases_or_missing(self):
        self.assertIsNot(
            GameCategoryAgreementIconTypes.CONFIRMATION,
            GameCategoryAgreementIconTypes.RESTRICTION,
        )
        self.assertTrue(
            {"TWO_DAYS", "SEVEN_DAYS", "FIFTEEN_DAYS", "THIRTY_DAYS"}
            <= GameCategoryAutoConfirmPeriods.__members__.keys()
        )
        self.assertIs(
            GameCategoryAutoConfirmPeriods.SEVEN_DEYS,
            GameCategoryAutoConfirmPeriods.SEVEN_DAYS,
        )
        self.assertEqual(GameCategoryAutoConfirmPeriods.SEVEN_DEYS.value, 0)
        self.assertIn("TEXTAREA", GameCategoryDataFieldInputTypes.__members__)
        self.assertTrue({"RADIO", "RANGE"} <= OptionStyle.__members__.keys())
        self.assertIn("MOBILE_GAME", GameTypes.__members__)
        self.assertIn("GROUP", RoomKind.__members__)
        self.assertTrue(
            {"CRYPTO", "BANK_CARD_KZ", "TON", "TRC20", "ERC20"}
            <= PayGateway.__members__.keys()
        )
        self.assertTrue(
            {"FRAGMENT_DEPOSIT", "ITEM_CUSTOM_PRIORITY", "ITEM_VIP_PRIORITY", "REFUND"}
            <= TxKind.__members__.keys()
        )
        self.assertTrue(
            {"DISCONTINUED", "PENDING_STATUS_PAYMENT", "REMOVED"}
            <= ListingStage.__members__.keys()
        )

    def test_config_paths_do_not_depend_on_working_directory(self):
        project_root = Path(__file__).resolve().parents[1]
        for config_file in FILES:
            path = Path(config_file.path)
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.is_relative_to(project_root))

    def test_transaction_decoder_uses_graphql_camel_case_fields(self):
        tx = decode_transaction(
            {
                "id": "tx-id",
                "operation": "DEPOSIT",
                "direction": "IN",
                "providerId": "CRYPTO",
                "status": "CONFIRMED",
                "createdAt": "created",
                "verifiedAt": "verified",
                "completedAt": "completed",
                "paymentMethodId": "MIR",
                "isSuspicious": True,
                "spbBankName": "bank",
                "autoClaimedAt": "claimed",
                "props": {"paymentGateway": "CRYPTO"},
            }
        )

        self.assertEqual(tx.verified_at, "verified")
        self.assertEqual(tx.completed_at, "completed")
        self.assertIs(tx.payment_method_id, PayMethod.MIR)
        self.assertTrue(tx.is_suspicious)
        self.assertEqual(tx.sbp_bank_name, "bank")
        self.assertEqual(tx.auto_claimed_at, "claimed")
        self.assertEqual(tx.props, {"paymentGateway": "CRYPTO"})

    def test_reviews_query_supplies_required_support_flag(self):
        captured = {}

        class Account:
            base_url = "https://playerok.com"

            def request(self, method, url, headers, payload=None, files=None):
                captured.update(payload=payload)
                return _Response(
                    {
                        "data": {
                            "testimonials": {
                                "edges": [],
                                "pageInfo": None,
                                "totalCount": 0,
                            }
                        }
                    }
                )

        user = object.__new__(UserProfile)
        user.id = "user-id"
        user.account = Account()
        user.get_reviews(count=1)

        variables = __import__("json").loads(captured["payload"]["variables"])
        self.assertIs(variables["hasSupportAccess"], False)


class ConnectionRegressionTests(unittest.TestCase):
    def test_request_rejects_unknown_http_method(self):
        conn = _conn()
        with self.assertRaises(ValueError):
            Conn.request(conn, "delete", "https://playerok.com/graphql", {})

    def test_client_uses_running_engine_account(self):
        sentinel = object()
        with patch("bot.core.active_engine", return_value=SimpleNamespace(account=sentinel)):
            self.assertIs(get_account(), sentinel)
        with patch("bot.core.active_engine", return_value=None):
            with self.assertRaises(RuntimeError):
                get_account()

    def test_edit_listing_sends_explicit_falsy_values(self):
        conn = _conn()
        captured = {}

        def request(method, url, headers, payload=None, files=None):
            captured.update(payload=payload, files=files)
            return _Response({"data": {"updateItem": {"id": "item-id", "__typename": "MyItem"}}})

        conn.request = request
        conn.edit_listing("item-id", name="", price=0, description="", options=[], data_fields=[],
                          remove_attachments=[], keep_in_sale=False)
        input_data = captured["payload"]["variables"]["input"]
        self.assertEqual(input_data["name"], "")
        self.assertEqual(input_data["price"], 0)
        self.assertEqual(input_data["description"], "")
        self.assertEqual(input_data["attributes"], {})
        self.assertEqual(input_data["dataFields"], [])
        self.assertEqual(input_data["removedAttachments"], [])
        self.assertIs(input_data["keepInSale"], False)

    def test_listing_upload_files_are_closed(self):
        conn = _conn()
        opened_files = []

        def request(method, url, headers, payload=None, files=None):
            opened_files.extend((files or {}).values())
            self.assertTrue(all(not fh.closed for fh in opened_files))
            return _Response({"data": {"createItem": {"id": "new", "__typename": "MyItem"}}})

        conn.request = request
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment = Path(temp_dir) / "attachment.bin"
            attachment.write_bytes(b"test")
            conn.new_listing("category-id", "obtaining-id", "name", 100, "description", [], [], [str(attachment)])
        self.assertTrue(opened_files)
        self.assertTrue(all(fh.closed for fh in opened_files))

    def _clone_source(self):
        return SimpleNamespace(
            name="Telegram Premium", price=276, raw_price=310, description="desc", comment=None,
            category=SimpleNamespace(id="cat"), obtaining_type=SimpleNamespace(id="obt"),
            attachments=[SimpleNamespace(id="file-1", url="https://i.playerok.com/a.png"),
                         SimpleNamespace(id="file-2", url="https://i.playerok.com/b.png")],
            data_fields=[SimpleNamespace(id="field", value="v")], attributes={"a": 1},
        )

    def _capture_clone(self, conn):
        captured = {}

        def download(url, folder):
            path = Path(folder) / url.rsplit("/", 1)[-1]
            path.write_bytes(b"png")
            return str(path)

        def request(method, url, headers, payload=None, files=None):
            captured.update(operations=__import__("json").loads(payload["operations"]),
                            mapping=__import__("json").loads(payload["map"]),
                            names=[Path(fh.name).name for fh in files.values()])
            return _Response({"data": {"createItem": {"id": "copy", "__typename": "MyItem", "status": "DRAFT"}}})

        conn.download_attachment = download
        conn.request = request
        return captured

    def test_listing_clone_uploads_source_images_again(self):
        conn = _conn()
        captured = self._capture_clone(conn)
        created = conn.clone_listing(self._clone_source())
        fields = captured["operations"]["variables"]["input"]
        self.assertNotIn("attachmentIds", fields)
        self.assertEqual(captured["names"], ["a.png", "b.png"])
        self.assertEqual(captured["mapping"], {"1": ["variables.attachments.0"], "2": ["variables.attachments.1"]})
        self.assertEqual(fields["price"], 310)
        self.assertEqual(fields["obtainingTypeId"], "obt")
        self.assertEqual(fields["dataFields"], [{"fieldId": "field", "value": "v"}])
        self.assertEqual(created.id, "copy")

    def test_listing_clone_to_other_obtaining_type_drops_foreign_fields(self):
        conn = _conn()
        captured = self._capture_clone(conn)
        conn.clone_listing(self._clone_source(), obtaining_type_id="gift")
        fields = captured["operations"]["variables"]["input"]
        self.assertEqual(fields["obtainingTypeId"], "gift")
        self.assertNotIn("dataFields", fields)

    def test_listing_clone_requires_images(self):
        conn = _conn()
        source = self._clone_source()
        source.attachments = []
        with self.assertRaises(ValueError):
            conn.clone_listing(source)

    def test_attachment_download_only_from_playerok(self):
        conn = _conn()
        for url in ("http://i.playerok.com/a.png", "https://evil.example/a.png", "https://playerok.com.evil.io/a"):
            with self.assertRaises(ValueError):
                conn.download_attachment(url, ".")

    def test_attachment_download_saves_image(self):
        conn = _conn()
        response = SimpleNamespace(status_code=200, content=b"\x89PNG", headers={"content-type": "image/png"})
        conn._session = SimpleNamespace(get=lambda *a, **k: response)
        with tempfile.TemporaryDirectory() as folder:
            path = conn.download_attachment("https://i.playerok.com/x.png", folder)
            self.assertEqual(Path(path).read_bytes(), b"\x89PNG")
            self.assertTrue(path.endswith(".png"))
        response.headers = {"content-type": "text/html"}
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            conn.download_attachment("https://i.playerok.com/x.png", folder)

    def test_anonymous_connection_is_explicit(self):
        with self.assertRaises(ValueError):
            Conn()
        conn = Conn(anonymous=True)
        self.assertEqual(conn.token, "")
        self.assertEqual(conn._cookie_header(), "")
        conn.close()

    def test_missing_listing_returns_none(self):
        conn = _conn()

        def request(method, url, headers, payload=None, files=None):
            raise RequestApiError(SimpleNamespace(json=lambda: {"errors": [{"message": "нет", "extensions": {"code": "NOT_FOUND"}}]}))

        conn.request = request
        self.assertIsNone(conn.load_listing("gone"))

    def test_publish_and_boost_pass_keep_in_sale(self):
        conn = _conn()
        calls = []

        def request(method, url, headers, payload=None, files=None):
            calls.append(payload)
            name = payload["operationName"]
            return _Response({"data": {name: {"id": "i", "__typename": "MyItem"}}})

        conn.request = request
        conn.activate_listing("i", "tier", keep_in_sale=True)
        conn.apply_boost("i", "tier", keep_in_sale=False)
        conn.activate_listing("i", "tier")
        self.assertIs(calls[0]["variables"]["input"]["keepInSale"], True)
        self.assertIs(calls[1]["variables"]["input"]["keepInSale"], False)
        self.assertNotIn("keepInSale", calls[2]["variables"]["input"])

    def test_transaction_zero_value_filters_are_preserved(self):
        conn = _conn()
        conn.id = "user-id"
        captured = {}

        def request(method, url, headers, payload=None, files=None):
            captured.update(payload=payload)
            return _Response({"data": {"transactions": {"edges": [], "pageInfo": None, "totalCount": 0}}})

        conn.request = request
        conn.load_txs(min_value=0, max_value=0)
        self.assertEqual(captured["payload"]["variables"]["filter"]["value"], {"min": "0", "max": "0"})

    def test_chat_search_stops_on_repeated_cursor(self):
        conn = _conn()
        calls = []
        page = SimpleNamespace(chats=[], page_info=SimpleNamespace(has_next_page=True, end_cursor="same"))
        conn.load_chats = lambda **kwargs: calls.append(kwargs) or page
        with self.assertRaises(ResponseContractError):
            conn.find_chat_by_name("nobody")
        self.assertEqual(len(calls), 2)

    def test_send_message_survives_mark_as_read_failure(self):
        conn = _conn()
        sent = []

        def request(method, url, headers, payload=None, files=None):
            if payload["operationName"] == "markChatAsRead":
                raise RequestSendingError(url, "boom")
            sent.append(payload)
            return _Response({"data": {"createChatMessage": {"id": "m", "text": "hi"}}})

        conn.request = request
        message = conn.send_message("chat", text="hi", read_chat=True)
        self.assertEqual(message.id, "m")
        self.assertEqual(sent[0]["variables"]["input"], {"chatId": "chat", "imagesIds": [], "text": "hi"})

    def test_invalid_cookie_values_are_dropped_instead_of_failing(self):
        conn = Conn(cookies='token=abc; broken=va"lue; __ddg5_=x')
        self.assertEqual(conn.cookies, {"token": "abc", "__ddg5_": "x"})


if __name__ == "__main__":
    unittest.main()
