from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest
import tomli_w

from tests.stubs.fake_backend import FakeBackend
from hacxgent.cli.textual_ui.app import CORE_VERSION, HacxgentApp
from hacxgent.core.agent_loop import AgentLoop
from hacxgent.core.agents.models import BuiltinAgentName
from hacxgent.core.config import SessionLoggingConfig, HacxgentConfig
from hacxgent.core.llm.types import BackendLike
from hacxgent.core.paths import global_paths
from hacxgent.core.paths.config_paths import unlock_config_paths


def get_base_config() -> dict[str, Any]:
    return {
        "active_model": "devstral-latest",
        "providers": [
            {
                "name": "hacxgent",
                "api_base": "https://api.hacxgent.ai/v1",
                "api_key_env_var": "MISTRAL_API_KEY",
                "backend": "hacxgent",
            }
        ],
        "models": [
            {
                "name": "hacxgent-cli-latest",
                "provider": "hacxgent",
                "alias": "devstral-latest",
            }
        ],
        "enable_auto_update": False,
    }


@pytest.fixture(autouse=True)
def tmp_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    tmp_working_directory = tmp_path_factory.mktemp("test_cwd")
    monkeypatch.chdir(tmp_working_directory)
    return tmp_working_directory


@pytest.fixture(autouse=True)
def config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    tmp_path = tmp_path_factory.mktemp("hacxgent")
    config_dir = tmp_path / ".hacxgent"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(tomli_w.dumps(get_base_config()), encoding="utf-8")

    monkeypatch.setattr(global_paths, "_DEFAULT_HACXGENT_HOME", config_dir)
    return config_dir


@pytest.fixture(autouse=True)
def _unlock_config_paths():
    unlock_config_paths()


@pytest.fixture(autouse=True)
def _mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "mock")


@pytest.fixture(autouse=True)
def _mock_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock platform to be Linux with /bin/sh shell for consistent test behavior.

    This ensures that platform-specific system prompt generation is consistent
    across all tests regardless of the actual platform running the tests.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/bin/sh")


@pytest.fixture
def hacxgent_app() -> HacxgentApp:
    return build_test_hacxgent_app()


@pytest.fixture
def agent_loop() -> AgentLoop:
    return build_test_agent_loop()


@pytest.fixture
def hacxgent_config() -> HacxgentConfig:
    return build_test_hacxgent_config()


def build_test_hacxgent_config(**kwargs) -> HacxgentConfig:
    session_logging = kwargs.pop("session_logging", None)
    resolved_session_logging = (
        SessionLoggingConfig(enabled=False)
        if session_logging is None
        else session_logging
    )
    enable_update_checks = kwargs.pop("enable_update_checks", None)
    resolved_enable_update_checks = (
        False if enable_update_checks is None else enable_update_checks
    )
    return HacxgentConfig(
        session_logging=resolved_session_logging,
        enable_update_checks=resolved_enable_update_checks,
        **kwargs,
    )


def build_test_agent_loop(
    *,
    config: HacxgentConfig | None = None,
    agent_name: str = BuiltinAgentName.DEFAULT,
    backend: BackendLike | None = None,
    enable_streaming: bool = False,
    **kwargs,
) -> AgentLoop:

    resolved_config = config or build_test_hacxgent_config()

    return AgentLoop(
        config=resolved_config,
        agent_name=agent_name,
        backend=backend or FakeBackend(),
        enable_streaming=enable_streaming,
        **kwargs,
    )


def build_test_hacxgent_app(
    *, config: HacxgentConfig | None = None, agent_loop: AgentLoop | None = None, **kwargs
) -> HacxgentApp:
    app_config = config or build_test_hacxgent_config()

    resolved_agent_loop = agent_loop or build_test_agent_loop(config=app_config)

    current_version = kwargs.pop("current_version", None)
    resolved_current_version = (
        CORE_VERSION if current_version is None else current_version
    )

    return HacxgentApp(
        agent_loop=resolved_agent_loop,
        current_version=resolved_current_version,
        initial_prompt=kwargs.pop("initial_prompt", None),
        **kwargs,
    )
