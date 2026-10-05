import shutil
from pathlib import Path

import clean


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "conf").mkdir(parents=True)
    (root / "conf" / "config.json").write_text("{}", encoding="utf-8")
    (root / "pkg" / "__pycache__").mkdir(parents=True)
    shutil.copy(clean.__file__, root / "clean.py")
    return root


def test_clean_without_confirmation_keeps_data(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr(clean, "__file__", str(root / "clean.py"))
    assert clean.main([]) == 0
    assert (root / "conf" / "config.json").exists()
    assert (root / "pkg" / "__pycache__").exists()


def test_clean_with_confirmation_removes_project_data(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr(clean, "__file__", str(root / "clean.py"))
    assert clean.main(["--yes"]) == 0
    assert not (root / "conf").exists()
    assert not (root / "pkg" / "__pycache__").exists()
    assert (root / "pkg").exists()
