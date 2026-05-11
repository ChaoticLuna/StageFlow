"""Comprehensive tests for StageRegistry, Stage, and Transition classes."""

import pytest
import yaml

from stageflow.core.registry import StageRegistry, Stage, Transition


# ═══════════════════════════════════════════════════════════════════════════
# Loading from YAML config
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadFromYaml:
    def test_loads_all_stages(self, registry):
        assert len(registry.all_stages) == 3
        assert set(registry.stage_names) == {"start", "middle", "end"}

    def test_loads_all_transitions(self, registry):
        assert len(registry.all_transitions) == 2
        from_names = {t.from_stage for t in registry.all_transitions}
        to_names = {t.to_stage for t in registry.all_transitions}
        assert from_names == {"start", "middle"}
        assert to_names == {"middle", "end"}

    def test_stage_has_tools(self, registry):
        stage = registry.get_stage("start")
        assert stage.tools == ["Read", "Write"]

    def test_end_stage_empty_tools_means_allow_all(self, registry):
        stage = registry.get_stage("end")
        assert stage.tools == []

    def test_stage_description_from_meta(self, registry):
        stage = registry.get_stage("start")
        assert stage.description == "Starting stage"

    def test_transition_has_conditions(self, registry):
        transitions = registry.get_transitions_from("start")
        assert len(transitions) == 1
        assert len(transitions[0].conditions) == 1

    def test_nonexistent_config_returns_empty(self, temp_dir):
        reg = StageRegistry(str(temp_dir / "no_config.yaml"))
        assert len(reg.all_stages) == 0
        assert len(reg.all_transitions) == 0


# ═══════════════════════════════════════════════════════════════════════════
# get_stage
# ═══════════════════════════════════════════════════════════════════════════

class TestGetStage:
    def test_valid_stage_returns_stage_object(self, registry):
        stage = registry.get_stage("start")
        assert isinstance(stage, Stage)
        assert stage.name == "start"

    def test_invalid_stage_returns_none(self, registry):
        assert registry.get_stage("nonexistent") is None

    def test_empty_string_returns_none(self, registry):
        assert registry.get_stage("") is None


# ═══════════════════════════════════════════════════════════════════════════
# get_transitions_from
# ═══════════════════════════════════════════════════════════════════════════

class TestGetTransitionsFrom:
    def test_valid_source_returns_transitions(self, registry):
        transitions = registry.get_transitions_from("start")
        assert len(transitions) == 1
        assert transitions[0].from_stage == "start"
        assert transitions[0].to_stage == "middle"

    def test_invalid_source_returns_empty_list(self, registry):
        assert registry.get_transitions_from("nonexistent") == []

    def test_terminal_stage_has_no_outgoing(self, registry):
        assert registry.get_transitions_from("end") == []


# ═══════════════════════════════════════════════════════════════════════════
# get_transitions_to
# ═══════════════════════════════════════════════════════════════════════════

class TestGetTransitionsTo:
    def test_valid_target_returns_transitions(self, registry):
        transitions = registry.get_transitions_to("middle")
        assert len(transitions) == 1
        assert transitions[0].from_stage == "start"

    def test_invalid_target_returns_empty_list(self, registry):
        assert registry.get_transitions_to("nonexistent") == []

    def test_entry_stage_has_no_incoming(self, registry):
        assert registry.get_transitions_to("start") == []


# ═══════════════════════════════════════════════════════════════════════════
# get_next_stages
# ═══════════════════════════════════════════════════════════════════════════

class TestGetNextStages:
    def test_returns_correct_next_stage_names(self, registry):
        next_stages = registry.get_next_stages("start")
        assert next_stages == ["middle"]

    def test_terminal_stage_returns_empty(self, registry):
        assert registry.get_next_stages("end") == []

    def test_invalid_stage_returns_empty(self, registry):
        assert registry.get_next_stages("nowhere") == []


# ═══════════════════════════════════════════════════════════════════════════
# stage_names property
# ═══════════════════════════════════════════════════════════════════════════

