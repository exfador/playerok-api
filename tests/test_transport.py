import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from curl_cffi.requests.exceptions import Timeout

from constants.contracts import GRAPHQL_URL
from constants.transport import DEFAULT_USER_AGENT
from pok.contract import PERSISTED_QUERIES, QUERIES
from pok.defs import RequestApiError, RequestFailedError, RequestSendingError
from pok.transport import (
    GraphQLTransport,
    MutationOutcomeUnknown,
    ResponseContractError,
)


def response(body, status=200, headers=None):
    encoded = json.dumps(body)
    return SimpleNamespace(status_code=status, headers=headers or {}, text=encoded,
                           content=encoded.encode(), json=lambda: body, url=GRAPHQL_URL)


@pytest.fixture
def transport():
    owner = SimpleNamespace(request_max_retries=2, user_agent=DEFAULT_USER_AGENT,
                            _timeout=10, logger=Mock(), _cookie_header=lambda: "token=secret",
                            _ingest_set_cookie=Mock())
    return GraphQLTransport(Mock(), owner, sleep=Mock())


def test_persisted_miss_retries_once_with_current_document(transport):
    transport.session.get.return_value = response({"errors": [{"extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"}}]})
    transport.session.post.return_value = response({"data": {"viewer": {"id": "viewer"}}})
    result = transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer", "variables": {}})
    assert result.json()["data"]["viewer"]["id"] == "viewer"
    assert transport.session.post.call_args.kwargs["json"]["query"] == QUERIES["viewer"]
    assert transport.session.get.call_count == transport.session.post.call_count == 1


def test_network_error_never_retries_a_mutation(transport):
    transport.session.post.side_effect = Timeout("sensitive request details")
    payload = {"operationName": "publishItem", "query": QUERIES["publishItem"], "variables": {"input": {}}}
    with pytest.raises(MutationOutcomeUnknown) as error:
        transport.send("post", GRAPHQL_URL, {}, payload)
    assert transport.session.post.call_count == 1
    assert "sensitive" not in str(error.value)
    transport.sleep.assert_not_called()


def test_ambiguous_publication_cannot_fall_back_to_paid_tier(transport):
    transport.session.post.side_effect = Timeout("network")
    for tier in ([], ["premium"]):
        payload = {"operationName": "publishItem", "variables": {
            "input": {"itemId": "fixture", "priorityStatuses": tier},
        }}
        with pytest.raises(MutationOutcomeUnknown):
            transport.send("post", GRAPHQL_URL, {}, payload)
    assert transport.session.post.call_count == 1


def test_successful_mutation_does_not_block_following_edits(transport):
    transport.session.post.return_value = response({"data": {"updateItem": {"id": "fixture"}}})
    payload = {"operationName": "updateItem", "variables": {"input": {"id": "fixture"}}}
    transport.send("post", GRAPHQL_URL, {}, payload)
    transport.send("post", GRAPHQL_URL, {}, payload)
    assert transport.session.post.call_count == 2


def test_graphql_internal_error_marks_write_outcome_unknown(transport):
    transport.session.post.return_value = response({"errors": [{"extensions": {"code": "INTERNAL_SERVER_ERROR"}}]})
    payload = {"operationName": "publishItem", "variables": {"input": {"itemId": "fixture"}}}
    with pytest.raises(MutationOutcomeUnknown):
        transport.send("post", GRAPHQL_URL, {}, payload)
    with pytest.raises(MutationOutcomeUnknown):
        transport.send("post", GRAPHQL_URL, {}, payload)
    assert transport.session.post.call_count == 1


def test_network_error_retries_a_read_even_over_post(transport):
    transport.session.get.side_effect = [Timeout("network"), response({"data": {"viewer": None}})]
    result = transport.send("post", GRAPHQL_URL, {}, {"operationName": "viewer", "variables": {}})
    assert result.json()["data"]["viewer"] is None
    assert transport.session.get.call_count == 2
    transport.session.post.assert_not_called()


def test_persisted_miss_registers_document_with_hash(transport):
    transport.session.get.return_value = response({"errors": [{"extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"}}]})
    transport.session.post.return_value = response({"data": {"viewer": {"id": "viewer"}}})
    transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer", "variables": {}})
    sent = transport.session.post.call_args.kwargs["json"]
    assert sent["query"] == QUERIES["viewer"]
    assert sent["extensions"]["persistedQuery"]["sha256Hash"] == PERSISTED_QUERIES["viewer"]


def test_mark_chat_as_read_failure_never_blocks_later_messages(transport):
    transport.session.post.side_effect = [response({}, 502), response({"data": {"markChatAsRead": {"id": "c"}}})]
    payload = {"operationName": "markChatAsRead", "variables": {"input": {"chatId": "c"}}}
    with pytest.raises(MutationOutcomeUnknown):
        transport.send("post", GRAPHQL_URL, {}, payload)
    transport.send("post", GRAPHQL_URL, {}, payload)
    assert transport.session.post.call_count == 2


