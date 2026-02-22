from __future__ import annotations

import asyncio
import webbrowser
from enum import StrEnum, auto
from pathlib import Path
import subprocess
import time
from typing import Any, ClassVar, assert_never, cast
from weakref import WeakKeyDictionary

from pydantic import BaseModel
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalGroup, VerticalScroll
from textual.events import AppBlur, AppFocus, MouseUp
from textual.widget import Widget
from textual.widgets import Static

from hacxgent import __version__ as CORE_VERSION
from hacxgent.cli.clipboard import copy_selection_to_clipboard
from hacxgent.cli.commands import CommandRegistry
from hacxgent.cli.terminal_setup import setup_terminal
from hacxgent.cli.textual_ui.handlers.event_handler import EventHandler
from hacxgent.cli.textual_ui.widgets.approval_app import ApprovalApp
from hacxgent.cli.textual_ui.widgets.banner.banner import Banner
from hacxgent.cli.textual_ui.widgets.chat_input import ChatInputContainer
from hacxgent.cli.textual_ui.widgets.compact import CompactMessage
from hacxgent.cli.textual_ui.widgets.config_app import ConfigApp
from hacxgent.cli.textual_ui.widgets.context_progress import ContextProgress, TokenState
from hacxgent.cli.textual_ui.widgets.load_more import HistoryLoadMoreRequested
from hacxgent.cli.textual_ui.widgets.loading import LoadingWidget, paused_timer
from hacxgent.cli.textual_ui.widgets.messages import (
    AssistantMessage,
    BashOutputMessage,
    ErrorMessage,
    InterruptMessage,
    ReasoningMessage,
    StreamingMessageBase,
    UserCommandMessage,
    UserMessage,
    WarningMessage,
)
from hacxgent.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from hacxgent.cli.textual_ui.widgets.path_display import PathDisplay
from hacxgent.cli.textual_ui.widgets.question_app import QuestionApp
from hacxgent.cli.textual_ui.widgets.tools import ToolCallMessage, ToolResultMessage
from hacxgent.cli.textual_ui.windowing import (
    HISTORY_RESUME_TAIL_MESSAGES,
    LOAD_MORE_BATCH_SIZE,
    HistoryLoadMoreManager,
    SessionWindowing,
    build_history_widgets,
    create_resume_plan,
    non_system_history_messages,
    should_resume_history,
    sync_backfill_state,
)
from hacxgent.core.agent_loop import AgentLoop
from hacxgent.core.agents import AgentProfile
from hacxgent.core.autocompletion.path_prompt_adapter import render_path_prompt
from hacxgent.core.config import HacxgentConfig, AnimationType
from hacxgent.core.paths.config_paths import HISTORY_FILE, CONFIG_FILE
from hacxgent.core.session.session_loader import SessionLoader
from hacxgent.core.tools.base import ToolPermission
from hacxgent.core.tools.builtins.ask_user_question import (
    AskUserQuestionArgs,
    AskUserQuestionResult,
)
from hacxgent.core.types import (
    AgentStats,
    ApprovalResponse,
    LLMMessage,
    RateLimitError,
    Role,
)
from hacxgent.core.utils import (
    CancellationReason,
    get_user_cancellation_message,
    is_dangerous_directory,
    logger,
)


class BottomApp(StrEnum):
    """Bottom panel app types.

    Convention: Each value must match the widget class name with "App" suffix removed.
    E.g., ApprovalApp -> Approval, ConfigApp -> Config, QuestionApp -> Question.
    This allows dynamic lookup via: BottomApp[type(widget).__name__.removesuffix("App")]
    """

    Approval = auto()
    Config = auto()
    Input = auto()
    Question = auto()


class ChatScroll(VerticalScroll):
    """Optimized scroll container that skips cascading style recalculations."""

    def update_node_styles(self, animate: bool = True) -> None:
        pass


PRUNE_LOW_MARK = 1000
PRUNE_HIGH_MARK = 1500


async def prune_by_height(messages_area: Widget, low_mark: int, high_mark: int) -> bool:
    """Remove older children to keep virtual height within bounds."""
    height = messages_area.virtual_size.height
    if height <= high_mark:
        return False
    prune_children: list[Widget] = []
    bottom_margin = 0
    prune_height = 0
    for child in messages_area.children:
        if not child.display:
            prune_children.append(child)
            continue
        top, _, bottom, _ = child.styles.margin
        child_height = child.outer_size.height
        prune_height = (
            (prune_height - bottom_margin + max(bottom_margin, top))
            + bottom
            + child_height
        )
        bottom_margin = bottom
        if height - prune_height <= low_mark:
            break
        prune_children.append(child)
    if prune_children:
        await messages_area.remove_children(prune_children)
    return bool(prune_children)


