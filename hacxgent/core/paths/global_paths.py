from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from hacxgent import HACXGENT_ROOT


class GlobalPath:
    def __init__(self, resolver: Callable[[], Path]) -> None:
        self._resolver = resolver

    @property
    def path(self) -> Path:
        return self._resolver()


_DEFAULT_HACXGENT_HOME = Path.home() / ".hacxgent"


def _get_hacxgent_home() -> Path:
    if hacxgent_home := os.getenv("HACXGENT_HOME"):
        return Path(hacxgent_home).expanduser().resolve()
    return _DEFAULT_HACXGENT_HOME


HACXGENT_HOME = GlobalPath(_get_hacxgent_home)
GLOBAL_CONFIG_FILE = GlobalPath(lambda: HACXGENT_HOME.path / "settings.json")
GLOBAL_ENV_FILE = GlobalPath(lambda: HACXGENT_HOME.path / ".env")
GLOBAL_TOOLS_DIR = GlobalPath(lambda: HACXGENT_HOME.path / "tools")
GLOBAL_SKILLS_DIR = GlobalPath(lambda: HACXGENT_HOME.path / "skills")
GLOBAL_AGENTS_DIR = GlobalPath(lambda: HACXGENT_HOME.path / "agents")
GLOBAL_PROMPTS_DIR = GlobalPath(lambda: HACXGENT_HOME.path / "prompts")
SESSION_LOG_DIR = GlobalPath(lambda: HACXGENT_HOME.path / "logs" / "session")
TRUSTED_FOLDERS_FILE = GlobalPath(lambda: HACXGENT_HOME.path / "trusted_folders.toml")
LOG_DIR = GlobalPath(lambda: HACXGENT_HOME.path / "logs")
LOG_FILE = GlobalPath(lambda: HACXGENT_HOME.path / "hacxgent.log")

DEFAULT_TOOL_DIR = GlobalPath(lambda: HACXGENT_ROOT / "core" / "tools" / "builtins")
