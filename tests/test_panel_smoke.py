import asyncio
import html
import inspect
import itertools
import logging
import re
from datetime import datetime, timezone

import pytest
from aiogram.client.session.base import BaseSession
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import ctrl
from ctrl import keys, panel
from ctrl import states as state_module
from ctrl.cb import CX
from ctrl.cmd import router as cmd_router
from lib import cfg as cfgmod
from lib import db as dbmod

TELEGRAM_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "tg-spoiler",
                 "span", "blockquote", "tg-emoji"}
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s[^<>]*)?)>")
_ENTITY = re.compile(r"&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);")


def telegram_html_problem(text):
    stack = []
    for match in _TAG.finditer(text):
        closing, tag = match.group(1), match.group(2).lower()
        if tag not in TELEGRAM_TAGS:
            return f"тег <{tag}> не поддерживается Telegram"
        if closing:
            if not stack or stack[-1] != tag:
                return f"закрывающий </{tag}> без пары"
            stack.pop()
        else:
            stack.append(tag)
    if stack:
        return f"незакрытый <{stack[-1]}>"
    rest = _TAG.sub("", text)
    if "<" in rest:
        return "неэкранированный <"
    if "&" in _ENTITY.sub("", rest):
        return "неэкранированный &"
    return None


ADMIN = 4242
BOT_ID = 123456
TOKEN = f"{BOT_ID}:local-smoke-token"
_ids = itertools.count(100)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.buttons = {}
        self.violations = []
        self.texts = []
        self.alerts = []

    def _check_limits(self, name, method):
        markup = getattr(method, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or []:
            for button in row:
                if button.callback_data and len(button.callback_data.encode()) > 64:
                    self.violations.append(f"{name}: callback_data > 64 байт: {button.callback_data!r}")
                if not (button.text or "").strip():
                    self.violations.append(f"{name}: кнопка без текста")
        text = getattr(method, "text", None) if name != "AnswerCallbackQuery" else None
        if text is None:
            text = getattr(method, "caption", None)
        if not isinstance(text, str):
            return
        if not text.strip():
            self.violations.append(f"{name}: пустой текст")
        parse_mode = getattr(method, "parse_mode", None)
        visible = text
        if parse_mode == "HTML":
            problem = telegram_html_problem(text)
            if problem:
                self.violations.append(f"{name}: {problem}: {text[:120]!r}")
            visible = html.unescape(re.sub(r"<[^>]+>", "", text))
        limit = 1024 if getattr(method, "caption", None) is not None else 4096
        if len(visible) > limit:
            self.violations.append(f"{name}: текст {len(visible)} > {limit} символов")

    async def close(self):
        return None

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.calls.append(name)
        self._check_limits(name, method)
        if name == "AnswerCallbackQuery" and getattr(method, "text", None):
            self.alerts.append(method.text)
        elif isinstance(getattr(method, "text", None), str):
            self.texts.append(method.text)
        markup = getattr(method, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or []:
            for button in row:
                if button.callback_data:
                    self.buttons.setdefault(button.callback_data, button.text)
        if name in {"SendMessage", "EditMessageText", "SendPhoto", "EditMessageMedia", "SendDocument",
                    "EditMessageReplyMarkup", "EditMessageCaption"}:
            return Message(message_id=getattr(method, "message_id", None) or next(_ids), date=datetime.now(timezone.utc),
                           chat=Chat(id=getattr(method, "chat_id", ADMIN) or ADMIN, type="private"),
                           from_user=User(id=BOT_ID, is_bot=True, first_name="bot"),
                           text=getattr(method, "text", None) or "ok")
        if name == "GetMe":
            return User(id=BOT_ID, is_bot=True, first_name="bot", username="smoke_bot")
        if name in {"GetChat", "GetFile"}:
            raise RuntimeError(f"{name} недоступен в тесте")
        return True


def _isolate_side_effects(monkeypatch, tmp_path):
    import os
    import subprocess
    import urllib.request

    import curl_cffi.requests
    import requests

    import ctrl.priority
    import lib.updater_apply as updater_apply
    import lib.util as util

    blocked = []

    def refuse(name):
        def handler(*args, **kwargs):
            blocked.append(name)
            raise RuntimeError(f"{name} заблокирован в тесте")
        return handler

    targets = [
        (updater_apply, "download_to_file"), (updater_apply, "extract_zip"), (updater_apply, "apply_update"),
        (updater_apply, "schedule_reboot"), (util, "reboot"), (ctrl.priority, "reboot"),
        (requests.sessions.Session, "request"), (curl_cffi.requests.Session, "request"),
        (urllib.request, "urlopen"), (subprocess, "Popen"), (subprocess, "call"), (subprocess, "run"),
        (os, "execv"), (os, "_exit"),
    ]
    for owner, attr in targets:
        monkeypatch.setattr(owner, attr, refuse(f"{getattr(owner, '__name__', owner)}.{attr}"))
    import ctrl.cmd
    import lib.ext

    monkeypatch.setattr(updater_apply, "project_root", lambda: str(tmp_path))
    monkeypatch.setattr(util, "project_root_dir", lambda: str(tmp_path))
    monkeypatch.setattr(util, "COOKIES_JSON_PATH", str(tmp_path / "conf" / "cookies.json"))
    monkeypatch.setattr(lib.ext, "ADDONS_DIR", str(tmp_path / "ext"))
    monkeypatch.setattr(ctrl.cmd, "ADDONS_DIR", str(tmp_path / "ext"))
    monkeypatch.chdir(tmp_path)
    return blocked


@pytest.fixture
def smoke_panel(monkeypatch, tmp_path):
    blocked = _isolate_side_effects(monkeypatch, tmp_path)
    for entry in list(cfgmod._STORE.values()):
        monkeypatch.setattr(entry, "path", str(tmp_path / "conf" / f"{entry.name}.json"))
    for entry in dbmod._ALL:
        monkeypatch.setattr(entry, "path", str(tmp_path / "db" / f"{entry.name}.json"))
    config = cfgmod.AppConf.read("config")
    config["bot"].update(token=TOKEN, admins=[ADMIN], password_hash="x")
    cfgmod.AppConf.write("config", config)
    for router in (ctrl.router, cmd_router):
        parent = router.parent_router
        if parent is not None:
            parent.sub_routers.remove(router)
            router._parent_router = None
    monkeypatch.setattr(panel, "_panel", None)
    monkeypatch.setattr(panel, "all_extensions", lambda: [])
    import bot.core as core
    monkeypatch.setattr(core, "live_bridge", lambda: None)
    instance = panel.Panel()
    session = FakeSession()
    session.blocked = blocked
    instance.bot.session = session
    yield instance, session
    for router in (ctrl.router, cmd_router):
        parent = router.parent_router
        if parent is not None:
            parent.sub_routers.remove(router)
            router._parent_router = None


def user():
    return User(id=ADMIN, is_bot=False, first_name="Admin")


def bot_message(message_id=None):
    return Message(message_id=message_id or next(_ids), date=datetime.now(timezone.utc), chat=Chat(id=ADMIN, type="private"),
                   from_user=User(id=BOT_ID, is_bot=True, first_name="bot"), text="screen")


def callback_update(data: str, message_id=None) -> Update:
    query = CallbackQuery(id=str(next(_ids)), from_user=user(), chat_instance="ci", message=bot_message(message_id), data=data)
    return Update(update_id=next(_ids), callback_query=query)


def text_update(text: str) -> Update:
    message = Message(message_id=next(_ids), date=datetime.now(timezone.utc), chat=Chat(id=ADMIN, type="private"),
                      from_user=user(), text=text)
    return Update(update_id=next(_ids), message=message)


SAMPLE_VALUES = {"to": ["index", "default", "auth", "proxy", "restore", "complete", "bump", "logger", "watermark",
                        "other", "updates", "profile", "logs", "settings"],
                 "do": ["tiers", "kis", "go", "keep", "clone", "clone_go", "remove", "remove_go", "unlock",
                        "send_mess", "tpl_list", "refund", "complete"],
                 "cmd_id": ["abc123", "x"], "message_id": ["first_message", "t_custom", "x"], "index": [0, 1, 9],
                 "page": [0, 1, 50]}

POPULATED = {
    "auto_deliveries": [
        {"keyphrases": ["ключ"], "piece": True, "goods": [f"code-{n}" for n in range(12)], "message": []},
        {"keyphrases": ["текст"], "piece": False, "goods": [], "message": ["Спасибо за покупку"]},
    ],
    "custom_commands": {"items": [{"id": "abc123", "trigger": "!вызвать", "events": [], "reply_lines": ["Скоро буду"]}]},
    "auto_restore_items": {"included": [["лот"], ["второй"]]},
    "auto_complete_deals": {"included": [["лот"]]},
    "auto_bump_items": {"included": [["лот"]], "excluded": [["искл"]]},
}
FSM_DATA = {"auto_delivery_index": 0, "auto_delivery_keys": ["ключ"], "message_id": "t_custom",
            "custom_cmd_id": "abc123", "last_page": 0, "username": "buyer", "deal_id": "deal-1"}


def populate():
    for name, value in POPULATED.items():
        cfgmod.AppConf.write(name, value)
    messages = cfgmod.AppConf.read("messages")
    messages["t_custom"] = {"enabled": True, "title": "Свой шаблон", "text": ["Привет, $buyer"]}
    cfgmod.AppConf.write("messages", messages)
    config = cfgmod.AppConf.read("config")
    config["features"].update(commands=True, deliveries=True)
    cfgmod.AppConf.write("config", config)


def sample_callbacks():
    out = []
    for name, cls in inspect.getmembers(keys, inspect.isclass):
        if not issubclass(cls, CallbackData) or cls is CallbackData:
            continue
        fields = cls.model_fields
        variants = []
        for field_name, info in fields.items():
            annotation = info.annotation
            if field_name in SAMPLE_VALUES:
                variants.append([(field_name, value) for value in SAMPLE_VALUES[field_name]])
            elif annotation is int or annotation == (int | None):
                variants.append([(field_name, 0)])
            elif annotation is bool:
                variants.append([(field_name, True), (field_name, False)])
            else:
                variants.append([(field_name, "x")])
        for combo in itertools.product(*variants) if variants else [()]:
            try:
                out.append((f"{name}{dict(combo)}", cls(**dict(combo)).pack()))
            except Exception:
                continue
    for name, value in vars(CX).items():
        if not name.startswith("_") and isinstance(value, str):
            out.append((f"CX.{name}", value))
    return out


def all_states():
    found = []
    for _, group in inspect.getmembers(state_module, inspect.isclass):
        if issubclass(group, StatesGroup) and group is not StatesGroup:
            found.extend(value.state for value in vars(group).values() if isinstance(value, State))
    return sorted(set(found))


async def feed(instance, update, state_name=None, data=None):
    state = instance.dp.fsm.get_context(bot=instance.bot, chat_id=ADMIN, user_id=ADMIN)
    await state.set_state(state_name)
    if data is not None:
        await state.set_data(dict(data))
    return await instance.dp.feed_update(instance.bot, update)


def run_all(instance, updates, data=None, before=None, silent=None):
    failures = []
    calls = instance.bot.session.calls

    async def go():
        for label, update, state_name in updates:
            if before is not None:
                before()
            seen = len(calls)
            try:
                result = await feed(instance, update, state_name, data)
            except Exception as exc:
                failures.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            if silent is not None and (result is UNHANDLED or len(calls) == seen):
                silent.append(label)
        await instance.dp.storage.close()

    logging.getLogger("cxh.ctrl").disabled = True
    try:
        asyncio.run(go())
    finally:
        logging.getLogger("cxh.ctrl").disabled = False
    return failures


def test_every_button_runs_without_crashing(smoke_panel):
    instance, session = smoke_panel
    updates = [(label, callback_update(data), None) for label, data in sample_callbacks()]
    assert len(updates) > 150
    failures = run_all(instance, updates)
    assert not failures, "\n".join(failures)
    assert session.calls.count("AnswerCallbackQuery") + session.calls.count("EditMessageText") > 0


def test_update_and_restart_never_reach_the_real_project(smoke_panel):
    instance, session = smoke_panel
    updates = [("sys_dl_do", callback_update(CX.sys_dl_do), None), ("/restart", text_update("/restart"), None)]
    failures = run_all(instance, updates)
    assert not failures, "\n".join(failures)
    assert "apply_update" not in " ".join(session.blocked)
    assert any(name.endswith("reboot") for name in session.blocked)


@pytest.mark.parametrize("tag, downloads", [("2.0.6", False), ("v2.1.0", False), ("9.9.9", True)])
def test_update_button_installs_only_newer_releases(smoke_panel, tag, downloads):
    instance, session = smoke_panel
    dbmod.AppDb.set("updater_state", {"latest_tag": tag, "latest_download_url": "https://example.invalid/r.zip"})
    failures = run_all(instance, [("sys_dl_do", callback_update(CX.sys_dl_do), None)])
    assert not failures, "\n".join(failures)
    assert any(name.endswith("download_to_file") for name in session.blocked) is downloads
    assert not any(name.endswith("apply_update") for name in session.blocked)


@pytest.mark.parametrize("text", ["test", "1", "0", "-5", "abc,def", "999999999"])
def test_every_input_state_accepts_any_text_without_crashing(smoke_panel, text):
    instance, _ = smoke_panel
    updates = [(f"{state}:{text}", text_update(text), state) for state in all_states()]
    assert len(updates) > 30
    failures = run_all(instance, updates)
    assert not failures, "\n".join(failures)


def test_every_button_survives_populated_settings(smoke_panel):
    instance, _ = smoke_panel
    updates = [(label, callback_update(data), None) for label, data in sample_callbacks()]
    failures = run_all(instance, updates, data=FSM_DATA, before=populate)
    assert not failures, "\n".join(failures)


def test_every_reachable_button_answers(smoke_panel):
    instance, session = smoke_panel
    populate()
    failures = run_all(instance, [("/start", text_update("/start"), None)])
    silent, visited = [], set()
    while len(visited) < 1500:
        pending = [data for data in session.buttons if data not in visited]
        if not pending:
            break
        visited.update(pending)
        updates = [(f"{session.buttons[data]} [{data}]", callback_update(data), None) for data in pending]
        failures += run_all(instance, updates, before=populate, silent=silent)
    assert len(visited) > 60
    assert not failures, "\n".join(failures)
    assert not silent, "Кнопки без ответа: " + ", ".join(silent)


@pytest.mark.parametrize("text", ["ключ, второй", "2", "0", "-1", "<b>x</b>", "a" * 5000])
def test_every_input_state_handles_text_with_populated_settings(smoke_panel, text):
    instance, _ = smoke_panel
    silent = []
    updates = [(f"{state}:{text[:20]}", text_update(text), state) for state in all_states()]
    failures = run_all(instance, updates, data=FSM_DATA, before=populate, silent=silent)
    assert not failures, "\n".join(failures)
    assert not silent, "Ввод без ответа: " + ", ".join(silent)


@pytest.mark.parametrize("command", ["/start", "/status", "/logs", "/logs 01.01.2026", "/logs bad"])
def test_admin_commands_work(smoke_panel, command):
    instance, session = smoke_panel
    failures = run_all(instance, [(command, text_update(command), None)])
    assert not failures, "\n".join(failures)
    assert "SendMessage" in session.calls or "EditMessageText" in session.calls