class HacxgentApp(App):  # noqa: PLR0904
    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "app.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "clear_quit", "Quit", show=False),
        Binding("ctrl+d", "force_quit", "Quit", show=False, priority=True),
        Binding("escape", "interrupt", "Interrupt", show=False, priority=True),
        Binding("ctrl+o", "toggle_tool", "Toggle Tool", show=False),
        Binding("ctrl+y", "copy_selection", "Copy", show=False, priority=True),
        Binding("ctrl+shift+c", "copy_selection", "Copy", show=False, priority=True),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
        Binding("shift+up", "scroll_chat_up", "Scroll Up", show=False, priority=True),
        Binding(
            "shift+down", "scroll_chat_down", "Scroll Down", show=False, priority=True
        ),
    ]

    def __init__(
        self,
        agent_loop: AgentLoop,
        initial_prompt: str | None = None,
        current_version: str = CORE_VERSION,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.agent_loop = agent_loop
        self._agent_running = False
        self._interrupt_requested = False
        self._agent_task: asyncio.Task | None = None

        self._loading_widget: LoadingWidget | None = None
        self._pending_approval: asyncio.Future | None = None
        self._pending_question: asyncio.Future | None = None

        self.event_handler: EventHandler | None = None

        self.commands = CommandRegistry()

        self._chat_input_container: ChatInputContainer | None = None
        self._current_bottom_app: BottomApp = BottomApp.Input

        self.history_file = HISTORY_FILE.path

        self._tools_collapsed = True
        self._current_streaming_message: AssistantMessage | None = None
        self._current_streaming_reasoning: ReasoningMessage | None = None
        self._windowing = SessionWindowing(load_more_batch_size=LOAD_MORE_BATCH_SIZE)
        self._load_more = HistoryLoadMoreManager()
        self._tool_call_map: dict[str, str] | None = None
        self._history_widget_indices: WeakKeyDictionary[Widget, int] = (
            WeakKeyDictionary()
        )
        self._current_version = current_version
        self._initial_prompt = initial_prompt
        self._auto_scroll = True
        self._last_escape_time: float | None = None
        self._banner: Banner | None = None
        self._cached_messages_area: Widget | None = None
        self._cached_chat: ChatScroll | None = None
        self._cached_loading_area: Widget | None = None

    @property
    def config(self) -> HacxgentConfig:
        return self.agent_loop.config

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat"):
            self._banner = Banner(self.config, self.agent_loop.skill_manager)
            yield self._banner
            yield VerticalGroup(id="messages")

        with Horizontal(id="loading-area"):
            yield Static(id="loading-area-content")

        with Static(id="bottom-app-container"):
            yield ChatInputContainer(
                history_file=self.history_file,
                command_registry=self.commands,
                id="input-container",
                safety=self.agent_loop.agent_profile.safety,
                agent_name=self.agent_loop.agent_profile.display_name.lower(),
                skill_entries_getter=self._get_skill_entries,
            )

        with Horizontal(id="bottom-bar"):
            yield PathDisplay(self.config.displayed_workdir or Path.cwd())
            yield NoMarkupStatic(id="spacer")
            yield ContextProgress()

    async def on_mount(self) -> None:
        self.theme = "textual-ansi"

        self._cached_messages_area = self.query_one("#messages")
        self._cached_chat = self.query_one("#chat", ChatScroll)
        self._cached_loading_area = self.query_one("#loading-area-content")

        self.event_handler = EventHandler(
            mount_callback=self._mount_and_scroll,
            scroll_callback=self._scroll_to_bottom_deferred,
            get_tools_collapsed=lambda: self._tools_collapsed,
        )

        self._chat_input_container = self.query_one(ChatInputContainer)
        context_progress = self.query_one(ContextProgress)

        def update_context_progress(stats: AgentStats) -> None:
            active_model = self.config.get_active_model()
            max_tokens = active_model.max_context_tokens if active_model.max_context_tokens > 0 else self.config.auto_compact_threshold
            context_progress.tokens = TokenState(
                max_tokens=max_tokens,
                current_tokens=stats.context_tokens,
            )

        self.agent_loop.stats.add_listener("context_tokens", update_context_progress)
        self.agent_loop.stats.trigger_listeners()

        self.agent_loop.set_approval_callback(self._approval_callback)
        self.agent_loop.set_user_input_callback(self._user_input_callback)
        self._refresh_profile_widgets()

        chat_input_container = self.query_one(ChatInputContainer)
        chat_input_container.focus_input()
        await self._show_dangerous_directory_warning()
        await self._resume_history_from_messages()

        if self._initial_prompt:
            self.call_after_refresh(self._process_initial_prompt)

    def _process_initial_prompt(self) -> None:
        if self._initial_prompt:
            self.run_worker(
                self._handle_user_message(self._initial_prompt), exclusive=False
            )

    async def on_chat_input_container_submitted(
        self, event: ChatInputContainer.Submitted
    ) -> None:
        value = event.value.strip()
        if not value:
            return

        input_widget = self.query_one(ChatInputContainer)
        input_widget.value = ""

        if self._agent_running:
            await self._interrupt_agent_loop()

        if value.startswith("!"):
            await self._handle_bash_command(value[1:])
            return

        if await self._handle_command(value):
            return

        if await self._handle_skill(value):
            return

        await self._handle_user_message(value)

    async def on_approval_app_approval_granted(
        self, message: ApprovalApp.ApprovalGranted
    ) -> None:
        if self._pending_approval and not self._pending_approval.done():
            self._pending_approval.set_result((ApprovalResponse.YES, None))

        await self._switch_to_input_app()

    async def on_approval_app_approval_granted_always_tool(
        self, message: ApprovalApp.ApprovalGrantedAlwaysTool
    ) -> None:
        self._set_tool_permission_always(
            message.tool_name, save_permanently=message.save_permanently
        )

        if self._pending_approval and not self._pending_approval.done():
            self._pending_approval.set_result((ApprovalResponse.YES, None))

        await self._switch_to_input_app()

    async def on_approval_app_approval_rejected(
        self, message: ApprovalApp.ApprovalRejected
    ) -> None:
        if self._pending_approval and not self._pending_approval.done():
            feedback = str(
                get_user_cancellation_message(CancellationReason.OPERATION_CANCELLED)
            )
            self._pending_approval.set_result((ApprovalResponse.NO, feedback))

        await self._switch_to_input_app()

        if self._loading_widget and self._loading_widget.parent:
            await self._remove_loading_widget()

    async def on_question_app_answered(self, message: QuestionApp.Answered) -> None:
        if self._pending_question and not self._pending_question.done():
            result = AskUserQuestionResult(answers=message.answers, cancelled=False)
            self._pending_question.set_result(result)

        await self._switch_to_input_app()

    async def on_question_app_cancelled(self, message: QuestionApp.Cancelled) -> None:
        if self._pending_question and not self._pending_question.done():
            result = AskUserQuestionResult(answers=[], cancelled=True)
            self._pending_question.set_result(result)

        await self._switch_to_input_app()
        await self._interrupt_agent_loop()

    async def _remove_loading_widget(self) -> None:
        if self._loading_widget and self._loading_widget.parent:
            await self._loading_widget.remove()
            self._loading_widget = None

    async def on_config_app_config_closed(
        self, message: ConfigApp.ConfigClosed
    ) -> None:
        if message.changes:
            HacxgentConfig.save_updates(message.changes)
            await self._reload_config()
        else:
            await self._mount_and_scroll(
                UserCommandMessage("Configuration closed (no changes saved).")
            )

        await self._switch_to_input_app()

    async def on_compact_message_completed(
        self, message: CompactMessage.Completed
    ) -> None:
        messages_area = self._cached_messages_area or self.query_one("#messages")
        children = list(messages_area.children)

        try:
            compact_index = children.index(message.compact_widget)
        except ValueError:
            return

        if compact_index == 0:
            return

        with self.batch_update():
            for widget in children[:compact_index]:
                await widget.remove()

    def _set_tool_permission_always(
        self, tool_name: str, save_permanently: bool = False
    ) -> None:
        self.agent_loop.set_tool_permission(
            tool_name, ToolPermission.ALWAYS, save_permanently
        )

    async def _handle_command(self, user_input: str) -> bool:
        if command := self.commands.find_command(user_input):
            await self._mount_and_scroll(UserMessage(user_input))
            handler = getattr(self, command.handler)
            if asyncio.iscoroutinefunction(handler):
                await handler(user_input)
            else:
                handler(user_input)
            return True
        return False

    def _get_skill_entries(self) -> list[tuple[str, str]]:
        if not self.agent_loop:
            return []
        return [
            (f"/{name}", info.description)
            for name, info in self.agent_loop.skill_manager.available_skills.items()
            if info.user_invocable
        ]

    async def _handle_skill(self, user_input: str) -> bool:
        if not user_input.startswith("/"):
            return False

        if not self.agent_loop:
            return False

        skill_name = user_input[1:].strip().lower()
        skill_info = self.agent_loop.skill_manager.get_skill(skill_name)
        if not skill_info:
            return False

        try:
            skill_content = skill_info.skill_path.read_text(encoding="utf-8")
        except OSError as e:
            await self._mount_and_scroll(
                ErrorMessage(
                    f"Failed to read skill file: {e}", collapsed=self._tools_collapsed
                )
            )
            return True

        await self._handle_user_message(skill_content)
        return True

    async def _handle_bash_command(self, command: str) -> None:
        if not command:
            await self._mount_and_scroll(
                ErrorMessage(
                    "No command provided after '!'", collapsed=self._tools_collapsed
                )
            )
            return

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=False, timeout=30
            )
            stdout = (
                result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            )
            stderr = (
                result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            )
            output = stdout or stderr or "(no output)"
            exit_code = result.returncode
            await self._mount_and_scroll(
                BashOutputMessage(command, str(Path.cwd()), output, exit_code)
            )
        except subprocess.TimeoutExpired:
            await self._mount_and_scroll(
                ErrorMessage(
                    "Command timed out after 30 seconds",
                    collapsed=self._tools_collapsed,
                )
            )
        except Exception as e:
            await self._mount_and_scroll(
                ErrorMessage(f"Command failed: {e}", collapsed=self._tools_collapsed)
            )

    async def _handle_user_message(self, message: str) -> None:
        user_message = UserMessage(message)

        await self._mount_and_scroll(user_message)

        if not self._agent_running:
            self._agent_task = asyncio.create_task(
                self._handle_agent_loop_turn(message)
            )

    async def _resume_history_from_messages(self) -> None:
        messages_area = self._cached_messages_area or self.query_one("#messages")
        if not should_resume_history(list(messages_area.children)):
            return

        self._windowing.reset()
        history_messages = non_system_history_messages(self.agent_loop.messages)
        if (
            plan := create_resume_plan(history_messages, HISTORY_RESUME_TAIL_MESSAGES)
        ) is None:
            return
        await self._mount_history_batch(
            plan.tail_messages,
            messages_area,
            plan.tool_call_map,
            start_index=plan.tail_start_index,
        )
        self.call_after_refresh(
            lambda: self._align_chat_after_history_rebuild(plan.has_backfill)
        )
        self._tool_call_map = plan.tool_call_map
        self._windowing.set_backfill(plan.backfill_messages)
        await self._load_more.set_visible(
            messages_area,
            visible=self._windowing.has_backfill,
            remaining=self._windowing.remaining,
        )

    async def _mount_history_batch(
        self,
        batch: list[LLMMessage],
        messages_area: Widget,
        tool_call_map: dict[str, str],
        *,
        start_index: int,
        before: Widget | int | None = None,
        after: Widget | None = None,
    ) -> None:
        widgets = build_history_widgets(
            batch=batch,
            tool_call_map=tool_call_map,
            start_index=start_index,
            tools_collapsed=self._tools_collapsed,
            history_widget_indices=self._history_widget_indices,
        )

        with self.batch_update():
            if not widgets:
                return
            if before is not None:
                await messages_area.mount_all(widgets, before=before)
                return
            if after is not None:
                await messages_area.mount_all(widgets, after=after)
                return
            await messages_area.mount_all(widgets)

    def _is_tool_enabled_in_main_agent(self, tool: str) -> bool:
        return tool in self.agent_loop.tool_manager.available_tools

    async def _approval_callback(
        self, tool: str, args: BaseModel, tool_call_id: str
    ) -> tuple[ApprovalResponse, str | None]:
        if self.agent_loop and self.agent_loop.config.auto_approve:
            if self._is_tool_enabled_in_main_agent(tool):
                return (ApprovalResponse.YES, None)

        self._pending_approval = asyncio.Future()
        with paused_timer(self._loading_widget):
            await self._switch_to_approval_app(tool, args)
            result = await self._pending_approval

        self._pending_approval = None
        return result

    async def _user_input_callback(self, args: BaseModel) -> BaseModel:
        self._pending_question = asyncio.Future()
        with paused_timer(self._loading_widget):
            await self._switch_to_question_app(args)
            result = await self._pending_question

        self._pending_question = None
        return result

    async def _handle_agent_loop_turn(self, prompt: str) -> None:
        self._agent_running = True

        loading_area = self._cached_loading_area or self.query_one(
            "#loading-area-content"
        )

        loading = LoadingWidget()
        self._loading_widget = loading
        await loading_area.mount(loading)

        try:
            rendered_prompt = render_path_prompt(prompt, base_dir=Path.cwd())
            async for event in self.agent_loop.act(rendered_prompt):
                if self.event_handler:
                    await self.event_handler.handle_event(
                        event,
                        loading_active=self._loading_widget is not None,
                        loading_widget=self._loading_widget,
                    )

        except asyncio.CancelledError:
            if self._loading_widget and self._loading_widget.parent:
                await self._loading_widget.remove()
            if self.event_handler:
                self.event_handler.stop_current_tool_call(success=False)
            raise
        except Exception as e:
            if self._loading_widget and self._loading_widget.parent:
                await self._loading_widget.remove()
            if self.event_handler:
                self.event_handler.stop_current_tool_call(success=False)

            message = str(e)
            if isinstance(e, RateLimitError):
                message = "Rate limits exceeded. Please wait a moment before trying again."

            await self._mount_and_scroll(
                ErrorMessage(message, collapsed=self._tools_collapsed)
            )
        finally:
            self._agent_running = False
            self._interrupt_requested = False
            self._agent_task = None
            if self._loading_widget:
                await self._loading_widget.remove()
            self._loading_widget = None
            await self._finalize_current_streaming_message()
            await self._refresh_windowing_from_history()

    async def _interrupt_agent_loop(self) -> None:
        if not self._agent_running or self._interrupt_requested:
            return

        self._interrupt_requested = True

        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            try:
                await self._agent_task
            except asyncio.CancelledError:
                pass

        if self.event_handler:
            self.event_handler.stop_current_tool_call(success=False)
            self.event_handler.stop_current_compact()

        self._agent_running = False
        loading_area = self._cached_loading_area or self.query_one(
            "#loading-area-content"
        )
        await loading_area.remove_children()
        self._loading_widget = None

        await self._finalize_current_streaming_message()
        await self._mount_and_scroll(InterruptMessage())

        self._interrupt_requested = False

    async def _show_help(self, user_input: str | None = None) -> None:
        help_text = self.commands.get_help_text()
        await self._mount_and_scroll(UserCommandMessage(help_text))

    async def _show_status(self, user_input: str | None = None) -> None:
        stats = self.agent_loop.stats
        status_text = f"""## Agent Statistics

- **Steps**: {stats.steps:,}
- **Session Prompt Tokens**: {stats.session_prompt_tokens:,}
- **Session Completion Tokens**: {stats.session_completion_tokens:,}
- **Session Total LLM Tokens**: {stats.session_total_llm_tokens:,}
- **Last Turn Tokens**: {stats.last_turn_total_tokens:,}
- **Cost**: ${stats.session_cost:.4f}
"""
        await self._mount_and_scroll(UserCommandMessage(status_text))

    async def _run_setup_cmd(self, user_input: str | None = None) -> None:
        from hacxgent.setup.onboarding import run_onboarding
        await self._mount_and_scroll(UserCommandMessage("Opening setup..."))
        self.exit(result="run_setup")

    async def _open_settings_json(self, user_input: str | None = None) -> None:
        import os
        settings_path = CONFIG_FILE.path
        await self._mount_and_scroll(UserCommandMessage(f"Opening [bold]{settings_path}[/]..."))
        try:
            if os.name == 'nt':
                os.startfile(settings_path)
            else:
                import subprocess
                subprocess.run(['xdg-open', str(settings_path)], check=False)
        except Exception as e:
            await self._mount_and_scroll(ErrorMessage(f"Could not open settings: {e}"))

    async def _change_animation(self, user_input: str | None = None) -> None:
        current = self.config.animation
        options = list(AnimationType)
        next_idx = (options.index(current) + 1) % len(options)
        new_anim = options[next_idx]
        
        HacxgentConfig.save_updates({"animation": new_anim.value})
        self.config.animation = new_anim
        
        if self._banner:
            await self._banner.update_animation(new_anim)
            await self._mount_and_scroll(UserCommandMessage(f"Animation updated to: [bold]{new_anim.value.upper()}[/]"))

    async def _handle_memory_cmd(self, user_input: str) -> None:
        parts = user_input.split()
        
        if len(parts) < 2:
            status = self._get_memory_status()
            await self._mount_and_scroll(UserCommandMessage(status))
            return

        subcmd = parts[1].lower()
        if subcmd == "status":
            await self._mount_and_scroll(UserCommandMessage(self._get_memory_status()))
        elif subcmd == "interval" and len(parts) > 2:
            try:
                val = int(parts[2])
                HacxgentConfig.save_updates({"memory_interval": val})
                self.config.memory_interval = val
                for mw in self.agent_loop.middleware_pipeline.middlewares:
                    if hasattr(mw, "interval"):
                        mw.interval = val
                await self._mount_and_scroll(UserCommandMessage(f"Memory interval updated to: [bold]{val}[/] turns."))
            except ValueError:
                await self._mount_and_scroll(ErrorMessage("Invalid interval. Please provide a number."))
        elif subcmd == "threshold" and len(parts) > 2:
            try:
                val = int(parts[2])
                HacxgentConfig.save_updates({"memory_threshold": val})
                self.config.memory_threshold = val
                for mw in self.agent_loop.middleware_pipeline.middlewares:
                    if hasattr(mw, "threshold"):
                        mw.threshold = val
                await self._mount_and_scroll(UserCommandMessage(f"Memory threshold updated to: [bold]{val}[/] characters."))
            except ValueError:
                await self._mount_and_scroll(ErrorMessage("Invalid threshold. Please provide a number."))
        else:
            await self._mount_and_scroll(UserCommandMessage("Usage: `/memory [status|interval <n>|threshold <n>]`"))

    def _get_memory_status(self) -> str:
        interval = getattr(self.config, "memory_interval", 10)
        threshold = getattr(self.config, "memory_threshold", 1000)
        return f"## Smart Memory Status\n\n- **Interval**: {interval} turns\n- **Redaction Threshold**: {threshold} chars"

    async def _show_config(self, user_input: str | None = None) -> None:
        """Switch to the configuration app in the bottom panel."""
        if self._current_bottom_app == BottomApp.Config:
            return
        await self._switch_to_config_app()

    async def _reload_config(self, user_input: str | None = None) -> None:
        try:
            self._windowing.reset()
            self._tool_call_map = None
            self._history_widget_indices = WeakKeyDictionary()
            await self._load_more.hide()
            base_config = HacxgentConfig.load()

            await self.agent_loop.reload_with_initial_messages(base_config=base_config)

            if self._banner:
                self._banner.set_state(base_config, self.agent_loop.skill_manager)
            await self._mount_and_scroll(UserCommandMessage("Configuration reloaded."))
        except Exception as e:
            await self._mount_and_scroll(
                ErrorMessage(
                    f"Failed to reload config: {e}", collapsed=self._tools_collapsed
                )
            )

    async def _clear_history(self, user_input: str | None = None) -> None:
        try:
            self._windowing.reset()
            self._tool_call_map = None
            self._history_widget_indices = WeakKeyDictionary()
            await self.agent_loop.clear_history()
            await self._finalize_current_streaming_message()
            messages_area = self._cached_messages_area or self.query_one("#messages")
            await messages_area.remove_children()

            await messages_area.mount(UserMessage("/clear"))
            await self._mount_and_scroll(
                UserCommandMessage("Conversation history cleared!")
            )
            chat = self._cached_chat or self.query_one("#chat", ChatScroll)
            chat.scroll_home(animate=False)

        except Exception as e:
            await self._mount_and_scroll(
                ErrorMessage(
                    f"Failed to clear history: {e}", collapsed=self._tools_collapsed
                )
            )

    async def _show_log_path(self, user_input: str | None = None) -> None:
        if not self.agent_loop.session_logger.enabled:
            await self._mount_and_scroll(
                ErrorMessage(
                    "Session logging is disabled in configuration.",
                    collapsed=self._tools_collapsed,
                )
            )
            return

        try:
            log_path = str(self.agent_loop.session_logger.session_dir)
            await self._mount_and_scroll(
                UserCommandMessage(
                    f"## Current Log Directory\n\n`{log_path}`\n\nYou can send this directory to share your interaction."
                )
            )
        except Exception as e:
            await self._mount_and_scroll(
                ErrorMessage(
                    f"Failed to get log path: {e}", collapsed=self._tools_collapsed
                )
            )

    async def _compact_history(self, user_input: str | None = None) -> None:
        if self._agent_running:
            await self._mount_and_scroll(
                ErrorMessage(
                    "Cannot compact while agent loop is processing. Please wait.",
                    collapsed=self._tools_collapsed,
                )
            )
            return

        if len(self.agent_loop.messages) <= 1:
            await self._mount_and_scroll(
                ErrorMessage(
                    "No conversation history to compact yet.",
                    collapsed=self._tools_collapsed,
                )
            )
            return

        if not self.event_handler:
            return

        old_tokens = self.agent_loop.stats.context_tokens
        compact_msg = CompactMessage()
        self.event_handler.current_compact = compact_msg
        await self._mount_and_scroll(compact_msg)

        self._agent_task = asyncio.create_task(
            self._run_compact(compact_msg, old_tokens)
        )

    async def _run_compact(self, compact_msg: CompactMessage, old_tokens: int) -> None:
        self._agent_running = True
        try:
            await self.agent_loop.compact()
            new_tokens = self.agent_loop.stats.context_tokens
            compact_msg.set_complete(old_tokens=old_tokens, new_tokens=new_tokens)

        except asyncio.CancelledError:
            compact_msg.set_error("Compaction interrupted")
            raise
        except Exception as e:
            compact_msg.set_error(str(e))
        finally:
            self._agent_running = False
            self._agent_task = None
            if self.event_handler:
                self.event_handler.current_compact = None

    def _get_session_resume_info(self) -> str | None:
        if not self.agent_loop.session_logger.enabled:
            return None
        if not self.agent_loop.session_logger.session_id:
            return None
        session_config = self.agent_loop.session_logger.session_config
        session_path = SessionLoader.does_session_exist(
            self.agent_loop.session_logger.session_id, session_config
        )
        if session_path is None:
            return None
        return self.agent_loop.session_logger.session_id[:8]

    async def _exit_app(self, user_input: str | None = None) -> None:
        self.exit(result=self._get_session_resume_info())

    async def _setup_terminal(self, user_input: str | None = None) -> None:
        result = setup_terminal()

        if result.success:
            if result.requires_restart:
                message = f"{result.message or 'Set up Shift+Enter keybind'} (You may need to restart your terminal.)"
                await self._mount_and_scroll(
                    UserCommandMessage(f"{result.terminal.value}: {message}")
                )
            else:
                message = result.message or "Shift+Enter keybind already set up"
                await self._mount_and_scroll(
                    WarningMessage(f"{result.terminal.value}: {message}")
                )
        else:
            await self._mount_and_scroll(
                ErrorMessage(result.message, collapsed=self._tools_collapsed)
            )

    async def _switch_from_input(self, widget: Widget, scroll: bool = False) -> None:
        bottom_container = self.query_one("#bottom-app-container")

        if self._chat_input_container:
            self._chat_input_container.display = False
            self._chat_input_container.disabled = True

        self._current_bottom_app = BottomApp[type(widget).__name__.removesuffix("App")]
        await bottom_container.mount(widget)

        self.call_after_refresh(widget.focus)
        if scroll:
            self.call_after_refresh(self._scroll_to_bottom)

    async def _switch_to_config_app(self) -> None:
        if self._current_bottom_app == BottomApp.Config:
            return

        await self._mount_and_scroll(UserCommandMessage("Configuration opened..."))
        await self._switch_from_input(ConfigApp(self.config))

    async def _switch_to_approval_app(
        self, tool_name: str, tool_args: BaseModel
    ) -> None:
        approval_app = ApprovalApp(
            tool_name=tool_name, tool_args=tool_args, config=self.config
        )
        await self._switch_from_input(approval_app, scroll=True)

    async def _switch_to_question_app(self, args: BaseModel) -> None:
        await self._switch_from_input(QuestionApp(args=args), scroll=True)

    async def _switch_to_input_app(self) -> None:
        for app in BottomApp:
            if app != BottomApp.Input:
                try:
                    await self.query_one(f"#{app.value}-app").remove()
                except Exception:
                    pass

        if self._chat_input_container:
            self._chat_input_container.disabled = False
            self._chat_input_container.display = True
            self._current_bottom_app = BottomApp.Input
            self.call_after_refresh(self._chat_input_container.focus_input)

    def _focus_current_bottom_app(self) -> None:
        try:
            match self._current_bottom_app:
                case BottomApp.Input:
                    self.query_one(ChatInputContainer).focus_input()
                case BottomApp.Config:
                    self.query_one(ConfigApp).focus()
                case BottomApp.Approval:
                    self.query_one(ApprovalApp).focus()
                case BottomApp.Question:
                    self.query_one(QuestionApp).focus()
                case app:
                    assert_never(app)
        except Exception:
            pass

    def action_interrupt(self) -> None:
        current_time = time.monotonic()

        if self._current_bottom_app == BottomApp.Config:
            try:
                config_app = self.query_one(ConfigApp)
                config_app.action_close()
            except Exception:
                pass
            self._last_escape_time = None
            return

        if self._current_bottom_app == BottomApp.Approval:
            try:
                approval_app = self.query_one(ApprovalApp)
                approval_app.action_reject()
            except Exception:
                pass
            self._last_escape_time = None
            return

        if self._current_bottom_app == BottomApp.Question:
            try:
                question_app = self.query_one(QuestionApp)
                question_app.action_cancel()
            except Exception:
                pass
            self._last_escape_time = None
            return

        if (
            self._current_bottom_app == BottomApp.Input
            and self._last_escape_time is not None
            and (current_time - self._last_escape_time) < 0.2  # noqa: PLR2004
        ):
            try:
                input_widget = self.query_one(ChatInputContainer)
                if input_widget.value:
                    input_widget.value = ""
                    self._last_escape_time = None
                    return
            except Exception:
                pass

        if self._agent_running:
            self.run_worker(self._interrupt_agent_loop(), exclusive=False)

        self._last_escape_time = current_time
        self._scroll_to_bottom()
        self._focus_current_bottom_app()

    async def on_history_load_more_requested(self, _: HistoryLoadMoreRequested) -> None:
        self._load_more.set_enabled(False)
        try:
            if not self._windowing.has_backfill:
                await self._load_more.hide()
                return
            if (batch := self._windowing.next_load_more_batch()) is None:
                await self._load_more.hide()
                return
            messages_area = self._cached_messages_area or self.query_one("#messages")
            if self._tool_call_map is None:
                self._tool_call_map = {}
            if self._load_more.widget:
                before: Widget | int | None = None
                after: Widget | None = self._load_more.widget
            else:
                before = 0
                after = None
            await self._mount_history_batch(
                batch.messages,
                messages_area,
                self._tool_call_map,
                start_index=batch.start_index,
                before=before,
                after=after,
            )
            if not self._windowing.has_backfill:
                await self._load_more.hide()
            else:
                await self._load_more.show(messages_area, self._windowing.remaining)
        finally:
            self._load_more.set_enabled(True)

    async def action_toggle_tool(self) -> None:
        self._tools_collapsed = not self._tools_collapsed

        for result in self.query(ToolResultMessage):
            await result.set_collapsed(self._tools_collapsed)

        try:
            for error_msg in self.query(ErrorMessage):
                error_msg.set_collapsed(self._tools_collapsed)
        except Exception:
            pass

    def action_cycle_mode(self) -> None:
        if self._current_bottom_app != BottomApp.Input:
            return
        self._refresh_profile_widgets()
        self._focus_current_bottom_app()
        self.run_worker(self._cycle_agent(), group="mode_switch", exclusive=True)

    def _refresh_profile_widgets(self) -> None:
        self._update_profile_widgets(self.agent_loop.agent_profile)

    def _update_profile_widgets(self, profile: AgentProfile) -> None:
        if self._chat_input_container:
            self._chat_input_container.set_safety(profile.safety)
            self._chat_input_container.set_agent_name(profile.display_name.lower())

    async def _cycle_agent(self) -> None:
        new_profile = self.agent_loop.agent_manager.next_agent(
            self.agent_loop.agent_profile
        )
        self._update_profile_widgets(new_profile)
        await self.agent_loop.switch_agent(new_profile.name)
        self.agent_loop.set_approval_callback(self._approval_callback)
        self.agent_loop.set_user_input_callback(self._user_input_callback)

    def action_clear_quit(self) -> None:
        input_widgets = self.query(ChatInputContainer)
        if input_widgets:
            input_widget = input_widgets.first()
            if input_widget.value:
                input_widget.value = ""
                return

        self.action_force_quit()

    def action_force_quit(self) -> None:
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()

        self.exit(result=self._get_session_resume_info())

    def action_scroll_chat_up(self) -> None:
        try:
            chat = self._cached_chat or self.query_one("#chat", ChatScroll)
            chat.scroll_relative(y=-5, animate=False)
            self._auto_scroll = False
        except Exception:
            pass

    def action_scroll_chat_down(self) -> None:
        try:
            chat = self._cached_chat or self.query_one("#chat", ChatScroll)
            chat.scroll_relative(y=5, animate=False)
            if self._is_scrolled_to_bottom(chat):
                self._auto_scroll = True
        except Exception:
            pass

    async def _show_dangerous_directory_warning(self) -> None:
        is_dangerous, reason = is_dangerous_directory()
        if is_dangerous:
            warning = (
                f"⚠ WARNING: {reason}\n\nRunning in this location is not recommended."
            )
            await self._mount_and_scroll(WarningMessage(warning, show_border=False))

    async def _finalize_current_streaming_message(self) -> None:
        if self._current_streaming_reasoning is not None:
            self._current_streaming_reasoning.stop_spinning()
            await self._current_streaming_reasoning.stop_stream()
            self._current_streaming_reasoning = None

        if self._current_streaming_message is None:
            return

        await self._current_streaming_message.stop_stream()
        self._current_streaming_message = None

    async def _handle_streaming_widget[T: StreamingMessageBase](
        self,
        widget: T,
        current_stream: T | None,
        other_stream: StreamingMessageBase | None,
        messages_area: Widget,
    ) -> T | None:
        if other_stream is not None:
            await other_stream.stop_stream()

        if current_stream is not None:
            if widget._content:
                await current_stream.append_content(widget._content)
            return None

        await messages_area.mount(widget)
        await widget.write_initial_content()
        return widget

    async def _mount_and_scroll(self, widget: Widget) -> None:
        messages_area = self._cached_messages_area or self.query_one("#messages")
        chat = self._cached_chat or self.query_one("#chat", ChatScroll)
        was_at_bottom = self._is_scrolled_to_bottom(chat)
        result: Widget | None = None

        if was_at_bottom:
            self._auto_scroll = True

        if isinstance(widget, ReasoningMessage):
            result = await self._handle_streaming_widget(
                widget,
                self._current_streaming_reasoning,
                self._current_streaming_message,
                messages_area,
            )
            if result is not None:
                self._current_streaming_reasoning = result
            self._current_streaming_message = None
        elif isinstance(widget, AssistantMessage):
            if self._current_streaming_reasoning is not None:
                self._current_streaming_reasoning.stop_spinning()
            result = await self._handle_streaming_widget(
                widget,
                self._current_streaming_message,
                self._current_streaming_reasoning,
                messages_area,
            )
            if result is not None:
                self._current_streaming_message = result
            self._current_streaming_reasoning = None
        else:
            await self._finalize_current_streaming_message()
            await messages_area.mount(widget)
            result = widget

            is_tool_message = isinstance(widget, (ToolCallMessage, ToolResultMessage))

            if not is_tool_message:
                self.call_after_refresh(self._scroll_to_bottom)

        if result is not None:
            self.call_after_refresh(self._try_prune)
        if was_at_bottom:
            self.call_after_refresh(self._anchor_if_scrollable)

    def _is_scrolled_to_bottom(self, scroll_view: VerticalScroll) -> bool:
        try:
            threshold = 3
            return scroll_view.scroll_y >= (scroll_view.max_scroll_y - threshold)
        except Exception:
            return True

    def _scroll_to_bottom(self) -> None:
        try:
            chat = self._cached_chat or self.query_one("#chat", ChatScroll)
            chat.scroll_end(animate=False)
        except Exception:
            pass

    def _scroll_to_bottom_deferred(self) -> None:
        self.call_after_refresh(self._scroll_to_bottom)

    async def _try_prune(self) -> None:
        messages_area = self._cached_messages_area or self.query_one("#messages")
        await prune_by_height(messages_area, PRUNE_LOW_MARK, PRUNE_HIGH_MARK)
        if self._load_more.widget and not self._load_more.widget.parent:
            self._load_more.widget = None

    async def _refresh_windowing_from_history(self) -> None:
        if self._load_more.widget is None:
            return
        messages_area = self._cached_messages_area or self.query_one("#messages")
        has_backfill, tool_call_map = sync_backfill_state(
            history_messages=non_system_history_messages(self.agent_loop.messages),
            messages_children=list(messages_area.children),
            history_widget_indices=self._history_widget_indices,
            windowing=self._windowing,
        )
        self._tool_call_map = tool_call_map
        await self._load_more.set_visible(
            messages_area, visible=has_backfill, remaining=self._windowing.remaining
        )

    def _anchor_if_scrollable(self) -> None:
        if not self._auto_scroll:
            return
        try:
            chat = self._cached_chat or self.query_one("#chat", ChatScroll)
            if chat.max_scroll_y == 0:
                return
            chat.anchor()
        except Exception:
            pass

    def _align_chat_after_history_rebuild(self, has_backfill: bool) -> None:
        try:
            chat = self._cached_chat or self.query_one("#chat", ChatScroll)
            if has_backfill and chat.max_scroll_y > 0:
                chat.anchor(True)
                chat.scroll_end(animate=False)
                chat.anchor(False)
                return
            chat.scroll_end(animate=False)
        except Exception:
            pass

    def action_copy_selection(self) -> None:
        copy_selection_to_clipboard(self, show_toast=False)

    def on_mouse_up(self, event: MouseUp) -> None:
        if self.config.autocopy_to_clipboard:
            copy_selection_to_clipboard(self, show_toast=True)

    def on_app_blur(self, event: AppBlur) -> None:
        if self._chat_input_container and self._chat_input_container.input_widget:
            self._chat_input_container.input_widget.set_app_focus(False)

    def on_app_focus(self, event: AppFocus) -> None:
        if self._chat_input_container and self._chat_input_container.input_widget:
            self._chat_input_container.input_widget.set_app_focus(True)


def run_textual_ui(
    agent_loop: AgentLoop,
    initial_prompt: str | None = None,
) -> Any:
    app = HacxgentApp(
        agent_loop=agent_loop,
        initial_prompt=initial_prompt,
    )
    return app.run()
