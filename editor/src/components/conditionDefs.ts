export interface ParamDef {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "textarea" | "json";
  options?: string[];
  default?: unknown;
  placeholder?: string;
  required?: boolean;
}

export interface ConditionTypeDef {
  type: string;
  label: string;
  description: string;
  params: ParamDef[];
}

type RawDefs = Record<string, { label: string; description: string; params: ParamDef[] }>;

const defs: RawDefs = {
  always: {
    label: "Always",
    description: "Always passes (no-op condition)",
    params: [],
  },
  never: {
    label: "Never",
    description: "Always fails with a reason",
    params: [{ name: "reason", label: "Reason", type: "text", placeholder: "Why this transition is blocked" }],
  },
  file_exists: {
    label: "File Exists",
    description: "Check that a file exists on disk",
    params: [{ name: "path", label: "File path", type: "text", placeholder: "artifacts/runs/{{var.run_id}}/analyze/findings.md", required: true }],
  },
  file_not_exists: {
    label: "File Not Exists",
    description: "Check that a file does NOT exist",
    params: [{ name: "path", label: "File path", type: "text", placeholder: "artifacts/runs/{{var.run_id}}/temp/draft.md", required: true }],
  },
  file_contains: {
    label: "File Contains",
    description: "Check that a file contains a pattern (regex)",
    params: [
      { name: "path", label: "File path", type: "text", placeholder: "artifacts/runs/{{var.run_id}}/analyze/findings.md", required: true },
      { name: "pattern", label: "Pattern (regex)", type: "text", placeholder: "## Root Cause", required: true },
    ],
  },
  file_not_contains: {
    label: "File Not Contains",
    description: "Check that a file does NOT contain a pattern",
    params: [
      { name: "path", label: "File path", type: "text", placeholder: "src/main.py", required: true },
      { name: "pattern", label: "Pattern (regex)", type: "text", placeholder: "eval\\(", required: true },
    ],
  },
  json_field: {
    label: "JSON Field",
    description: "Check a field in a JSON file",
    params: [
      { name: "path", label: "JSON file path", type: "text", required: true },
      { name: "field", label: "Field name", type: "text", required: true },
      { name: "op", label: "Operator", type: "select", options: ["exists", "not_empty", "equals", "not_equals"], default: "exists" },
      { name: "value", label: "Expected value", type: "text", placeholder: "(only for equals/not_equals)" },
    ],
  },
  yaml_field: {
    label: "YAML Field",
    description: "Check a field in a YAML file",
    params: [
      { name: "path", label: "YAML file path", type: "text", required: true },
      { name: "field", label: "Field name", type: "text", required: true },
      { name: "op", label: "Operator", type: "select", options: ["exists", "not_empty", "equals", "not_equals"], default: "exists" },
      { name: "value", label: "Expected value", type: "text", placeholder: "(only for equals/not_equals)" },
    ],
  },
  shell_test: {
    label: "Shell Test",
    description: "Run a shell command and check the result",
    params: [
      { name: "command", label: "Command", type: "text", placeholder: "pytest -q", required: true },
      { name: "op", label: "Check", type: "select", options: ["exit_zero", "exit_nonzero", "output_contains", "output_empty"], default: "exit_zero" },
      { name: "expected", label: "Expected output", type: "text", placeholder: "(only for output_contains)" },
    ],
  },
  python_expr: {
    label: "Python Expression",
    description: "Evaluate a Python expression (must return bool)",
    params: [{ name: "expr", label: "Expression", type: "textarea", placeholder: "1 + 1 == 2", required: true }],
  },
  env_var: {
    label: "Environment Variable",
    description: "Check an environment variable",
    params: [
      { name: "name", label: "Variable name", type: "text", placeholder: "CI", required: true },
      { name: "op", label: "Operator", type: "select", options: ["equals", "not_equals", "exists", "not_exists"], default: "exists" },
      { name: "value", label: "Expected value", type: "text", placeholder: "(only for equals/not_equals)" },
    ],
  },
  all_of: {
    label: "All Of (AND)",
    description: "All sub-conditions must pass",
    params: [{ name: "conditions", label: "Sub-conditions", type: "json", placeholder: '[{"always": true}, {"file_exists": "x.md"}]', required: true }],
  },
  any_of: {
    label: "Any Of (OR)",
    description: "At least one sub-condition must pass",
    params: [{ name: "conditions", label: "Sub-conditions", type: "json", placeholder: '[{"always": true}, {"file_exists": "x.md"}]', required: true }],
  },
  not: {
    label: "Not (Negate)",
    description: "Negate a sub-condition",
    params: [{ name: "condition", label: "Condition to negate", type: "json", placeholder: '{"file_exists": "x.md"}', required: true }],
  },
  git_status: {
    label: "Git Status",
    description: "Check the git working tree status",
    params: [
      { name: "op", label: "Check", type: "select", options: ["clean", "dirty", "branch", "branch_equals"], default: "clean" },
      { name: "value", label: "Branch name", type: "text", placeholder: "(only for branch/branch_equals)" },
    ],
  },
  http_status: {
    label: "HTTP Status",
    description: "Check an HTTP endpoint response",
    params: [
      { name: "url", label: "URL", type: "text", placeholder: "https://api.example.com/health", required: true },
      { name: "method", label: "Method", type: "select", options: ["GET", "POST", "HEAD"], default: "GET" },
      { name: "expected_status", label: "Expected status", type: "number", default: 200 },
      { name: "timeout", label: "Timeout (seconds)", type: "number", default: 10 },
    ],
  },
  time_range: {
    label: "Time Range",
    description: "Check that the current time is within a range",
    params: [
      { name: "after", label: "After (HH:MM)", type: "text", placeholder: "09:00", required: true },
      { name: "before", label: "Before (HH:MM)", type: "text", placeholder: "17:00", required: true },
    ],
  },
  compare_files: {
    label: "Compare Files",
    description: "Compare two files",
    params: [
      { name: "path1", label: "File 1 path", type: "text", required: true },
      { name: "path2", label: "File 2 path", type: "text", required: true },
      { name: "op", label: "Comparison", type: "select", options: ["identical", "different", "size_equal", "checksum_equal"], default: "identical" },
    ],
  },
  json_schema: {
    label: "JSON Schema",
    description: "Validate a JSON file against a JSON Schema",
    params: [
      { name: "path", label: "Data file path", type: "text", required: true },
      { name: "schema_path", label: "Schema file path", type: "text", required: true },
    ],
  },
  hash_file: {
    label: "Hash File",
    description: "Check a file hash",
    params: [
      { name: "path", label: "File path", type: "text", required: true },
      { name: "expected", label: "Expected hash", type: "text", required: true },
      { name: "algo", label: "Algorithm", type: "select", options: ["sha256", "md5", "sha1"], default: "sha256" },
    ],
  },
  file_age: {
    label: "File Age",
    description: "Check the last modification time of a file",
    params: [
      { name: "path", label: "File path", type: "text", required: true },
      { name: "max_age", label: "Max age (seconds)", type: "number", default: 300 },
    ],
  },
  file_size: {
    label: "File Size",
    description: "Check the size of a file in bytes",
    params: [
      { name: "path", label: "File path", type: "text", required: true },
      { name: "min", label: "Min size (bytes)", type: "number", placeholder: "1"},
      { name: "max", label: "Max size (bytes)", type: "number", placeholder: "1048576"},
    ],
  },
  glob_count: {
    label: "Glob Count",
    description: "Count files matching a glob pattern",
    params: [
      { name: "pattern", label: "Glob pattern", type: "text", placeholder: "**/*.py", required: true },
      { name: "min", label: "Min count", type: "number", placeholder: "1"},
      { name: "max", label: "Max count", type: "number", placeholder: "100"},
    ],
  },
  retry: {
    label: "Retry",
    description: "Retry a sub-condition with delay",
    params: [
      { name: "condition", label: "Condition to retry", type: "json", placeholder: '{"file_exists": "x.md"}', required: true },
      { name: "max_attempts", label: "Max attempts", type: "number", default: 12 },
      { name: "delay", label: "Delay (seconds)", type: "number", default: 5 },
    ],
  },
  command_exists: {
    label: "Command Exists",
    description: "Check that a CLI command is available",
    params: [{ name: "command", label: "Command name", type: "text", placeholder: "pytest", required: true }],
  },
  diff_contains: {
    label: "Diff Contains",
    description: "Check git diff for a pattern (security gate)",
    params: [
      { name: "pattern", label: "Pattern (regex)", type: "text", placeholder: "eval\\(", required: true },
      { name: "op", label: "Check", type: "select", options: ["contains", "not_contains"], default: "not_contains" },
    ],
  },
  json_count: {
    label: "JSON Count",
    description: "Count elements in a JSON array or object",
    params: [
      { name: "path", label: "JSON file path", type: "text", required: true },
      { name: "field", label: "Field path (optional)", type: "text", placeholder: "results.items"},
      { name: "min", label: "Min count", type: "number", placeholder: "1"},
      { name: "max", label: "Max count", type: "number", placeholder: "100"},
    ],
  },
};

