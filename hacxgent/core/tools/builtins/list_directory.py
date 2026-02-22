from __future__ import annotations

import os
import stat
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


class FileInfo(BaseModel):
    name: str
    type: str  # "file" or "directory"
    size: int
    modified: float


class ListDirectoryArgs(BaseModel):
    path: str = Field(".", description="Path to the directory to list")


class ListDirectoryResult(BaseModel):
    path: str
    items: list[FileInfo]


class ListDirectoryConfig(BaseToolConfig):
    permission: ToolPermission = ToolPermission.ASK


class ListDirectoryState(BaseToolState):
    pass


class ListDirectory(
    BaseTool[ListDirectoryArgs, ListDirectoryResult, ListDirectoryConfig, ListDirectoryState],
    ToolUIData[ListDirectoryArgs, ListDirectoryResult],
):
    description: ClassVar[str] = (
        "List files and directories in a given path with metadata. "
        "Preferred over bash 'ls' for structured, cross-platform directory inspection."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, ListDirectoryArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        return ToolCallDisplay(summary=f"Listing directory: [bold]{event.args.path}[/]")

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, ListDirectoryResult):
            count = len(event.result.items)
            return ToolResultDisplay(
                success=True,
                message=f"Found {count} items in {event.result.path}",
            )
        return ToolResultDisplay(success=True, message="Directory listed")

    @classmethod
    def get_status_text(cls) -> str:
        return "Listing files"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "list_directory.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: ListDirectoryArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | ListDirectoryResult, None]:
        path = Path(args.path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        if not path.exists():
            raise ToolError(f"Directory not found: {args.path}")
        if not path.is_dir():
            raise ToolError(f"Path is not a directory: {args.path}")

        items = []
        try:
            for entry in os.scandir(path):
                s = entry.stat()
                items.append(FileInfo(
                    name=entry.name,
                    type="directory" if entry.is_dir() else "file",
                    size=s.st_size,
                    modified=s.st_mtime
                ))
        except Exception as e:
            raise ToolError(f"Error listing directory: {e}")

        yield ListDirectoryResult(
            path=str(path),
            items=items
        )
