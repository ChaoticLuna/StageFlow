# Access Policy — Layered Verification Guide

> Phase 39 task-134 | 2026-05-16

Verification of fine-grained file access control across every layer of the stack.
Each layer increases difficulty. Run them in order — a failure at layer N does not
block investigation of layer N+1.

## Quick Verification (all layers)

```bash
pytest tests/test_access_layered.py -v
```

44 tests across 8 layers.

---

## Layer 1 — Schema Load

**What**: YAML with `access.read` and `access.write` sections passes schema
validation and is correctly parsed into `Stage.extra`.

### Commands & Expected Results

```bash
# Test: access.read.allow is valid
pytest tests/test_access_layered.py::TestLayer1SchemaLoad::test_read_allow_is_valid -v
# Expected: PASSED — stage.extra["access"]["read"]["allow"] == ["artifacts/**", "*.md"]

# Test: access.read with allow + deny is valid
pytest tests/test_access_layered.py::TestLayer1SchemaLoad::test_read_allow_and_deny_is_valid -v
# Expected: PASSED — deny list preserved

# Test: access.write.allow is valid
pytest tests/test_access_layered.py::TestLayer1SchemaLoad::test_write_allow_is_valid -v
# Expected: PASSED

# Test: both read + write in same stage
pytest tests/test_access_layered.py::TestLayer1SchemaLoad::test_both_read_and_write_is_valid -v
# Expected: PASSED

# Test: stage without access has empty extra
pytest tests/test_access_layered.py::TestLayer1SchemaLoad::test_missing_access_has_empty_extra -v
# Expected: PASSED — stage.extra == {}

# Test: to_dict() includes access
pytest tests/test_access_layered.py::TestLayer1SchemaLoad::test_access_round_trips_through_to_dict -v
# Expected: PASSED — reg.to_dict()["stages"][0]["access"] is present
```

---

## Layer 2 — Policy Helper (AccessPolicy in Isolation)

**What**: `AccessPolicy.check_read()` / `check_write()` / `check_search()` work
correctly without any registry, state machine, or hook infrastructure.

### Commands & Expected Results

```bash
# Allow: file matches glob in allow list
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_read_allowed_in_allow_list -v
# Expected: PASSED — "README.md" matches "*.md" in allow list

# Block: file not in allow list
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_read_blocked_outside_allow_list -v
# Expected: PASSED — "secret.env" blocked, reason contains "not in allow"

# Deny overrides allow
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_deny_overrides_allow -v
# Expected: PASSED — "config.env" blocked despite allow: ["**"]

# Write: allowed under artifacts/**
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_write_allowed -v
# Expected: PASSED

# Write: blocked outside artifacts/**
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_write_blocked -v
# Expected: PASSED

# No policy → everything allowed
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_no_policy_allows_everything -v
# Expected: PASSED

# Empty policy dict → everything allowed
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_empty_policy_allows_everything -v
# Expected: PASSED

# Only deny → unlisted files allowed
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_only_deny_allows_unlisted -v
# Expected: PASSED — "public/file.md" allowed, "secrets/key.pem" blocked

# Variable interpolation
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_variable_interpolation -v
# Expected: PASSED — {{var.run_id}} resolved to "abc123"

# Search root allowed under allow pattern
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_search_root_allowed_under_allow -v
# Expected: PASSED

# Search root blocked when not covered
pytest tests/test_access_layered.py::TestLayer2PolicyHelper::test_search_root_blocked_when_not_covered -v
# Expected: PASSED
```

---

## Layer 3 — StageGuard Programmatic Check

**What**: `StageGuard.check()` enforces access policy when called in-process
(with a populated state file).

### Commands & Expected Results

```bash
# Read allowed by access policy
pytest tests/test_access_layered.py::TestLayer3StageGuard::test_read_allowed -v
# Expected: PASSED — guard.check("Read", {"file_path": "README.md"}) returns True

# Read blocked by access policy
pytest tests/test_access_layered.py::TestLayer3StageGuard::test_read_blocked -v
# Expected: PASSED — guard.check("Read", {"file_path": "secret.env"}) returns False

# Write allowed in artifacts
pytest tests/test_access_layered.py::TestLayer3StageGuard::test_write_allowed -v
# Expected: PASSED

# Write blocked outside artifacts
pytest tests/test_access_layered.py::TestLayer3StageGuard::test_write_blocked -v
# Expected: PASSED

# Tool not in allowlist still blocked (even if access would allow)
pytest tests/test_access_layered.py::TestLayer3StageGuard::test_tool_not_in_allowlist_still_blocked -v
# Expected: PASSED — Write blocked because not in tools: ["Read"]

# No access policy → tool allowlist only
pytest tests/test_access_layered.py::TestLayer3StageGuard::test_no_policy_uses_tool_allowlist_only -v
# Expected: PASSED
```

