from __future__ import annotations

import anyio.to_thread
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import ClassVar, final

from pydantic import BaseModel, Field

from hacxgent.core.tools.base import (
    BaseTool,
    BaseToolConfig,
    BaseToolState,
    InvokeContext,
    ToolError,
    ToolPermission,
)
from hacxgent.core.tools.ui import ToolCallDisplay, ToolResultDisplay, ToolUIData
from hacxgent.core.types import ToolCallEvent, ToolResultEvent, ToolStreamEvent


class ReadLinesArgs(BaseModel):
    file_path: str = Field(..., description="Path to the file to read")
    start_line: int = Field(1, description="1-based starting line number (inclusive)")
    end_line: int = Field(..., description="1-based ending line number (inclusive)")


class ReadLinesResult(BaseModel):
    file_path: str
    content: str
    lines_read: int
    total_lines: int


class ReadLinesConfig(BaseToolConfig):
    permission: ToolPermission = ToolPermission.ASK
    max_read_bytes: int = Field(
        default=64_000, description="Maximum total bytes to read in one go."
    )


class ReadLinesState(BaseToolState):
    pass


class ReadLines(
    BaseTool[ReadLinesArgs, ReadLinesResult, ReadLinesConfig, ReadLinesState],
    ToolUIData[ReadLinesArgs, ReadLinesResult],
):
    description: ClassVar[str] = (
        "Read a specific range of lines from a file. "
        "Use this for surgical inspection of code segments identified by file_meta."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, ReadLinesArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        args = event.args
        return ToolCallDisplay(
            summary=f"Reading lines {args.start_line}-{args.end_line} of {args.file_path}"
        )

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, ReadLinesResult):
            return ToolResultDisplay(
                success=True,
                message=f"Read {event.result.lines_read} lines from {event.result.file_path}",
            )
        return ToolResultDisplay(success=True, message="Lines read successfully")

    @classmethod
    def get_status_text(cls) -> str:
        return "Reading lines"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "read_lines.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: ReadLinesArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | ReadLinesResult, None]:
        path = Path(args.file_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        if not path.exists():
            raise ToolError(f"File not found: {args.file_path}")
        if not path.is_file():
            raise ToolError(f"Path is not a file: {args.file_path}")

        def sync_read():
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()
                    
                total = len(all_lines)
                start = max(1, args.start_line)
                end = min(total, args.end_line)
                
                if start > total:
                    return ReadLinesResult(file_path=str(path), content="", lines_read=0, total_lines=total)
                
                selected_lines = all_lines[start-1:end]
                content = "".join(selected_lines)
                
                if len(content.encode("utf-8")) > self.config.max_read_bytes:
                    raise ToolError(f"Read operation exceeds max_read_bytes ({self.config.max_read_bytes})")
                    
                return ReadLinesResult(
                    file_path=str(path),
                    content=content,
                    lines_read=len(selected_lines),
                    total_lines=total
                )
            except Exception as e:
                raise ToolError(f"Error reading lines: {e}")

        result = await anyio.to_thread.run_sync(sync_read)
        yield result
