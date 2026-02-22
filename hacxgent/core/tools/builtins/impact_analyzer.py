from __future__ import annotations

import re
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


class ImpactArgs(BaseModel):
    symbol: str = Field(..., description="The symbol name (function/class) to analyze for impacts")
    ignore_paths: list[str] = Field(default_factory=list, description="Paths to ignore (e.g., node_modules, build)")


class ImpactReference(BaseModel):
    file_path: str
    line_number: int
    context: str


class ImpactResult(BaseModel):
    symbol: str
    references: list[ImpactReference]


class ImpactConfig(BaseToolConfig):
    pass


class ImpactState(BaseToolState):
    pass


class ImpactAnalyzer(
    BaseTool[ImpactArgs, ImpactResult, ImpactConfig, ImpactState],
    ToolUIData[ImpactArgs, ImpactResult],
):
    description: ClassVar[str] = (
        "Analyze the global impact of modifying a symbol (function, class, variable). "
        "Finds all references to the symbol across the project."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, ImpactArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        return ToolCallDisplay(summary=f"Analyzing impacts for symbol: [bold]{event.args.symbol}[/]")

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, ImpactResult):
            count = len(event.result.references)
            return ToolResultDisplay(
                success=True,
                message=f"Found {count} references for symbol [bold]{event.result.symbol}[/]",
            )
        return ToolResultDisplay(success=True, message="Impact analysis complete")

    @classmethod
    def get_status_text(cls) -> str:
        return "Analyzing symbol impacts"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "impact_analyzer.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: ImpactArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | ImpactResult, None]:
        project_root = Path.cwd()
        symbol = args.symbol
        ignore = set(args.ignore_paths) | {".git", "node_modules", "pycache", "venv", ".hacx"}

        references = []
        # Pattern to find symbol with word boundaries to avoid partial matches
        pattern = re.compile(rf"\b{re.escape(symbol)}\b")

        for file in project_root.rglob("*"):
            if file.is_file() and not any(p in str(file) for p in ignore):
                try:
                    # Quick check to avoid reading large binaries
                    if file.stat().st_size > 1_000_000:
                        continue
                        
                    content = file.read_text(encoding="utf-8", errors="ignore")
                    if symbol in content:
                        lines = content.splitlines()
                        for i, line in enumerate(lines, 1):
                            if pattern.search(line):
                                references.append(ImpactReference(
                                    file_path=str(file.relative_to(project_root)),
                                    line_number=i,
                                    context=line.strip()
                                ))
                except Exception:
                    continue

        yield ImpactResult(
            symbol=symbol,
            references=references,
        )
