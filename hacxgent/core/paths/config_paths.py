from __future__ import annotations

from pathlib import Path
from typing import Literal

from hacxgent.core.paths.global_paths import HACXGENT_HOME, GlobalPath
from hacxgent.core.trusted_folders import trusted_folders_manager

_config_paths_locked: bool = True


class ConfigPath(GlobalPath):
    @property
    def path(self) -> Path:
        if _config_paths_locked:
            raise RuntimeError("Config path is locked")
        return super().path


def _resolve_config_path(basename: str, type: Literal["file", "dir"]) -> Path:
    cwd = Path.cwd()
    is_folder_trusted = trusted_folders_manager.is_trusted(cwd)
    if not is_folder_trusted:
        return HACXGENT_HOME.path / basename
    if type == "file":
        if (candidate := cwd / ".hacxgent" / basename).is_file():
            return candidate
    elif type == "dir":
        if (candidate := cwd / ".hacxgent" / basename).is_dir():
            return candidate
    return HACXGENT_HOME.path / basename


def resolve_local_tools_dir(dir: Path) -> Path | None:
    if not trusted_folders_manager.is_trusted(dir):
        return None
    if (candidate := dir / ".hacxgent" / "tools").is_dir():
        return candidate
    return None


def resolve_local_skills_dir(dir: Path) -> Path | None:
    if not trusted_folders_manager.is_trusted(dir):
        return None
    if (candidate := dir / ".hacxgent" / "skills").is_dir():
        return candidate
    return None


def resolve_local_agents_dir(dir: Path) -> Path | None:
    if not trusted_folders_manager.is_trusted(dir):
        return None
    if (candidate := dir / ".hacxgent" / "agents").is_dir():
        return candidate
    return None


def unlock_config_paths() -> None:
    global _config_paths_locked
    _config_paths_locked = False


CONFIG_FILE = ConfigPath(lambda: _resolve_config_path("settings.json", "file"))
CONFIG_DIR = ConfigPath(lambda: CONFIG_FILE.path.parent)
PROMPTS_DIR = ConfigPath(lambda: _resolve_config_path("prompts", "dir"))
HISTORY_FILE = ConfigPath(lambda: _resolve_config_path("hacxgenthistory", "file"))
