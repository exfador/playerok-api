from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

_LOG_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_LOG_DATE = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True, slots=True)
class CleanupConfig:
    data_dir_names: tuple[str, ...] = ("conf", "db", "storage", "logs")
    pycache_name: str = "__pycache__"


class ProjectScope:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def contains(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return resolved == self._root or self._root in resolved.parents


class LoggingBootstrap:
    _configured: ClassVar[bool] = False

    @classmethod
    def configure(cls, level: int = logging.INFO) -> logging.Logger:
        log = logging.getLogger("play.cleanup")
        if cls._configured:
            return log
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(fmt=_LOG_FMT, datefmt=_LOG_DATE))
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(h)
        root.setLevel(level)
        cls._configured = True
        return log


@dataclass
class CleanupReport:
    removed_data_dirs: list[str] = field(default_factory=list)
    removed_pycache_dirs: int = 0
    skipped_outside_root: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class LocalDataCleaner:
    def __init__(self, scope: ProjectScope, *, config: CleanupConfig | None = None, log: logging.Logger | None = None) -> None:
        self._scope = scope
        self._config = config or CleanupConfig()
        self._log = log or logging.getLogger("play.cleanup")

    def run(self) -> CleanupReport:
        report = CleanupReport()
        self._purge_data_directories(report)
        self._purge_pycache(report)
        self._summarize(report)
        return report

    def _purge_data_directories(self, report: CleanupReport) -> None:
        for name in self._config.data_dir_names:
            target = self._scope.root / name
            if not target.exists():
                continue
            if self._safe_remove_tree(target, report):
                report.removed_data_dirs.append(name)
                self._log.debug("Removed %s/", name)

    def _purge_pycache(self, report: CleanupReport) -> None:
        name = self._config.pycache_name
        roots = sorted((p for p in self._scope.root.rglob(name) if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
        for path in roots:
            if not self._safe_remove_tree(path, report):
                continue
            report.removed_pycache_dirs += 1
            try:
                rel = path.relative_to(self._scope.root)
            except ValueError:
                rel = path
            self._log.debug("Removed %s", rel)
        if report.removed_pycache_dirs:
            self._log.info("Removed %d %r directories.", report.removed_pycache_dirs, name)

    def _safe_remove_tree(self, path: Path, report: CleanupReport) -> bool:
        if not self._scope.contains(path):
            report.skipped_outside_root.append(str(path))
            self._log.warning("Skipped path outside project root (possible symlink): %s", path)
            return False
        try:
            shutil.rmtree(path, ignore_errors=False)
            return True
        except OSError as exc:
            msg = f"{path}: {exc}"
            report.errors.append(msg)
            self._log.error("Failed to remove tree: %s", msg)
            return False

    def _summarize(self, report: CleanupReport) -> None:
        root = self._scope.root
        leftover = [n for n in self._config.data_dir_names if (root / n).exists()]
        if leftover:
            self._log.warning("Data paths still on disk (skipped or failed): %s", ", ".join(leftover))
        if report.removed_data_dirs:
            self._log.info("Removed data directories: %s", ", ".join(report.removed_data_dirs))
        elif not report.removed_pycache_dirs and not leftover:
            dirs = "/".join(self._config.data_dir_names)
            self._log.info("No %s or %s trees required cleanup.", dirs, self._config.pycache_name)
        if report.errors:
            self._log.warning("Completed with %d error(s).", len(report.errors))


def main() -> int:
    log = LoggingBootstrap.configure(logging.INFO)
    root = Path(__file__).resolve().parent
    report = LocalDataCleaner(ProjectScope(root), log=log).run()
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
