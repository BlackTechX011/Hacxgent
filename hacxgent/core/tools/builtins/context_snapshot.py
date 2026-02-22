from __future__ import annotations

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
)
from hacxgent.core.tools.ui import ToolCallDisplay, ToolResultDisplay, ToolUIData
from hacxgent.core.types import ToolCallEvent, ToolResultEvent, ToolStreamEvent


class SnapshotArgs(BaseModel):
    action: str = Field(..., description="Action: 'create', 'restore', or 'list'")
    name: str | None = Field(None, description="Name of the snapshot (required for create/restore)")


class SnapshotResult(BaseModel):
    action: str
    name: str
    message: str


class SnapshotConfig(BaseToolConfig):
    pass


class SnapshotState(BaseToolState):
    pass


class ContextSnapshot(
    BaseTool[SnapshotArgs, SnapshotResult, SnapshotConfig, SnapshotState],
    ToolUIData[SnapshotArgs, SnapshotResult],
):
    description: ClassVar[str] = (
        "Manage codebase 'Save Points'. "
        "Create a snapshot before major changes to easily rollback if something goes wrong."
    )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, SnapshotArgs):
            return ToolCallDisplay(summary="Invalid arguments")
        return ToolCallDisplay(summary=f"{event.args.action.capitalize()} snapshot: [bold]{event.args.name}[/]")

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if isinstance(event.result, SnapshotResult):
            return ToolResultDisplay(
                success=True,
                message=event.result.message,
            )
        return ToolResultDisplay(success=True, message="Snapshot action complete")

    @classmethod
    def get_status_text(cls) -> str:
        return "Managing save points"

    @classmethod
    def get_tool_prompt(cls) -> str | None:
        from hacxgent.core.paths.global_paths import DEFAULT_TOOL_DIR
        path = DEFAULT_TOOL_DIR.path / "builtins" / "prompts" / "context_snapshot.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    @final
    async def run(
        self, args: SnapshotArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | SnapshotResult, None]:
        snapshot_dir = Path.cwd() / ".hacx" / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        target_dir = snapshot_dir / args.name
        project_root = Path.cwd()

        if args.action == "create":
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True)
            
            # Simple recursive copy of tracked files (excluding .hacx, .git, node_modules)
            ignore = shutil.ignore_patterns(".git", ".hacx", "node_modules", "pycache", "venv")
            for item in project_root.iterdir():
                if item.name not in {".git", ".hacx", "node_modules", "__pycache__"}:
                    if item.is_dir():
                        shutil.copytree(item, target_dir / item.name, ignore=ignore)
                    else:
                        shutil.copy2(item, target_dir)
            
            yield SnapshotResult(action="create", name=args.name, message=f"Created snapshot '{args.name}'")

        elif args.action == "restore":
            if not target_dir.exists():
                raise ToolError(f"Snapshot '{args.name}' does not exist.")
                
            # Restore files from snapshot
            for item in target_dir.iterdir():
                dest = project_root / item.name
                if dest.is_dir():
                    shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            
            yield SnapshotResult(action="restore", name=args.name, message=f"Restored from snapshot '{args.name}'")

        elif args.action == "list":
            snapshots = [d.name for d in snapshot_dir.iterdir() if d.is_dir()]
            yield SnapshotResult(action="list", name="", message=f"Snapshots available: {', '.join(snapshots) or 'None'}")
        else:
            raise ToolError(f"Unknown action: {args.action}")
