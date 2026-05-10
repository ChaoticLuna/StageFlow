"""Comprehensive tests for dynamic extensibility: programmatic stage/transition management.

Covers the core requirement: dynamically add, remove, re-add stages
and transitions; verify correct tool isolation; test round-trip through many stages.
"""

import json
import sys
import yaml
import pytest
from pathlib import Path

from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry, Stage, Transition


def create_config_with_n_stages(n: int, base_path: Path) -> Path:
    """Create a YAML config with N stages and linear transitions between them."""
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


# ============================================================================
# Many stages: creation and verification
# ============================================================================

class TestManyStages:
    def test_create_15_stages_dynamically(self, temp_dir):
        config_path = create_config_with_n_stages(15, temp_dir)
        reg = StageRegistry(str(config_path))
        assert len(reg.all_stages) == 15
        assert "stage_0" in reg.stage_names
        assert "stage_14" in reg.stage_names

    def test_create_15_stages_with_consecutive_transitions(self, temp_dir):
        config_path = create_config_with_n_stages(15, temp_dir)
        reg = StageRegistry(str(config_path))
        assert len(reg.all_transitions) == 14
        t0 = reg.get_transitions_from("stage_0")
        assert len(t0) == 1
        assert t0[0].to_stage == "stage_1"

        t_last = reg.get_transitions_from("stage_13")
        assert len(t_last) == 1
        assert t_last[0].to_stage == "stage_14"

    def test_generate_n_stages_edge_cases(self, temp_dir):
        config_path = create_config_with_n_stages(1, temp_dir)
        reg = StageRegistry(str(config_path))
        assert len(reg.all_stages) == 1
        assert len(reg.all_transitions) == 0

    def test_generate_n_stages_large(self, temp_dir):
        config_path = create_config_with_n_stages(50, temp_dir)
        reg = StageRegistry(str(config_path))
        assert len(reg.all_stages) == 50
        assert len(reg.all_transitions) == 49


# ============================================================================
# Remove stages and verify cleanup
# ============================================================================

class TestRemoveStages:
    def test_remove_stage_cleans_up_transitions(self, temp_dir):
        config_path = create_config_with_n_stages(10, temp_dir)
        reg = StageRegistry(str(config_path))
        reg.unregister_stage("stage_5")
        assert reg.get_stage("stage_5") is None
        for t in reg.all_transitions:
            assert t.from_stage != "stage_5"
            assert t.to_stage != "stage_5"

    def test_remove_stage_preserves_unrelated_transitions(self, temp_dir):
        config_path = create_config_with_n_stages(6, temp_dir)
        reg = StageRegistry(str(config_path))
        reg.unregister_stage("stage_2")
        t = reg.get_transitions_from("stage_0")
        assert len(t) == 1
        assert t[0].to_stage == "stage_1"

        t2 = reg.get_transitions_from("stage_3")
        assert len(t2) == 1
        assert t2[0].to_stage == "stage_4"

    def test_remove_all_stages_one_by_one(self, temp_dir):
        config_path = create_config_with_n_stages(5, temp_dir)
        reg = StageRegistry(str(config_path))
        for i in range(5):
            reg.unregister_stage(f"stage_{i}")
        assert len(reg.all_stages) == 0
        assert len(reg.all_transitions) == 0


# ============================================================================
# Full round-trip: register, transition through all, verify history
# ============================================================================

class TestRoundTrip:
    def test_full_round_trip_10_stages(self, temp_dir):
        config_path = create_config_with_n_stages(10, temp_dir)
        reg = StageRegistry(str(config_path))
        sm = StateMachine(reg, str(temp_dir))

        sm.initialize("stage_0")
        for i in range(1, 10):
            target = f"stage_{i}"
            ok, msgs = sm.transition_to(target)
            assert ok, f"Transition to {target} failed: {msgs}"
            assert sm.current_stage == target

        assert sm.current_stage == "stage_9"
        assert len(sm.history) == 9
        for idx, entry in enumerate(sm.history):
            assert entry["from"] == f"stage_{idx}"
            assert entry["to"] == f"stage_{idx + 1}"

    def test_tool_isolation_across_round_trip(self, temp_dir):
        config_path = create_config_with_n_stages(5, temp_dir)
        reg = StageRegistry(str(config_path))
        sm = StateMachine(reg, str(temp_dir))

        sm.initialize("stage_0")
        assert sm.is_tool_allowed("tool_0")[0]
        assert sm.is_tool_allowed("common_tool_0")[0]
        assert not sm.is_tool_allowed("tool_1")[0]

        sm.transition_to("stage_1")
        assert sm.is_tool_allowed("tool_1")[0]
        assert sm.is_tool_allowed("common_tool_1")[0]
        assert not sm.is_tool_allowed("tool_0")[0]

        sm.transition_to("stage_2")
        assert sm.is_tool_allowed("tool_2")[0]
        assert sm.is_tool_allowed("common_tool_2")[0]
        assert not sm.is_tool_allowed("tool_1")[0]


