"""Edge case and robustness tests for StageFlow framework."""

from __future__ import annotations

import pytest
from pathlib import Path

from stageflow.core.registry import StageRegistry, Stage
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate_all, clear_cache, set_cache_ttl


class TestCorruptedState:
    """Tests for corrupted or missing state file scenarios."""

    def test_corrupted_state_file_is_handled(self, tmp_path):
        """Corrupted JSON in state file should not crash the engine."""
        state_dir = tmp_path / ".claude"
        state_dir.mkdir()
        state_file = state_dir / "current_stage.json"
        state_file.write_text("this is not json{{{", encoding="utf-8")

        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")

        sm = StateMachine(reg, str(tmp_path))
        assert sm.current_stage is None

    def test_missing_state_file_is_handled(self, tmp_path):
        """No state file should result in clean defaults."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")

        sm = StateMachine(reg, str(tmp_path))
        assert sm.current_stage is None
        assert sm.history == []
        assert sm.get_retry_count("any") == 0


class TestEmptyConditions:
    """Tests for edge cases with conditions."""

    def test_empty_conditions_list_passes(self):
        """Empty conditions list should always pass."""
        ok, msgs = evaluate_all([])
        assert ok
        assert msgs == []

    def test_cache_clearing(self):
        """Cache should be clearable."""
        clear_cache()
        set_cache_ttl(30)
        ok1, _ = evaluate_all([{"always": True}])
        assert ok1
        clear_cache()
        ok2, _ = evaluate_all([{"always": True}])
        assert ok2

    def test_cache_disabled(self):
        """cache_ttl=0 should disable caching."""
        ok1, _ = evaluate_all([{"always": True}], cache_ttl=0)
        assert ok1
        ok2, _ = evaluate_all([{"always": True}], cache_ttl=0)
        assert ok2


class TestUnicodeStageNames:
    """Tests for unicode/international stage names and descriptions."""

    def test_unicode_stage_name(self):
        """Stage names should support unicode."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")

        reg.register_stage("分析阶段", tools=["Read"],
                           description="分析中文描述")
        assert "分析阶段" in reg.stage_names


class TestRapidTransitions:
    """Tests for rapid consecutive transitions."""

    def test_rapid_forward_back(self, tmp_path):
        """Rapid forward and back transitions should maintain correct state."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")

        reg.register_stage("a", tools=[])
        reg.register_stage("b", tools=[])
        reg.register_transition("a", "b", [{"always": True}])

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        for _ in range(50):
            sm.transition_to("b")
            assert sm.current_stage == "b"
            sm.force_transition_to("a")
            assert sm.current_stage == "a"

        assert len(sm.history) == 100  # 50 round-trips x 2


class TestDeepVariableStorage:
    """Tests for deep/nested variables."""

    def test_complex_variables(self, tmp_path):
        """Complex nested variables should be stored and retrieved."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")
        reg.register_stage("test", tools=[])

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("test")

        deep_data = {
            "issue": {"id": 123, "title": "Bug fix", "tags": ["critical", "backend"]},
            "files": ["a.py", "b.py"],
            "nested": {"level1": {"level2": {"value": 42}}}
        }
        sm.set_var("context", deep_data)
        assert sm.get_var("context")["issue"]["id"] == 123
        assert sm.get_var("context")["nested"]["level1"]["level2"]["value"] == 42


class TestMaxRetries:
    """Tests for retry count limits."""

    def test_retry_count_tracking(self, tmp_path):
        """Retry count should be tracked per stage."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")

        reg.register_stage("s1", tools=[])
        reg.register_stage("s2", tools=[])
        reg.register_transition("s1", "s2", [{"never": "always blocked"}], on_fail="s1")

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("s1")

        for i in range(10):
            sm.transition_to("s2")
            assert sm.current_stage == "s1"
            assert sm.get_retry_count("s1") == i + 1


class TestTransitionToUnknown:
    """Tests for transitions to unknown/non-existent stages."""

    def test_transition_to_nonexistent(self, tmp_path):
        """Transition to non-existent stage should fail gracefully."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")
        reg.register_stage("only_stage", tools=[])

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("only_stage")

        ok, msgs = sm.transition_to("nonexistent")
        assert not ok
        assert any("No transition" in m or "Available" in m for m in msgs)

    def test_force_transition_to_unknown(self, tmp_path):
        """Force transition to unknown stage should work (no condition checks)."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
        reg.config_path = Path("nonexistent.yaml")
        reg.register_stage("known", tools=[])

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("known")

        ok, msgs = sm.force_transition_to("unknown")
        assert ok
        assert sm.current_stage == "unknown"
