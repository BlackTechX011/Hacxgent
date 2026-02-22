from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.stubs.fake_backend import FakeBackend
from tests.stubs.fake_client import FakeClient
from hacxgent.acp.acp_agent_loop import HacxgentAcpAgentLoop
from hacxgent.core.agent_loop import AgentLoop
from hacxgent.core.types import LLMChunk, LLMMessage, LLMUsage, Role


@pytest.fixture
def backend() -> FakeBackend:
    backend = FakeBackend(
        LLMChunk(
            message=LLMMessage(role=Role.assistant, content="Hi"),
            usage=LLMUsage(prompt_tokens=1, completion_tokens=1),
        )
    )
    return backend


def _create_acp_agent() -> HacxgentAcpAgentLoop:
    hacxgent_acp_agent = HacxgentAcpAgentLoop()
    client = FakeClient()

    hacxgent_acp_agent.on_connect(client)
    client.on_connect(hacxgent_acp_agent)

    return hacxgent_acp_agent  # pyright: ignore[reportReturnType]


@pytest.fixture
def acp_agent_loop(backend: FakeBackend) -> HacxgentAcpAgentLoop:
    class PatchedAgent(AgentLoop):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs, backend=backend)

    patch("hacxgent.acp.acp_agent_loop.AgentLoop", side_effect=PatchedAgent).start()
    return _create_acp_agent()
