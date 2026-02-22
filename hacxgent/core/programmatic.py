from __future__ import annotations

import asyncio

from hacxgent.core.agent_loop import AgentLoop
from hacxgent.core.agents.models import BuiltinAgentName
from hacxgent.core.config import HacxgentConfig
from hacxgent.core.output_formatters import create_formatter
from hacxgent.core.types import AssistantEvent, LLMMessage, OutputFormat, Role
from hacxgent.core.utils import ConversationLimitException, logger


def run_programmatic(
    config: HacxgentConfig,
    prompt: str,
    max_turns: int | None = None,
    max_price: float | None = None,
    output_format: OutputFormat = OutputFormat.TEXT,
    previous_messages: list[LLMMessage] | None = None,
    agent_name: str = BuiltinAgentName.AUTO_APPROVE,
) -> str | None:
    formatter = create_formatter(output_format)

    agent_loop = AgentLoop(
        config,
        agent_name=agent_name,
        message_observer=formatter.on_message_added,
        max_turns=max_turns,
        max_price=max_price,
        enable_streaming=False,
    )
    logger.info("USER: %s", prompt)

    async def _async_run() -> str | None:
        if previous_messages:
            non_system_messages = [
                msg for msg in previous_messages if not (msg.role == Role.system)
            ]
            agent_loop.messages.extend(non_system_messages)
            logger.info(
                "Loaded %d messages from previous session", len(non_system_messages)
            )

        async for event in agent_loop.act(prompt):
            formatter.on_event(event)
            if isinstance(event, AssistantEvent) and event.stopped_by_middleware:
                raise ConversationLimitException(event.content)

        return formatter.finalize()

    return asyncio.run(_async_run())
