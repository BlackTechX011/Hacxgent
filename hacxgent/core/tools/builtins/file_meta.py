from __future__ import annotations

import ast
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


class FileSymbol(BaseModel):
    name: str
    type: str  # "class", "function", "method"
    start_line: int
    end_line: int
    children: list[FileSymbol] = Field(default_factory=list)


class FileMetaArgs(BaseModel):
    file_path: str = Field(..., description="Path to the file to analyze")


class FileMetaResult(BaseModel):
    file_path: str
    total_lines: int
    symbols: list[FileSymbol]


class FileMetaConfig(BaseToolConfig):
    pass


class FileMetaState(BaseToolState):
    pass


class FileMeta(
    BaseTool[FileMetaArgs, FileMetaResult, FileMetaConfig, FileMetaState],
    ToolUIData[FileMetaArgs, FileMetaResult],
):
    description: ClassVar[str] = (
        "Return a structural map of a file (classes, functions, methods) with line numbers. "
        "Highly context-efficient for understanding large files without reading them entirely."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, FileMetaArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        return ToolCallDisplay(summary=f"Mapping symbols in {event.args.file_path}")

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, FileMetaResult):
            count = len(event.result.symbols)
            return ToolResultDisplay(
                success=True,
                message=f"Found {count} top-level symbols in {event.result.file_path}",
            )
        return ToolResultDisplay(success=True, message="File mapped")

    @classmethod
    def get_status_text(cls) -> str:
        return "Analyzing file structure"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "file_meta.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: FileMetaArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | FileMetaResult, None]:
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

        lines = content.splitlines()
        
        symbols = []
        if path.suffix == ".py":
            symbols = self._parse_python(content)
        else:
            symbols = self._parse_generic(lines)

        yield FileMetaResult(
            file_path=str(path),
            total_lines=len(lines),
            symbols=symbols,
        )

    def _parse_python(self, content: str) -> list[FileSymbol]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        def get_symbols(node: ast.AST) -> list[FileSymbol]:
            res = []
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbol_type = "class" if isinstance(child, ast.ClassDef) else "function"
                    
                    # Estimate end line
                    end_line = getattr(child, "end_lineno", child.lineno)
                    
                    symbol = FileSymbol(
                        name=child.name,
                        type=symbol_type,
                        start_line=child.lineno,
                        end_line=end_line,
                        children=get_symbols(child)
                    )
                    res.append(symbol)
            return res

        return get_symbols(tree)

    def _parse_generic(self, lines: list[str]) -> list[FileSymbol]:
        """Simple generic regex-based symbol detection for non-python files."""
        import re
        # Heuristic patterns for common languages
        patterns = [
            (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)"), "function"),
            (re.compile(r"^\s*(?:export\s+)?class\s+([a-zA-Z0-9_]+)"), "class"),
            (re.compile(r"^\s*(?:pub\s+)?fn\s+([a-zA-Z0-9_]+)"), "function"), # Rust
            (re.compile(r"^\s*def\s+([a-zA-Z0-9_]+)"), "function"), # Ruby/Python
        ]

        symbols = []
        for i, line in enumerate(lines, 1):
            for pattern, sym_type in patterns:
                match = pattern.search(line)
                if match:
                    symbols.append(FileSymbol(
                        name=match.group(1),
                        type=sym_type,
                        start_line=i,
                        end_line=i, # Unknown for generic
                    ))
                    break
        return symbols
