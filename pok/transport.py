import json
import mimetypes
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from curl_cffi import CurlMime
from curl_cffi.requests.exceptions import RequestException

from constants.contracts import GRAPHQL_URL, IDEMPOTENT_OPERATIONS, ORIGIN, READ_OPERATIONS
from constants.transport import (
    DEFAULT_HEADERS,
    DEFAULT_IMPERSONATION,
    MAX_READ_ATTEMPTS,
    MAX_RESPONSE_BYTES,
    MAX_RETRY_DELAY,
    MUTATION_LOCK_SLOTS,
    OPERATION_PATHS,
    PERSISTED_QUERY_MISSING,
    RETRYABLE_STATUSES,
)

from .contract import PERSISTED_QUERIES, QUERIES
from .defs import (
    BotCheckDetectedException,
    CloudflareDetectedException,
    RequestApiError,
    RequestFailedError,
    RequestSendingError,
)
from .mutations import mutation_key


class ResponseContractError(ValueError):
    pass


class MutationOutcomeUnknown(RequestSendingError):
    def __init__(self, operation):
        super().__init__(GRAPHQL_URL, f"{operation}: результат неизвестен, проверьте на Playerok перед повтором")
        self.operation = operation


def impersonation_for(user_agent):
    try:
        from curl_cffi.requests.impersonate import BrowserType
        targets = {item.value for item in BrowserType}
    except ImportError:
        return DEFAULT_IMPERSONATION
    match = re.search(r"Chrome/(\d+)", user_agent or "")
    if not match or "Edg/" in user_agent or "OPR/" in user_agent:
        return DEFAULT_IMPERSONATION
    wanted = int(match.group(1))
    versions = sorted(
        int(re.match(r"chrome(\d+)", target).group(1))
        for target in targets
        if re.fullmatch(r"chrome\d+a?", target)
    )
    eligible = [version for version in versions if version <= wanted]
    chosen = eligible[-1] if eligible else (versions[0] if versions else None)
    if chosen is None:
        return DEFAULT_IMPERSONATION
    plain = f"chrome{chosen}"
    return plain if plain in targets else f"chrome{chosen}a"


def parse_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise TypeError("GraphQL payload values must be objects")
    return parsed


def prepare_payload(payload):
    operations = parse_object(payload.get("operations", payload))
    name = operations.get("operationName")
    if name not in QUERIES:
        raise ValueError(f"Unknown GraphQL operation: {name}")
    variables = parse_object(operations.get("variables", {}))
    result = {"operationName": name, "variables": variables}
    if name in READ_OPERATIONS and "operations" not in payload:
        result["extensions"] = {"persistedQuery": {"version": 1, "sha256Hash": PERSISTED_QUERIES[name]}}
    else:
        result["query"] = QUERIES[name]
    return result


def request_headers(name, variables, user_agent, cookies, caller_headers, multipart):
    path = OPERATION_PATHS.get(name, "/")
    variables = variables if isinstance(variables, dict) else {}
    filter_value = variables.get("filter") if isinstance(variables.get("filter"), dict) else {}
    input_value = variables.get("input") if isinstance(variables.get("input"), dict) else {}
    entity_id = filter_value.get("chatId") or input_value.get("chatId") or input_value.get("id") or variables.get("id")
    if "[id]" in path and entity_id:
        referer = f"{ORIGIN}{path.replace('[id]', str(entity_id))}"
    elif "[" in path:
        referer = f"{ORIGIN}/"
    else:
        referer = f"{ORIGIN}{path}"
    headers = {**DEFAULT_HEADERS, "user-agent": user_agent, "referer": referer,
               "x-gql-op": name, "x-apollo-operation-name": name, "x-gql-path": path}
    if cookies:
        headers["cookie"] = cookies
    for key, value in (caller_headers or {}).items():
        if key.lower() == "accept":
            headers["accept"] = value
    if not multipart:
        headers["content-type"] = "application/json"
    return headers


def response_json(response):
    content = getattr(response, "content", b"") or b""
    if len(content) > MAX_RESPONSE_BYTES:
        raise ResponseContractError("GraphQL response exceeds size limit")
    try:
        body = response.json()
    except ValueError:
        classify_non_json(response)
        raise ResponseContractError("Expected a GraphQL JSON response") from None
    if not isinstance(body, dict):
        raise ResponseContractError("Expected a GraphQL response object")
    errors = body.get("errors")
    if errors is not None and (not isinstance(errors, list) or any(not isinstance(e, dict) for e in errors)):
        raise ResponseContractError("Malformed GraphQL errors")
    return body


def classify_non_json(response):
    text = (getattr(response, "text", "") or "").lower()
    if "ddos-guard" in text or "check.ddos-guard" in text:
        raise BotCheckDetectedException(response)
    if "_cf_chl_opt" in text or "<title>just a moment" in text:
        raise CloudflareDetectedException(response)
    if response.status_code != 200:
        raise RequestFailedError(response)


def needs_document(body):
    for error in body.get("errors") or []:
        code = (error.get("extensions") or {}).get("code")
        if code == PERSISTED_QUERY_MISSING or error.get("message") == "PersistedQueryNotFound":
            return True
    return False


