import logging
import os
from types import SimpleNamespace

import pytest

from lib import util
from pok.feed import Feed


@pytest.mark.parametrize("name", ["pl.conn", "pl.feed", "pl.ctrl", "cxh.bot"])
def test_verbose_switch_controls_every_bot_logger(name):
    util.apply_verbose(False)
    assert logging.getLogger(name).level == logging.INFO
    util.apply_verbose(True)
    assert logging.getLogger(name).level == logging.DEBUG
    util.apply_verbose(False)


def test_order_pipeline_failures_are_visible_without_verbose(caplog):
    util.apply_verbose(False)
    feed = Feed(SimpleNamespace(id="user"))
    feed.q = None
    with caplog.at_level(logging.DEBUG, logger="pl.feed"):
        logging.getLogger("pl.feed").setLevel(logging.INFO)
        feed.process_ws_message('{"type": "next", "id": "x", "payload": {"data": {"chatUpdated": {"id": "c", "type": "PM"}}}}')
    assert any(r.levelno == logging.WARNING and "WebSocket" in r.getMessage() for r in caplog.records)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_log_files_are_private(tmp_path):
    handler = util._DateFolderFileHandler(str(tmp_path))
    try:
        day = next(p for p in tmp_path.iterdir() if p.is_dir())
        assert (tmp_path.stat().st_mode & 0o777) == 0o700
        assert ((day / "bot.log").stat().st_mode & 0o777) == 0o600
    finally:
        handler.close()
