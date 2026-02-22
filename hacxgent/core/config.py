from __future__ import annotations

from collections.abc import MutableMapping
from enum import StrEnum, auto
import os
import json
from pathlib import Path
import re
import shlex
from typing import Annotated, Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_core import to_jsonable_python
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from hacxgent.core.paths.config_paths import CONFIG_DIR, CONFIG_FILE, PROMPTS_DIR
from hacxgent.core.paths.global_paths import (
    GLOBAL_ENV_FILE,
    GLOBAL_PROMPTS_DIR,
    SESSION_LOG_DIR,
)
from hacxgent.core.prompts import SystemPrompt
from hacxgent.core.tools.base import BaseToolConfig


def load_dotenv_values(
    env_path: Path = GLOBAL_ENV_FILE.path,
    environ: MutableMapping[str, str] = os.environ,
) -> None:
    if not env_path.is_file() and not env_path.is_fifo():
        return

    env_vars = dotenv_values(env_path)
    for key, value in env_vars.items():
        if not value:
            continue
        environ.update({key: value})


class MissingAPIKeyError(RuntimeError):
    def __init__(self, env_key: str, provider_name: str) -> None:
        super().__init__(
            f"Missing {env_key} environment variable for {provider_name} provider"
        )
        self.env_key = env_key
        self.provider_name = provider_name


class MissingPromptFileError(RuntimeError):
    def __init__(
        self, system_prompt_id: str, prompt_dir: str, global_prompt_dir: str
    ) -> None:
        extra_global_prompt_dir = (
            f" or {global_prompt_dir}" if global_prompt_dir != prompt_dir else ""
        )

        super().__init__(
            f"Invalid system_prompt_id value: '{system_prompt_id}'. "
            f"Must be one of the available prompts ({', '.join(f'{p.name.lower()}' for p in SystemPrompt)}), "
            f"or correspond to a .md file in {prompt_dir}{extra_global_prompt_dir}"
        )
        self.system_prompt_id = system_prompt_id
        self.prompt_dir = prompt_dir


class JsonFileSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self.json_data = self._load_json()

    def _load_json(self) -> dict[str, Any]:
        file = CONFIG_FILE.path
        try:
            with file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in {file}: {e}") from e
        except OSError as e:
            raise RuntimeError(f"Cannot read {file}: {e}") from e

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        return self.json_data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self.json_data


class ProjectContextConfig(BaseSettings):
    max_chars: int = 40_000
    default_commit_count: int = 5
    max_doc_bytes: int = 32 * 1024
    truncation_buffer: int = 1_000
    max_depth: int = 3
    max_files: int = 1000
    max_dirs_per_level: int = 20
    timeout_seconds: float = 2.0


class SessionLoggingConfig(BaseSettings):
    save_dir: str = ""
    session_prefix: str = "session"
    enabled: bool = True

    @field_validator("save_dir", mode="before")
    @classmethod
    def set_default_save_dir(cls, v: str) -> str:
        if not v:
            return str(SESSION_LOG_DIR.path)
        return v

    @field_validator("save_dir", mode="after")
    @classmethod
    def expand_save_dir(cls, v: str) -> str:
        return str(Path(v).expanduser().resolve())


class AnimationType(StrEnum):
    MATRIX = auto()
    CAT = auto()
    NONE = auto()


class Backend(StrEnum):
    HACXGENT = auto()
    GENERIC = auto()


class ProviderConfig(BaseModel):
    name: str
    api_base: str
    api_key_env_var: str = ""
    api_style: str = "openai"
    backend: Backend = Backend.GENERIC
    reasoning_field_name: str = "reasoning_content"


class _MCPBase(BaseModel):
    name: str = Field(description="Short alias used to prefix tool names")
    prompt: str | None = Field(
        default=None, description="Optional usage hint appended to tool descriptions"
    )
    startup_timeout_sec: float = Field(
        default=10.0,
        gt=0,
        description="Timeout in seconds for the server to start and initialize.",
    )
    tool_timeout_sec: float = Field(
        default=60.0, gt=0, description="Timeout in seconds for tool execution."
    )

    @field_validator("name", mode="after")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", v)
        normalized = normalized.strip("_-")
        return normalized[:256]


