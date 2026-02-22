from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from hacxgent import __version__
from hacxgent.cli.textual_ui.widgets.banner.matrix import MatrixRain
from hacxgent.cli.textual_ui.widgets.banner.cat import PetitChat
from hacxgent.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from hacxgent.core.config import HacxgentConfig, AnimationType
from hacxgent.core.skills.manager import SkillManager

# EASY EXTENSION: Add new animation classes here
ANIMATION_REGISTRY: dict[AnimationType, Type[Widget]] = {
    AnimationType.MATRIX: MatrixRain,
    AnimationType.CAT: PetitChat,
}

@dataclass
class BannerState:
    active_model: str = ""
    models_count: int = 0
    mcp_servers_count: int = 0
    skills_count: int = 0
    animation: AnimationType = AnimationType.MATRIX


class Banner(Static):
    state = reactive(BannerState(), init=False)

    def __init__(
        self, config: HacxgentConfig, skill_manager: SkillManager, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.can_focus = False
        self._initial_state = BannerState(
            active_model=config.active_model,
            models_count=len(config.models),
            mcp_servers_count=len(config.mcp_servers),
            skills_count=len(skill_manager.available_skills),
            animation=config.animation
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="banner-container"):
            # Dynamically yield the configured animation
            anim_class = ANIMATION_REGISTRY.get(self._initial_state.animation)
            if anim_class:
                # Standard sizing for animations
                yield anim_class(id="banner-animation")
            
            with Vertical(id="banner-info"):
                with Horizontal(classes="banner-line"):
                    yield NoMarkupStatic("Hacxgent", id="banner-brand")
                    yield NoMarkupStatic(" ", classes="banner-spacer")
                    yield NoMarkupStatic("v1 · ", classes="banner-meta")
                    yield NoMarkupStatic("", id="banner-model")
                with Horizontal(classes="banner-line"):
                    yield NoMarkupStatic("", id="banner-meta-counts")
                with Horizontal(classes="banner-line"):
                    yield NoMarkupStatic("Type ", classes="banner-meta")
                    yield NoMarkupStatic("/help", classes="banner-cmd")
                    yield NoMarkupStatic(" for more information", classes="banner-meta")

    def on_mount(self) -> None:
        self.state = self._initial_state

    def watch_state(self) -> None:
        self.query_one("#banner-model", NoMarkupStatic).update(self.state.active_model)
        self.query_one("#banner-meta-counts", NoMarkupStatic).update(
            self._format_meta_counts()
        )

    async def update_animation(self, animation: AnimationType) -> None:
        if self.state.animation == animation:
            return
        
        self.state.animation = animation
        
        try:
            old_anim = self.query_one("#banner-animation")
            await old_anim.remove()
        except Exception:
            pass
            
        anim_class = ANIMATION_REGISTRY.get(animation)
        if anim_class:
            container = self.query_one("#banner-container")
            await container.mount(anim_class(id="banner-animation"), before="#banner-info")

    def set_state(self, config: HacxgentConfig, skill_manager: SkillManager) -> None:
        self.state = BannerState(
            active_model=config.active_model,
            models_count=len(config.models),
            mcp_servers_count=len(config.mcp_servers),
            skills_count=len(skill_manager.available_skills),
            animation=config.animation
        )

    def _format_meta_counts(self) -> str:
        return (
            f"{self.state.models_count} model{'s' if self.state.models_count != 1 else ''}"
            f" · {self.state.mcp_servers_count} MCP server{'s' if self.state.mcp_servers_count != 1 else ''}"
            f" · {self.state.skills_count} skill{'s' if self.state.skills_count != 1 else ''}"
        )
