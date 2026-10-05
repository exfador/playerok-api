import json

import pytest

from lib import util

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"


@pytest.mark.parametrize("proxy", [
    "1.2.3.4:8080",
    " 1.2.3.4:8080 ",
    "user:pass@1.2.3.4:8080",
    "1.2.3.4:8080:user:pass",
    "http://user:pass@1.2.3.4:8080",
    "https://1.2.3.4:443/",
    "proxy.example.com:3128",
    "user:pa:ss@gate.provider.io:10000",
    "socks5://user:pass@host.net:1080",
    "socks5h://1.2.3.4:1080",
    "socks5:1.2.3.4:1080:user:pass",
    "socks5h://user:pass@1.2.3.4:1080:user:pass",
])
def test_valid_proxies(proxy):
    assert util.proxy_ok(proxy)
    assert util.proxy_url_for_requests(proxy)


@pytest.mark.parametrize("proxy", [
    "", "   ", None, "1.2.3.4", "1.2.3.4:0", "1.2.3.4:70000", "999.1.1.1:80", "abc:80", "localhost",
    "socks5://host", "socks5://host:99999", "http://", "user@1.2.3.4:80", "1.2.3.4:80 extra", "ftp://1.2.3.4:21",
])
def test_invalid_proxies(proxy):
    assert not util.proxy_ok(proxy)


@pytest.mark.parametrize("raw, expected", [
    ("1.2.3.4:8080", "http://1.2.3.4:8080"),
    ("1.2.3.4:8080:user:pass", "http://user:pass@1.2.3.4:8080"),
    ("http://user:pass@1.2.3.4:8080", "http://user:pass@1.2.3.4:8080"),
    ("socks5h://user:pass@1.2.3.4:1080:user:pass", "socks5h://user:pass@1.2.3.4:1080"),
    ("socks5:1.2.3.4:1080:user:pass", "socks5h://user:pass@1.2.3.4:1080"),
    ("socks5://host", None),
    ("", None),
])
def test_proxy_url_for_requests(raw, expected):
    assert util.proxy_url_for_requests(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("", ""),
    (None, ""),
    ("1.2.3.4:8080", "1.2.3.4:8080"),
    ("user:secret@1.2.3.4:8080", "user:•••@1.2.3.4:8080"),
    ("1.2.3.4:8080:user:secret", "user:•••@1.2.3.4:8080"),
    ("http://user:se<c&r>et@proxy.example.com:3128", "http://user:•••@proxy.example.com:3128"),
    ("socks5h://user:secret@host.net:1080", "socks5h://user:•••@host.net:1080"),
    ("garbage:secret@", "garbage:•••@"),
])
def test_proxy_password_is_masked(raw, expected):
    assert util.proxy_masked(raw) == expected


@pytest.mark.parametrize("count, word", [
    (0, "товаров"), (1, "товар"), (2, "товара"), (4, "товара"), (5, "товаров"), (11, "товаров"), (12, "товаров"),
    (21, "товар"), (22, "товара"), (25, "товаров"), (101, "товар"), (111, "товаров"), (-3, "товара"),
])
def test_russian_plural(count, word):
    assert util.plural(count, "товар", "товара", "товаров") == word


def test_aiogram_gets_plain_socks5_scheme():
    assert util.proxy_url_for_aiogram("socks5h://u:p@1.2.3.4:1080") == "socks5://u:p@1.2.3.4:1080"
    assert util.proxy_url_for_aiogram("1.2.3.4:8080") == "http://1.2.3.4:8080"
    assert util.proxy_url_for_aiogram("") is None


@pytest.mark.parametrize("raw, expected", [
    (None, (None, None, None, None)),
    ("1.2.3.4:8080", ("1.2.3.4", "8080", None, None)),
    ("user:pass@1.2.3.4:8080", ("1.2.3.4", "8080", "user", "pass")),
    ("1.2.3.4:8080:user:pass", ("1.2.3.4", "8080", "user", "pass")),
    ("socks5h://user:pass@host.net:1080", ("host.net", "1080", "user", "pass")),
    ("garbage", (None, None, None, None)),
])
def test_proxy_display_parts(raw, expected):
    assert util.proxy_display_parts(raw) == expected


