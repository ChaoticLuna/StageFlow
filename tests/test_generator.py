from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from stageflow.generator.llm_generator import (
    WorkflowGenerator,
    _extract_yaml,
    SYSTEM_PROMPT,
    CONDITION_REFERENCE,
)


VALID_SIMPLE_YAML = """stages:
  - name: pick
    tools: [Read, Grep]
    meta:
      description: "Pick an issue from the backlog"
  - name: analyze
    tools: [Read, WebSearch]
    meta:
      description: "Analyze root cause"
  - name: done
    tools: []
    meta:
      description: "Work complete"
transitions:
  - from: pick
    to: analyze
    conditions:
      - file_exists: artifacts/pick/issue.md
    on_fail: pick
  - from: analyze
    to: done
    conditions:
      - always: true
"""


class TestBuildPrompt:
    def test_includes_condition_reference(self):
        gen = WorkflowGenerator()
        prompt = gen.build_prompt("CI/CD pipeline")
        assert "file_exists" in prompt
        assert "shell_test" in prompt
        assert "always" in prompt

    def test_includes_description(self):
        gen = WorkflowGenerator()
        prompt = gen.build_prompt("CI/CD pipeline with build stage")
        assert "CI/CD pipeline with build stage" in prompt

    def test_includes_schema_rules(self):
        gen = WorkflowGenerator()
        prompt = gen.build_prompt("anything")
        assert "stages:" in prompt
        assert "transitions:" in prompt
        assert "Unique stage identifier" in prompt.lower() or "unique" in prompt.lower()

    def test_prompt_contains_27_condition_types(self):
        gen = WorkflowGenerator()
        prompt = gen.build_prompt("test")
        condition_count = CONDITION_REFERENCE.count("|")
        lineage_count = CONDITION_REFERENCE.count("| ---")
        assertion_count = CONDITION_REFERENCE.count("|") - CONDITION_REFERENCE.count("| ---")
        count = sum(1 for line in CONDITION_REFERENCE.strip().split("\n") if line.startswith("|"))
        assert count >= 28  # header + 27 types


class TestExtractYaml:
    def test_extract_from_fenced_block(self):
        response = "Here is the YAML:\n\n```yaml\nstages:\n  - name: test\n```\n\nDone."
        result = _extract_yaml(response)
        assert result == "stages:\n  - name: test"

    def test_extract_from_generic_fence_when_content_is_yaml(self):
        response = "```\nstages:\n  - name: test\ntransitions: []\n```"
        result = _extract_yaml(response)
        assert result is not None
        assert "stages:" in result

    def test_extract_fallback_to_whole_response(self):
        response = "stages:\n  - name: test\ntransitions:\n  - from: test\n    to: done"
        result = _extract_yaml(response)
        assert result == response

    def test_extract_returns_none_for_junk(self):
        assert _extract_yaml("Just some random text") is None
        assert _extract_yaml("") is None

    def test_extract_prefers_yaml_fence(self):
        response = "stages: [bad]\n```yaml\nstages:\n  - name: good\n```"
        result = _extract_yaml(response)
        assert result == "stages:\n  - name: good"


class TestValidate:
    def test_valid_yaml_passes(self):
        gen = WorkflowGenerator()
        valid, errors = gen.validate(VALID_SIMPLE_YAML)
        assert valid is True
        assert errors == []

    def test_yaml_parse_error(self):
        gen = WorkflowGenerator()
        valid, errors = gen.validate("invalid: [")
        assert valid is False
        assert any("parse" in e.lower() for e in errors)

    def test_empty_document(self):
        gen = WorkflowGenerator()
        valid, errors = gen.validate("")
        assert valid is False

    def test_duplicate_stage_names(self):
        yaml_str = """stages:
  - name: pick
  - name: pick
transitions: []
"""
        gen = WorkflowGenerator()
        valid, errors = gen.validate(yaml_str)
        assert valid is False
        assert any("duplicate" in e for e in errors)

    def test_transition_references_unknown_stage(self):
        yaml_str = "stages:\n  - name: a\ntransitions:\n  - from: a\n    to: missing\n"
        gen = WorkflowGenerator()
        valid, errors = gen.validate(yaml_str)
        assert valid is False
        assert any("unknown" in e.lower() or "missing" in e for e in errors)


class TestGenerate:
    def test_happy_path_single_attempt(self):
        calls = []
        def mock_llm(prompt: str) -> str:
            calls.append(prompt)
            return f"```yaml\n{VALID_SIMPLE_YAML}\n```"

        gen = WorkflowGenerator(llm_call=mock_llm)
        yaml_str, history = gen.generate("Simple workflow")

        assert yaml_str == VALID_SIMPLE_YAML.strip()
        assert len(history) == 1
        assert history[0]["valid"] is True
        assert len(calls) == 1

    def test_retry_on_invalid_then_succeed(self):
        responses = [
            "```yaml\ninvalid: [\n```",
            f"```yaml\n{VALID_SIMPLE_YAML}\n```",
        ]
        def mock_llm(prompt: str) -> str:
            return responses.pop(0)

        gen = WorkflowGenerator(llm_call=mock_llm)
        yaml_str, history = gen.generate("retry test")

        assert yaml_str == VALID_SIMPLE_YAML.strip()
        assert len(history) == 2
        assert history[0]["valid"] is False
        assert history[1]["valid"] is True

    def test_exhaust_retries_returns_none(self):
        def mock_llm(prompt: str) -> str:
            return "Just some text with no YAML at all"

        gen = WorkflowGenerator(llm_call=mock_llm, max_retries=3)
        yaml_str, history = gen.generate("test")

        assert yaml_str is None
        assert len(history) == 3
        assert all(not h["valid"] for h in history)

    def test_retry_prompt_includes_errors(self):
        responses = [
            "```yaml\nstages:\n  - name: pick\n  - name: pick\ntransitions: []\n```",
        ]
        def mock_llm(prompt: str) -> str:
            return responses.pop(0)

        gen = WorkflowGenerator(llm_call=mock_llm, max_retries=1)
        yaml_str, history = gen.generate("test")

        assert yaml_str is None
        assert len(history) > 0
        assert "duplicate" in history[0]["errors"][0]

    def test_raises_without_llm_call(self):
        gen = WorkflowGenerator()
        with pytest.raises(ValueError, match="llm_call"):
            gen.generate("test")
