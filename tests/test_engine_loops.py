from datetime import datetime, timedelta

import pytest

import bot.core as core


@pytest.mark.parametrize("value, expected", [
    (None, 300), ("", 300), ("1h", 300), ("120.7", 120), (45, 45), (5, 30), ("inf", 300), ("nan", 300), (10 ** 9, 86400),
])
def test_seconds_parsing_never_raises(value, expected):
    assert core._seconds(value, 300, 30, 86400) == expected


def bridge(interval, stamp):
    instance = object.__new__(core.MarketBridge)
    instance.config = {"auto": {"bump": {"interval": interval}}}
    instance.latest_events_times = {"auto_bump_items": stamp}
    return instance


def test_bump_interval_from_old_config_is_clamped():
    last = datetime(2026, 10, 5, 12, 0, 0)
    assert bridge(1, last.isoformat())._next_at("auto_bump_items") == last + timedelta(seconds=core.MIN_BUMP_INTERVAL)
    assert bridge("2h", last.isoformat())._next_at("auto_bump_items") == last + timedelta(seconds=3600)
    assert bridge(7200, last.isoformat())._next_at("auto_bump_items") == last + timedelta(seconds=7200)


def test_corrupted_bump_timestamp_does_not_crash_loop():
    before = datetime.now()
    assert bridge(3600, "вчера")._next_at("auto_bump_items") >= before
    assert bridge(3600, None)._next_at("auto_bump_items") >= before