class TestStageNames:
    def test_returns_sorted_names(self, registry):
        names = registry.stage_names
        assert names == sorted(names)
        assert names == ["end", "middle", "start"]

    def test_empty_registry_returns_empty_list(self, empty_registry):
        assert empty_registry.stage_names == []


# ═══════════════════════════════════════════════════════════════════════════
# register_stage
# ═══════════════════════════════════════════════════════════════════════════

class TestRegisterStage:
    def test_adds_new_stage(self, empty_registry):
        stage = empty_registry.register_stage("new_stage", tools=["ToolA", "ToolB"])
        assert stage.name == "new_stage"
        assert stage.tools == ["ToolA", "ToolB"]
        assert empty_registry.get_stage("new_stage") is not None

    def test_appears_in_stage_names(self, empty_registry):
        empty_registry.register_stage("extra")
        assert "extra" in empty_registry.stage_names

    def test_defaults_empty_tools_and_description(self, empty_registry):
        stage = empty_registry.register_stage("bare")
        assert stage.tools == []
        assert stage.description == ""

    def test_with_description(self, empty_registry):
        stage = empty_registry.register_stage(
            "described", tools=["Read"], description="A described stage"
        )
        assert stage.description == "A described stage"

    def test_overwrites_existing_stage(self, registry):
        original_tools = registry.get_stage("start").tools
        registry.register_stage("start", tools=["NewTool"])
        assert registry.get_stage("start").tools == ["NewTool"]
        assert registry.get_stage("start").tools != original_tools

    def test_extra_kwargs_stored(self, empty_registry):
        stage = empty_registry.register_stage("custom", custom_field="custom_value")
        # Extra kwargs are stored in Stage.extra
        assert stage.extra.get("custom_field") == "custom_value"
        # Verify in to_dict
        d = stage.to_dict()
        assert d.get("custom_field") == "custom_value"


# ═══════════════════════════════════════════════════════════════════════════
# unregister_stage
# ═══════════════════════════════════════════════════════════════════════════

class TestUnregisterStage:
    def test_removes_stage(self, registry):
        assert registry.get_stage("start") is not None
        result = registry.unregister_stage("start")
        assert result is True
        assert registry.get_stage("start") is None

    def test_returns_false_for_unknown_stage(self, registry):
        assert registry.unregister_stage("nonexistent") is False

    def test_cleans_up_transitions(self, registry):
        # Removing start should remove start->middle transition
        registry.unregister_stage("start")
        all_ts = registry.all_transitions
        for t in all_ts:
            assert t.from_stage != "start"
            assert t.to_stage != "start"
        # middle->end should still exist
        middle_ts = registry.get_transitions_from("middle")
        assert len(middle_ts) == 1
        assert middle_ts[0].to_stage == "end"

    def test_cleans_up_transitions_referencing_target(self, registry):
        # Removing middle should remove start->middle and middle->end
        registry.unregister_stage("middle")
        assert registry.get_transitions_from("start") == []
        assert registry.get_transitions_to("end") == []

    def test_only_removes_referenced_transitions(self, temp_dir):
        # Create config with 4 stages: A->B->C->D
        config = {
            "stages": [
                {"name": "s1", "tools": []},
                {"name": "s2", "tools": []},
                {"name": "s3", "tools": []},
                {"name": "s4", "tools": []},
            ],
            "transitions": [
                {"from": "s1", "to": "s2", "conditions": [{"always": True}]},
                {"from": "s2", "to": "s3", "conditions": [{"always": True}]},
                {"from": "s3", "to": "s4", "conditions": [{"always": True}]},
            ],
        }
        cfg = temp_dir / "chain.yaml"
        cfg.write_text(yaml.dump(config))
        reg = StageRegistry(str(cfg))

        # Remove s2; s1->s2 and s2->s3 should be gone, s3->s4 should remain
        reg.unregister_stage("s2")
        assert len(reg.all_transitions) == 1
        remaining = reg.all_transitions[0]
        assert remaining.from_stage == "s3"
        assert remaining.to_stage == "s4"


