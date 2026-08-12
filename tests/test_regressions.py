from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
    RequestSendingError,
)
from pok.models import GameProfile
from pok.models import UserProfile
from pok.gql import decode_transaction
from pok.client import get_account
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

        previous = getattr(Conn, "instance", None)
        Conn.instance = Account()
        user = object.__new__(UserProfile)
        user.id = "user-id"
        try:
            user.get_reviews(count=1)
        finally:
            if previous is None:
                delattr(Conn, "instance")
            else:
                Conn.instance = previous

        variables = __import__("json").loads(captured["payload"]["variables"])
        self.assertIs(variables["hasSupportAccess"], False)


class ConnectionRegressionTests(unittest.TestCase):
    def test_request_rejects_unknown_http_method(self):
        conn = _conn()
        with self.assertRaises(ValueError):
            Conn.request(conn, "delete", "https://playerok.com/graphql", {})

    def test_client_falls_back_to_standalone_active_connection(self):
        sentinel = object()
        previous = getattr(Conn, "instance", None)
        Conn.instance = sentinel
        try:
            self.assertIs(get_account(), sentinel)
        finally:
            if previous is None:
                delattr(Conn, "instance")
            else:
                Conn.instance = previous

    def test_request_merges_caller_headers(self):
        conn = _conn()

        class Session:
            headers = None

            def get(self, **kwargs):
                self.headers = kwargs["headers"]
                return _Response()

        session = Session()
        conn._Conn__curl_session = session

        Conn.request(
            conn,
            "get",
            "https://playerok.com/graphql",
            {"accept": "application/json", "x-test-header": "present"},
            {"operationName": "test", "variables": "{}"},
        )

        self.assertEqual(session.headers["accept"], "application/json")
        self.assertEqual(session.headers["x-test-header"], "present")

    def test_request_honors_configured_attempt_limit(self):
        conn = _conn(retries=2)

        class Session:
            calls = 0

            def get(self, **kwargs):
                self.calls += 1
                raise TimeoutError("timed out")

        session = Session()
        conn._Conn__curl_session = session
        conn._refresh_clients = lambda: None

        with self.assertRaises(RequestSendingError):
            Conn.request(
                conn,
                "get",
                "https://playerok.com/graphql",
                {},
                {"operationName": "test", "variables": "{}"},
            )

        self.assertEqual(session.calls, 2)

    def test_multipart_request_lets_client_set_boundary(self):
        conn = _conn()

        class Session:
            headers = None

            def post(self, **kwargs):
                self.headers = kwargs["headers"]
                return _Response()

        session = Session()
        conn._Conn__tls_requests = session

        Conn.request(
            conn,
            "post",
            "https://playerok.com/graphql",
            {"Content-Type": "application/json"},
            {"operations": "{}", "map": "{}"},
            {"1": object()},
        )

        self.assertNotIn("content-type", {key.lower() for key in session.headers})

    def test_multipart_retry_rewinds_file_stream(self):
        conn = _conn(retries=2)

        class Session:
            bodies = []

            def post(self, **kwargs):
                self.bodies.append(kwargs["files"]["1"].read())
                if len(self.bodies) == 1:
                    raise TimeoutError("timed out")
                return _Response()

        session = Session()
        conn._Conn__tls_requests = session
        conn._refresh_clients = lambda: None

        with tempfile.TemporaryFile() as attachment:
            attachment.write(b"payload")
            attachment.seek(0)
            Conn.request(
                conn,
                "post",
                "https://playerok.com/graphql",
                {},
                {"operations": "{}", "map": "{}"},
                {"1": attachment},
            )

        self.assertEqual(session.bodies, [b"payload", b"payload"])

    def test_non_transport_errors_are_not_retried(self):
        conn = _conn(retries=5)

        class Session:
            calls = 0

            def get(self, **kwargs):
                self.calls += 1
                raise ValueError("invalid request")

        session = Session()
        conn._Conn__curl_session = session

        with self.assertRaises(RequestSendingError):
            Conn.request(
                conn,
                "get",
                "https://playerok.com/graphql",
                {},
                {"operationName": "test", "variables": "{}"},
            )

        self.assertEqual(session.calls, 1)

    def test_edit_listing_sends_explicit_falsy_values(self):
        conn = _conn()
        captured = {}

        def request(method, url, headers, payload=None, files=None):
            captured.update(payload=payload, files=files)
            return _Response({"data": {"updateItem": None}})

        conn.request = request
        conn.edit_listing(
            "item-id",
            name="",
            price=0,
            description="",
            options=[],
            data_fields=[],
            remove_attachments=[],
        )

        input_data = captured["payload"]["variables"]["input"]
        self.assertEqual(input_data["name"], "")
        self.assertEqual(input_data["price"], 0)
        self.assertEqual(input_data["description"], "")
        self.assertEqual(input_data["attributes"], {})
        self.assertEqual(input_data["dataFields"], [])
        self.assertEqual(input_data["removedAttachments"], [])

    def test_listing_upload_files_are_closed(self):
        conn = _conn()
        opened_files = []

        def request(method, url, headers, payload=None, files=None):
            opened_files.extend((files or {}).values())
            self.assertTrue(all(not fh.closed for fh in opened_files))
            return _Response({"data": {"createItem": None}})

        conn.request = request
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment = Path(temp_dir) / "attachment.bin"
            attachment.write_bytes(b"test")
            conn.new_listing(
                "category-id",
                "obtaining-id",
                "name",
                100,
                "description",
                [],
                [],
                [str(attachment)],
            )

        self.assertTrue(opened_files)
        self.assertTrue(all(fh.closed for fh in opened_files))

    def test_listing_without_attachments_sends_normal_graphql_json(self):
        conn = _conn()
        captured = {}

        def request(method, url, headers, payload=None, files=None):
            captured.update(payload=payload, files=files)
            return _Response({"data": {"createItem": None}})

        conn.request = request
        conn.new_listing(
            "category-id",
            "obtaining-id",
            "name",
            100,
            "description",
            [],
            [],
            [],
        )

        self.assertEqual(captured["payload"]["operationName"], "createItem")
        self.assertIsNone(captured["files"])

    def test_transaction_zero_value_filters_are_preserved(self):
        conn = _conn()
        conn.id = "user-id"
        captured = {}

        def request(method, url, headers, payload=None, files=None):
            captured.update(payload=payload)
            return _Response(
                {
                    "data": {
                        "transactions": {
                            "edges": [],
                            "pageInfo": None,
                            "totalCount": 0,
                        }
                    }
                }
            )

        conn.request = request
        conn.load_txs(min_value=0, max_value=0)

        variables = __import__("json").loads(captured["payload"]["variables"])
        self.assertEqual(variables["filter"]["value"], {"min": "0", "max": "0"})

    def test_chat_search_stops_on_repeated_cursor(self):
        conn = _conn()
        calls = []
        page = type(
            "ChatPage",
            (),
            {
                "chats": [],
                "page_info": type(
                    "PageInfo", (), {"has_next_page": True, "end_cursor": "same"}
                )(),
            },
        )()
        conn.load_chats = lambda **kwargs: calls.append(kwargs) or page
        self.assertIsNone(conn.find_chat_by_name("nobody"))
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