---

## Layer 4 — Hook from Project Root

**What**: `stageflow hook` (CLI entrypoint) enforces access policy from stdin JSON
when invoked from the project root directory.

### Commands & Expected Results

```bash
# Read allowed via hook
pytest tests/test_access_layered.py::TestLayer4HookFromRoot::test_read_allowed_in_artifacts -v
# Expected: PASSED — stdout contains "allow"

# Read blocked via hook
pytest tests/test_access_layered.py::TestLayer4HookFromRoot::test_read_blocked_on_secret -v
# Expected: PASSED — exit code != 0, stdout contains "block"

# Write allowed in artifacts (via hook)
pytest tests/test_access_layered.py::TestLayer4HookFromRoot::test_write_allowed_in_artifacts -v
# Expected: PASSED

# Write blocked outside artifacts (via hook)
pytest tests/test_access_layered.py::TestLayer4HookFromRoot::test_write_blocked_outside_artifacts -v
# Expected: PASSED

# Grep with path in allowed dir
pytest tests/test_access_layered.py::TestLayer4HookFromRoot::test_grep_allowed_in_allowed_dir -v
# Expected: PASSED

# Grep without path -> fail closed
pytest tests/test_access_layered.py::TestLayer4HookFromRoot::test_grep_without_path_blocked -v
# Expected: PASSED
```

### Manual Commands

```bash
# Set up a project with access policy
stageflow init
cat > .stageflow/config/stages.yaml << 'EOF'
stages:
  - name: secured
    tools: [Read, Write, Edit, Grep, Glob]
    meta:
      description: "Stage with access policy"
    access:
      read:
        allow: ["artifacts/**", "*.md"]
        deny: ["*.env"]
      write:
        allow: ["artifacts/**"]
transitions: []
EOF

stageflow start secured

# Allowed read
echo '{"tool_name":"Read","tool_input":{"file_path":"README.md"}}' | stageflow hook
# Expected: {"decision":"allow","message":"..."}

# Blocked read
echo '{"tool_name":"Read","tool_input":{"file_path":".env"}}' | stageflow hook
# Expected: {"decision":"block","message":"access.read: '.env' denied by '*.env'"}

# Allowed write
echo '{"tool_name":"Write","tool_input":{"file_path":"artifacts/out.txt"}}' | stageflow hook
# Expected: {"decision":"allow","message":"..."}

# Blocked write
echo '{"tool_name":"Write","tool_input":{"file_path":"src/main.py"}}' | stageflow hook
# Expected: {"decision":"block","message":"access.write: 'src/main.py' not in allow list"}
```

---

## Layer 5 — Hook from Nested CWD

**What**: `stageflow hook` correctly resolves relative file paths against the
current working directory, not the project root, then normalises them to
project-relative paths before evaluating the access policy.

### Commands & Expected Results

```bash
# Relative path resolved from nested dir
pytest tests/test_access_layered.py::TestLayer5HookNestedCwd::test_relative_path_resolves_from_nested_dir -v
# Expected: PASSED — from src/components/, "Button.tsx" resolves correctly

# Blocked from nested dir outside scope
pytest tests/test_access_layered.py::TestLayer5HookNestedCwd::test_read_blocked_from_nested_dir_outside_scope -v
# Expected: PASSED — from tests/, "test_secret.py" -> blocked
```

### Manual Commands

```bash
mkdir -p src/components
cd src/components

echo '{"tool_name":"Read","tool_input":{"file_path":"Button.tsx"}}' | stageflow hook
# Expected: {"decision":"allow","message":"..."}
# (resolves to src/components/Button.tsx -> allowed by src/**)

echo '{"tool_name":"Read","tool_input":{"file_path":"../../.env"}}' | stageflow hook
# Expected: {"decision":"block","message":"...escapes project root..."}
```

---