class _MCPHttpFields(BaseModel):
    url: str = Field(description="Base URL of the MCP HTTP server")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Additional HTTP headers when using 'http' transport (e.g., Authorization or X-API-Key)."
        ),
    )
    api_key_env: str = Field(
        default="",
        description=(
            "Environment variable name containing an API token to send for HTTP transport."
        ),
    )
    api_key_header: str = Field(
        default="Authorization",
        description=(
            "HTTP header name to carry the token when 'api_key_env' is set (e.g., 'Authorization' or 'X-API-Key')."
        ),
    )
    api_key_format: str = Field(
        default="Bearer {token}",
        description=(
            "Format string for the header value when 'api_key_env' is set. Use '{token}' placeholder."
        ),
    )

    def http_headers(self) -> dict[str, str]:
        hdrs = dict(self.headers or {})
        env_var = (self.api_key_env or "").strip()
        if env_var and (token := os.getenv(env_var)):
            target = (self.api_key_header or "").strip() or "Authorization"
            if not any(h.lower() == target.lower() for h in hdrs):
                try:
                    value = (self.api_key_format or "{token}").format(token=token)
                except Exception:
                    value = token
                hdrs[target] = value
        return hdrs


class MCPHttp(_MCPBase, _MCPHttpFields):
    transport: Literal["http"]


class MCPStreamableHttp(_MCPBase, _MCPHttpFields):
    transport: Literal["streamable-http"]


class MCPStdio(_MCPBase):
    transport: Literal["stdio"]
    command: str | list[str]
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set for the MCP server process.",
    )

    def argv(self) -> list[str]:
        base = (
            shlex.split(self.command)
            if isinstance(self.command, str)
            else list(self.command or [])
        )
        return [*base, *self.args] if self.args else base


MCPServer = Annotated[
    MCPHttp | MCPStreamableHttp | MCPStdio, Field(discriminator="transport")
]


class ModelConfig(BaseModel):
    name: str
    provider: str
    alias: str
    temperature: float = 0.2
    input_price: float = 0.0
    output_price: float = 0.0
    rate_limit_rpm: int = 0
    max_context_tokens: int = 0

    @model_validator(mode="before")
    @classmethod
    def _default_alias_to_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "alias" not in data or data["alias"] is None:
                data["alias"] = data.get("name")
        return data


class AnimationType(StrEnum):
    MATRIX = auto()
    CAT = auto()
    NONE = auto()


