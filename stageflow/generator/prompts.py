"""Prompt templates for different workflow domains.

Each template provides role context, stage guidance, condition tips,
and an example YAML snippet to steer the LLM towards high-quality output.

Usage:
    from stageflow.generator.prompts import get_template, list_templates

    t = get_template("CI_CD")
    prompt = t.format_prompt(description="Build, test, deploy pipeline")
"""

from __future__ import annotations

from typing import Dict, List

TEMPLATES: Dict[str, "PromptTemplate"] = {}


class PromptTemplate:
    """A domain-specific prompt template for workflow generation."""

    def __init__(
        self,
        name: str,
        label: str,
        role: str,
        guide: str,
        example_yaml: str,
        example_desc: str = "",
    ):
        self.name = name
        self.label = label
        self.role = role
        self.guide = guide
        self.example_yaml = example_yaml
        self.example_desc = example_desc

    def format_prompt(self, condition_reference: str, description: str) -> str:
        """Build the full user prompt for this template."""
        return (
            f"{self.role}\n\n"
            f"{self.guide}\n\n"
            f"{condition_reference}\n\n"
            f"## Example\n"
            f"{self.example_desc}\n"
            f"```yaml\n{self.example_yaml}\n```\n\n"
            f"## Task\n"
            f"Design a StageFlow workflow for this description:\n\n"
            f"{description}\n\n"
            f"Output the stages.yaml now."
        )


def register_template(
    name: str,
    label: str,
    role: str,
    guide: str,
    example_yaml: str,
    example_desc: str = "",
) -> PromptTemplate:
    """Register a new prompt template and return it."""
    t = PromptTemplate(name, label, role, guide, example_yaml, example_desc)
    TEMPLATES[name.upper()] = t
    return t


def get_template(name: str) -> PromptTemplate:
    """Get a template by name (case-insensitive). Raises KeyError if not found."""
    key = name.upper()
    if key not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES))
        raise KeyError(f"Unknown template '{name}'. Available: {available}")
    return TEMPLATES[key]


def list_templates() -> List[PromptTemplate]:
    """Return all registered templates."""
    return list(TEMPLATES.values())


# ── Template Definitions ────────────────────────────────────────────────

register_template(
    name="GENERIC",
    label="Generic Workflow",
    role="You are a StageFlow workflow designer. Design a general-purpose stage workflow.",
    guide="""## Guidance
- Create 3-7 stages that model the described process.
- Use descriptive snake_case stage names.
- Provide a clear linear path from the first stage to a terminal stage ("done").
- Include rollback paths (on_fail) for stages that produce artifacts.
- Use appropriate Claude Code tools for each stage (Read, Write, Edit, Grep, Bash, etc.).
- Use conditions like `file_exists`, `file_contains`, and `shell_test` to gate transitions.""",
    example_yaml="""stages:
  - name: analyze
    tools: [Read, Grep, Glob, WebSearch]
    meta:
      description: "Analyze the issue and identify root cause"
  - name: plan
    tools: [Read, Write, Edit]
    meta:
      description: "Design the fix and write a task plan"
  - name: implement
    tools: [Read, Edit, Write, Bash(git *)]
    meta:
      description: "Implement the code changes"
  - name: done
    tools: []
    meta:
      description: "Workflow complete"
transitions:
  - from: analyze
    to: plan
    conditions:
      - file_exists: artifacts/analyze/findings.md
    on_fail: analyze
  - from: plan
    to: implement
    conditions:
      - file_exists: artifacts/plan/task_plan.md
    on_fail: plan
  - from: implement
    to: done
    conditions:
      - git_status: {op: dirty}""",
    example_desc="Example — a simple 4-stage issue resolution workflow:",
)

register_template(
    name="CI_CD",
    label="CI/CD Pipeline",
    role="You are a CI/CD pipeline designer. Design a StageFlow workflow for continuous integration and delivery.",
    guide="""## CI/CD Guidance
- Typical stages: lint, build, test, deploy, verify, rollback.
- Use `shell_test` conditions to run build/test commands and check exit codes.
- Use `command_exists` to verify required tools are available (npm, docker, kubectl, etc.).
- Use `file_exists` to check for build artifacts (dist/, binaries, docker images).
- Use `http_status` to verify deployments (health check endpoints).
- Use `time_range` to restrict deployments to business hours.
- Include rollback paths (on_fail) for deploy stages.
- Use `Bash(npm *)`, `Bash(docker *)`, `Bash(kubectl *)` for tool-specific commands.
- Use `file_size` to verify artifact sizes are reasonable.""",
    example_yaml="""stages:
  - name: checkout
    tools: [Bash(git *)]
    meta:
      description: "Check out the repository"
  - name: lint
    tools: [Bash(npm *), Bash(eslint *), Read]
    meta:
      description: "Run linters and static analysis"
  - name: test
    tools: [Bash(pytest *), Bash(npm test*), Bash(go test*)]
    meta:
      description: "Run the test suite"
  - name: build
    tools: [Bash(npm *), Bash(docker *), Write]
    meta:
      description: "Build artifacts and container images"
  - name: deploy
    tools: [Bash(kubectl *), Bash(helm *), Bash(docker *)]
    meta:
      description: "Deploy to staging/production"
  - name: verify
    tools: [Bash(curl *), Read, WebFetch]
    meta:
      description: "Verify deployment health"
  - name: done
    tools: []
    meta:
      description: "Pipeline complete"
transitions:
  - from: checkout
    to: lint
    conditions:
      - git_status: {op: clean}
  - from: lint
    to: test
    conditions:
      - shell_test: {command: "eslint src/ --max-warnings 0", op: exit_zero}
    on_fail: lint
  - from: test
    to: build
    conditions:
      - shell_test: {command: "pytest -q", op: exit_zero}
    on_fail: test
  - from: build
    to: deploy
    conditions:
      - file_exists: dist/
    on_fail: build
  - from: deploy
    to: verify
    conditions:
      - time_range: {after: "07:00", before: "19:00"}
    on_fail: build
  - from: verify
    to: done
    conditions:
      - http_status: {url: "https://api.example.com/health", expected_status: 200}""",
    example_desc="Example — a 7-stage CI/CD pipeline with deploy time gates:",
)

