import json
import time

import pytest

from pok.cookies import load_cookie_file, parse_cookies


def test_cookie_editor_export_is_supported_without_saving_secrets(tmp_path):
    source = tmp_path / "cookies.json"
    rows = [{"domain": ".playerok.com", "name": "token", "value": "fixture", "path": "/"}]
    source.write_text(json.dumps(rows))
    assert load_cookie_file(source) == {"token": "fixture"}
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("domain", ["evilplayerok.com", "playerok.com.evil.test", "example.org"])
def test_foreign_domain_cookies_are_rejected(domain):
    with pytest.raises(ValueError, match="foreign domain"):
        parse_cookies([{"domain": domain, "name": "token", "value": "secret"}])


def test_expired_cookies_are_not_sent():
    expired = {"domain": ".playerok.com", "name": "old", "value": "secret", "expirationDate": time.time() - 1}
    assert parse_cookies([expired]) == {}


@pytest.mark.parametrize("cookie", ["token=a; token=b", "token=a\r\nx-evil: value", "missing-equals"])
def test_ambiguous_or_injected_cookie_headers_are_rejected(cookie):
    with pytest.raises(ValueError):
        parse_cookies(cookie)


def test_cookie_header_preserves_equals_in_values():
    assert parse_cookies("token=a=b; other=c") == {"token": "a=b", "other": "c"}


def test_non_root_path_does_not_leak_to_graphql():
    with pytest.raises(ValueError, match="unsupported path"):
        parse_cookies([{"domain": ".playerok.com", "name": "scoped", "value": "secret", "path": "/private"}])