export const CONDITION_TYPES: ConditionTypeDef[] = Object.entries(defs).map(([type, d]) => ({ type, ...d }));

const map = new Map<string, ConditionTypeDef>();
for (const ct of CONDITION_TYPES) map.set(ct.type, ct);
export const CONDITION_MAP = map;

export function defaultParams(type: string): Record<string, unknown> {
  const def = defs[type];
  if (!def) return {};
  const params: Record<string, unknown> = {};
  for (const p of def.params) {
    if (p.default !== undefined) params[p.name] = p.default;
    else if (p.type === "number") params[p.name] = undefined;
    else params[p.name] = "";
  }
  return params;
}

export function formatConditionSummary(conditions: { type: string; params: Record<string, unknown> }[]): string {
  if (conditions.length === 0) return "always";
  if (conditions.length === 1) {
    const c = conditions[0];
    const label = defs[c.type]?.label ?? c.type;
    const path = c.params.path || c.params.pattern || c.params.command || c.params.name || c.params.url || c.params.expr || "";
    if (path && typeof path === "string" && path.length < 30) return `${label} — ${path}`;
    return label;
  }
  if (conditions.length <= 2) {
    return conditions.map((c) => defs[c.type]?.label ?? c.type).join(" + ");
  }
  return `${conditions.length} conditions`;
}
