from __future__ import annotations

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
)
from hacxgent.core.tools.ui import ToolCallDisplay, ToolResultDisplay, ToolUIData
from hacxgent.core.types import ToolCallEvent, ToolResultEvent, ToolStreamEvent


class LogWatcherArgs(BaseModel):
    file_path: str = Field(..., description="Path to the log file to watch")
    last_lines: int = Field(100, description="Number of tailing lines to retrieve")


class LogWatcherResult(BaseModel):
    file_path: str
    content: str
    line_count: int


class LogWatcherConfig(BaseToolConfig):
    pass


class LogWatcherState(BaseToolState):
    pass


class LogWatcher(
    BaseTool[LogWatcherArgs, LogWatcherResult, LogWatcherConfig, LogWatcherState],
    ToolUIData[LogWatcherArgs, LogWatcherResult],
):
    description: ClassVar[str] = (
        "Monitor the tailing output of a log file. "
        "Useful for observing runtime errors or process logs without reading the entire file."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, LogWatcherArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        return ToolCallDisplay(summary=f"Watching {event.args.last_lines} lines of {event.args.file_path}")

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, LogWatcherResult):
            return ToolResultDisplay(
                success=True,
                message=f"Retrieved {event.result.line_count} lines from {event.result.file_path}",
            )
        return ToolResultDisplay(success=True, message="Log tail retrieved")

    @classmethod
    def get_status_text(cls) -> str:
        return "Reading logs"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "log_watcher.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: LogWatcherArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | LogWatcherResult, None]:
        path = Path(args.file_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        if not path.exists():
            raise ToolError(f"Log file not found: {args.file_path}")
        if not path.is_file():
            raise ToolError(f"Path is not a file: {args.file_path}")

        try:
            # Read last lines using tail-like approach
            with open(path, "rb") as f:
                # Seek to end and look backwards for newlines
                f.seek(0, 2)
                file_size = f.tell()
                
                buffer_size = 1024
                lines_found = 0
                pos = file_size
                content = []

                while pos > 0 and lines_found < args.last_lines:
                    chunk_size = min(buffer_size, pos)
                    pos -= chunk_size
                    f.seek(pos)
                    chunk = f.read(chunk_size)
                    
                    lines_found += chunk.count(b"
")
                    content.insert(0, chunk)

                full_content = b"".join(content).decode("utf-8", errors="replace")
                final_lines = full_content.splitlines()[-args.last_lines:]
                final_text = "
".join(final_lines)

        except Exception as e:
            raise ToolError(f"Error reading log file: {e}")

        yield LogWatcherResult(
            file_path=str(path),
            content=final_text,
            line_count=len(final_lines),
        )
