import asyncio

import pytest

import tests.test_panel_smoke as smoke
from ctrl import keys, states
from ctrl.cb import CX
from lib import cfg as cfgmod
from tests.test_panel_smoke import FSM_DATA, callback_update, populate, run_all, text_update

smoke_panel = smoke.smoke_panel


def config():
    return cfgmod.AppConf.read("config")


def send(instance, state, text, data=None):
    return run_all(instance, [(f"{state}:{text}", text_update(text), state)], data=data)


@pytest.mark.parametrize("text, saved", [("1", 3600), ("599", 3600), ("²", 3600), ("abc", 3600), ("600", 600), ("7200", 7200)])
def test_bump_interval_has_safe_minimum(smoke_panel, text, saved):
    instance, session = smoke_panel
    assert not send(instance, states.PduBoostGrp.pdu_boost_interval_sec.state, text)
    assert config()["auto"]["bump"]["interval"] == saved
    if saved == 3600:
        assert any("❌" in t for t in session.texts)


@pytest.mark.parametrize("text, saved", [("0", 30), ("4", 30), ("301", 30), ("45", 45), (" 60 ", 60)])
def test_request_timeout_range(smoke_panel, text, saved):
    instance, session = smoke_panel
    assert not send(instance, states.PduConnGrp.pdu_http_timeout.state, text)
    assert config()["account"]["timeout"] == saved
    if saved != 30:
        assert any("применяется сразу" in t for t in session.texts)


def test_keep_in_sale_requires_premium(smoke_panel):
    instance, session = smoke_panel
    assert not run_all(instance, [("rs_kis", callback_update(CX.rs_kis), None)])
    assert config()["auto"]["restore"]["keep_in_sale"] is False
    assert any("PREMIUM" in a for a in session.alerts)
    cfg = config()
    cfg["auto"]["restore"]["premium"] = True
    cfgmod.AppConf.write("config", cfg)
    assert not run_all(instance, [("rs_kis", callback_update(CX.rs_kis), None)])
    assert config()["auto"]["restore"]["keep_in_sale"] is True


def test_delivery_delete_confirmation_names_rule_and_stock(smoke_panel):
    instance, session = smoke_panel
    populate()
    assert not run_all(instance, [("ad_dok", callback_update(CX.ad_dok), None)], data=FSM_DATA)
    assert any("<code>ключ</code>" in t and "12</b> товаров" in t for t in session.texts)


def test_bump_now_confirmation_mentions_cost(smoke_panel):
    instance, session = smoke_panel
    cfg = config()
    cfg["auto"]["bump"]["enabled"] = True
    cfgmod.AppConf.write("config", cfg)
    assert not run_all(instance, [("bm_go", callback_update(CX.bm_go), None)])
    assert any("до <b>50 ₽</b> за лот" in t and "200 ₽</b> в день" in t for t in session.texts)


def test_proxy_password_never_shown(smoke_panel, monkeypatch):
    instance, session = smoke_panel
    import ctrl.ui.settings as settings_ui
    monkeypatch.setattr(settings_ui, "proxy_http_latency_country", lambda proxy: (None, None))
    cfg = config()
    cfg["account"]["proxy"] = "user:s3cr<et@1.2.3.4:8080"
    cfgmod.AppConf.write("config", cfg)
    updates = [("proxy", callback_update(keys.PduPrefsScope(to="proxy").pack()), None),
               ("pl_px", callback_update(CX.pl_px), None)]
    assert not run_all(instance, updates)
    shown = " ".join(session.texts) + " ".join(session.buttons.values())
    assert "s3cr" not in shown
    assert "user:•••@1.2.3.4:8080" in shown


def test_phrase_lists_reject_empty_input(smoke_panel):
    instance, _ = smoke_panel
    for state, name in [(states.PduBoostGrp.pdu_boost_allow_line, "auto_bump_items"),
                        (states.PduSealGrp.pdu_seal_phrase_line, "auto_complete_deals"),
                        (states.PduReviveGrp.pdu_revive_phrase_line, "auto_restore_items")]:
        assert not send(instance, state.state, " , ,, ")
        assert cfgmod.AppConf.read(name)["included"] == []


