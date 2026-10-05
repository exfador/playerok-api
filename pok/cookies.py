import json
import re
import time
from pathlib import Path

from constants.transport import (
    COOKIE_DOMAIN,
    COOKIE_NAME_PATTERN,
    COOKIE_PATH,
    MAX_COOKIE_COUNT,
    MAX_COOKIE_EXPORT_BYTES,
)


def validate_pair(name, value):
    if not isinstance(name, str) or not re.fullmatch(COOKIE_NAME_PATTERN, name):
        raise ValueError("Invalid cookie name")
    if not isinstance(value, str):
        raise TypeError("Cookie value must be a string")
    if any(ord(char) < 33 or ord(char) > 126 or char in ';,"\\' for char in value):
        raise ValueError("Invalid cookie value")
    return name, value


def exported_cookie_pair(row, now):
    if not isinstance(row, dict):
        raise TypeError("Cookie export entries must be objects")
    if row.get("domain", "").lstrip(".").lower() != COOKIE_DOMAIN:
        raise ValueError("Cookie export contains a foreign domain")
    if row.get("path", COOKIE_PATH) != COOKIE_PATH:
        raise ValueError("Cookie export contains an unsupported path")
    expiry = row.get("expirationDate")
    if expiry is not None and (not isinstance(expiry, (int, float)) or expiry <= now):
        return None
    return validate_pair(row.get("name"), row.get("value"))


def parse_cookie_pairs(cookies):
    if isinstance(cookies, dict):
        return [validate_pair(name, value) for name, value in cookies.items()]
    if isinstance(cookies, list):
        return [pair for row in cookies if (pair := exported_cookie_pair(row, time.time()))]
    raise ValueError("Expected a cookie header, mapping, or exported array")


def parse_cookies(cookies):
    if cookies is None:
        return {}
    if isinstance(cookies, str):
        if len(cookies.encode()) > MAX_COOKIE_EXPORT_BYTES:
            raise ValueError("Cookie input exceeds size limit")
        cookies = decode_cookie_string(cookies)
    pairs = parse_cookie_pairs(cookies)
    if len(pairs) > MAX_COOKIE_COUNT:
        raise ValueError("Cookie count exceeds limit")
    if len(dict(pairs)) != len(pairs):
        raise ValueError("Duplicate cookie names")
    return dict(pairs)


def decode_cookie_string(value):
    if value.strip().startswith(("[", "{")):
        return json.loads(value)
    pairs = [part.strip().partition("=") for part in value.split(";") if part.strip()]
    if any(not separator for _, separator, _ in pairs):
        raise ValueError("Malformed cookie header")
    names = [name for name, _, _ in pairs]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate cookie names")
    return {name: content for name, _, content in pairs}


def parse_cookies_lenient(cookies):
    try:
        return parse_cookies(cookies)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    if isinstance(cookies, str):
        if cookies.strip().startswith(("[", "{")):
            try:
                cookies = json.loads(cookies)
            except json.JSONDecodeError:
                cookies = {}
        else:
            cookies = dict(
                (name.strip(), value.strip())
                for name, separator, value in (part.strip().partition("=") for part in cookies.split(";"))
                if separator and name.strip()
            )
    if isinstance(cookies, list):
        rows, now = cookies, time.time()
        cookies = {}
        for row in rows:
            try:
                pair = exported_cookie_pair(row, now)
            except (TypeError, ValueError):
                continue
            if pair:
                cookies[pair[0]] = pair[1]
    result = {}
    for name, value in (cookies or {}).items() if isinstance(cookies, dict) else []:
        try:
            validate_pair(name, value)
        except (TypeError, ValueError):
            continue
        result[name] = value
        if len(result) >= MAX_COOKIE_COUNT:
            break
    return result


def load_cookie_file(path):
    source = Path(path)
    if source.stat().st_size > MAX_COOKIE_EXPORT_BYTES:
        raise ValueError("Cookie export exceeds size limit")
    return parse_cookies(source.read_text())
