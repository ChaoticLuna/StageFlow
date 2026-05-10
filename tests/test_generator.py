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
from stageflow.generator.prompts import (
    get_template,
    list_templates,
    PromptTemplate,
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

    def test_generate_with_template(self):
        def mock_llm(prompt: str) -> str:
            return f"```yaml\n{VALID_SIMPLE_YAML}\n```"

        gen = WorkflowGenerator(llm_call=mock_llm)
        yaml_str, history = gen.generate("build pipeline", template="CI_CD")
        assert yaml_str is not None
        assert len(history) == 1

    def test_generate_uses_default_template(self):
        def mock_llm(prompt: str) -> str:
            return f"```yaml\n{VALID_SIMPLE_YAML}\n```"

        gen = WorkflowGenerator(llm_call=mock_llm, template="CI_CD")
        yaml_str, history = gen.generate("build pipeline")
        assert yaml_str is not None

    def test_build_prompt_with_unknown_template_falls_back(self):
        gen = WorkflowGenerator()
        prompt = gen.build_prompt("test", template="NONEXISTENT")
        assert "stages:" in prompt


class TestTemplates:
    def test_all_four_registered(self):
        templates = list_templates()
        names = {t.name for t in templates}
        assert names == {"GENERIC", "CI_CD", "CODE_REVIEW", "DATA_PIPELINE"}

    def test_get_template_ci_cd(self):
        t = get_template("CI_CD")
        assert isinstance(t, PromptTemplate)
        assert t.name == "CI_CD"
        assert "CI/CD" in t.role or "CI/CD" in t.label

    def test_get_template_code_review(self):
        t = get_template("CODE_REVIEW")
        assert "review" in t.role.lower() or "review" in t.label.lower()

    def test_get_template_data_pipeline(self):
        t = get_template("DATA_PIPELINE")
        assert "data" in t.role.lower() or "data" in t.label.lower()

    def test_get_template_generic(self):
        t = get_template("GENERIC")
        assert isinstance(t, PromptTemplate)

    def test_get_template_case_insensitive(self):
        t = get_template("ci_cd")
        assert t.name == "CI_CD"

    def test_unknown_template_raises(self):
        with pytest.raises(KeyError, match="Unknown template"):
            get_template("NONEXISTENT")

    def test_format_prompt_includes_everything(self):
        t = get_template("CI_CD")
        desc = "Test the build pipeline"
        prompt = t.format_prompt(CONDITION_REFERENCE, desc)
        assert desc in prompt
        assert "file_exists" in prompt
        assert "stages:" in prompt
        assert "transitions:" in prompt
        assert "checkout" in prompt.lower() or "lint" in prompt.lower()

    def test_ci_cd_example_is_valid_yaml(self):
        t = get_template("CI_CD")
        gen = WorkflowGenerator()
        valid, _ = gen.validate(t.example_yaml)
        assert valid is True

    def test_code_review_example_is_valid_yaml(self):
        t = get_template("CODE_REVIEW")
        gen = WorkflowGenerator()
        valid, _ = gen.validate(t.example_yaml)
        assert valid is True

    def test_data_pipeline_example_is_valid_yaml(self):
        t = get_template("DATA_PIPELINE")
        gen = WorkflowGenerator()
        valid, _ = gen.validate(t.example_yaml)
        assert valid is True

    def test_generic_example_is_valid_yaml(self):
        t = get_template("GENERIC")
        gen = WorkflowGenerator()
        valid, _ = gen.validate(t.example_yaml)
        assert valid is True
