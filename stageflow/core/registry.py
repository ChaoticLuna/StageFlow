"""Stage and transition registry. Loads declarative config and provides
query API for the state machine engine.

Usage:
    from stageflow.core.registry import StageRegistry
    reg = StageRegistry("stageflow/config/stages.yaml")
    stage = reg.get_stage("analyze")
    transitions = reg.get_transitions_from("analyze")
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .conditions import evaluate_all


class Stage:
    """A single stage (node) in the state machine."""

    def __init__(self, name: str, data: dict):
        self.name = name
        self.tools: List[str] = data.get("tools", data.get("allow_tools", []))
        self.description: str = data.get("description", data.get("meta", {}).get("description", ""))
        self.meta: dict = data.get("meta", {})
        self.max_iterations: Optional[int] = data.get("max_iterations")
        self.extra: dict = {k: v for k, v in data.items() if k not in ("name", "tools", "allow_tools", "description", "meta", "max_iterations")}

    def to_dict(self) -> dict:
        d = {"name": self.name, "tools": self.tools, "description": self.description, "meta": self.meta, **self.extra}
        if self.max_iterations is not None:
            d["max_iterations"] = self.max_iterations
        return d

    def __repr__(self):
        return f"Stage({self.name!r}, tools={len(self.tools)})"


class Transition:
    """A directed edge between two stages, with optional conditions."""

    def __init__(self, data: dict):
        self.from_stage: str = data["from"]
        self.to_stage: str = data["to"]
        self.conditions: List[dict] = data.get("conditions", [])
        self.on_fail: Optional[str] = data.get("on_fail")  # Stage to rollback to on failure
        self.description: str = data.get("description", "")

    def evaluate(self, base_path: str = ".", cache_ttl: float = 0,
                 variables: Optional[dict] = None) -> tuple[bool, list[str]]:
        """Evaluate all conditions for this transition.

        cache_ttl=0 by default: each transition check is a fresh evaluation.
        The engine needs fresh results because files may change between checks.

        Pass `variables` to resolve {{var.key}} patterns in condition params.
        """
        return evaluate_all(self.conditions, base_path, cache_ttl=cache_ttl,
                           variables=variables)

    def to_dict(self) -> dict:
        return {
            "from": self.from_stage, "to": self.to_stage,
            "conditions": self.conditions, "on_fail": self.on_fail,
            "description": self.description,
        }

    def __repr__(self):
        return f"Transition({self.from_stage!r} -> {self.to_stage!r}, conditions={len(self.conditions)})"


class StageRegistry:
    """Central registry for stages and transitions. Loads from YAML config.

    Supports:
      - Stage lookup by name
      - Transition lookup by source stage
      - Validation of the entire graph
      - Dynamic stage/transition registration (for programmatic extension)
    """

    def __init__(self, config_path: str = "stageflow/config/stages.yaml"):
        self.config_path = Path(config_path)
        self._stages: Dict[str, Stage] = {}
        self._transitions: List[Transition] = []
        self._transitions_from: Dict[str, List[Transition]] = {}
        self._transitions_to: Dict[str, List[Transition]] = {}
        if self.config_path.exists():
            self._load()

    _MAX_EXTENDS_DEPTH = 5

    @staticmethod
    def _merge_configs(parent: dict, child: dict) -> dict:
        """Merge child config into parent config. Child stages/transitions override parent ones by name."""
        merged = dict(parent)
        merged.pop("extends", None)

        parent_stages = {s["name"]: s for s in parent.get("stages", [])}
        for s in child.get("stages", []):
            parent_stages[s["name"]] = s
        merged["stages"] = list(parent_stages.values())

        parent_trans = {(t["from"], t["to"]): t for t in parent.get("transitions", [])}
        for t in child.get("transitions", []):
            parent_trans[(t["from"], t["to"])] = t
        merged["transitions"] = list(parent_trans.values())

        merged["groups"] = parent.get("groups", []) + child.get("groups", [])

        return merged

    def _resolve_extends(self, config: dict, depth: int = 0) -> dict:
        """Resolve `extends` references, merging parent configs up to _MAX_EXTENDS_DEPTH."""
        extends = config.get("extends")
        if not extends or not isinstance(extends, str):
            return config
        if depth >= self._MAX_EXTENDS_DEPTH:
            import warnings
            warnings.warn(f"StageFlow: 'extends' depth exceeded {self._MAX_EXTENDS_DEPTH} for {extends}")
            return config
        parent_path = (self.config_path.parent / extends).resolve()
        if not parent_path.exists():
            import warnings
            warnings.warn(f"StageFlow: extended config not found: {parent_path}")
            return config
        with open(parent_path, "r", encoding="utf-8") as f:
            parent_config = yaml.safe_load(f) or {}
        parent_config = self._resolve_extends(parent_config, depth + 1)
        return self._merge_configs(parent_config, config)

    def _load(self):
        """Load stages and transitions from YAML config, with schema validation."""
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        config = self._resolve_extends(config)

        from .schema import validate_stages_config
        valid, errors = validate_stages_config(config)
        if not valid:
            import warnings
            for e in errors:
                warnings.warn(f"StageFlow config error: {e}")

        for stage_data in config.get("stages", []):
            stage = Stage(stage_data["name"], stage_data)
            self._stages[stage.name] = stage

        for trans_data in config.get("transitions", []):
            trans = Transition(trans_data)
            self._add_transition(trans)

    def _add_transition(self, trans: Transition):
        self._transitions.append(trans)
        self._transitions_from.setdefault(trans.from_stage, []).append(trans)
        self._transitions_to.setdefault(trans.to_stage, []).append(trans)

    # ── Query API ──────────────────────────────────────────────────────

    def get_stage(self, name: str) -> Optional[Stage]:
        """Get a stage by name."""
        return self._stages.get(name)

    def get_transitions_from(self, stage_name: str) -> List[Transition]:
        """Get all transitions originating from a stage."""
        return self._transitions_from.get(stage_name, [])

    def get_transitions_to(self, stage_name: str) -> List[Transition]:
        """Get all transitions leading to a stage."""
        return self._transitions_to.get(stage_name, [])

    def get_next_stages(self, stage_name: str) -> List[str]:
        """Get names of stages reachable from the given stage."""
        return [t.to_stage for t in self.get_transitions_from(stage_name)]

    @property
    def stage_names(self) -> List[str]:
        return sorted(self._stages.keys())

    @property
    def all_stages(self) -> Dict[str, Stage]:
        return dict(self._stages)

    @property
    def all_transitions(self) -> List[Transition]:
        return list(self._transitions)

    # ── Registration API (for programmatic extension) ───────────────────

    def register_stage(self, name: str, tools: Optional[List[str]] = None,
                       description: str = "", **kwargs) -> Stage:
        """Dynamically register a new stage. Does not persist to YAML."""
        data = {"name": name, "tools": tools or [], "description": description, **kwargs}
        stage = Stage(name, data)
        self._stages[name] = stage
        return stage

    def unregister_stage(self, name: str) -> bool:
        """Remove a stage and all its transitions."""
        if name not in self._stages:
            return False
        del self._stages[name]
        self._transitions = [t for t in self._transitions
                             if t.from_stage != name and t.to_stage != name]
        self._transitions_from.pop(name, None)
        self._transitions_to.pop(name, None)
        # Also clean up other from/to references
        for k in list(self._transitions_from):
            self._transitions_from[k] = [t for t in self._transitions_from[k]
                                         if t.to_stage != name]
        for k in list(self._transitions_to):
            self._transitions_to[k] = [t for t in self._transitions_to[k]
                                       if t.from_stage != name]
        return True

    def register_transition(self, from_stage: str, to_stage: str,
                            conditions: Optional[List[dict]] = None,
                            on_fail: Optional[str] = None, description: str = "") -> Transition:
        """Dynamically register a new transition."""
        trans = Transition({
            "from": from_stage, "to": to_stage,
            "conditions": conditions or [],
            "on_fail": on_fail, "description": description,
        })
        self._add_transition(trans)
        return trans

    def unregister_transition(self, from_stage: str, to_stage: str) -> bool:
        """Remove a specific transition."""
        before = len(self._transitions)
        self._transitions = [t for t in self._transitions
                             if not (t.from_stage == from_stage and t.to_stage == to_stage)]
        if from_stage in self._transitions_from:
            self._transitions_from[from_stage] = [
                t for t in self._transitions_from[from_stage]
                if t.to_stage != to_stage
            ]
        if to_stage in self._transitions_to:
            self._transitions_to[to_stage] = [
                t for t in self._transitions_to[to_stage]
                if t.from_stage != from_stage
            ]
        return len(self._transitions) < before

    # ── Validation ──────────────────────────────────────────────────────

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the stage graph. Returns (valid, errors)."""
        errors = []
        # Check that all transition references exist
        for t in self._transitions:
            if t.from_stage not in self._stages:
                errors.append(f"Transition from unknown stage: {t.from_stage}")
            if t.to_stage not in self._stages:
                errors.append(f"Transition to unknown stage: {t.to_stage}")
        # Check for isolated stages (no transitions in or out, except entry/exit)
        connected = set()
        for t in self._transitions:
            connected.add(t.from_stage)
            connected.add(t.to_stage)
        for name in self._stages:
            if name not in connected:
                errors.append(f"Isolated stage (no transitions): {name}")
        # Check for duplicate transitions
        seen = set()
        for t in self._transitions:
            key = (t.from_stage, t.to_stage)
            if key in seen:
                errors.append(f"Duplicate transition: {t.from_stage} -> {t.to_stage}")
            seen.add(key)
        return len(errors) == 0, errors

    def to_dict(self) -> dict:
        return {
            "stages": [s.to_dict() for s in self._stages.values()],
            "transitions": [t.to_dict() for t in self._transitions],
        }

    def __repr__(self):
        return f"StageRegistry(stages={len(self._stages)}, transitions={len(self._transitions)})"
