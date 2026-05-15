import yaml from "js-yaml";
import type { StageNode, CondEdge, ConditionDef } from "../types";

interface YamlStage {
  name: string;
  tools?: string[];
  meta?: { description?: string };
  on_enter?: Record<string, string>[];
  on_exit?: Record<string, string>[];
}

interface YamlTransition {
  from: string;
  to: string;
  description?: string;
  conditions?: Record<string, unknown>[];
  on_fail?: string;
}

interface YamlDoc {
  stages?: YamlStage[];
  transitions?: YamlTransition[];
}

function conditionToYaml(c: ConditionDef): Record<string, unknown> {
  const keys = Object.keys(c.params).filter(
    (k) => c.params[k] !== "" && c.params[k] !== undefined && c.params[k] !== null
  );

  if (keys.length === 0) {
    return { [c.type]: true };
  }

  if (keys.length === 1 && typeof c.params[keys[0]] !== "object") {
    return { [c.type]: c.params[keys[0]] };
  }

  return { [c.type]: { ...c.params } };
}

function conditionFromYaml(obj: Record<string, unknown>): ConditionDef {
  const type = Object.keys(obj)[0];
  const val = obj[type];

  if (val === undefined || val === null) {
    return { type, params: {} };
  }

  if (typeof val !== "object" || val === null) {
    return { type, params: { [firstParamForType(type)]: val } };
  }

  return { type, params: val as Record<string, unknown> };
}

const FIRST_PARAMS: Record<string, string> = {
  file_exists: "path",
  file_not_exists: "path",
  file_contains: "path",
  file_not_contains: "path",
  json_field: "path",
  yaml_field: "path",
  shell_test: "command",
  python_expr: "expr",
  env_var: "name",
  git_status: "op",
  http_status: "url",
  time_range: "after",
  compare_files: "path1",
  json_schema: "path",
  hash_file: "path",
  file_age: "path",
  file_size: "path",
  glob_count: "pattern",
  command_exists: "command",
  diff_contains: "pattern",
  json_count: "path",
  never: "reason",
  always: "",
  all_of: "conditions",
  any_of: "conditions",
  not: "condition",
  retry: "condition",
};

function firstParamForType(type: string): string {
  return FIRST_PARAMS[type] ?? Object.keys({} as never)[0] ?? "";
}

function hooksToYaml(hooks: { shell?: string; python?: string }[]): Record<string, string>[] {
  return hooks.map((h) => {
    const out: Record<string, string> = {};
    if ("shell" in h) out.shell = h.shell ?? "";
    if ("python" in h) out.python = h.python ?? "";
    return out;
  });
}

function hooksFromYaml(raw: Record<string, string>[] | undefined): { shell?: string; python?: string }[] {
  if (!raw) return [];
  return raw.map((h) => {
    if ("shell" in h) return { shell: h.shell };
    if ("python" in h) return { python: h.python };
    return {};
  });
}

export function exportToYaml(nodes: StageNode[], edges: CondEdge[]): string {
  const stages: YamlStage[] = nodes.map((n) => {
    const d = n.data;
    const stage: YamlStage = { name: d.name };
    if (d.tools.length > 0) stage.tools = d.tools;
    if (d.description) {
      stage.meta = { description: d.description };
    }
    if (d.on_enter.length > 0) {
      const enter = hooksToYaml(d.on_enter);
      if (enter.length > 0) stage.on_enter = enter;
    }
    if (d.on_exit.length > 0) {
      const exit = hooksToYaml(d.on_exit);
      if (exit.length > 0) stage.on_exit = exit;
    }
    return stage;
  });

  const transitions: YamlTransition[] = edges.map((e) => {
    const d = e.data;
    const t: YamlTransition = { from: e.source, to: e.target };
    if (d?.description) t.description = d.description;
    if (d?.conditions && d.conditions.length > 0) {
      t.conditions = d.conditions.map((c) => conditionToYaml(c));
    }
    if (d?.on_fail) t.on_fail = d.on_fail;
    return t;
  });

  const doc: YamlDoc = {};
  if (stages.length > 0) doc.stages = stages;
  if (transitions.length > 0) doc.transitions = transitions;

  return yaml.dump(doc, {
    indent: 2,
    lineWidth: -1,
    noRefs: true,
    sortKeys: false,
    quotingType: '"',
    forceQuotes: false,
  });
}

export function importFromYaml(
  yamlString: string
): { nodes: StageNode[]; edges: CondEdge[] } | { error: string } {
  let doc: unknown;
  try {
    doc = yaml.load(yamlString);
  } catch (e) {
    return { error: `YAML parse error: ${String(e)}` };
  }

  if (!doc || typeof doc !== "object") {
    return { error: "YAML root must be an object with 'stages' and/or 'transitions'" };
  }

  const root = doc as YamlDoc;

  if (!root.stages && !root.transitions) {
    return { error: "No 'stages' or 'transitions' key found in YAML" };
  }

  const nodes: StageNode[] = [];
  const edges: CondEdge[] = [];
  const nodeNames = new Set<string>();

  if (root.stages) {
    root.stages.forEach((s, i) => {
      const name = s.name ?? `stage_${i + 1}`;
      nodeNames.add(name);
      nodes.push({
        id: name,
        type: "stageNode",
        position: { x: 80 + i * 240, y: 150 },
        data: {
          name,
          tools: s.tools ?? [],
          description: s.meta?.description ?? "",
          on_enter: hooksFromYaml(s.on_enter),
          on_exit: hooksFromYaml(s.on_exit),
        },
      });
    });
  }

  if (root.transitions) {
    root.transitions.forEach((t, i) => {
      const source = t.from;
      const target = t.to;
      if (!nodeNames.has(source)) {
        nodeNames.add(source);
        nodes.push({
          id: source,
          type: "stageNode",
          position: { x: 80, y: 400 + nodes.length * 60 },
          data: { name: source, tools: [], description: "(from transition)", on_enter: [], on_exit: [] },
        });
      }
      if (!nodeNames.has(target)) {
        nodeNames.add(target);
        nodes.push({
          id: target,
          type: "stageNode",
          position: { x: 320, y: 400 + nodes.length * 60 },
          data: { name: target, tools: [], description: "(from transition)", on_enter: [], on_exit: [] },
        });
      }

      const edgeId = `e-${source}-${target}-${i}`;
      const conditions: ConditionDef[] = (t.conditions ?? []).map((c) =>
        conditionFromYaml(c as Record<string, unknown>)
      );

      edges.push({
        id: edgeId,
        source,
        target,
        data: {
          conditions,
          on_fail: t.on_fail ?? null,
          description: t.description ?? "",
        },
      });
    });
  }

  return { nodes, edges };
}

export function validateYaml(yamlString: string): string | null {
  const result = importFromYaml(yamlString);
  if ("error" in result) return result.error;
  if (result.nodes.length === 0 && result.edges.length === 0) {
    return "YAML contains no stages or transitions";
  }
  return null;
}