@pytest.mark.parametrize("state, wrong, right, check", [
    (states.PduBoostGrp.pdu_boost_interval_sec, "1", "1200", lambda c: c["auto"]["bump"]["interval"] == 1200),
    (states.PduConnGrp.pdu_http_timeout, "abc", "40", lambda c: c["account"]["timeout"] == 40),
    (states.PduBoostGrp.pdu_daily_limit, "много", "150", lambda c: c["auto"]["daily_limit"] == 150),
])
def test_wrong_input_keeps_field_open_for_retry(smoke_panel, state, wrong, right, check):
    instance, session = smoke_panel

    async def go():
        context = instance.dp.fsm.get_context(bot=instance.bot, chat_id=smoke.ADMIN, user_id=smoke.ADMIN)
        await context.set_state(state)
        await instance.dp.feed_update(instance.bot, text_update(wrong))
        assert await context.get_state() == state.state
        await instance.dp.feed_update(instance.bot, text_update(right))
        assert await context.get_state() is None

    asyncio.run(go())
    assert check(config())
    assert any("Можно сразу отправить исправленное значение" in t for t in session.texts)


@pytest.mark.parametrize("data, header, back", [(CX.day_lim, "Авто-поднятие", "bump"), (CX.day_lim_rs, "Авто-восстановление", "restore")])
def test_daily_limit_returns_to_screen_it_was_opened_from(smoke_panel, data, header, back):
    instance, session = smoke_panel

    async def go():
        await instance.dp.feed_update(instance.bot, callback_update(data))
        await instance.dp.feed_update(instance.bot, text_update("120"))

    asyncio.run(go())
    assert config()["auto"]["daily_limit"] == 120
    assert header in session.texts[0] and header in session.texts[-1]
    assert "Лимит сохранён" in session.texts[-1]
    assert keys.PduPrefsScope(to=back).pack() in session.buttons


@pytest.mark.parametrize("stats, fragment", [
    ({"checked": 0, "bumped": 0}, "в продаже нет лотов"),
    ({"checked": 2, "bumped": 1, "skip_price": 1}, "Поднято: <b>1</b>"),
])
def test_bump_now_explains_empty_catalog(smoke_panel, monkeypatch, stats, fragment):
    from types import SimpleNamespace

    import bot.core as core
    instance, session = smoke_panel
    cfg = config()
    cfg["auto"]["bump"]["enabled"] = True
    cfgmod.AppConf.write("config", cfg)
    monkeypatch.setattr(core, "live_bridge", lambda: SimpleNamespace(bump_items=lambda: stats))
    assert not run_all(instance, [("bm_run", callback_update(CX.bm_run), None)])
    assert fragment in session.texts[-1]


@pytest.mark.parametrize("ua, label", [
    ("", "не задан"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36", "Chrome 144"),
    ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0", "Edge 141"),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0", "Firefox 139"),
])
def test_auth_screen_shows_user_agent_button(ua, label):
    from ctrl.ui import settings
    assert settings.browser_label(ua) == label


def test_user_agent_is_reachable_and_saved(smoke_panel):
    instance, session = smoke_panel
    assert not run_all(instance, [("auth", callback_update(keys.PduPrefsScope(to="auth").pack()), None)])
    assert CX.pl_ua in session.buttons
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
    assert not send(instance, states.PduConnGrp.pdu_browser_ua.state, f"  {ua}  ")
    assert config()["account"]["user_agent"] == ua
    assert "/restart" in session.texts[-1]


def test_logs_screen_is_reachable_and_sends_todays_log(smoke_panel, monkeypatch, tmp_path):
    import lib.util as util
    instance, session = smoke_panel
    log_file = tmp_path / "bot.log"
    log_file.write_text("a | ERROR | b\nc\n", encoding="utf-8")
    monkeypatch.setattr(util, "get_bot_log_path", lambda: str(log_file))
    assert not run_all(instance, [("system", callback_update(keys.PduRootNav(to="system").pack()), None)])
    assert keys.PduRootNav(to="logs").pack() in session.buttons
    assert not run_all(instance, [("logs", callback_update(keys.PduRootNav(to="logs").pack()), None)])
    assert {CX.log_sn, CX.log_mb} <= set(session.buttons)
    assert not run_all(instance, [("log_sn", callback_update(CX.log_sn), None)])
    assert "SendDocument" in session.calls


