from __future__ import annotations

import argparse
import sys

from rich import print as rprint

from pydantic import ValidationError

from hacxgent.cli.textual_ui.app import run_textual_ui
from hacxgent.core.agent_loop import AgentLoop
from hacxgent.core.agents.models import BuiltinAgentName
from hacxgent.core.config import (
    MissingAPIKeyError,
    MissingPromptFileError,
    HacxgentConfig,
    load_dotenv_values,
)
from hacxgent.core.paths.config_paths import CONFIG_FILE, HISTORY_FILE
from hacxgent.core.programmatic import run_programmatic
from hacxgent.core.session.session_loader import SessionLoader
from hacxgent.core.types import LLMMessage, OutputFormat, Role
from hacxgent.core.utils import ConversationLimitException, logger
from hacxgent.setup.onboarding import run_onboarding


def get_initial_agent_name(args: argparse.Namespace) -> str:
    if args.prompt is not None and args.agent == BuiltinAgentName.DEFAULT:
        return BuiltinAgentName.AUTO_APPROVE
    return args.agent


def get_prompt_from_stdin() -> str | None:
    if sys.stdin.isatty():
        return None
    try:
        if content := sys.stdin.read().strip():
            sys.stdin = sys.__stdin__ = open("/dev/tty")
            return content
    except KeyboardInterrupt:
        pass
    except OSError:
        return None

    return None


def load_config_or_exit() -> HacxgentConfig:
    try:
        config = HacxgentConfig.load()
        config.get_active_model()
        return config
    except (MissingAPIKeyError, ValueError, ValidationError):
        run_onboarding()
        return HacxgentConfig.load()
    except MissingPromptFileError as e:
        rprint(f"[yellow]Invalid system prompt id: {e}[/]")
        sys.exit(1)
    except Exception as e:
        rprint(f"[yellow]{e}[/]")
        sys.exit(1)


def bootstrap_config_files() -> None:
    if not CONFIG_FILE.path.exists():
        try:
            HacxgentConfig.save_updates(HacxgentConfig.create_default())
        except Exception as e:
            rprint(f"[yellow]Could not create default config file: {e}[/]")

    if not HISTORY_FILE.path.exists():
        try:
            HISTORY_FILE.path.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.path.write_text("Hello Hacxgent!\n", "utf-8")
        except Exception as e:
            rprint(f"[yellow]Could not create history file: {e}[/]")


def load_session(
    args: argparse.Namespace, config: HacxgentConfig
) -> list[LLMMessage] | None:
    if not args.continue_session and not args.resume:
        return None

    if not config.session_logging.enabled:
        rprint(
            "[red]Session logging is disabled. "
            "Enable it in config to use --continue or --resume[/]"
        )
        sys.exit(1)

    session_to_load = None
    if args.continue_session:
        session_to_load = SessionLoader.find_latest_session(config.session_logging)
        if not session_to_load:
            rprint(
                f"[red]No previous sessions found in "
                f"{config.session_logging.save_dir}[/]"
            )
            sys.exit(1)
    else:
        session_to_load = SessionLoader.find_session_by_id(
            args.resume, config.session_logging
        )
        if not session_to_load:
            rprint(
                f"[red]Session '{args.resume}' not found in "
                f"{config.session_logging.save_dir}[/]"
            )
            sys.exit(1)

    try:
        loaded_messages, _ = SessionLoader.load_session(session_to_load)
        return loaded_messages
    except Exception as e:
        rprint(f"[red]Failed to load session: {e}[/]")
        sys.exit(1)


def _load_messages_from_previous_session(
    agent_loop: AgentLoop, loaded_messages: list[LLMMessage]
) -> None:
    non_system_messages = [msg for msg in loaded_messages if msg.role != Role.system]
    agent_loop.messages.extend(non_system_messages)
    logger.info("Loaded %d messages from previous session", len(non_system_messages))


def _print_session_resume_message(session_id: str | None) -> None:
    if not session_id or not isinstance(session_id, str) or len(session_id) < 8:
        return

    print()
    print("To continue this session, run: hacxgent --continue")
    print(f"Or: hacxgent --resume {session_id}")


def run_cli(args: argparse.Namespace) -> None:
    load_dotenv_values()
    bootstrap_config_files()

    if args.setup:
        run_onboarding()
        sys.exit(0)

    try:
        initial_agent_name = get_initial_agent_name(args)
        config = load_config_or_exit()

        if args.enabled_tools:
            config.enabled_tools = args.enabled_tools

        loaded_messages = load_session(args, config)

        stdin_prompt = get_prompt_from_stdin()
        if args.prompt is not None:
            programmatic_prompt = args.prompt or stdin_prompt
            if not programmatic_prompt:
                print(
                    "Error: No prompt provided for programmatic mode", file=sys.stderr
                )
                sys.exit(1)
            output_format = OutputFormat(
                args.output if hasattr(args, "output") else "text"
            )

            try:
                final_response = run_programmatic(
                    config=config,
                    prompt=programmatic_prompt,
                    max_turns=args.max_turns,
                    max_price=args.max_price,
                    output_format=output_format,
                    previous_messages=loaded_messages,
                    agent_name=initial_agent_name,
                )
                if final_response:
                    print(final_response)
                sys.exit(0)
            except ConversationLimitException as e:
                print(e, file=sys.stderr)
                sys.exit(1)
            except RuntimeError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            agent_loop = AgentLoop(
                config, agent_name=initial_agent_name, enable_streaming=False
            )

            if loaded_messages:
                _load_messages_from_previous_session(agent_loop, loaded_messages)

            result = run_textual_ui(
                agent_loop=agent_loop,
                initial_prompt=args.initial_prompt or stdin_prompt,
            )

            if result == "run_setup":
                run_onboarding()
                # Restart after setup
                run_cli(args)
            else:
                _print_session_resume_message(result)

    except (KeyboardInterrupt, EOFError):
        rprint("\n[dim]Bye![/]")
        sys.exit(0)