# ============================================================================
# Different condition types per transition
# ============================================================================

class TestDifferentConditionTypes:
    def test_varied_conditions_across_transitions(self, temp_dir):
        (temp_dir / "flag_a.txt").write_text("ready")
        (temp_dir / "data.json").write_text(json.dumps({"status": "ok"}))
        (temp_dir / "data.yaml").write_text("version: 2\n")

        reg = StageRegistry(str(temp_dir / "nonexistent.yaml"))
        reg.register_stage("s0", tools=[])
        reg.register_stage("s1", tools=[])
        reg.register_stage("s2", tools=[])
        reg.register_stage("s3", tools=[])
        reg.register_stage("s4", tools=[])

        reg.register_transition("s0", "s1", conditions=[
            {"file_exists": "flag_a.txt"}
        ])
        reg.register_transition("s1", "s2", conditions=[
            {"json_field": {"path": "data.json", "field": "status",
             "op": "equals", "value": "ok"}},
            {"yaml_field": {"path": "data.yaml", "field": "version",
             "op": "exists"}},
        ])
        reg.register_transition("s2", "s3", conditions=[
            {"python_expr": {"expr": "1 + 2 == 3"}},
            {"env_var": {"name": "PATH", "op": "not_empty"}},
        ])
        reg.register_transition("s3", "s4", conditions=[
            {"all_of": {"conditions": [
                {"file_exists": "flag_a.txt"},
                {"always": True},
            ]}},
        ])

        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("s0")

        ok, msgs = sm.transition_to("s1")
        assert ok, f"s0->s1: {msgs}"
        ok, msgs = sm.transition_to("s2")
        assert ok, f"s1->s2: {msgs}"
        ok, msgs = sm.transition_to("s3")
        assert ok, f"s2->s3: {msgs}"
        ok, msgs = sm.transition_to("s4")
        assert ok, f"s3->s4: {msgs}"
        assert sm.current_stage == "s4"

    def test_condition_fails_blocks_transition(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        reg.register_stage("A", tools=[])
        reg.register_stage("B", tools=[])
        reg.register_transition("A", "B", conditions=[{"never": "permanently blocked"}])

        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("A")
        ok, _ = sm.can_transition_to("B")
        assert not ok
        ok2, _ = sm.transition_to("B")
        assert not ok2


# ============================================================================
# Remove middle stage, verify remaining transitions still valid
# ============================================================================

class TestRemoveMiddleStage:
    def test_remaining_transitions_still_function(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        for i in range(5):
            reg.register_stage(f"s{i}", tools=[])
        for i in range(4):
            reg.register_transition(f"s{i}", f"s{i+1}", conditions=[{"always": True}])

        reg.unregister_stage("s2")
        assert reg.get_stage("s0") is not None
        assert reg.get_stage("s1") is not None
        assert reg.get_stage("s2") is None
        assert reg.get_stage("s3") is not None

        t = reg.get_transitions_from("s0")
        assert len(t) == 1
        assert t[0].to_stage == "s1"
        assert reg.get_transitions_from("s1") == []

    def test_remove_then_add_new_transitions(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        for i in range(5):
            reg.register_stage(f"s{i}", tools=[])
        for i in range(4):
            reg.register_transition(f"s{i}", f"s{i+1}", conditions=[{"always": True}])

        reg.unregister_stage("s2")
        reg.register_transition("s1", "s3", conditions=[{"always": True}])

        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("s0")
        sm.transition_to("s1")
        ok, msgs = sm.transition_to("s3")
        assert ok, f"Bridged transition s1->s3 failed: {msgs}"
        sm.transition_to("s4")
        assert sm.current_stage == "s4"


# ============================================================================
# Tool isolation per stage
# ============================================================================

class TestToolIsolation:
    def test_each_stage_has_independent_tools(self, stageflow_empty_registry, temp_dir):
        reg = stageflow_empty_registry
        reg.register_stage("analysis", tools=["Read", "Grep", "Glob"])
        reg.register_stage("coding", tools=["Edit", "Write", "Bash(python *)"])
        reg.register_stage("testing", tools=["Bash(pytest *)", "Bash(npm test*)"])
        reg.register_transition("analysis", "coding", conditions=[{"always": True}])
        reg.register_transition("coding", "testing", conditions=[{"always": True}])

        sm = StateMachine(reg, str(temp_dir))

        sm.initialize("analysis")
        assert sm.is_tool_allowed("Read")[0]
        assert sm.is_tool_allowed("Grep")[0]
        assert sm.is_tool_allowed("Glob")[0]
        assert not sm.is_tool_allowed("Edit")[0]
        assert not sm.is_tool_allowed("Write")[0]

        sm.transition_to("coding")
        assert sm.is_tool_allowed("Edit")[0]
        assert sm.is_tool_allowed("Write")[0]
        assert sm.is_tool_allowed("Bash(python script.py)")[0]
        assert not sm.is_tool_allowed("Read")[0]
        assert not sm.is_tool_allowed("Grep")[0]

        sm.transition_to("testing")
        assert sm.is_tool_allowed("Bash(pytest tests/)")[0]
        assert sm.is_tool_allowed("Bash(npm test)")[0]
        assert not sm.is_tool_allowed("Edit")[0]
        assert not sm.is_tool_allowed("Bash(python test.py)")[0]

    def test_bash_subcommand_isolation(self, stageflow_empty_registry, temp_dir):
        reg = stageflow_empty_registry
        reg.register_stage("git_stage", tools=["Bash(git *)"])
        reg.register_stage("python_stage", tools=["Bash(python *)"])
        reg.register_stage("npm_stage", tools=["Bash(npm *)"])
        reg.register_transition("git_stage", "python_stage", conditions=[{"always": True}])
        reg.register_transition("python_stage", "npm_stage", conditions=[{"always": True}])

        sm = StateMachine(reg, str(temp_dir))

        sm.initialize("git_stage")
        assert sm.is_tool_allowed("Bash(git status)")[0]
        assert not sm.is_tool_allowed("Bash(python script.py)")[0]

        sm.transition_to("python_stage")
        assert sm.is_tool_allowed("Bash(python script.py)")[0]
        assert not sm.is_tool_allowed("Bash(git status)")[0]

        sm.transition_to("npm_stage")
        assert sm.is_tool_allowed("Bash(npm install)")[0]
        assert not sm.is_tool_allowed("Bash(python script.py)")[0]


# ============================================================================
# Add / remove / re-add stages (idempotency)
# ============================================================================

class TestAddRemoveReadd:
    def test_add_remove_readd_stage(self, stageflow_empty_registry):
        reg = stageflow_empty_registry
        reg.register_stage("toggle", tools=["ToolX"])
        assert "toggle" in reg.stage_names

        reg.unregister_stage("toggle")
        assert "toggle" not in reg.stage_names

        reg.register_stage("toggle", tools=["ToolY"])
        assert "toggle" in reg.stage_names
        assert reg.get_stage("toggle").tools == ["ToolY"]

    def test_add_remove_readd_transition(self, stageflow_empty_registry):
        reg = stageflow_empty_registry
        reg.register_stage("A")
        reg.register_stage("B")

        reg.register_transition("A", "B")
        assert len(reg.get_transitions_from("A")) == 1

        reg.unregister_transition("A", "B")
        assert len(reg.get_transitions_from("A")) == 0

        reg.register_transition("A", "B", conditions=[{"always": True}])
        assert len(reg.get_transitions_from("A")) == 1

    def test_remove_nonexistent_stage_returns_false(self, stageflow_empty_registry):
        assert stageflow_empty_registry.unregister_stage("nope") is False

    def test_remove_nonexistent_transition_returns_false(self, stageflow_empty_registry):
        assert stageflow_empty_registry.unregister_transition("A", "B") is False

    def test_register_same_stage_overwrites(self, stageflow_empty_registry):
        reg = stageflow_empty_registry
        reg.register_stage("dup", tools=["Original"])
        reg.register_stage("dup", tools=["Overwritten"])
        assert reg.get_stage("dup").tools == ["Overwritten"]

    def test_multiple_cycles_of_add_remove(self, stageflow_empty_registry):
        reg = stageflow_empty_registry
        for cycle in range(3):
            reg.register_stage(f"cycle_{cycle}", tools=[f"tool_{cycle}"])
            assert f"cycle_{cycle}" in reg.stage_names
            reg.unregister_stage(f"cycle_{cycle}")
            assert f"cycle_{cycle}" not in reg.stage_names
        assert len(reg.all_stages) == 0


# ============================================================================
# No tools / empty tools: allow all
# ============================================================================

class TestNoToolsAllowAll:
    def test_stage_with_no_tools_argument_allows_all(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        reg.register_stage("open_bar")
        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("open_bar")
        allowed, msg = sm.is_tool_allowed("SuperDangerousTool")
        assert allowed
        assert "All tools allowed" in msg

    def test_stage_with_explicit_empty_tools_allows_all(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        reg.register_stage("permissive", tools=[])
        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("permissive")
        allowed, _ = sm.is_tool_allowed("AnyTool")
        assert allowed

    def test_stage_with_none_tools_allows_all(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        reg.register_stage("none_stage", tools=None)
        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("none_stage")
        assert sm.is_tool_allowed("Foo")[0]

    def test_dynamic_stage_switching_tool_access(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no.yaml"))
        reg.register_stage("restricted", tools=["OnlyThis"])
        reg.register_stage("open", tools=[])
        reg.register_transition("restricted", "open", conditions=[{"always": True}])
        reg.register_transition("open", "restricted", conditions=[{"always": True}])

        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("restricted")
        assert sm.is_tool_allowed("OnlyThis")[0]
        assert not sm.is_tool_allowed("OtherTool")[0]

        sm.transition_to("open")
        assert sm.is_tool_allowed("OtherTool")[0]

        sm.transition_to("restricted")
        assert not sm.is_tool_allowed("OtherTool")[0]


# ============================================================================
# Edge cases
# ============================================================================

class TestExtensibilityEdgeCases:
    def test_empty_registry_transitions(self, stageflow_empty_registry):
        assert stageflow_empty_registry.get_transitions_from("any") == []
        assert stageflow_empty_registry.get_transitions_to("any") == []
        assert stageflow_empty_registry.get_next_stages("any") == []

    def test_state_machine_with_fully_dynamic_registry(self, stageflow_empty_registry, temp_dir):
        reg = stageflow_empty_registry
        reg.register_stage("build", tools=["Read", "Write"])
        reg.register_stage("test", tools=["Bash(pytest *)"])
        reg.register_stage("deploy", tools=["Bash(gh *)"])
        reg.register_transition("build", "test", conditions=[
            {"file_exists": "setup.py"},
            {"python_expr": {"expr": "True"}},
        ])
        reg.register_transition("test", "deploy", conditions=[{"always": True}])

        (temp_dir / "setup.py").write_text("# placeholder")

        sm = StateMachine(reg, str(temp_dir))
        sm.initialize("build")
        assert sm.current_stage == "build"

        ok, msgs = sm.can_transition_to("test")
        assert ok, f"build->test should pass: {msgs}"

        sm.transition_to("test")
        assert sm.current_stage == "test"

        sm.transition_to("deploy")
        assert sm.current_stage == "deploy"

    def test_register_transition_missing_stages(self, stageflow_empty_registry):
        reg = stageflow_empty_registry
        reg.register_stage("A")
        t = reg.register_transition("A", "B")
        assert t.from_stage == "A"
        assert t.to_stage == "B"
        valid, errors = reg.validate()
        assert not valid
        assert any("unknown stage" in e.lower() for e in errors)
