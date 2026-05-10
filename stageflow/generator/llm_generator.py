"""Natural language to stages.yaml generator using an LLM.

Usage:
    from stageflow.generator.llm_generator import WorkflowGenerator

    gen = WorkflowGenerator(llm_call=my_llm_function)
    yaml_str, history = gen.generate("CI/CD pipeline with build, test, deploy")
"""

from __future__ import annotations

import re
from typing import Callable, Optional

import yaml

from stageflow.core.schema import validate_stages_config
from stageflow.core.registry import StageRegistry

CONDITION_REFERENCE = """## Built-in Condition Types (27)

| type | description | params |
|------|-------------|--------|
| always | Always passes | (none) |
| never | Always fails | reason (string) |
| file_exists | File exists on disk | path (string) |
| file_not_exists | File does NOT exist | path (string) |
| file_contains | File contains regex pattern | path (string), pattern (regex) |
| file_not_contains | File does NOT contain pattern | path (string), pattern (regex) |
| json_field | Check JSON field | path (string), field (string), op (exists/not_empty/equals/not_equals), value? |
| yaml_field | Check YAML field | path (string), field (string), op (exists/not_empty/equals/not_equals), value? |
| shell_test | Run shell command | command (string), op (exit_zero/exit_nonzero/output_contains/output_empty), expected? |
| python_expr | Evaluate Python expression | expr (string, must return bool) |
| env_var | Check environment variable | name (string), op (equals/not_equals/exists/not_exists), value? |
| all_of | All sub-conditions must pass | conditions (list of condition dicts) |
| any_of | Any sub-condition can pass | conditions (list of condition dicts) |
| not | Negate a sub-condition | condition (single condition dict) |
| git_status | Check git working tree | op (clean/dirty/branch/branch_equals), value? |
| http_status | Check HTTP endpoint | url (string), method (GET/POST/HEAD), expected_status (int), timeout (int) |
| time_range | Current time within range | after (HH:MM), before (HH:MM) |
| compare_files | Compare two files | path1 (string), path2 (string), op (identical/different/size_equal/checksum_equal) |
| json_schema | Validate JSON against schema | path (string), schema_path (string) |
| hash_file | Check file hash | path (string), expected (string), algo (sha256/md5/sha1) |
| file_age | Check file modification time | path (string), max_age (seconds) |
| file_size | Check file size in bytes | path (string), min?, max? |
| glob_count | Count files matching glob | pattern (string), min?, max? |
| retry | Retry sub-condition with delay | condition (dict), max_attempts (int), delay (seconds) |
| command_exists | CLI command available | command (string) |
| diff_contains | Git diff pattern check | pattern (regex), op (contains/not_contains) |
| json_count | Count JSON elements | path (string), field?, min?, max? |

Condition format in YAML:
  - Simple (single param): `condition_type: value` (e.g., `file_exists: artifacts/analyze/findings.md`)
  - Complex (multiple params): `condition_type: { param1: val1, param2: val2 }`
  - Meta-conditions: `all_of: { conditions: [ {file_exists: x}, {shell_test: {command: pytest, op: exit_zero}} ] }`
  - `on_fail` specifies a fallback stage if conditions fail (optional)
"""

SYSTEM_PROMPT = """You are a StageFlow workflow designer. Given a natural language description of a workflow,
produce a valid stages.yaml configuration.

## Output Format
Output ONLY the YAML, enclosed in ```yaml ... ``` fences. Do not include any other text.

## Schema
```yaml
stages:
  - name: stage_id          # required: unique stage identifier (snake_case)
    tools:                  # optional: Claude Code tool names (empty = all allowed)
      - Read
      - Bash(git *)
    meta:
      description: "..."    # optional: human-readable description
    on_enter:               # optional: lifecycle hooks
      - shell: "command"
      - python: "code"
    on_exit:                # optional: lifecycle hooks
      - python: "code"

transitions:
  - from: source_stage
    to: target_stage
    description: "..."      # optional: description of this transition
    conditions:             # optional: list of conditions (empty = always passes)
      - file_exists: path/to/artifact
      - file_contains:
          path: path/to/file
          pattern: "regex"
    on_fail: fallback_stage # optional: where to go if conditions fail
```

## Rules
1. Every stage MUST have a unique `name`.
2. Every transition MUST reference existing stages for `from`, `to`, and `on_fail`.
3. Only use condition types from the reference above.
4. Terminal stages (like "done", "complete", "finished", "end") should have empty tools.
5. Prefer specific tools over wildcards. Use `Bash(git *)` for git operations, not `Bash(*)`.
6. The first stage in the list is the starting point.
7. Provide at least one transition path from start to a terminal stage.

{condition_reference}
"""

