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


class ReplaceLinesArgs(BaseModel):
    file_path: str = Field(..., description="Path to the file to modify")
    start_line: int = Field(..., description="1-based starting line number (inclusive)")
    end_line: int = Field(..., description="1-based ending line number (inclusive)")
    new_content: str = Field(..., description="The replacement content")


class ReplaceLinesResult(BaseModel):
    file_path: str
    lines_replaced: int
    new_total_lines: int


class ReplaceLinesConfig(BaseToolConfig):
    pass


class ReplaceLinesState(BaseToolState):
    pass


class ReplaceLines(
    BaseTool[ReplaceLinesArgs, ReplaceLinesResult, ReplaceLinesConfig, ReplaceLinesState],
    ToolUIData[ReplaceLinesArgs, ReplaceLinesResult],
):
    description: ClassVar[str] = (
        "Surgically replace a range of lines in a file. "
        "More efficient than search_replace when you know exact line numbers from file_meta."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, ReplaceLinesArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        args = event.args
        return ToolCallDisplay(
            summary=f"Replacing lines {args.start_line}-{args.end_line} in {args.file_path}",
            content=args.new_content,
        )

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, ReplaceLinesResult):
            return ToolResultDisplay(
                success=True,
                message=f"Replaced {event.result.lines_replaced} lines in {event.result.file_path}",
            )
        return ToolResultDisplay(success=True, message="File updated")

    @classmethod
    def get_status_text(cls) -> str:
        return "Editing file"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "replace_lines.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: ReplaceLinesArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | ReplaceLinesResult, None]:
        path = Path(args.file_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        if not path.exists():
            raise ToolError(f"File not found: {args.file_path}")
        if not path.is_file():
            raise ToolError(f"Path is not a file: {args.file_path}")

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            raise ToolError(f"Error reading file: {e}")

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        if args.start_line < 1 or args.start_line > total_lines:
            raise ToolError(f"Invalid start_line: {args.start_line} (total lines: {total_lines})")
        if args.end_line < args.start_line:
            raise ToolError(f"Invalid end_line: {args.end_line} (must be >= start_line)")
        if args.end_line > total_lines:
            # We'll allow replacing up to the end if it's slightly off
            args.end_line = total_lines

        # Replacement logic (indices are 0-based)
        start_idx = args.start_line - 1
        end_idx = args.end_line # end line is inclusive

        # Normalize replacement to have correct line endings if it doesn't
        new_lines_str = args.new_content
        if not new_lines_str.endswith("
") and (end_idx < total_lines or lines[-1].endswith("
")):
             new_lines_str += "
"

        lines[start_idx:end_idx] = [new_lines_str]

        try:
            path.write_text("".join(lines), encoding="utf-8")
        except Exception as e:
            raise ToolError(f"Error writing to file: {e}")

        yield ReplaceLinesResult(
            file_path=str(path),
            lines_replaced=(args.end_line - args.start_line + 1),
            new_total_lines=len(lines),
        )