# ═══════════════════════════════════════════════════════════════════════════
# register_transition
# ═══════════════════════════════════════════════════════════════════════════

class TestRegisterTransition:
    def test_adds_new_transition(self, empty_registry):
        empty_registry.register_stage("A", tools=[])
        empty_registry.register_stage("B", tools=[])
        trans = empty_registry.register_transition("A", "B")
        assert trans.from_stage == "A"
        assert trans.to_stage == "B"
        assert trans.conditions == []

    def test_appears_in_get_transitions_from(self, empty_registry):
        empty_registry.register_stage("A", tools=[])
        empty_registry.register_stage("B", tools=[])
        empty_registry.register_transition("A", "B")
        assert len(empty_registry.get_transitions_from("A")) == 1

    def test_appears_in_get_transitions_to(self, empty_registry):
        empty_registry.register_stage("A", tools=[])
        empty_registry.register_stage("B", tools=[])
        empty_registry.register_transition("A", "B")
        assert len(empty_registry.get_transitions_to("B")) == 1

    def test_with_conditions(self, empty_registry):
        empty_registry.register_stage("X", tools=[])
        empty_registry.register_stage("Y", tools=[])
        trans = empty_registry.register_transition("X", "Y", conditions=[
            {"always": True},
            {"never": "test"},
        ])
        assert len(trans.conditions) == 2

    def test_with_on_fail(self, empty_registry):
        empty_registry.register_stage("X", tools=[])
        empty_registry.register_stage("Y", tools=[])
        trans = empty_registry.register_transition("X", "Y", on_fail="X")
        assert trans.on_fail == "X"

    def test_with_description(self, empty_registry):
        empty_registry.register_stage("X", tools=[])
        empty_registry.register_stage("Y", tools=[])
        trans = empty_registry.register_transition(
            "X", "Y", description="Test transition"
        )
        assert trans.description == "Test transition"

    def test_multiple_transitions_from_same_source(self, empty_registry):
        empty_registry.register_stage("A", tools=[])
        empty_registry.register_stage("B", tools=[])
        empty_registry.register_stage("C", tools=[])
        empty_registry.register_transition("A", "B")
        empty_registry.register_transition("A", "C")
        from_a = empty_registry.get_transitions_from("A")
        assert len(from_a) == 2


# ═══════════════════════════════════════════════════════════════════════════
# unregister_transition
# ═══════════════════════════════════════════════════════════════════════════

class TestUnregisterTransition:
    def test_removes_specific_transition(self, registry):
        # Add extra transition to make test meaningful
        registry.register_transition("start", "end", conditions=[{"always": True}])
        assert len(registry.get_transitions_from("start")) == 2

        result = registry.unregister_transition("start", "end")
        assert result is True
        from_start = registry.get_transitions_from("start")
        assert len(from_start) == 1
        assert from_start[0].to_stage == "middle"

    def test_returns_false_for_nonexistent(self, registry):
        assert registry.unregister_transition("start", "end") is False

    def test_cleans_up_from_and_to_maps(self, empty_registry):
        empty_registry.register_stage("X")
        empty_registry.register_stage("Y")
        empty_registry.register_transition("X", "Y")
        empty_registry.unregister_transition("X", "Y")
        assert empty_registry.get_transitions_from("X") == []
        assert empty_registry.get_transitions_to("Y") == []


# ═══════════════════════════════════════════════════════════════════════════
# validate
# ═══════════════════════════════════════════════════════════════════════════