@pytest.mark.parametrize("text, saved", [("0", 300), ("99999", 300), ("50", 50)])
def test_log_size_range(smoke_panel, text, saved):
    instance, _ = smoke_panel
    assert not send(instance, states.PduConnGrp.pdu_log_tail.state, text)
    assert config()["logs"]["max_mb"] == saved


@pytest.mark.parametrize("kind, state, pager", [
    ("ad", states.PduFulfillGrp.pdu_ff_sheet, CX.ad_pg),
    ("cc", states.PduCmdGrp.pdu_cmd_sheet, CX.cc_pg),
])
def test_page_jump_is_reachable_and_validated(smoke_panel, kind, state, pager):
    from lib.custom_commands import cc_new_item, cc_wrap_items
    instance, session = smoke_panel
    cfg = config()
    cfg["features"].update(commands=True, deliveries=True)
    cfgmod.AppConf.write("config", cfg)
    if kind == "ad":
        cfgmod.AppConf.write("auto_deliveries", [{"keyphrases": ["same"], "piece": False, "message": ["x"]} for _ in range(10)])
        opener = keys.PduFulfillGrid(page=0).pack()
    else:
        cfgmod.AppConf.write("custom_commands", cc_wrap_items([cc_new_item(f"!c{i}") for i in range(10)]))
        opener = keys.PduCmdGrid(page=0).pack()
    assert not run_all(instance, [("open", callback_update(opener), None)])
    assert pager in session.buttons
    assert not send(instance, state.state, "5")
    assert "от 1 до 2" in session.texts[-1]
    assert not send(instance, state.state, "2")
    assert "от 1 до 2" not in session.texts[-1]


def test_identical_delivery_rules_open_their_own_cards(smoke_panel):
    from ctrl.ui import settings
    rules = [{"keyphrases": ["same"], "piece": False, "message": ["x"]} for _ in range(3)]
    cfgmod.AppConf.write("auto_deliveries", rules)
    cfg = config()
    cfg["features"]["deliveries"] = True
    cfgmod.AppConf.write("config", cfg)
    data = [b.callback_data for row in settings.fac_078(0).inline_keyboard for b in row]
    assert [keys.PduFulfillOpen(index=i).pack() for i in range(3)] == [d for d in data if d.startswith(keys.PduFulfillOpen.__prefix__)]


def test_status_reports_freshest_server_signal(smoke_panel, monkeypatch):
    import time
    from types import SimpleNamespace

    import bot.core as core
    instance, session = smoke_panel
    now = time.monotonic()
    feed = {"connected": True, "last_pong_at": now - 600, "last_message_at": now - 5, "subscriptions": 3}
    bridge = SimpleNamespace(health=lambda: {"feed": feed, "workers": {"a": True}, "feed_supervisor_alive": True, "started_at": None})
    monkeypatch.setattr(core, "live_bridge", lambda: bridge)
    assert not run_all(instance, [("status", text_update("/status"), None)])
    assert "сигнал от сервера: 5 с назад" in session.texts[-1]


def test_restore_screen_opens_daily_limit_with_restore_origin():
    from ctrl.ui import settings
    config = {"auto": {"daily_limit": 100}}
    assert settings.daily_limit_button(config, "restore").callback_data == CX.day_lim_rs
    assert settings.daily_limit_button(config).callback_data == CX.day_lim


def flaky_session(monkeypatch, session, error_factory, failures):
    real = session.make_request
    left = {"n": failures}

    async def make_request(bot, method, timeout=None):
        if type(method).__name__ == "SendMessage" and left["n"] > 0:
            left["n"] -= 1
            raise error_factory(method)
        return await real(bot, method, timeout)

    monkeypatch.setattr(session, "make_request", make_request)


