from __future__ import annotations

import os
import shutil
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


class FileOperationArgs(BaseModel):
    action: str = Field(..., description="Action: 'delete', 'move', 'copy', or 'mkdir'")
    source: str = Field(..., description="Source path (file or directory)")
    destination: str | None = Field(None, description="Destination path (for move, copy, mkdir)")


class FileOperationResult(BaseModel):
    action: str
    message: str


class FileOperationConfig(BaseToolConfig):
    permission: ToolPermission = ToolPermission.ASK


class FileOperationState(BaseToolState):
    pass


class FileOperations(
    BaseTool[FileOperationArgs, FileOperationResult, FileOperationConfig, FileOperationState],
    ToolUIData[FileOperationArgs, FileOperationResult],
):
    description: ClassVar[str] = (
        "Perform file management tasks: delete, move, copy, or create directory. "
        "More structured and safer than raw bash commands."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, FileOperationArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        args = event.args
        msg = f"{args.action.capitalize()}: [bold]{args.source}[/]"
        if args.destination:
            msg += f" -> [bold]{args.destination}[/]"
        return ToolCallDisplay(summary=msg)

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, FileOperationResult):
            return ToolResultDisplay(
                success=True,
                message=event.result.message,
            )
        return ToolResultDisplay(success=True, message="File operation complete")

    @classmethod
    def get_status_text(cls) -> str:
        return "Managing files"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "file_operations.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: FileOperationArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | FileOperationResult, None]:
        source_path = Path(args.source).expanduser()
        if not source_path.is_absolute():
            source_path = (Path.cwd() / source_path).resolve()
            
        dest_path = None
        if args.destination:
            dest_path = Path(args.destination).expanduser()
            if not dest_path.is_absolute():
                dest_path = (Path.cwd() / dest_path).resolve()

        try:
            if args.action == "delete":
                if not source_path.exists():
                    raise ToolError(f"Source not found: {args.source}")
                if source_path.is_dir():
                    shutil.rmtree(source_path)
                else:
                    source_path.unlink()
                msg = f"Deleted '{args.source}'"

            elif args.action == "move":
                if not dest_path:
                    raise ToolError("Destination required for move")
                if not source_path.exists():
                    raise ToolError(f"Source not found: {args.source}")
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_path), str(dest_path))
                msg = f"Moved '{args.source}' to '{args.destination}'"

            elif args.action == "copy":
                if not dest_path:
                    raise ToolError("Destination required for copy")
                if not source_path.exists():
                    raise ToolError(f"Source not found: {args.source}")
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if source_path.is_dir():
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
                msg = f"Copied '{args.source}' to '{args.destination}'"

            elif args.action == "mkdir":
                # For mkdir, 'source' is the directory to create
                source_path.mkdir(parents=True, exist_ok=True)
                msg = f"Created directory '{args.source}'"
            else:
                raise ToolError(f"Unknown action: {args.action}")

        except Exception as e:
            raise ToolError(f"File operation failed: {e}")

        yield FileOperationResult(
            action=args.action,
            message=msg
        )
