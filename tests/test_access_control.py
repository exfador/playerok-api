import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ctrl import access, panel
from ctrl.states import PduGateGrp, PduReplyDraftGrp


@pytest.fixture
def config(monkeypatch):
    store = {"config": {"bot": {"admins": [1, 2, 3], "password_hash": "old"}}}
    read = lambda name: copy.deepcopy(store[name])
    write = lambda name, value: store.__setitem__(name, copy.deepcopy(value))
    for module in (access, panel):
        monkeypatch.setattr(module.cfg, "read", read)
        monkeypatch.setattr(module.cfg, "write", write)
    monkeypatch.setattr(access, "emit_overlay", AsyncMock())
    return store


def message(uid, text):
    return SimpleNamespace(from_user=SimpleNamespace(id=uid), text=text, delete=AsyncMock(), chat=SimpleNamespace(id=uid))


@pytest.mark.parametrize("uid,text,state,allowed", [
    (1, "hello", None, True),
    (9, "/start", None, True),
    (9, "secret", PduGateGrp.pdu_gate_secret.state, True),
    (9, "сообщение покупателю", PduReplyDraftGrp.pdu_reply_body.state, False),
    (9, "просто текст", None, False),
])
def test_only_admins_reach_dialog_handlers(config, uid, text, state, allowed):
    assert panel._message_allowed(message(uid, text), uid, {"raw_state": state}) is allowed


def test_kick_keeps_only_current_admin(config):
    callback = SimpleNamespace(from_user=SimpleNamespace(id=2), bot=SimpleNamespace(get_chat=AsyncMock(side_effect=RuntimeError)),
                               message=SimpleNamespace(message_id=5), answer=AsyncMock())
    state = SimpleNamespace(set_state=AsyncMock())
    asyncio.run(access.on_kick(callback, state))
    assert config["config"]["bot"]["admins"] == [2]


def test_weak_password_is_rejected_and_message_deleted(config):
    msg = message(1, "123456")
    asyncio.run(access.on_password(msg, SimpleNamespace(set_state=AsyncMock())))
    msg.delete.assert_awaited()
    assert config["config"]["bot"]["password_hash"] == "old"
    assert config["config"]["bot"]["admins"] == [1, 2, 3]


def test_new_password_revokes_other_admins(config, monkeypatch):
    monkeypatch.setattr(access, "hash_password", lambda value: f"hashed:{value}")
    msg = message(3, "NewPassw0rd!")
    asyncio.run(access.on_password(msg, SimpleNamespace(set_state=AsyncMock())))
    assert config["config"]["bot"]["password_hash"] == "hashed:NewPassw0rd!"
    assert config["config"]["bot"]["admins"] == [3]
    msg.delete.assert_awaited()