def test_notifications_wait_out_telegram_flood_limit(smoke_panel, monkeypatch):
    from aiogram.exceptions import TelegramRetryAfter
    import ctrl.panel as panel_module
    instance, session = smoke_panel
    pauses = []

    async def fake_sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(panel_module.asyncio, "sleep", fake_sleep)
    flaky_session(monkeypatch, session, lambda m: TelegramRetryAfter(method=m, message="Too Many Requests", retry_after=3), 2)
    asyncio.run(instance.log_event("<b>Новый заказ</b>"))
    assert pauses == [3.5, 3.5]
    assert session.texts[-1] == "<b>Новый заказ</b>"


def test_blocked_admin_is_not_retried_and_broken_html_falls_back(smoke_panel, monkeypatch):
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    instance, session = smoke_panel
    flaky_session(monkeypatch, session, lambda m: TelegramForbiddenError(method=m, message="bot was blocked by the user"), 1)
    asyncio.run(instance.log_event("<b>Заказ</b>"))
    assert session.texts == []
    flaky_session(monkeypatch, session, lambda m: TelegramBadRequest(method=m, message="can't parse entities"), 1)
    asyncio.run(instance.log_event("<b>Заказ</b> &amp; ключ"))
    assert session.texts[-1] == "Заказ & ключ"


def test_health_probe_never_parks_executor_threads(smoke_panel, monkeypatch):
    import types

    import ctrl.panel as panel_module
    instance, _ = smoke_panel
    clock = [0.0]
    real_sleep = asyncio.sleep
    probes = []

    async def fake_sleep(seconds):
        clock[0] += seconds
        await real_sleep(0)

    async def get_me():
        probes.append(clock[0])
        if len(probes) == 3:
            instance._stop_event.set()

    def no_threads(*args, **kwargs):
        raise AssertionError("health probe must not occupy executor threads")

    monkeypatch.setattr(panel_module, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(panel_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(panel_module.asyncio, "to_thread", no_threads)
    monkeypatch.setattr(instance.bot, "get_me", get_me)
    asyncio.run(instance._health_probe())
    assert probes == [60.0, 120.0, 180.0]


def addon_import(instance, monkeypatch, tmp_path, entries):
    import shutil
    import zipfile
    from datetime import datetime, timezone

    from aiogram.types import Chat, Document, Message, Update

    archive = tmp_path / "upload.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)

    async def download(file, destination=None, **kwargs):
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(type(instance.bot), "download", lambda self, file, destination=None, **kw: download(file, destination))
    message = Message(message_id=900, date=datetime.now(timezone.utc), chat=Chat(id=smoke.ADMIN, type="private"),
                      from_user=smoke.user(), document=Document(file_id="f", file_unique_id="u", file_name="pack.zip"))
    return run_all(instance, [("import", Update(update_id=901, message=message), states.PduAddonGrp.pdu_addon_import_file.state)])


def test_addon_import_unpacks_valid_extension(smoke_panel, monkeypatch, tmp_path):
    instance, session = smoke_panel
    assert not addon_import(instance, monkeypatch, tmp_path, {"myext/__init__.py": "NAME = 'x'\n"})
    assert (tmp_path / "ext" / "myext" / "__init__.py").exists(), session.texts
    assert any("myext" in t and "перезапуск" in t for t in session.texts)


@pytest.mark.parametrize("entries, fragment", [
    ({"../evil/__init__.py": "x", "ok/__init__.py": "x"}, "Опасный путь"),
    ({"C:/evil/__init__.py": "x"}, "Опасный путь"),
    ({"bomb/__init__.py": "x", "bomb/zeros.bin": b"\0" * (2 * 1024 * 1024)}, "слишком большой"),
])
def test_addon_import_rejects_dangerous_archives(smoke_panel, monkeypatch, tmp_path, entries, fragment):
    import ctrl.cmd
    monkeypatch.setattr(ctrl.cmd, "MAX_ADDON_BYTES", 1024 * 1024)
    instance, session = smoke_panel
    assert not addon_import(instance, monkeypatch, tmp_path, entries)
    assert any(fragment in t for t in session.texts)
    assert not (tmp_path / "evil").exists()
    assert not (tmp_path / "ext" / "bomb").exists()


def test_system_screen_reflects_update_check_setting(smoke_panel):
    instance, session = smoke_panel
    assert not run_all(instance, [("system", callback_update(keys.PduRootNav(to="system").pack()), None)])
    assert any("Автопроверка релизов выключена" in t for t in session.texts)
