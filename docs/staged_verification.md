# StageFlow — Staged Verification (Phase 37 task-122)

> Layers of increasing difficulty — an AI agent can rerun each layer independently.

## Quick Run

```bash
# Run all verification layers
pytest tests/test_staged_verification.py -v

# Run a single layer
pytest tests/test_staged_verification.py::TestLayer1_EngineComplete -v
pytest tests/test_staged_verification.py::TestLayer2_StatusOutput -v
# ... etc for layers 3-7
```

---

## Layer 1: Engine-only complete behavior

**What it proves**: `StateMachine.complete()` works correctly at the engine level.

```bash
pytest tests/test_staged_verification.py::TestLayer1_EngineComplete -v
```

**Expected output** (4 passed):
- `test_complete_succeeds_at_terminal_stage` — terminal stage (gamma with no outgoing transitions) → complete succeeds, current_stage=null, run_status=completed, final_stage=gamma
- `test_complete_fails_at_non_terminal_stage` — non-terminal stage (alpha has outgoing→beta) → complete fails with "not terminal"/"outgoing"
- `test_complete_fails_when_no_active_run` — uninitialized SM → complete fails with "no active run"
- `test_complete_prerequisites_layer1` — metadata: run_status, final_stage, completed_at, run_id preserved, history≥3 entries

---

## Layer 2: Status output after init, active, complete, reset

**What it proves**: Human and JSON status output correctly distinguishes the four states.

```bash
pytest tests/test_staged_verification.py::TestLayer2_StatusOutput -v
```

**Expected output** (4 passed):
- `test_status_after_init_no_active_run` — fresh `.stageflow/` project, `status` prints "No active run"
- `test_status_after_start_shows_active` — after `start`, `status` shows "alpha" (current stage)
- `test_status_json_after_complete` — `status --json` after complete: current_stage=null, run_status=completed, final_stage present, completed_at ISO-8601, variables.run_id present
- `test_status_after_reset_no_active_run` — after reset: "No active run"

---

## Layer 3: CLI complete from project root

**What it proves**: Full lifecycle via CLI from project root directory.

```bash
pytest tests/test_staged_verification.py::TestLayer3_CLICompleteFromRoot -v
```

**Expected output** (2 passed):
- `test_full_lifecycle_from_root` — status(no run) → start(alpha) → next --force(beta) → next(gamma) → complete → status JSON confirms completed
- `test_complete_refused_at_non_terminal_from_root` — start at alpha, complete refused (not terminal)

**Manual equivalent**:
```bash
mkdir /tmp/test_project && cd /tmp/test_project
mkdir -p .stageflow/config
# Write YAML_ABC to .stageflow/config/stages.yaml
stageflow status          # → No active run
stageflow start           # → starts at alpha
stageflow next --force    # → alpha → beta
stageflow next            # → beta → gamma (always: true)
stageflow complete        # → Run completed at stage 'gamma'
stageflow status --json   # → current_stage: null, run_status: completed
```

---

## Layer 4: CLI complete from nested directory

**What it proves**: CLI commands discover the project root from deeply nested subdirectories.

```bash
pytest tests/test_staged_verification.py::TestLayer4_CLICompleteFromNestedDir -v
```

**Expected output** (2 passed):
- `test_complete_from_nested_subdir` — start from root, run `next` and `complete` from `src/lib/deep/` → succeeds
- `test_status_from_nested_subdir` — start from root, `status` from `a/b/c/` shows "alpha"

**Manual equivalent**:
```bash
cd /tmp/test_project/src/lib/deep
stageflow status          # → shows current stage from ancestor .stageflow/
stageflow next --force    # → transitions the ancestor project
stageflow complete        # → completes the ancestor project
```

---

## Layer 5: Multi-repo isolation

**What it proves**: Completing a run in repo A does not touch repo B.

```bash
pytest tests/test_staged_verification.py::TestLayer5_MultiRepoIsolation -v
```

**Expected output** (2 passed):
- `test_multi_repo_complete_isolation` — repo_a completed → current_stage=null, run_status=completed; repo_b still active at alpha, run_status absent
- `test_source_checkout_not_affected` — isolated repo created/completed, source checkout state unchanged

**Manual equivalent**:
```bash
# Setup two independent projects
cd /tmp/repo_a && stageflow start
cd /tmp/repo_b && stageflow start
# Complete repo_a only
cd /tmp/repo_a
stageflow next --force && stageflow next && stageflow complete
# repo_a status shows completed
# repo_b status still shows alpha (active)
```

---

## Layer 6: Run-scoped artifact isolation

**What it proves**: Stale artifacts from an old completed run do not unlock a new run.

```bash
pytest tests/test_staged_verification.py::TestLayer6_RunScopedArtifacts -v
```

**Expected output** (2 passed):
- `test_stale_artifact_does_not_unlock_new_run` — run1 completes with artifacts; run2 starts fresh, stale run1 artifacts fail to satisfy run2's file_exists condition with `{{var.run_id}}` interpolation; creating run2's own artifacts allows transition
- `test_two_runs_independent_artifact_dirs` — run1 and run2 have separate artifact directories under `artifacts/runs/<different_run_ids>/`

**Manual equivalent**:
```bash
# Run 1
stageflow start                                    # creates run_id A
mkdir -p artifacts/runs/<run_id_A>/start
echo "ok" > artifacts/runs/<run_id_A>/start/gate.txt
stageflow next                                     # passes (A's artifact)
stageflow complete                                 # run completed

# Run 2
stageflow start                                    # creates run_id B ≠ A
stageflow next                                     # FAILS — A's artifacts don't match B's run_id
mkdir -p artifacts/runs/<run_id_B>/start
echo "ok" > artifacts/runs/<run_id_B>/start/gate.txt
stageflow next                                     # passes (B's artifact)
```

---

## Layer 7: Editor save gate

**What it proves**: Editor save is allowed after init/complete/reset, blocked during active run.

```bash
pytest tests/test_staged_verification.py::TestLayer7_EditorSaveGate -v
```

**Expected output** (5 passed):
- `test_save_allowed_after_init` — POST /api/project/save-config with current_stage=null → 200, saved=true
- `test_save_allowed_after_complete` — current_stage=null, run_status=completed → 200
- `test_save_allowed_after_reset` — current_stage=null → 200
- `test_save_blocked_during_active_run` — current_stage=alpha → 403, "active" in detail
- `test_save_blocked_at_terminal_stage_before_complete` — current_stage=gamma → 403 (active run, not yet completed)

**Manual equivalent** (with server running):
```bash
# Start editor server
python editor/server.py --dev &

# Save allowed (no active run)
curl -X POST http://localhost:8000/api/project/save-config \
  -H "Content-Type: application/json" \
  -d '{"yaml": "..."}'
# → 200 {"saved": true, ...}

# After stageflow start (active run)
curl -X POST http://localhost:8000/api/project/save-config ...
# → 403 {"detail": "Cannot save workflow config while a run is active..."}
```
