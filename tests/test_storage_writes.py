import json
from unittest.mock import Mock

import pytest

from lib import cfg as cfgmod
from lib import db as dbmod


def test_replace_retries_while_file_is_locked(monkeypatch, tmp_path):
    source, target = tmp_path / "new.tmp", tmp_path / "data.json"
    source.write_text("{}", encoding="utf-8")
    real_replace = cfgmod.os.replace
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked by antivirus")
        return real_replace(a, b)

    monkeypatch.setattr(cfgmod.os, "replace", flaky)
    monkeypatch.setattr("time.sleep", Mock())
    cfgmod.replace_with_retry(str(source), str(target))
    assert calls["n"] == 3 and target.exists()


def test_replace_gives_up_and_keeps_old_file(monkeypatch, tmp_path):
    target = tmp_path / "data.json"
    target.write_text('{"old": true}', encoding="utf-8")
    monkeypatch.setattr(cfgmod.os, "replace", Mock(side_effect=PermissionError("locked")))
    monkeypatch.setattr("time.sleep", Mock())
    with pytest.raises(PermissionError):
        cfgmod._save(str(target), {"new": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_config_and_state_writes_are_flushed_to_disk(monkeypatch, tmp_path):
    synced = []
    real_fsync = cfgmod.os.fsync
    monkeypatch.setattr(cfgmod.os, "fsync", lambda fd: synced.append(fd) or real_fsync(fd))
    cfgmod._save(str(tmp_path / "a.json"), [1])
    dbmod._write(str(tmp_path / "b.json"), [2])
    assert len(synced) == 2
    assert json.loads((tmp_path / "b.json").read_text(encoding="utf-8")) == [2]