def test_uncertain_listing_lock_can_be_reset(transport):
    transport.session.post.side_effect = [Timeout("network"), response({"data": {"publishItem": {"id": "i"}}})]
    payload = {"operationName": "publishItem", "variables": {"input": {"itemId": "i", "priorityStatuses": []}}}
    with pytest.raises(MutationOutcomeUnknown):
        transport.send("post", GRAPHQL_URL, {}, payload)
    with pytest.raises(MutationOutcomeUnknown):
        transport.send("post", GRAPHQL_URL, {}, payload)
    transport.forget_uncertain("listing:i")
    transport.send("post", GRAPHQL_URL, {}, payload)
    assert transport.session.post.call_count == 2


def test_read_retry_budget_is_bounded(transport):
    transport.session.get.side_effect = Timeout("network")
    with pytest.raises(RequestSendingError):
        transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer"})
    assert transport.session.get.call_count == 3


def test_rate_limit_honors_bounded_retry_after(transport):
    transport.session.get.side_effect = [response({}, 429, {"retry-after": "2"}), response({"data": {"games": {}}})]
    transport.send("get", GRAPHQL_URL, {}, {"operationName": "games"})
    transport.sleep.assert_called_once_with(2)


@pytest.mark.parametrize("status", [502, 503, 504])
def test_server_errors_do_not_replay_writes(transport, status):
    transport.session.post.return_value = response({}, status)
    with pytest.raises(MutationOutcomeUnknown):
        transport.send("post", GRAPHQL_URL, {}, {"operationName": "createItem", "variables": {}})
    assert transport.session.post.call_count == 1


def test_redirect_cannot_forward_credentials(transport):
    transport.session.get.return_value = response({}, 302, {"location": "https://example.org"})
    with pytest.raises(RequestFailedError):
        transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer"})
    assert transport.session.get.call_args.kwargs["allow_redirects"] is False


def test_foreign_endpoint_is_rejected_before_sending(transport):
    with pytest.raises(ValueError):
        transport.send("get", "https://example.org/graphql", {}, {"operationName": "viewer"})
    transport.session.get.assert_not_called()


@pytest.mark.parametrize("body", [None, [], {}, {"data": []}, {"errors": "invalid"}])
def test_malformed_response_is_not_treated_as_success(transport, body):
    transport.session.get.return_value = response(body)
    with pytest.raises(ResponseContractError):
        transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer"})


def test_partial_graphql_errors_are_not_silently_ignored(transport):
    body = {"data": {"viewer": {}}, "errors": [{"message": "denied", "extensions": {"code": "FORBIDDEN"}}]}
    transport.session.get.return_value = response(body)
    with pytest.raises(RequestApiError):
        transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer"})
    assert transport.session.get.call_count == 1


def test_caller_headers_are_normalized_without_losing_accept(transport):
    transport.session.get.return_value = response({"data": {"viewer": None}})
    transport.send("get", GRAPHQL_URL, {"Accept": "application/json"}, {"operationName": "viewer"})
    headers = transport.session.get.call_args.kwargs["headers"]
    assert headers["accept"] == "application/json"
    assert headers["cookie"] == "token=secret"


def test_multipart_does_not_force_json_content_type(transport, tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(b"fixture")
    transport.session.post.return_value = response({"data": {"createItem": {}}})
    operations = {"operationName": "createItem", "query": QUERIES["createItem"], "variables": {"attachments": [None]}}
    payload = {"operations": json.dumps(operations), "map": json.dumps({"1": ["variables.attachments.0"]})}
    with path.open("rb") as file:
        transport.send("post", GRAPHQL_URL, {}, payload, {"1": file})
    options = transport.session.post.call_args.kwargs
    assert "content-type" not in options["headers"]
    assert "multipart" in options and "json" not in options


def _concurrency_transport(delay=0.2):
    import threading
    import time as clock
    active = {"now": 0, "peak": 0}
    guard = threading.Lock()

    def slow(*args, **kwargs):
        with guard:
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        clock.sleep(delay)
        with guard:
            active["now"] -= 1
        return response({"data": {"publishItem": {"id": "x"}, "viewer": {"id": "viewer"}}})

    sessions = threading.local()

    def thread_session():
        if not hasattr(sessions, "value"):
            sessions.value = SimpleNamespace(get=slow, post=slow)
        return sessions.value

    owner = SimpleNamespace(request_max_retries=0, user_agent=DEFAULT_USER_AGENT, _timeout=10, logger=Mock(),
                            _cookie_header=lambda: "", _ingest_set_cookie=Mock(), _thread_session=thread_session)
    return GraphQLTransport(None, owner, sleep=Mock()), active


def _run_parallel(calls):
    import threading
    threads = [threading.Thread(target=call) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def _publish(transport, item):
    payload = {"operationName": "publishItem", "variables": {"input": {"itemId": item, "priorityStatuses": []}}}
    return lambda: transport.send("post", GRAPHQL_URL, {}, payload)


def test_mutations_on_one_listing_never_overlap():
    transport, active = _concurrency_transport()
    _run_parallel([_publish(transport, "same") for _ in range(3)])
    assert active["peak"] == 1


def test_reads_and_other_listings_run_in_parallel():
    transport, active = _concurrency_transport()
    read = lambda: transport.send("get", GRAPHQL_URL, {}, {"operationName": "viewer", "variables": {}})
    _run_parallel([read, read, _publish(transport, "a"), _publish(transport, "b")])
    assert active["peak"] >= 3