class TestValidate:
    def test_valid_config_passes(self, registry):
        valid, errors = registry.validate()
        assert valid
        assert errors == []

    def test_empty_registry_passes(self, empty_registry):
        valid, errors = empty_registry.validate()
        assert valid
        assert errors == []

    def test_transition_from_unknown_stage(self, empty_registry):
        empty_registry.register_stage("A")
        # Manually insert a transition with bad from_stage
        empty_registry._transitions.append(Transition({
            "from": "NONEXISTENT", "to": "A"
        }))
        valid, errors = empty_registry.validate()
        assert not valid
        assert any("from unknown stage" in e for e in errors)

    def test_transition_to_unknown_stage(self, empty_registry):
        empty_registry.register_stage("A")
        empty_registry._transitions.append(Transition({
            "from": "A", "to": "NONEXISTENT"
        }))
        valid, errors = empty_registry.validate()
        assert not valid
        assert any("to unknown stage" in e for e in errors)

    def test_isolated_stage(self, empty_registry):
        empty_registry.register_stage("A")
        empty_registry.register_stage("B")
        empty_registry.register_stage("orphan")
        empty_registry.register_transition("A", "B")
        valid, errors = empty_registry.validate()
        assert not valid
        assert any("Isolated stage" in e for e in errors)
        assert any("orphan" in e for e in errors)

    def test_duplicate_transition(self, empty_registry):
        empty_registry.register_stage("A")
        empty_registry.register_stage("B")
        empty_registry.register_transition("A", "B")
        empty_registry.register_transition("A", "B")  # Duplicate
        valid, errors = empty_registry.validate()
        assert not valid
        assert any("Duplicate" in e for e in errors)

    def test_multiple_errors_aggregated(self, empty_registry):
        empty_registry.register_stage("A")
        empty_registry.register_stage("B")
        # Two errors: duplicate + isolated stage (B is isolated)
        empty_registry.register_transition("A", "A")
        empty_registry.register_transition("A", "A")
        valid, errors = empty_registry.validate()
        assert not valid
        # Should have at least: duplicate A->A, isolated B
        assert len(errors) >= 2


