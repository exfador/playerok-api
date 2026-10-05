from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib import util


class Exited(Exception):
    pass


@pytest.fixture
def exits(monkeypatch):
    codes = []

    def fake_exit(code):
        codes.append(code)
        raise Exited()

    monkeypatch.setattr(util.os, "_exit", fake_exit)
    monkeypatch.setattr(util, "_persist_engine_state", Mock())
    monkeypatch.setattr(util, "clear_terminal", Mock())
    return codes


def test_restart_under_start_bat_uses_exit_code(monkeypatch, exits):
    monkeypatch.setattr(util.sys, "platform", "win32")
    monkeypatch.setenv("CXH_LAUNCHER", "bat")
    call = Mock()
    monkeypatch.setattr(util.subprocess, "call", call)
    with pytest.raises(Exited):
        util.reboot()
    assert exits == [util.RESTART_EXIT_CODE]
    call.assert_not_called()
    util._persist_engine_state.assert_called_once()


def test_restart_on_windows_without_launcher_quotes_paths(monkeypatch, exits):
    monkeypatch.setattr(util.sys, "platform", "win32")
    monkeypatch.delenv("CXH_LAUNCHER", raising=False)
    monkeypatch.setattr(util.sys, "argv", [r"C:\Users\Имя Фамилия\bot\main.py"])
    call = Mock(return_value=0)
    monkeypatch.setattr(util.subprocess, "call", call)
    with pytest.raises(Exited):
        util.reboot()
    assert call.call_args.args[0][1] == r"C:\Users\Имя Фамилия\bot\main.py"
    assert exits == [0]


def test_restart_on_linux_replaces_process(monkeypatch, exits):
    monkeypatch.setattr(util.sys, "platform", "linux")
    execv = Mock()
    monkeypatch.setattr(util.os, "execv", execv)
    monkeypatch.setattr(util.sys, "argv", ["/opt/my bot/main.py"])
    util.reboot()
    assert execv.call_args.args[1][1:] == ["/opt/my bot/main.py"]


def test_engine_state_is_saved_before_restart(monkeypatch):
    import bot.core as core
    saved = {}
    monkeypatch.setattr(core, "db", SimpleNamespace(set=lambda key, value: saved.__setitem__(key, value)))
    monkeypatch.setattr(core, "_flush_counters", lambda stats: saved.__setitem__("stats", stats))
    engine = object.__new__(core.MarketBridge)
    engine.initialized_users, engine.saved_items, engine.latest_events_times = ["buyer"], [], {"auto_bump_items": None}
    engine.stats = SimpleNamespace(deals_completed=1)
    engine.persist_state()
    assert saved["initialized_users"] == ["buyer"] and saved["stats"].deals_completed == 1