def validate_response(response, body):
    if body.get("errors"):
        raise RequestApiError(response)
    if response.status_code != 200:
        raise RequestFailedError(response)
    if not isinstance(body.get("data"), dict):
        raise ResponseContractError("GraphQL response has no data object")


def retry_delay(response, attempt):
    header = response.headers.get("retry-after", "") if response is not None else ""
    try:
        delay = float(header) if header else 2 ** attempt
    except (TypeError, ValueError):
        delay = MAX_RETRY_DELAY
    return max(0, min(delay, MAX_RETRY_DELAY))


@contextmanager
def multipart_body(payload, files):
    mime = CurlMime()
    try:
        for name, value in payload.items():
            mime.addpart(name, data=str(value).encode())
        for name, file in files.items():
            path = Path(file.name)
            mime.addpart(name, local_path=path, filename=path.name,
                         content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        yield mime
    finally:
        mime.close()


class GraphQLTransport:
    def __init__(self, session, owner, sleep=time.sleep):
        self._fixed_session = session
        self.owner = owner
        self.sleep = sleep
        self.uncertain_mutations = set()
        self._mutation_locks = [threading.Lock() for _ in range(MUTATION_LOCK_SLOTS)]

    @property
    def session(self):
        if self._fixed_session is not None:
            return self._fixed_session
        return self.owner._thread_session()

    def _mutation_lock(self, key):
        return self._mutation_locks[hash(key) % len(self._mutation_locks)]

    def send(self, method, url, headers, payload, files=None):
        if url != GRAPHQL_URL or method not in ("get", "post"):
            raise ValueError("Only the Playerok GraphQL endpoint is allowed")
        prepared = prepare_payload(payload)
        operation = prepared["operationName"]
        if operation in READ_OPERATIONS:
            return self.send_prepared(prepared, payload, headers, files)
        key = mutation_key(operation, prepared["variables"])
        with self._mutation_lock(key):
            if key in self.uncertain_mutations:
                raise MutationOutcomeUnknown(operation)
            try:
                return self.send_prepared(prepared, payload, headers, files)
            except (MutationOutcomeUnknown, ResponseContractError):
                if operation not in IDEMPOTENT_OPERATIONS:
                    self.uncertain_mutations.add(key)
                raise MutationOutcomeUnknown(operation) from None

    def forget_uncertain(self, prefix=None):
        if prefix is None:
            self.uncertain_mutations.clear()
            return
        self.uncertain_mutations = {key for key in self.uncertain_mutations if not key.startswith(prefix)}

    def send_prepared(self, prepared, original, headers, files):
        operation = prepared["operationName"]
        readable = operation in READ_OPERATIONS
        method = "get" if readable and "extensions" in prepared and not files else "post"
        response = self.send_with_retries(method, headers, prepared, original, files)
        if not readable and response.status_code >= 500:
            raise MutationOutcomeUnknown(operation)
        body = response_json(response)
        if not readable and any(
            (error.get("extensions") or {}).get("code") == "INTERNAL_SERVER_ERROR"
            for error in body.get("errors") or []
        ):
            raise MutationOutcomeUnknown(operation)
        if readable and needs_document(body):
            registered = {**prepared, "query": QUERIES[operation]}
            response = self.send_with_retries("post", headers, registered, registered, None)
            body = response_json(response)
        validate_response(response, body)
        return response

    def send_with_retries(self, method, headers, prepared, original, files):
        operation = prepared["operationName"]
        readable = operation in READ_OPERATIONS
        attempts = min(MAX_READ_ATTEMPTS, max(1, int(self.owner.request_max_retries) + 1)) if readable else 1
        response = None
        for attempt in range(attempts):
            response = self.send_attempt(method, headers, prepared, original, files, readable)
            if response is not None and response.status_code not in RETRYABLE_STATUSES:
                return response
            if not readable:
                raise MutationOutcomeUnknown(operation)
            if attempt + 1 < attempts:
                self.sleep(retry_delay(response, attempt))
        if response is not None:
            return response
        raise RequestSendingError(GRAPHQL_URL, f"{operation}: transport unavailable")

    def send_attempt(self, method, headers, prepared, original, files, readable):
        name = prepared["operationName"]
        outgoing = request_headers(name, prepared["variables"], self.owner.user_agent,
                                   self.owner._cookie_header(), headers, bool(files))
        try:
            response = self.perform(method, outgoing, prepared, original, files)
        except (RequestException, OSError, TimeoutError) as error:
            if not readable:
                raise MutationOutcomeUnknown(name) from None
            self.owner.logger.warning("GraphQL transport failed op=%s: %s", name, type(error).__name__)
            return None
        self.owner._ingest_set_cookie(response)
        self.owner.logger.debug("GraphQL response op=%s status=%s", name, response.status_code)
        return response

    def perform(self, method, headers, prepared, original, files):
        options = {"headers": headers, "timeout": self.owner._timeout,
                   "allow_redirects": False, "discard_cookies": True}
        if files:
            encoded = {**original, "operations": json.dumps(prepared)}
            with multipart_body(encoded, files) as mime:
                return self.session.post(GRAPHQL_URL, multipart=mime, **options)
        if method == "get":
            params = {key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value
                      for key, value in prepared.items()}
            return self.session.get(GRAPHQL_URL, params=params, **options)
        return self.session.post(GRAPHQL_URL, json=prepared, **options)