class TestValidateSchema:
    """Direct tests for validate_stages_config covering all error paths."""

    def test_non_dict_config(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config("not a dict")
        assert not valid
        assert any("must be a dict" in e for e in errors)

    def test_stages_not_list(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"stages": "not_a_list"})
        assert not valid
        assert any("stages" in e and "list" in e for e in errors)

    def test_stage_entry_not_dict(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"stages": ["string_instead_of_dict"]})
        assert not valid
        assert any("must be a dict" in e for e in errors)

    def test_stage_missing_name(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"stages": [{"tools": []}]})
        assert not valid
        assert any("name" in e for e in errors)

    def test_stage_name_not_string(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"stages": [{"name": 123}]})
        assert not valid
        assert any("name" in e for e in errors)

    def test_stage_tools_not_list(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"stages": [{"name": "a", "tools": "not_list"}]})
        assert not valid
        assert any("tools" in e and "list" in e for e in errors)

    def test_transitions_not_list(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"transitions": "not_a_list"})
        assert not valid
        assert any("transitions" in e and "list" in e for e in errors)

    def test_transition_entry_not_dict(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"transitions": ["string_instead_of_dict"]})
        assert not valid
        assert any("must be a dict" in e for e in errors)

    def test_transition_missing_from(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"transitions": [{"to": "b"}]})
        assert not valid
        assert any("from" in e for e in errors)

    def test_transition_missing_to(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"transitions": [{"from": "a"}]})
        assert not valid
        assert any("to" in e for e in errors)

    def test_transition_from_not_string(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"transitions": [{"from": 123, "to": "b"}]})
        assert not valid
        assert any("from" in e for e in errors)

    def test_transition_to_not_string(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"transitions": [{"from": "a", "to": 456}]})
        assert not valid
        assert any("to" in e for e in errors)

    def test_conditions_not_list(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config(
            {"transitions": [{"from": "a", "to": "b", "conditions": "not_list"}]}
        )
        assert not valid
        assert any("conditions" in e and "list" in e for e in errors)

    def test_on_fail_not_string(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config(
            {"transitions": [{"from": "a", "to": "b", "on_fail": 123}]}
        )
        assert not valid
        assert any("on_fail" in e and "string" in e for e in errors)

    def test_groups_not_list(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({"groups": "not_a_list"})
        assert not valid
        assert any("groups" in e and "list" in e for e in errors)

    def test_duplicate_transition_at_schema_level(self):
        from stageflow.core.schema import validate_stages_config
        valid, errors = validate_stages_config({
            "transitions": [
                {"from": "a", "to": "b"},
                {"from": "a", "to": "b"},
            ]
        })
        assert not valid
        assert any("duplicate" in e for e in errors)

    def test_valid_minimal_config(self):
        from stageflow.core.schema import validate_stages_config
        config = {
            "stages": [{"name": "a", "tools": ["Read"]}],
            "transitions": [{"from": "a", "to": "b"}],
        }
        valid, errors = validate_stages_config(config)
        assert valid
        assert errors == []

    def test_load_invalid_config_warns_through_registry(self, temp_dir):
        """lines 146-148: _load warns when schema validation fails."""
        import warnings
        invalid_yaml = temp_dir / "invalid.yaml"
        invalid_yaml.write_text(yaml.dump({
            "stages": [{"name": "dup", "tools": []}, {"name": "dup", "tools": []}],
        }))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            reg = StageRegistry(str(invalid_yaml))
            schema_warnings = [x for x in w if "config error" in str(x.message).lower() or "duplicate" in str(x.message).lower()]
        assert len(schema_warnings) >= 1, f"Expected schema warning, got {[str(x.message) for x in w]}"


# ═══════════════════════════════════════════════════════════════════════════
# Stage class
# ═══════════════════════════════════════════════════════════════════════════

class TestStageClass:
    def test_to_dict(self):
        stage = Stage("test", {"tools": ["A"], "description": "Desc"})
        d = stage.to_dict()
        assert d["name"] == "test"
        assert d["tools"] == ["A"]
        assert d["description"] == "Desc"

    def test_to_dict_with_max_iterations(self):
        """line 36: to_dict includes max_iterations when set."""
        stage = Stage("test", {"tools": ["A"], "max_iterations": 5})
        d = stage.to_dict()
        assert d["max_iterations"] == 5

    def test_allow_tools_alias(self):
        stage = Stage("test", {"allow_tools": ["X", "Y"]})
        assert stage.tools == ["X", "Y"]

    def test_description_from_meta(self):
        stage = Stage("test", {"meta": {"description": "Meta desc"}})
        assert stage.description == "Meta desc"

    def test_repr(self):
        stage = Stage("example", {"tools": ["T1", "T2", "T3"]})
        r = repr(stage)
        assert "example" in r
        assert "3" in r

    def test_extra_fields(self):
        stage = Stage("test", {"tools": [], "custom_field": "value", "another": 42})
        assert stage.extra["custom_field"] == "value"
        assert stage.extra["another"] == 42
        # Standard keys should NOT be in extra
        assert "name" not in stage.extra
        assert "tools" not in stage.extra


# ═══════════════════════════════════════════════════════════════════════════
# Transition class
# ═══════════════════════════════════════════════════════════════════════════

class TestTransitionClass:
    def test_basic_properties(self):
        trans = Transition({
            "from": "A", "to": "B",
            "conditions": [{"always": True}],
        })
        assert trans.from_stage == "A"
        assert trans.to_stage == "B"
        assert len(trans.conditions) == 1
        assert trans.on_fail is None

    def test_evaluate_conditions(self):
        trans = Transition({
            "from": "A", "to": "B",
            "conditions": [{"always": True}],
        })
        ok, msgs = trans.evaluate(".")
        assert ok

    def test_evaluate_failing_condition(self):
        trans = Transition({
            "from": "A", "to": "B",
            "conditions": [{"never": "blocked"}],
        })
        ok, msgs = trans.evaluate(".")
        assert not ok

    def test_evaluate_multiple_conditions(self):
        trans = Transition({
            "from": "A", "to": "B",
            "conditions": [
                {"always": True},
                {"always": True},
                {"always": True},
            ],
        })
        ok, msgs = trans.evaluate(".")
        assert ok
        assert len(msgs) == 3

    def test_evaluate_stops_at_first_failure(self):
        trans = Transition({
            "from": "A", "to": "B",
            "conditions": [
                {"always": True},
                {"never": "stop"},
                {"always": True},  # Never reached
            ],
        })
        ok, msgs = trans.evaluate(".")
        assert not ok
        assert len(msgs) == 2  # Stopped after second condition

    def test_with_on_fail(self):
        trans = Transition({
            "from": "A", "to": "B",
            "on_fail": "A",
        })
        assert trans.on_fail == "A"

    def test_to_dict(self):
        trans = Transition({
            "from": "A", "to": "B",
            "conditions": [{"always": True}],
            "on_fail": "A",
            "description": "Test edge",
        })
        d = trans.to_dict()
        assert d["from"] == "A"
        assert d["to"] == "B"
        assert d["conditions"] == [{"always": True}]
        assert d["on_fail"] == "A"
        assert d["description"] == "Test edge"

    def test_repr(self):
        trans = Transition({"from": "A", "to": "B", "conditions": [{"a": 1}, {"b": 2}]})
        r = repr(trans)
        assert "A" in r
        assert "B" in r
        assert "2" in r  # conditions count


# ═══════════════════════════════════════════════════════════════════════════
# to_dict on registry
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistryToDict:
    def test_to_dict_contains_stages_and_transitions(self, registry):
        d = registry.to_dict()
        assert "stages" in d
        assert "transitions" in d
        assert len(d["stages"]) == 3
        assert len(d["transitions"]) == 2

    def test_to_dict_round_trip_structure(self, registry):
        d = registry.to_dict()
        # Stages should have names
        stage_names = [s["name"] for s in d["stages"]]
        assert "start" in stage_names
        assert "middle" in stage_names
        assert "end" in stage_names


# ═══════════════════════════════════════════════════════════════════════════
# repr
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistryRepr:
    def test_repr_includes_counts(self, registry):
        r = repr(registry)
        assert "3" in r  # stages count
        assert "2" in r  # transitions count
        assert "StageRegistry" in r

    def test_empty_registry_repr(self, empty_registry):
        r = repr(empty_registry)
        assert "0" in r


# ============================================================================
# Config inheritance (extends)
# ============================================================================

class TestConfigExtends:
    def test_child_inherits_parent_stages(self, temp_dir):
        parent_path = temp_dir / "parent.yaml"
        parent_path.write_text(yaml.dump({
            "stages": [
                {"name": "base_analyze", "tools": ["Read"], "meta": {"description": "from parent"}},
                {"name": "base_plan", "tools": ["Grep"]},
            ],
            "transitions": [
                {"from": "base_analyze", "to": "base_plan", "conditions": [{"always": True}]},
            ],
        }))
        child_path = temp_dir / "child.yaml"
        child_path.write_text(yaml.dump({
            "extends": "parent.yaml",
            "stages": [
                {"name": "custom_stage", "tools": ["Write"]},
            ],
            "transitions": [
                {"from": "base_plan", "to": "custom_stage", "conditions": [{"always": True}]},
            ],
        }))
        reg = StageRegistry(str(child_path))
        assert "base_analyze" in reg.all_stages
        assert "base_plan" in reg.all_stages
        assert "custom_stage" in reg.all_stages
        assert len(reg.all_stages) == 3

    def test_child_overrides_parent_stage(self, temp_dir):
        parent_path = temp_dir / "parent.yaml"
        parent_path.write_text(yaml.dump({
            "stages": [
                {"name": "shared", "tools": ["Read"], "meta": {"description": "parent version"}},
            ],
        }))
        child_path = temp_dir / "child.yaml"
        child_path.write_text(yaml.dump({
            "extends": "parent.yaml",
            "stages": [
                {"name": "shared", "tools": ["Write", "Edit"], "meta": {"description": "child version"}},
            ],
        }))
        reg = StageRegistry(str(child_path))
        assert len(reg.all_stages) == 1
        stage = reg.get_stage("shared")
        assert stage.tools == ["Write", "Edit"]
        assert stage.description == "child version"

    def test_child_overrides_parent_transition(self, temp_dir):
        parent_path = temp_dir / "parent.yaml"
        parent_path.write_text(yaml.dump({
            "stages": [
                {"name": "start", "tools": ["Read"]},
                {"name": "end", "tools": []},
            ],
            "transitions": [
                {"from": "start", "to": "end", "conditions": [{"always": True}],
                 "description": "parent transition"},
            ],
        }))
        child_path = temp_dir / "child.yaml"
        child_path.write_text(yaml.dump({
            "extends": "parent.yaml",
            "transitions": [
                {"from": "start", "to": "end", "conditions": [{"never": "blocked"}],
                 "description": "child version"},
            ],
        }))
        reg = StageRegistry(str(child_path))
        transitions = reg.get_transitions_from("start")
        assert len(transitions) == 1
        assert transitions[0].description == "child version"
        assert len(transitions[0].conditions) == 1
        assert "never" in transitions[0].conditions[0]

    def test_extends_missing_parent_warns(self, temp_dir):
        child_path = temp_dir / "child.yaml"
        child_path.write_text(yaml.dump({
            "extends": "nonexistent.yaml",
            "stages": [{"name": "only_me", "tools": ["Read"]}],
        }))
        with pytest.warns(UserWarning, match="extended config not found"):
            reg = StageRegistry(str(child_path))
        assert len(reg.all_stages) == 1
        assert "only_me" in reg.all_stages

    def test_extends_depth_limit(self, temp_dir):
        a = temp_dir / "a.yaml"
        b = temp_dir / "b.yaml"
        c = temp_dir / "c.yaml"
        a.write_text(yaml.dump({"stages": [{"name": "deep_a", "tools": ["Read"]}]}))
        b.write_text(yaml.dump({"extends": "a.yaml", "stages": [{"name": "deep_b", "tools": ["Grep"]}]}))
        c.write_text(yaml.dump({"extends": "b.yaml", "stages": [{"name": "deep_c", "tools": ["Write"]}]}))
        reg = StageRegistry(str(c))
        assert "deep_a" in reg.all_stages
        assert "deep_b" in reg.all_stages
        assert "deep_c" in reg.all_stages
        assert len(reg.all_stages) == 3

    def test_merge_configs_static_method(self):
        parent = {"stages": [{"name": "a", "tools": ["Read"]}]}
        child = {"stages": [{"name": "b", "tools": ["Write"]}]}
        merged = StageRegistry._merge_configs(parent, child)
        assert len(merged["stages"]) == 2
        names = {s["name"] for s in merged["stages"]}
        assert names == {"a", "b"}

    def test_extends_with_groups(self, temp_dir):
        parent_path = temp_dir / "parent.yaml"
        parent_path.write_text(yaml.dump({
            "stages": [{"name": "stage1", "tools": ["Read"]}],
            "groups": ["core"],
        }))
        child_path = temp_dir / "child.yaml"
        child_path.write_text(yaml.dump({
            "extends": "parent.yaml",
            "stages": [{"name": "stage2", "tools": ["Write"]}],
            "groups": ["extras"],
        }))
        reg = StageRegistry(str(child_path))
        assert "stage1" in reg.all_stages
        assert "stage2" in reg.all_stages

    def test_extends_depth_exceeded_warns(self, temp_dir):
        """lines 123-125: depth > _MAX_EXTENDS_DEPTH triggers warning."""
        import warnings
        # Create 7 files: 1 → 2 → 3 → 4 → 5 → 6 → 7 (depth 6 > 5 limit at file 7)
        paths = []
        for i in range(7):
            p = temp_dir / f"chain_{i}.yaml"
            paths.append(p)
        # Write innermost first
        paths[0].write_text(yaml.dump({"stages": [{"name": f"s0", "tools": ["Read"]}]}))
        for i in range(1, 7):
            paths[i].write_text(yaml.dump({"extends": f"chain_{i-1}.yaml", "stages": [{"name": f"s{i}", "tools": ["Read"]}]}))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            reg = StageRegistry(str(paths[6]))
            depth_warnings = [x for x in w if "extends" in str(x.message) and "depth exceeded" in str(x.message)]
        assert len(depth_warnings) >= 1, f"Expected depth exceeded warning, got {[str(x.message) for x in w]}"

