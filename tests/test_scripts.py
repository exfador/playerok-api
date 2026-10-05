import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@pytest.mark.parametrize("script", ["check-playerok.py", "check-websocket.py", "refresh-contracts.py"])
def test_documented_scripts_start_from_any_directory(script, tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"], cwd=tmp_path, env=ENV,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout


def test_clean_script_is_dry_run_by_default(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "clean.py")], cwd=tmp_path, env=ENV,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert "--yes" in result.stderr + result.stdout
