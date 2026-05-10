"""StageFlow pytest plugin — provides fixtures and markers for testing
stage-dependent code.

Fixtures:
    stageflow_registry      Loaded from default stages.yaml
    stageflow_sm            StateMachine initialized at 'pick'
    stageflow_empty_registry Empty registry for dynamic tests
    stageflow_temp_sm       StateMachine with empty registry in temp dir
    stageflow_artifacts     Pre-created artifact directories

    temp_dir                Alias for tmp_path (for test convenience)
    sample_config_yaml      Minimal 3-stage config in temp_dir
    registry                StageRegistry from sample config
    state_machine           StateMachine with sample registry
    make_n_stage_config     Factory: call make_n_stage_config(N) for N-stage config
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


# ═══════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════

def create_config_with_n_stages(n: int, base_path: Path) -> Path:
    """Create a YAML config file with N stages (stage_0..stage_{n-1})
    and linear transitions between consecutive stages using 'always' condition.

    Returns the Path to the created config file.
    """
    stages = []
    transitions = []
    for i in range(n):
        stage_name = f"stage_{i}"
        stages.append({
            "name": stage_name,
            "tools": [f"tool_{i}", f"common_tool_{i}"],
            "meta": {"description": f"Auto-generated stage {i}"},
        })
        if i > 0:
            transitions.append({
                "from": f"stage_{i - 1}",
                "to": stage_name,
                "conditions": [{"always": True}],
                "description": f"stage_{i - 1} -> stage_{i}",
            })

    config = {"stages": stages, "transitions": transitions}
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "stages.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return config_path


# ═══════════════════════════════════════════════════════════════════════════
# Core fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory for test file operations (alias for tmp_path)."""
    return tmp_path


@pytest.fixture
def stageflow_config_dir(tmp_path) -> Path:
    """Temporary stageflow config directory with default stages.yaml."""
    config_dir = tmp_path / "stageflow" / "config"
    config_dir.mkdir(parents=True)
    src = Path(__file__).resolve().parent.parent / "stageflow" / "config" / "stages.yaml"
    shutil.copy(src, config_dir / "stages.yaml")
    return tmp_path


@pytest.fixture
def stageflow_registry(stageflow_config_dir):
    """StageRegistry loaded from default config in temp dir."""
    config_path = str(stageflow_config_dir / "stageflow" / "config" / "stages.yaml")
    return StageRegistry(config_path)


@pytest.fixture
def stageflow_sm(stageflow_config_dir, stageflow_registry):
    """StateMachine initialized at 'pick' in temp directory."""
    sm = StateMachine(stageflow_registry, str(stageflow_config_dir))
    sm.initialize("pick")
    return sm


@pytest.fixture
def stageflow_empty_registry():
    """Empty StageRegistry for dynamic registration tests."""
    reg = StageRegistry.__new__(StageRegistry)
    reg.config_path = Path("nonexistent.yaml")
    reg._stages = {}
    reg._transitions = []
    reg._transitions_from = {}
    reg._transitions_to = {}
    return reg


@pytest.fixture
def stageflow_temp_sm(stageflow_empty_registry, tmp_path):
    """StateMachine with empty registry in temp directory."""
    return StateMachine(stageflow_empty_registry, str(tmp_path))


@pytest.fixture
def empty_registry(stageflow_empty_registry):
    """Alias for stageflow_empty_registry."""
    return stageflow_empty_registry


# ═══════════════════════════════════════════════════════════════════════════
# Minimal 3-stage sample config fixture (for basic engine/registry testing)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_config_yaml(temp_dir):
    """Create a minimal sample YAML stages config with 3 stages and 2 transitions.

    Stages: start (tools: Read, Write), middle (tools: Edit, Bash(git *)), end (tools: [])
    Transitions: start->middle(always), middle->end(always)
    """
    config = {
        "stages": [
            {
                "name": "start",
                "tools": ["Read", "Write"],
                "meta": {"description": "Starting stage"},
            },
            {
                "name": "middle",
                "tools": ["Edit", "Bash(git *)"],
                "meta": {"description": "Middle stage"},
            },
            {
                "name": "end",
                "tools": [],
                "meta": {"description": "End stage, empty tools = allow all"},
            },
        ],
        "transitions": [
            {
                "from": "start",
                "to": "middle",
                "conditions": [{"always": True}],
                "description": "Start to middle transition",
            },
            {
                "from": "middle",
                "to": "end",
                "conditions": [{"always": True}],
                "description": "Middle to end transition",
            },
        ],
    }
    config_dir = temp_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "stages.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return config_path


@pytest.fixture
def registry(sample_config_yaml):
    """StageRegistry loaded from the sample 3-stage config."""
    return StageRegistry(str(sample_config_yaml))


@pytest.fixture
def state_machine(registry, temp_dir):
    """StateMachine wired to the sample 3-stage registry, using temp_dir as base_path."""
    return StateMachine(registry, str(temp_dir))


# ═══════════════════════════════════════════════════════════════════════════
# Dynamic N-stage config factory
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def make_n_stage_config(temp_dir):
    """Fixture factory: call make_n_stage_config(N) to create a config with N stages.

    Returns the Path to the generated YAML file.
    """
    def _make(n: int) -> Path:
        return create_config_with_n_stages(n, temp_dir)
    return _make


# ═══════════════════════════════════════════════════════════════════════════
# pytest configuration hooks
# ═══════════════════════════════════════════════════════════════════════════

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "stageflow(stage_name): mark test to verify it runs in the specified stage"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests marked with @pytest.mark.stageflow if wrong stage."""
    state_file = Path.cwd() / ".claude" / "current_stage.json"
    current_stage = None
    if state_file.exists():
        try:
            current_stage = json.loads(state_file.read_text()).get("current_stage")
        except Exception:
            pass

    for item in items:
        marker = item.get_closest_marker("stageflow")
        if marker and current_stage:
            required = marker.args[0] if marker.args else marker.kwargs.get("stage")
            if required and current_stage != required:
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"Test requires stage '{required}', current is '{current_stage}'"
                    )
                )