def write(tmp_path, content, name="cookies.json"):
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return str(path)


def export(*cookies):
    return [{"name": n, "value": v, "domain": d} for n, v, d in cookies]


def test_cookie_editor_array_export(tmp_path):
    path = write(tmp_path, export(("token", JWT, ".playerok.com"), ("__ddg5_", "abc", "playerok.com"),
                                  ("token", "foreign", ".evil.com"), ("sid", "x", "notplayerok.com")))
    jar, error = util.load_cookies_json(path)
    assert error is None
    assert jar == {"token": JWT, "__ddg5_": "abc"}


def test_cookie_export_with_bom_and_wrapper(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"ready": True, "cookies": export(("token", JWT, "playerok.com"))}).encode())
    assert util.load_cookies_json(str(path)) == ({"token": JWT}, None)


@pytest.mark.parametrize("content, fragment", [
    ("", "пустой"),
    ("{not json", "некорректный JSON"),
    ({"ready": False, "cookies": []}, '"ready": false'),
    ({"something": 1}, "не нашлось списка Cookie"),
    (export(("token", JWT, ".evil.com")), "нет Cookie для playerok.com"),
    (export(("sid", "x", ".playerok.com")), "нет валидного Cookie `token=`"),
    (export(("token", "not-a-jwt", ".playerok.com")), "нет валидного Cookie `token=`"),
])
def test_cookie_file_errors_are_explained(tmp_path, content, fragment):
    jar, error = util.load_cookies_json(write(tmp_path, content))
    assert jar == {}
    assert fragment in error


def test_missing_cookie_file_and_template(tmp_path):
    path = str(tmp_path / "conf" / "cookies.json")
    jar, error = util.load_cookies_json(path)
    assert jar == {} and "не найден" in error
    assert util.ensure_cookies_json(path) is True
    assert util.ensure_cookies_json(path) is False
    assert '"ready": false' in util.load_cookies_json(path)[1]


@pytest.mark.parametrize("value, expected", [
    (JWT, True),
    ("YQ.Yg.Yw", True),
    ("a.b.c", False),
    ("a.b", False),
    ("a.b.c.d", False),
    ("a.b.c=", False),
    ("", False),
])
def test_token_validation(value, expected):
    assert util.token_ok(value) is expected


def test_cookie_string_parsing():
    assert util.parse_cookies_string(" token = abc ; empty=; =x; noeq ; a=b=c ") == {"token": "abc", "empty": "", "a": "b=c"}
    assert util.cookies_ok(f"__ddg5_=1; token={JWT}")
    assert not util.cookies_ok("token=bad")
    assert not util.cookies_ok("x" * 40000)
    assert not util.cookies_ok(None)
    assert util.cookie_header_from_jar({"a": "1", "b": "", "c": "3"}) == "a=1; c=3"


@pytest.mark.parametrize("value, expected", [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0.0.0 Safari/537.36", True),
    ("short", False),
    ("Mozilla/5.0 кириллица", False),
    ("x" * 600, False),
    ("", False),
])
def test_user_agent_validation(value, expected):
    assert util.ua_ok(value) is expected


@pytest.mark.parametrize("value, expected", [
    ("1234567890:AAH" + "x" * 32, True),
    ("123:abc", False),
    ("1234567890:" + "x" * 10, False),
    ("", False),
])
def test_telegram_token_validation(value, expected):
    assert bool(util.tg_token_ok(value)) is expected


def test_display_dates(monkeypatch):
    monkeypatch.setattr(util, "_display_tz", lambda: __import__("datetime").timezone.utc)
    assert util.iso_to_display_str(None) == "—"
    assert util.iso_to_display_str("not a date") == "not a date"
    assert util.iso_to_display_str("2026-10-05T10:00:00.000Z", fmt="%d.%m %H:%M") == "05.10 10:00"