USER_PROMPT = """Design a StageFlow workflow for the following description:

{description}

Output the stages.yaml now."""

RETRY_PROMPT = """Your previous YAML output had validation errors:

{errors}

Please fix these errors and output the corrected YAML in ```yaml ... ``` fences."""


def _extract_yaml(response: str) -> Optional[str]:
    """Extract YAML content from an LLM response. Looks for ```yaml fences first."""
    match = re.search(r"```yaml\s*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", response, re.DOTALL)
    if match:
        inner = match.group(1).strip()
        if inner.startswith("stages:") or inner.startswith("transitions:"):
            return inner
    if "stages:" in response:
        return response.strip()
    return None


class WorkflowGenerator:
    """Generate stages.yaml from a natural language description using an LLM.

    The LLM is invoked via a pluggable `llm_call` function.
    The generator validates output and retries up to `max_retries` times
    with error feedback.
    """

    def __init__(
        self,
        llm_call: Optional[Callable[[str], str]] = None,
        max_retries: int = 3,
    ):
        self.llm_call = llm_call
        self.max_retries = max_retries

    def build_prompt(self, description: str) -> str:
        """Build the full prompt for the LLM (system + user)."""
        system = SYSTEM_PROMPT.format(condition_reference=CONDITION_REFERENCE)
        user = USER_PROMPT.format(description=description)
        return f"{system}\n\n{user}"

    def extract_yaml(self, response: str) -> Optional[str]:
        """Extract YAML content from an LLM response string."""
        return _extract_yaml(response)

    def validate(self, yaml_str: str) -> tuple[bool, list[str]]:
        """Validate a YAML string as a StageFlow config. Returns (valid, errors)."""
        try:
            doc = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            return False, [f"YAML parse error: {e}"]

        if doc is None:
            return False, ["YAML document is empty"]
        if not isinstance(doc, dict):
            return False, ["YAML must be a mapping with 'stages' and 'transitions' keys"]

        valid, errors = validate_stages_config(doc)
        if not valid:
            return False, errors

        try:
            reg = StageRegistry("__nonexistent__.yaml")
            for s in doc.get("stages", []):
                reg.register_stage(s["name"], tools=s.get("tools", []),
                                  description=s.get("meta", {}).get("description", ""))
            for t in doc.get("transitions", []):
                reg.register_transition(t["from"], t["to"],
                                        conditions=t.get("conditions", []),
                                        on_fail=t.get("on_fail"))
            valid, reg_errors = reg.validate()
            errors.extend(reg_errors)
        except Exception as e:
            return False, [f"Registry validation failed: {e}"]

        return len(errors) == 0, errors

    def generate(self, description: str) -> tuple[Optional[str], list[dict]]:
        """Generate stages.yaml from a description.

        Returns (yaml_string_or_None, history).
        Each history entry: {attempt, yaml, valid, errors, prompt}.
        """
        history: list[dict] = []

        if not self.llm_call:
            raise ValueError(
                "No llm_call function provided. Set generator.llm_call or pass to constructor."
            )

        prompt = self.build_prompt(description)

        for attempt in range(1, self.max_retries + 1):
            response = self.llm_call(prompt)
            yaml_str = _extract_yaml(response)
            entry: dict = {
                "attempt": attempt,
                "raw_response": response,
                "yaml": yaml_str,
                "valid": False,
                "errors": [],
            }

            if yaml_str is None:
                entry["errors"] = ["Could not extract YAML from response"]
                history.append(entry)
                prompt = f"{response}\n\n{RETRY_PROMPT.format(errors='No YAML found. Please enclose your YAML in ```yaml ... ``` fences.')}"
                continue

            valid, errors = self.validate(yaml_str)

            if not valid:
                entry["errors"] = errors
                history.append(entry)
                prompt = f"{response}\n\n{RETRY_PROMPT.format(errors=chr(10).join(f'- {e}' for e in errors))}"
                continue

            entry["valid"] = True
            history.append(entry)
            return yaml_str, history

        return None, history
