from __future__ import annotations

import os
from typing import ClassVar

from dotenv import set_key
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Vertical, ScrollableContainer
from textual.widgets import Input, Static, Label, Button

from hacxgent.core.config import HacxgentConfig, ProviderConfig, ModelConfig
from hacxgent.core.paths.global_paths import GLOBAL_ENV_FILE
from hacxgent.setup.onboarding.base import OnboardingScreen


def _save_to_env_file(env_key: str, api_key: str) -> None:
    GLOBAL_ENV_FILE.path.parent.mkdir(parents=True, exist_ok=True)
    set_key(GLOBAL_ENV_FILE.path, env_key, api_key)


class SetupScreen(OnboardingScreen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="setup-outer"):
            yield Static("Hacxgent Initialization", id="setup-title")
            
            yield Label("Provider Configuration", classes="section-label")
            yield Label("Provider Name (e.g. OpenAI, Anthropic):")
            yield Input(id="provider_name", placeholder="OpenAI")
            
            yield Label("API Base URL (for /chat/completions):")
            yield Input(id="api_base", placeholder="https://api.openai.com/v1")
            
            yield Label("API Key:")
            yield Input(id="api_key", password=True, placeholder="sk-...")
            
            yield Label("Model Configuration", classes="section-label")
            yield Label("Model Name (e.g. gpt-4o):")
            yield Input(id="model_name", placeholder="gpt-4o")
            
            yield Label("Model Alias (local name):")
            yield Input(id="model_alias", placeholder="default")

            yield Label("Advanced Settings", classes="section-label")
            yield Label("Rate Limit (Requests per Minute, 0 for none):")
            yield Input(id="rate_limit", placeholder="0")
            
            yield Label("Max Context Tokens (0 for model default):")
            yield Input(id="max_tokens", placeholder="0")

            yield Static("", id="setup-feedback")
            with Center():
                yield Button("Finish Setup", id="submit-btn", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#provider_name").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-btn":
            self.process_setup()

    def process_setup(self) -> None:
        provider_name = self.query_one("#provider_name", Input).value.strip() or "OpenAI"
        api_base = self.query_one("#api_base", Input).value.strip() or "https://api.openai.com/v1"
        api_key = self.query_one("#api_key", Input).value.strip()
        model_name = self.query_one("#model_name", Input).value.strip() or "gpt-4o"
        model_alias = self.query_one("#model_alias", Input).value.strip() or "default"
        rate_limit = self.query_one("#rate_limit", Input).value.strip() or "0"
        max_tokens = self.query_one("#max_tokens", Input).value.strip() or "0"

        if not api_key:
            self.query_one("#setup-feedback", Static).update("[red]API Key is required.[/]")
            return

        try:
            rl = int(rate_limit)
            mt = int(max_tokens)
        except ValueError:
            self.query_one("#setup-feedback", Static).update("[red]Rate limit and Max tokens must be numbers.[/]")
            return

        api_key_env = f"{provider_name.upper()}_API_KEY"

        # Create config
        provider = ProviderConfig(
            name=provider_name.lower(),
            api_base=api_base,
            api_key_env_var=api_key_env,
        )
        model = ModelConfig(
            name=model_name,
            provider=provider_name.lower(),
            alias=model_alias,
            rate_limit_rpm=rl,
            max_context_tokens=mt
        )

        updates = {
            "active_model": model_alias,
            "providers": [provider.model_dump()],
            "models": [model.model_dump()],
            "auto_compact_threshold": mt if mt > 0 else 200000
        }

        # Save updates to settings.json
        HacxgentConfig.save_updates(updates)

        # Save API key to .env
        os.environ[api_key_env] = api_key
        try:
            _save_to_env_file(api_key_env, api_key)
        except OSError as err:
            self.app.exit(f"save_error:{err}")
            return
        
        self.app.exit("completed")
