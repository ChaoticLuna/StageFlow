"""Verify that run-scoped {{var.run_id}} templates survive YAML round-trip.

Simulates the editor's js-yaml import/export cycle using Python's PyYAML,
which is semantically equivalent to js-yaml for this purpose. Confirms that
templated paths like artifacts/runs/{{var.run_id}}/review/changes_requested.md
are not escaped, resolved, or deleted during serialization.

Usage:
    python scripts/verify_editor_fidelity.py
    python scripts/verify_editor_fidelity.py --verbose
"""

import re
import sys
from pathlib import Path

import yaml as pyyaml

STAGES_YAML = Path(__file__).resolve().parent.parent / "stageflow" / "config" / "stages.yaml"

TEMPLATE = "{{var.run_id}}"
ESCAPED_FORMS = [
    "&#123;&#123;var.run_id&#125;&#125;",
    "{{&lbrace;&rbrace;var.run_id&lbrace;&rbrace;}}",
    r"\{\{var.run_id\}\}",
    "%7B%7Bvar.run_id%7D%7D",
]


def count_template(text: str) -> int:
    return text.count(TEMPLATE)


def check_escaped(text: str) -> list[str]:
    found = []
    for form in ESCAPED_FORMS:
        if form in text:
            found.append(form)
    return found


def verify() -> bool:
    print("=== Editor Fidelity Check: run-scoped {{var.run_id}} paths ===\n")

    original = STAGES_YAML.read_text(encoding="utf-8")
    original_count = count_template(original)
    print(f"1. Original stages.yaml: {original_count} {{var.run_id}} templates found")

    if original_count == 0:
        print("   [WARN] No templates in original -- nothing to verify")
        return False

    try:
        doc = pyyaml.safe_load(original)
    except Exception as e:
        print(f"   [FAIL] PyYAML parse error: {e}")
        return False

    re_serialized = pyyaml.dump(
        doc,
        indent=2,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    round_trip_count = count_template(re_serialized)
    print(f"2. After YAML round-trip: {round_trip_count} {{var.run_id}} templates found")

    if round_trip_count != original_count:
        print(f"   [FAIL] Template count mismatch: {original_count} -> {round_trip_count}")
        if "--verbose" in sys.argv or "-v" in sys.argv:
            print("\n--- Re-serialized YAML ---")
            print(re_serialized)
        return False

    escaped = check_escaped(re_serialized)
    if escaped:
        print(f"   [FAIL] Escaped/mangled templates found: {escaped}")
        return False
    print("3. No escaping or mangling detected")

    expected_paths = [
        "artifacts/runs/{{var.run_id}}/pick/issue_context.md",
        "artifacts/runs/{{var.run_id}}/analyze/findings.md",
        "artifacts/runs/{{var.run_id}}/plan/task_plan.md",
        "artifacts/runs/{{var.run_id}}/verify/test_results.md",
        "artifacts/runs/{{var.run_id}}/document/changelog.md",
        "artifacts/runs/{{var.run_id}}/review/changes_requested.md",
    ]
    all_found = True
    for path in expected_paths:
        if path in re_serialized:
            print(f"   [OK] {path}")
        else:
            print(f"   [MISSING] {path}")
            all_found = False

    if not all_found:
        print("\n   [FAIL] Some expected run-scoped paths missing from output")
        return False

    uuid_pattern = re.compile(
        r"artifacts/runs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )
    resolved = uuid_pattern.findall(re_serialized)
    if resolved:
        print(f"\n   [FAIL] Template was RESOLVED into actual UUID paths: {resolved}")
        return False

    print("\n4. No resolved UUIDs found -- template preserved as-is")
    print("\n=== ALL CHECKS PASSED ===")
    print("Run-scoped {{var.run_id}} templates survive YAML round-trip correctly.")
    return True


if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
