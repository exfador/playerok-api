import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from ctrl import actions, panel, states
from ctrl.cb import CX
from ctrl.cmd import on_cmd_start, rx_029
from lib import ext

TEST_TOKEN = "123456:local-test-token"
TEST_USER_ID = 100
CORE_STATE = "Core:input"
PLUGIN_STATE = "Plugin:input"
INPUT_TEXT = "test-input"
TIMEOUT_INPUT = "45"


@pytest.fixture
def routed_panel(monkeypatch):
    config = {"bot": {"token": TEST_TOKEN, "proxy": "", "admins": [TEST_USER_ID]}}
    plugin = Router(name="plugin")
    core = Router(name="core")
    commands = Router(name="commands")
    monkeypatch.setattr(panel.cfg, "read", lambda name: config)
    monkeypatch.setattr(panel, "_panel", None)
    monkeypatch.setattr(panel, "main_router", core)
    monkeypatch.setattr(panel, "cmd_router", commands)
    monkeypatch.setattr(panel, "all_extensions", lambda: [SimpleNamespace(bot_paths=[plugin])])
    monkeypatch.setattr("ctrl.router", core)
    monkeypatch.setattr("ctrl.cmd.router", commands)
    instance = panel.Panel()
    return instance, commands, plugin


def message_update(text):
    message = Message(message_id=1, date=datetime.now(timezone.utc), text=text,
                      chat=Chat(id=TEST_USER_ID, type="private"),
                      from_user=User(id=TEST_USER_ID, is_bot=False, first_name="Test"))
    return Update(update_id=1, message=message)


async def dispatch_message(instance, text, state_name=None):
    state = instance.dp.fsm.get_context(bot=instance.bot, chat_id=TEST_USER_ID,
                                        user_id=TEST_USER_ID)
    await state.set_state(state_name)
    try:
        result = await instance.dp.feed_update(instance.bot, message_update(text))
        return result, await state.get_state()
    finally:
        await instance.bot.session.close()
        await instance.dp.storage.close()


@pytest.mark.parametrize("state_name", [None, CORE_STATE, PLUGIN_STATE])
def test_start_reaches_real_core_handler_before_greedy_plugin(routed_panel, monkeypatch, state_name):
    instance, commands, plugin = routed_panel
    overlay = AsyncMock()
    greedy = AsyncMock(aiogram_flag={})
    monkeypatch.setattr("ctrl.cmd.emit_overlay", overlay)
    commands.message.register(on_cmd_start, Command("start"))
    plugin.message.register(greedy)
    _, final_state = asyncio.run(dispatch_message(instance, "/start", state_name))
    overlay.assert_awaited_once()
    greedy.assert_not_awaited()
    assert final_state is None


def test_core_input_is_not_swallowed(routed_panel):
    instance, commands, plugin = routed_panel
    core_input = AsyncMock(aiogram_flag={})
    greedy = AsyncMock(aiogram_flag={})
    commands.message.register(core_input, StateFilter(CORE_STATE))
    plugin.message.register(greedy)
    asyncio.run(dispatch_message(instance, INPUT_TEXT, CORE_STATE))
    core_input.assert_awaited_once()
    greedy.assert_not_awaited()


@pytest.mark.parametrize("text,state_name", [("/plugin", None), (INPUT_TEXT, PLUGIN_STATE)])
def test_plugin_commands_and_states_remain_available(routed_panel, text, state_name):
    instance, commands, plugin = routed_panel
    core_input = AsyncMock(aiogram_flag={})
    plugin_input = AsyncMock(aiogram_flag={})
    commands.message.register(core_input, StateFilter(CORE_STATE))
    plugin.message.register(plugin_input)
    asyncio.run(dispatch_message(instance, text, state_name))
    plugin_input.assert_awaited_once()
    core_input.assert_not_awaited()