register_template(
    name="CODE_REVIEW",
    label="Code Review",
    role="You are a code review workflow designer. Design a StageFlow workflow for collaborative code review.",
    guide="""## Code Review Guidance
- Typical stages: submit, review, discuss, revise, approve, merge.
- Use `git_status` to check branch state and PR status.
- Use `diff_contains` to verify security gates (e.g., no eval/exec in diff).
- Use `file_contains` to check review checklists and approval status.
- Use `file_size` to gate on PR size (prevent overly large changes).
- Use `glob_count` to check number of changed files.
- Use `all_of` to combine multiple review requirements (tests + lint + review).
- Use `shell_test` with `gh` CLI to check PR state, CI status.
- Include revise → review retry loops with on_fail.
- Use `command_exists` to verify required tools (gh, git).""",
    example_yaml="""stages:
  - name: submit
    tools: [Bash(git *), Bash(gh *), Write, Edit]
    meta:
      description: "Submit code for review (push branch, create PR)"
  - name: review
    tools: [Read, Grep, Glob, Bash(git *), Bash(gh *)]
    meta:
      description: "Review the code changes"
  - name: revise
    tools: [Edit, Write, Bash(git *)]
    meta:
      description: "Address review feedback"
  - name: approve
    tools: [Bash(gh *), Bash(git *)]
    meta:
      description: "Approve and merge the PR"
  - name: done
    tools: []
    meta:
      description: "Review complete, PR merged"
transitions:
  - from: submit
    to: review
    conditions:
      - shell_test: {command: "gh pr view --json state", op: output_contains, expected: "OPEN"}
      - all_of:
          conditions:
            - glob_count: {pattern: "**/*.py", max: 20}
            - file_size: {path: .git/HEAD, max: 1048576}
  - from: review
    to: approve
    conditions:
      - file_exists: artifacts/review/approval.md
      - diff_contains: {pattern: 'eval(', op: not_contains}
    on_fail: revise
  - from: review
    to: revise
    conditions:
      - file_exists: artifacts/review/changes_requested.md
  - from: revise
    to: review
    conditions:
      - git_status: {op: dirty}
  - from: approve
    to: done
    conditions:
      - shell_test: {command: "gh pr view --json mergedAt", op: exit_zero}""",
    example_desc="Example — a 5-stage code review workflow with security gate:",
)

register_template(
    name="DATA_PIPELINE",
    label="Data Pipeline",
    role="You are a data pipeline designer. Design a StageFlow workflow for data extraction, transformation, and loading.",
    guide="""## Data Pipeline Guidance
- Typical stages: extract, transform, validate, load, report.
- Use `file_exists` to check for source data files.
- Use `file_size` to verify data volumes are reasonable.
- Use `json_schema` to validate structured data against schemas.
- Use `json_count` to verify row counts and record volumes.
- Use `json_field` / `yaml_field` to check metadata fields.
- Use `glob_count` to verify file counts in partitioned datasets.
- Use `hash_file` to verify data integrity after transfer.
- Use `shell_test` for running SQL/Spark/Script jobs.
- Use `compare_files` to verify consistency across replicas.
- Include validation → transform retry loops for data quality issues.""",
    example_yaml="""stages:
  - name: extract
    tools: [Read, Bash(python *), Bash(curl *)]
    meta:
      description: "Extract data from source systems"
  - name: transform
    tools: [Bash(python *), Bash(spark-submit *), Write]
    meta:
      description: "Transform and clean the data"
  - name: validate
    tools: [Read, Bash(python *), Grep]
    meta:
      description: "Validate data quality and integrity"
  - name: load
    tools: [Bash(python *), Bash(dbt *), Write]
    meta:
      description: "Load data into the warehouse"
  - name: report
    tools: [Write, Bash(python *)]
    meta:
      description: "Generate pipeline run report"
  - name: done
    tools: []
    meta:
      description: "Pipeline complete"
transitions:
  - from: extract
    to: transform
    conditions:
      - file_exists: data/raw/
      - glob_count: {pattern: "data/raw/**/*", min: 1}
    on_fail: extract
  - from: transform
    to: validate
    conditions:
      - file_exists: data/processed/
    on_fail: transform
  - from: validate
    to: load
    conditions:
      - json_schema: {path: data/processed/schema.json, schema_path: schemas/output.json}
      - json_count: {path: data/processed/output.json, min: 1}
    on_fail: transform
  - from: validate
    to: transform
    conditions:
      - file_exists: data/processed/quality_issues.md
  - from: load
    to: report
    conditions:
      - shell_test: {command: "python -c 'import dbt; print(1)'", op: exit_zero}
    on_fail: load
  - from: report
    to: done
    conditions:
      - file_exists: artifacts/pipeline_report.md""",
    example_desc="Example — a 6-stage data pipeline with quality gates:",
)
