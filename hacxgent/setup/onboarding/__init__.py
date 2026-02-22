from __future__ import annotations

import sys

from rich import print as rprint
from textual.app import App

from hacxgent.core.paths.global_paths import GLOBAL_ENV_FILE
from hacxgent.setup.onboarding.screens import SetupScreen, WelcomeScreen


class OnboardingApp(App[str | None]):
    CSS_PATH = "onboarding.tcss"

    def on_mount(self) -> None:
        self.theme = "textual-ansi"

        self.install_screen(WelcomeScreen(), "welcome")
        self.install_screen(SetupScreen(), "setup")
        self.push_screen("welcome")


def run_onboarding(app: App | None = None) -> None:
    result = (app or OnboardingApp()).run()
    match result:
        case None:
            rprint("\n[yellow]Setup cancelled. See you next time![/]")
            sys.exit(0)
        case str() as s if s.startswith("save_error:"):
            err = s.removeprefix("save_error:")
            rprint(
                f"\n[yellow]Warning: Could not save settings to .env file: {err}[/]"
                "\n[dim]The settings are set for this session only. "
                f"You may need to set it manually in {GLOBAL_ENV_FILE.path}[/]\n"
            )
        case "completed":
            rprint(
                '\nSetup complete 🎉. Run "hacxgent" to start using the Hacxgent CLI.\n'
            )