def test_hot_reload_does_not_restore_plugin_priority(routed_panel):
    instance, commands, plugin = routed_panel
    core_input = AsyncMock(aiogram_flag={})
    greedy = AsyncMock(aiogram_flag={})
    replacement = Router(name="replacement")
    commands.message.register(core_input, StateFilter(CORE_STATE))
    replacement.message.register(greedy)
    ext._replace_extension_tg_routers([plugin], [replacement])
    asyncio.run(dispatch_message(instance, INPUT_TEXT, CORE_STATE))
    core_input.assert_awaited_once()
    greedy.assert_not_awaited()
    assert plugin.parent_router is None


def test_reload_preserves_other_plugin_order_and_can_roll_back(routed_panel):
    instance, commands, plugin = routed_panel
    sibling = Router(name="sibling")
    replacement = Router(name="replacement")
    parent = plugin.parent_router
    parent.include_router(sibling)
    ext._replace_extension_tg_routers([plugin], [replacement])
    assert parent.sub_routers == [commands, replacement, sibling]
    ext._replace_extension_tg_routers([replacement], [plugin])
    assert parent.sub_routers == [commands, plugin, sibling]
    assert replacement.parent_router is None
    asyncio.run(instance.bot.session.close())


def test_handler_diagnostics_do_not_log_message_contents(routed_panel, caplog):
    instance, commands, _ = routed_panel
    commands.message.register(AsyncMock(aiogram_flag={}), StateFilter(CORE_STATE))
    with caplog.at_level("DEBUG", logger="cxh.ctrl"):
        asyncio.run(dispatch_message(instance, INPUT_TEXT, CORE_STATE))
    assert "handler enter name=" in caplog.text
    assert "handler exit name=" in caplog.text
    assert INPUT_TEXT not in caplog.text


def test_unhandled_message_does_not_log_contents(routed_panel, caplog):
    instance, _, _ = routed_panel
    with caplog.at_level("DEBUG", logger="cxh.ctrl"):
        asyncio.run(dispatch_message(instance, INPUT_TEXT))
    assert "handler" in caplog.text
    assert INPUT_TEXT not in caplog.text


async def dispatch_timeout_form(instance):
    update = message_update(TIMEOUT_INPUT)
    query = CallbackQuery(id="test-callback", from_user=update.message.from_user,
                          chat_instance="test-chat", message=update.message, data=CX.pl_to)
    state = instance.dp.fsm.get_context(bot=instance.bot, chat_id=TEST_USER_ID,
                                        user_id=TEST_USER_ID)
    try:
        await instance.dp.feed_update(instance.bot, Update(update_id=2, callback_query=query))
        assert await state.get_state() == states.PduConnGrp.pdu_http_timeout.state
        await instance.dp.feed_update(instance.bot, update)
        assert await state.get_state() is None
    finally:
        await instance.bot.session.close()
        await instance.dp.storage.close()


def test_button_then_text_reaches_real_setting_handler(routed_panel, monkeypatch):
    instance, commands, plugin = routed_panel
    config = panel.cfg.read("config")
    config["account"] = {"timeout": 30}
    save = Mock()
    overlay = AsyncMock()
    greedy = AsyncMock(aiogram_flag={})
    monkeypatch.setattr(panel.cfg, "write", save)
    monkeypatch.setattr("ctrl.cmd.emit_overlay", overlay)
    monkeypatch.setattr(actions, "emit_overlay", overlay)
    commands.callback_query.register(actions.hx_047, F.data == CX.pl_to)
    commands.message.register(rx_029, states.PduConnGrp.pdu_http_timeout, F.text)
    plugin.message.register(greedy)
    plugin.callback_query.register(greedy)
    asyncio.run(dispatch_timeout_form(instance))
    assert config["account"]["timeout"] == int(TIMEOUT_INPUT)
    save.assert_called_once_with("config", config)
    assert overlay.await_count == 2
    greedy.assert_not_awaited()
