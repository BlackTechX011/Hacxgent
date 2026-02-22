from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import json
import os
import queue
import threading
import time
from typing import TYPE_CHECKING, Any

from hacxgent.core.llm.backend.API import Client, APIError
from hacxgent.core.types import (
    AvailableTool,
    LLMChunk,
    LLMMessage,
    LLMUsage,
    Role,
    StrToolChoice,
    ToolCall,
    FunctionCall
)

if TYPE_CHECKING:
    from hacxgent.core.config import ModelConfig, ProviderConfig

class UniversalBackend:
    _last_request_time: float = 0.0
    _request_lock = asyncio.Lock()

    def __init__(self, provider: ProviderConfig, timeout: float = 720.0) -> None:
        self._provider = provider
        self._timeout = timeout
        self._client = None

    def _get_client(self) -> Client:
        if self._client is None:
            api_key = os.getenv(self._provider.api_key_env_var) if self._provider.api_key_env_var else ""
            self._client = Client(
                api_key=api_key,
                base_url=self._provider.api_base,
                timeout=self._timeout
            )
        return self._client

    async def _apply_rate_limit(self, model: ModelConfig) -> None:
        if model.rate_limit_rpm <= 0:
            return

        interval = 60.0 / model.rate_limit_rpm
        async with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            self._last_request_time = time.time()

    def _prepare_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        msgs = []
        for msg in messages:
            m = {
                "role": msg.role.value,
                "content": msg.content or ""
            }
            if msg.role == Role.assistant:
                if msg.tool_calls:
                    m["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in msg.tool_calls
                    ]
            elif msg.role == Role.tool:
                m["tool_call_id"] = msg.tool_call_id
                m["name"] = msg.name
            msgs.append(m)
        return msgs

    def _prepare_tools(self, tools: list[AvailableTool] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [tool.model_dump(exclude_none=True) for tool in tools]

    def _map_response_to_chunk(self, response: Any) -> LLMChunk:
        usage = None
        usage_data = getattr(response, "usage", None)
        if usage_data:
            usage = LLMUsage(
                prompt_tokens=getattr(usage_data, "prompt_tokens", 0),
                completion_tokens=getattr(usage_data, "completion_tokens", 0)
            )

        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            message_data = getattr(choice, "message", None) or getattr(choice, "delta", None)
            
            if not message_data:
                 return LLMChunk(message=LLMMessage(role=Role.assistant, content=""), usage=usage)

            role_str = getattr(message_data, "role", "assistant") or "assistant"
            content = getattr(message_data, "content", "") or ""
            reasoning = getattr(message_data, "reasoning_content", None) or getattr(message_data, "thought", None)
            
            tool_calls = None
            raw_tool_calls = getattr(message_data, "tool_calls", None)
            if raw_tool_calls:
                tool_calls = [
                    ToolCall(
                        id=getattr(tc, "id", None),
                        index=getattr(tc, "index", None),
                        function=FunctionCall(
                            name=getattr(tc.function, "name", None) if tc.function else None,
                            arguments=getattr(tc.function, "arguments", None) if tc.function else None
                        )
                    ) for tc in raw_tool_calls
                ]

            return LLMChunk(
                message=LLMMessage(
                    role=Role(role_str),
                    content=content,
                    reasoning_content=reasoning,
                    tool_calls=tool_calls
                ),
                usage=usage
            )
        
        return LLMChunk(message=LLMMessage(role=Role.assistant, content=""), usage=usage)

    async def complete(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        tools: list[AvailableTool] | None = None,
        max_tokens: int | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LLMChunk:
        await self._apply_rate_limit(model)
        client = self._get_client()
        
        def _call():
            try:
                return client.chat.completions.create(
                    model=model.name,
                    messages=self._prepare_messages(messages),
                    temperature=temperature,
                    tools=self._prepare_tools(tools),
                    tool_choice=tool_choice if isinstance(tool_choice, str) else (tool_choice.model_dump() if tool_choice else None),
                    max_tokens=max_tokens,
                    extra_headers=extra_headers,
                    stream=False
                )
            except Exception as e:
                import sys
                print(f"API Error: {e}", file=sys.stderr)
                raise e

        response = await asyncio.to_thread(_call)
        return self._map_response_to_chunk(response)

    async def complete_streaming(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        tools: list[AvailableTool] | None = None,
        max_tokens: int | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        await self._apply_rate_limit(model)
        client = self._get_client()
        
        q = queue.Queue()
        done = threading.Event()

        def _producer():
            try:
                stream = client.chat.completions.create(
                    model=model.name,
                    messages=self._prepare_messages(messages),
                    temperature=temperature,
                    tools=self._prepare_tools(tools),
                    tool_choice=tool_choice if isinstance(tool_choice, str) else (tool_choice.model_dump() if tool_choice else None),
                    max_tokens=max_tokens,
                    extra_headers=extra_headers,
                    stream=True,
                    stream_options={"include_usage": True}
                )
                for chunk in stream:
                    q.put(chunk)
            except Exception as e:
                import sys
                print(f"API Stream Error: {e}", file=sys.stderr)
                q.put(e)
            finally:
                done.set()

        threading.Thread(target=_producer, daemon=True).start()

        while not done.is_set() or not q.empty():
            try:
                # Use a timeout to avoid blocking forever if something hangs
                item = await asyncio.to_thread(q.get, timeout=0.1)
                if isinstance(item, Exception):
                    raise item
                yield self._map_response_to_chunk(item)
            except queue.Empty:
                continue

    async def count_tokens(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        tools: list[AvailableTool] | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> int:
        try:
            from hacxgent.core.llm.backend.API import count_messages_tokens_approx
            return count_messages_tokens_approx(self._prepare_messages(messages))
        except Exception:
            return len(str(messages)) // 4

    async def close(self) -> None:
        pass