class HacxgentConfig(BaseSettings):
    active_model: str = ""
    animation: AnimationType = AnimationType.MATRIX
    vim_keybindings: bool = False
    disable_welcome_banner_animation: bool = False
    autocopy_to_clipboard: bool = True
    displayed_workdir: str = ""
    auto_compact_threshold: int = 200000
    memory_interval: int = 10
    memory_threshold: int = 1000
    context_warnings: bool = False
    auto_approve: bool = False
    system_prompt_id: str = "cli"
    include_commit_signature: bool = True
    include_model_info: bool = True
    include_project_context: bool = True
    include_prompt_detail: bool = True
    enable_update_checks: bool = False
    api_timeout: float = 720.0
    
    # UI Customization
    theme_color: str = "#00BFFF"  # Hacxgent Blue
    show_banner: bool = True
    auto_approve: bool = False
    system_prompt_id: str = "cli"
    include_commit_signature: bool = True
    include_model_info: bool = True
    include_project_context: bool = True
    include_prompt_detail: bool = True
    enable_update_checks: bool = False
    api_timeout: float = 720.0

    providers: list[ProviderConfig] = Field(default_factory=list)
    models: list[ModelConfig] = Field(default_factory=list)

    project_context: ProjectContextConfig = Field(default_factory=ProjectContextConfig)
    session_logging: SessionLoggingConfig = Field(default_factory=SessionLoggingConfig)
    tools: dict[str, BaseToolConfig] = Field(default_factory=dict)
    tool_paths: list[Path] = Field(default_factory=list)
    mcp_servers: list[MCPServer] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    agent_paths: list[Path] = Field(default_factory=list)
    enabled_agents: list[str] = Field(default_factory=list)
    disabled_agents: list[str] = Field(default_factory=list)
    skill_paths: list[Path] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    disabled_skills: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="HACXGENT_", case_sensitive=False, extra="ignore"
    )

    @property
    def system_prompt(self) -> str:
        try:
            return SystemPrompt[self.system_prompt_id.upper()].read()
        except KeyError:
            pass

        for current_prompt_dir in [PROMPTS_DIR.path, GLOBAL_PROMPTS_DIR.path]:
            custom_sp_path = (current_prompt_dir / self.system_prompt_id).with_suffix(
                ".md"
            )
            if custom_sp_path.is_file():
                return custom_sp_path.read_text()

        raise MissingPromptFileError(
            self.system_prompt_id, str(PROMPTS_DIR.path), str(GLOBAL_PROMPTS_DIR.path)
        )

    def get_active_model(self) -> ModelConfig:
        if not self.active_model and self.models:
            return self.models[0]
        for model in self.models:
            if model.alias == self.active_model:
                return model
        if not self.models:
            raise ValueError("No models configured.")
        raise ValueError(
            f"Active model '{self.active_model}' not found in configuration."
        )

    def get_provider_for_model(self, model: ModelConfig) -> ProviderConfig:
        for provider in self.providers:
            if provider.name == model.provider:
                return provider
        raise ValueError(
            f"Provider '{model.provider}' for model '{model.name}' not found in configuration."
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            JsonFileSettingsSource(settings_cls),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def _check_api_key(self) -> HacxgentConfig:
        active_model = self.get_active_model()
        provider = self.get_provider_for_model(active_model)
        api_key_env = provider.api_key_env_var
        if api_key_env and not os.getenv(api_key_env):
            raise MissingAPIKeyError(api_key_env, provider.name)
        return self

    @field_validator("tool_paths", mode="before")
    @classmethod
    def _expand_tool_paths(cls, v: Any) -> list[Path]:
        if not v:
            return []
        return [Path(p).expanduser().resolve() for p in v]

    @field_validator("skill_paths", mode="before")
    @classmethod
    def _expand_skill_paths(cls, v: Any) -> list[Path]:
        if not v:
            return []
        return [Path(p).expanduser().resolve() for p in v]

    @field_validator("tools", mode="before")
    @classmethod
    def _normalize_tool_configs(cls, v: Any) -> dict[str, BaseToolConfig]:
        if not isinstance(v, dict):
            return {}

        normalized: dict[str, BaseToolConfig] = {}
        for tool_name, tool_config in v.items():
            if isinstance(tool_config, BaseToolConfig):
                normalized[tool_name] = tool_config
            elif isinstance(tool_config, dict):
                normalized[tool_name] = BaseToolConfig.model_validate(tool_config)
            else:
                normalized[tool_name] = BaseToolConfig()

        return normalized

    @model_validator(mode="after")
    def _validate_model_uniqueness(self) -> HacxgentConfig:
        seen_aliases: set[str] = set()
        for model in self.models:
            if model.alias in seen_aliases:
                raise ValueError(
                    f"Duplicate model alias found: '{model.alias}'. Aliases must be unique."
                )
            seen_aliases.add(model.alias)
        return self

    @model_validator(mode="after")
    def _check_system_prompt(self) -> HacxgentConfig:
        _ = self.system_prompt
        return self

    @classmethod
    def save_updates(cls, updates: dict[str, Any]) -> None:
        CONFIG_DIR.path.mkdir(parents=True, exist_ok=True)
        current_config = JsonFileSettingsSource(cls).json_data

        def deep_merge(target: dict, source: dict) -> None:
            for key, value in source.items():
                if (
                    key in target
                    and isinstance(target.get(key), dict)
                    and isinstance(value, dict)
                ):
                    deep_merge(target[key], value)
                elif (
                    key in target
                    and isinstance(target.get(key), list)
                    and isinstance(value, list)
                ):
                    if key in {"providers", "models"}:
                        target[key] = value
                    else:
                        target[key] = list(set(value + target[key]))
                else:
                    target[key] = value

        deep_merge(current_config, updates)
        cls.dump_config(
            to_jsonable_python(current_config, exclude_none=True, fallback=str)
        )

    @classmethod
    def dump_config(cls, config: dict[str, Any]) -> None:
        with CONFIG_FILE.path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    @classmethod
    def load(cls, **overrides: Any) -> HacxgentConfig:
        return cls(**(overrides or {}))

    @classmethod
    def create_default(cls) -> dict[str, Any]:
        try:
            config = cls()
        except Exception:
            config = cls.model_construct()

        config_dict = config.model_dump(mode="json", exclude_none=True)

        from hacxgent.core.tools.manager import ToolManager

        tool_defaults = ToolManager.discover_tool_defaults()
        if tool_defaults:
            config_dict["tools"] = tool_defaults

        return config_dict