## Layer 6 — Windows / Absolute Paths

**What**: Absolute paths outside the project root and relative path escapes
(`../../etc/passwd`) are always blocked regardless of the access policy.

### Commands & Expected Results

```bash
# Path escape blocked (via hook)
pytest tests/test_access_layered.py::TestLayer6WindowsAbsolutePaths::test_path_escape_blocked -v
# Expected: PASSED — "../../etc/passwd" blocked despite allow: ["**"]

# Absolute path outside blocked (via hook)
pytest tests/test_access_layered.py::TestLayer6WindowsAbsolutePaths::test_absolute_path_outside_blocked -v
# Expected: PASSED — "C:/Windows/System32/config/SAM" blocked

# Absolute path escape (via AccessPolicy directly)
pytest tests/test_access_layered.py::TestLayer6WindowsAbsolutePaths::test_policy_absolute_path_escape -v
# Expected: PASSED — "/etc/passwd" blocked by _normalize_path

# Relative escape (via AccessPolicy directly)
pytest tests/test_access_layered.py::TestLayer6WindowsAbsolutePaths::test_policy_relative_escape -v
# Expected: PASSED — "../../etc/passwd" blocked by _normalize_path
```

---

## Layer 7 — YAML Round-Trip Preservation

**What**: Serialising stages (to YAML) and parsing them back preserves the
`access` configuration via the `Stage.extra` mechanism.

### Commands & Expected Results

```bash
# Access.read preserved through load
pytest tests/test_access_layered.py::TestLayer7YamlRoundTrip::test_preserves_read_access -v
# Expected: PASSED — allow/deny lists intact in stage.extra["access"]["read"]

# Access.write preserved through load
pytest tests/test_access_layered.py::TestLayer7YamlRoundTrip::test_preserves_write_access -v
# Expected: PASSED

# Empty access dict preserved
pytest tests/test_access_layered.py::TestLayer7YamlRoundTrip::test_preserves_empty_access -v
# Expected: PASSED — stage.extra["access"] == {}

# Access preserved alongside hooks
pytest tests/test_access_layered.py::TestLayer7YamlRoundTrip::test_preserves_access_with_other_fields -v
# Expected: PASSED — on_enter/on_exit + access both preserved

# No access -> not in to_dict
pytest tests/test_access_layered.py::TestLayer7YamlRoundTrip::test_no_access_in_to_dict_when_no_access -v
# Expected: PASSED — "access" not in stage.to_dict()
```

---

## Layer 8 — Old-Workflow Backward Compatibility

**What**: Stages **without** an `access` field keep their original behaviour:
tool allowlist enforcement, unrestricted stages, and no path-level policy.

### Commands & Expected Results

```bash
# No access policy -> tool allowlist only
pytest tests/test_access_layered.py::TestLayer8BackwardCompat::test_no_policy_reads_all_work -v
# Expected: PASSED — Read allowed on any path

# Write blocked because tool not in allowlist
pytest tests/test_access_layered.py::TestLayer8BackwardCompat::test_no_policy_write_still_needs_tool_allow -v
# Expected: PASSED — Write blocked (not in tools: ["Read"])

# Unrestricted stage (empty tools) allows everything
pytest tests/test_access_layered.py::TestLayer8BackwardCompat::test_no_policy_allows_anything_when_tools_empty -v
# Expected: PASSED

# StageGuard: no policy -> checks only tool allowlist
pytest tests/test_access_layered.py::TestLayer8BackwardCompat::test_guard_check_no_policy -v
# Expected: PASSED
```

---

## Architecture Summary

```
Layer 8  Backward compat       stageflow hook (no access field)
  |
Layer 7  YAML round-trip       Stage.extra <-> YAML serialisation
  |
Layer 6  Windows/Absolute      path normalisation blocks escapes
  |
Layer 5  Nested CWD            Path.cwd() relative resolution
  |
Layer 4  Hook from root        cmd_hook() -> AccessPolicy
  |
Layer 3  StageGuard.check()    guard.py -> AccessPolicy
  |
Layer 2  AccessPolicy          check_read / check_write / check_search
  |
Layer 1  Schema load           StageRegistry -> Stage.extra["access"]
```

All layers use the same `AccessPolicy` class. `StageGuard` and `cmd_hook` differ
only in how they resolve the working directory (project root vs. `Path.cwd()`).
