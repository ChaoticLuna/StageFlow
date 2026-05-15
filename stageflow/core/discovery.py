"""Project root discovery. Walks upward from cwd to find a StageFlow project marker.

Marker priority (checked at each directory level):
    1. .stageflow/ directory          → new-style project
    2. stageflow/config/stages.yaml   → legacy project
    3. .claude/current_stage.json     → legacy (state-only) project
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ProjectRoot:
    """Discovered StageFlow project root with typed paths."""

    path: Path
    marker_type: str  # "new" | "legacy" | "legacy_state_only"
    config_path: Path
    state_path: Path
    artifacts_dir: Path
    audit_dir: Path


def discover_project(start_path: str | Path | None = None) -> Optional[ProjectRoot]:
    """Walk upward from *start_path* (default cwd) to find a StageFlow project marker.

    Returns ProjectRoot for the nearest ancestor with a marker, or None if no
    project is found before hitting the filesystem root.
    """
    current = Path(start_path).resolve() if start_path else Path.cwd()

    while True:
        # Priority 1: .stageflow/ directory (new-style)
        stageflow_dir = current / ".stageflow"
        if stageflow_dir.is_dir():
            return ProjectRoot(
                path=current,
                marker_type="new",
                config_path=stageflow_dir / "config" / "stages.yaml",
                state_path=stageflow_dir / "current_stage.json",
                artifacts_dir=current / "artifacts" / "runs",
                audit_dir=stageflow_dir,
            )

        # Priority 2: stageflow/config/stages.yaml (legacy)
        legacy_config = current / "stageflow" / "config" / "stages.yaml"
        if legacy_config.is_file():
            return ProjectRoot(
                path=current,
                marker_type="legacy",
                config_path=legacy_config,
                state_path=current / ".claude" / "current_stage.json",
                artifacts_dir=current / "artifacts" / "runs",
                audit_dir=current / ".claude",
            )

        # Priority 3: .claude/current_stage.json (legacy state-only)
        legacy_state = current / ".claude" / "current_stage.json"
        if legacy_state.is_file():
            return ProjectRoot(
                path=current,
                marker_type="legacy_state_only",
                config_path=current / "stageflow" / "config" / "stages.yaml",
                state_path=legacy_state,
                artifacts_dir=current / "artifacts" / "runs",
                audit_dir=current / ".claude",
            )

        # Stop at filesystem root
        parent = current.parent
        if parent == current:
            return None
        current = parent
