"""Phase 27 acceptance verification — run-scoped artifacts, resume semantics, editor fidelity.

Runs the targeted verification set for Phase 27/28 stabilisation work.
On Windows, sets TEMP, TMP, and PYTEST_DEBUG_TEMPROOT to repo .tmp to avoid
temp-directory permission failures. Each pytest suite gets a unique --basetemp
subdirectory to avoid cross-suite file locking on Windows.

Usage:
    python scripts/phase27_acceptance.py
    python scripts/phase27_acceptance.py --verbose
    python scripts/phase27_acceptance.py --json
"""

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGETS = {
    "Engine — Run Identity": [
        "tests/test_engine.py::TestRunIdentity",
        "tests/test_engine.py::TestCleanArtifacts",
        "tests/test_engine.py::TestResumeSemantics",
    ],
    "E2E — Run-Scoped Artifacts": [
        "tests/test_e2e.py::TestRunScopedArtifacts",
    ],
    "Hybrid — Prompts & Status": [
        "tests/test_hybrid.py::TestRunScopedPrompts",
        "tests/test_hybrid.py::TestStagePrompts",
        "tests/test_hybrid.py::TestStatus",
    ],
    "CLI — Resume & Reset": [
        "tests/test_main.py::TestStageflowCLI::test_resume_keeps_run_id_in_new_session",
        "tests/test_main.py::TestStageflowCLI::test_status_run_id_changes_after_reset",
        "tests/test_main.py::TestStageflowCLI::test_status_run_id_preserved_after_reset_reuse",
        "tests/test_main.py::TestMainInProcess",
    ],
    "Demo — Sequential Two-Task": [
        "tests/test_run_demo.py",
    ],
}


def setup_environment():
    """Point temp dirs at repo .tmp on Windows, clean all suite-NN dirs first."""
    if sys.platform == "win32":
        tmp_dir = REPO_ROOT / ".tmp"
        tmp_dir.mkdir(exist_ok=True)
        # Clean all temp content from previous runs (suite-NN and pytest-of-*)
        for name in os.listdir(str(tmp_dir)):
            entry = tmp_dir / name
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
        os.environ["TEMP"] = str(tmp_dir)
        os.environ["TMP"] = str(tmp_dir)
        os.environ["PYTEST_DEBUG_TEMPROOT"] = str(tmp_dir)

    # Fix UnicodeEncodeError on Windows GBK stdout
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )


def run_pytest(suite_name: str, targets: list[str], index: int) -> tuple[bool, str, str]:
    """Run pytest with a unique --basetemp per suite to avoid cross-run locking."""
    basetemp = REPO_ROOT / ".tmp" / f"suite-{index:02d}"
    cmd = [
        sys.executable, "-m", "pytest",
        "-v",
        "--tb=short",
        "--no-header",
        "--basetemp", str(basetemp),
        *targets,
    ]
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode == 0, result.stdout, result.stderr


def run_editor_fidelity() -> tuple[bool, str]:
    """Run the editor fidelity verification script."""
    script = REPO_ROOT / "scripts" / "verify_editor_fidelity.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0, result.stdout


def main() -> int:
    setup_environment()

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    json_out = "--json" in sys.argv

    if not json_out:
        print("=" * 64)
        print("Phase 27 Acceptance Verification")
        print(f"Temp root: {os.environ.get('TEMP', 'default')}")
        print("=" * 64)

    results: dict[str, dict] = {}
    all_pass = True

    # 1. Pytest suites (each with unique --basetemp)
    for idx, (suite_name, targets) in enumerate(TARGETS.items()):
        if not json_out:
            print(f"\n-- {suite_name} --")
        passed, stdout, stderr = run_pytest(suite_name, targets, idx)

        summary_line = ""
        for line in stdout.strip().splitlines():
            if "passed" in line or "failed" in line or "error" in line:
                summary_line = line.strip()

        results[suite_name] = {
            "passed": passed,
            "summary": summary_line,
            "targets": targets,
        }

        if verbose and not json_out:
            print(stdout)
            if stderr.strip():
                print(stderr, file=sys.stderr)
        elif not json_out:
            if passed:
                print(f"  [PASS] {summary_line}")
            else:
                print(f"  [FAIL] {summary_line}")
                print(stdout)
                if stderr.strip():
                    print(stderr, file=sys.stderr)

        if not passed:
            all_pass = False

    # 2. Editor fidelity
    if not json_out:
        print(f"\n-- Editor Fidelity --")
    ed_pass, ed_stdout = run_editor_fidelity()
    results["Editor Fidelity"] = {
        "passed": ed_pass,
        "summary": "ALL CHECKS PASSED" if ed_pass else "FAILED",
        "targets": ["scripts/verify_editor_fidelity.py"],
    }

    if verbose and not json_out:
        print(ed_stdout)
    elif not json_out:
        if ed_pass:
            for line in ed_stdout.strip().splitlines():
                if "PASSED" in line or "OK" in line or "===" in line:
                    print(f"  [OK] {line.strip('=').strip()}")
            else:
                print("  [PASS] ALL CHECKS PASSED")
        else:
            print(f"  [FAIL]")
            print(ed_stdout)

    if not ed_pass:
        all_pass = False

    # 3. Summary
    if json_out:
        import json
        print(json.dumps(results, indent=2))
    else:
        print("\n" + "=" * 64)
        print("RESULTS SUMMARY")
        print("=" * 64)
        for suite_name, info in results.items():
            status = "PASS" if info["passed"] else "FAIL"
            marker = "[OK]" if info["passed"] else "[XX]"
            print(f"  {marker} {suite_name}: {status}")
            if info["summary"]:
                print(f"       {info['summary']}")

        print()
        if all_pass:
            print("-- ALL CHECKS PASSED --")
            print("Phase 27 acceptance criteria satisfied.")
        else:
            print("-- SOME CHECKS FAILED --")
            print("Review failures above before proceeding.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
