import { describe, it, expect } from "vitest";
import { exportToYaml, importFromYaml, validateYaml } from "./yaml";
import type { StageNode, CondEdge } from "../types";

const baseNode = (overrides: Partial<StageNode> = {}): StageNode => ({
  id: "investigate",
  type: "stageNode",
  position: { x: 0, y: 0 },
  data: {
    name: "investigate",
    tools: ["Read", "Grep"],
    description: "Investigation phase",
    on_enter: [],
    on_exit: [],
  },
  ...overrides,
});

// ── exportToYaml ──

describe("exportToYaml", () => {
  it("exports a single stage", () => {
    const yaml = exportToYaml([baseNode()], []);
    expect(yaml).toContain("stages:");
    expect(yaml).toContain("name: investigate");
    expect(yaml).toContain("Read");
    expect(yaml).toContain("Grep");
  });

  it("exports multiple stages", () => {
    const nodes: StageNode[] = [
      baseNode(),
      baseNode({
        id: "implement",
        data: { ...baseNode().data, name: "implement", tools: ["Edit", "Write"] },
      }),
    ];
    const yaml = exportToYaml(nodes, []);
    expect(yaml).toContain("investigate");
    expect(yaml).toContain("implement");
  });

  it("exports stages without tool arrays when empty", () => {
    const node = baseNode({ data: { ...baseNode().data, tools: [] } });
    const yaml = exportToYaml([node], []);
    expect(yaml).not.toContain("tools:");
  });

  it("exports transitions with conditions", () => {
    const nodes = [baseNode(), baseNode({ id: "implement", data: { ...baseNode().data, name: "implement" } })];
    const edges: CondEdge[] = [
      {
        id: "e-investigate-implement-0",
        source: "investigate",
        target: "implement",
        data: {
          conditions: [{ type: "file_exists", params: { path: "findings.md" } }],
          on_fail: "investigate",
          description: "",
        },
      },
    ];
    const yaml = exportToYaml(nodes, edges);
    expect(yaml).toContain("transitions:");
    expect(yaml).toContain("from: investigate");
    expect(yaml).toContain("to: implement");
    expect(yaml).toContain("file_exists: findings.md");
  });

  it("exports condition with always:true for empty params", () => {
    const nodes = [baseNode(), baseNode({ id: "b", data: { ...baseNode().data, name: "b" } })];
    const edges: CondEdge[] = [
      {
        id: "e-a-b-0",
        source: "investigate",
        target: "b",
        data: { conditions: [{ type: "always", params: {} }], on_fail: null, description: "" },
      },
    ];
    const yaml = exportToYaml(nodes, edges);
    expect(yaml).toContain("always: true");
  });

  it("exports transition with single-scalar condition param", () => {
    const nodes = [baseNode(), baseNode({ id: "b", data: { ...baseNode().data, name: "b" } })];
    const edges: CondEdge[] = [
      {
        id: "e",
        source: "investigate",
        target: "b",
        data: { conditions: [{ type: "file_exists", params: { path: "x.md" } }], on_fail: null, description: "" },
      },
    ];
    const yaml = exportToYaml(nodes, edges);
    expect(yaml).toContain("file_exists: x.md");
  });

  it("exports on_fail in transition", () => {
    const nodes = [baseNode(), baseNode({ id: "b", data: { ...baseNode().data, name: "b" } })];
    const edges: CondEdge[] = [
      {
        id: "e",
        source: "investigate",
        target: "b",
        data: { conditions: [], on_fail: "investigate", description: "" },
      },
    ];
    const yaml = exportToYaml(nodes, edges);
    expect(yaml).toContain("on_fail: investigate");
  });

  it("exports hooks on_enter and on_exit", () => {
    const node = baseNode({
      data: {
        ...baseNode().data,
        on_enter: [{ python: "print('hello')" }],
        on_exit: [{ shell: "echo done" }],
      },
    });
    const yaml = exportToYaml([node], []);
    expect(yaml).toContain("on_enter:");
    expect(yaml).toContain("python: print('hello')");
    expect(yaml).toContain("on_exit:");
    expect(yaml).toContain("shell: echo done");
  });
});

// ── importFromYaml ──

describe("importFromYaml", () => {
  it("parses stages", () => {
    const yaml = `
stages:
  - name: investigate
    tools:
      - Read
      - Grep
    meta:
      description: Investigation phase
`;
    const result = importFromYaml(yaml);
    expect("nodes" in result).toBe(true);
    if ("nodes" in result) {
      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0].data.name).toBe("investigate");
      expect(result.nodes[0].data.tools).toEqual(["Read", "Grep"]);
    }
  });

  it("parses transitions", () => {
    const yaml = `
transitions:
  - from: investigate
    to: implement
    conditions:
      - file_exists: findings.md
`;
    const result = importFromYaml(yaml);
    if ("nodes" in result) {
      expect(result.edges).toHaveLength(1);
      expect(result.edges[0].source).toBe("investigate");
      expect(result.edges[0].target).toBe("implement");
    }
  });

  it("parses conditions correctly", () => {
    const yaml = `
transitions:
  - from: a
    to: b
    conditions:
      - file_exists: path/to/file.md
      - always: true
`;
    const result = importFromYaml(yaml);
    if ("nodes" in result) {
      expect(result.edges[0].data.conditions).toHaveLength(2);
      expect(result.edges[0].data.conditions[0].type).toBe("file_exists");
      expect(result.edges[0].data.conditions[1].type).toBe("always");
    }
  });

  it("returns error for invalid YAML", () => {
    const result = importFromYaml("{{{ bad yaml");
    expect("error" in result).toBe(true);
    if ("error" in result) {
      expect(result.error).toContain("YAML parse error");
    }
  });

  it("returns error for non-object YAML root", () => {
    const result = importFromYaml("- just a list");
    expect("error" in result).toBe(true);
  });

  it("returns error for missing stages and transitions", () => {
    const result = importFromYaml("other: 42");
    expect("error" in result).toBe(true);
    if ("error" in result) {
      expect(result.error).toContain("No 'stages' or 'transitions'");
    }
  });

  it("returns empty nodes for empty YAML", () => {
    const result = importFromYaml("stages:\ntransitions:");
    if ("nodes" in result) {
      expect(result.nodes).toHaveLength(0);
      expect(result.edges).toHaveLength(0);
    }
  });

  it("creates implicit stage nodes from transition references", () => {
    const yaml = `
transitions:
  - from: analyze
    to: fix
`;
    const result = importFromYaml(yaml);
    if ("nodes" in result) {
      const names = result.nodes.map((n) => n.data.name);
      expect(names).toContain("analyze");
      expect(names).toContain("fix");
    }
  });

  it("parses on_fail in transition", () => {
    const yaml = `
transitions:
  - from: a
    to: b
    on_fail: a
`;
    const result = importFromYaml(yaml);
    if ("nodes" in result) {
      expect(result.edges[0].data.on_fail).toBe("a");
    }
  });

  it("parses hooks from on_enter and on_exit", () => {
    const yaml = `
stages:
  - name: deploy
    on_enter:
      - shell: echo starting
    on_exit:
      - python: cleanup()
`;
    const result = importFromYaml(yaml);
    if ("nodes" in result) {
      const node = result.nodes[0];
      expect(node.data.on_enter).toEqual([{ shell: "echo starting" }]);
      expect(node.data.on_exit).toEqual([{ python: "cleanup()" }]);
    }
  });
});

// ── validateYaml ──

describe("validateYaml", () => {
  it("returns null for valid YAML", () => {
    const yaml = `
stages:
  - name: test
`;
    expect(validateYaml(yaml)).toBeNull();
  });

  it("returns error string for invalid YAML syntax", () => {
    expect(validateYaml("{{{")).toContain("YAML parse error");
  });

  it("returns error for empty YAML", () => {
    expect(validateYaml("stages: []\ntransitions: []")).toContain("no stages or transitions");
  });

  it("returns error for missing root keys", () => {
    expect(validateYaml("other: 42")).toContain("No 'stages' or 'transitions'");
  });
});

// ── round-trip ──

describe("YAML round-trip", () => {
  it("export then import preserves stages", () => {
    const nodes: StageNode[] = [
      baseNode(),
      baseNode({
        id: "implement",
        data: { ...baseNode().data, name: "implement", tools: ["Edit"] },
      }),
    ];
    const edges: CondEdge[] = [
      {
        id: "e-0",
        source: "investigate",
        target: "implement",
        data: {
          conditions: [{ type: "file_exists", params: { path: "f.md" } }],
          on_fail: "investigate",
          description: "",
        },
      },
    ];

    const yaml = exportToYaml(nodes, edges);
    const result = importFromYaml(yaml);

    if ("nodes" in result) {
      expect(result.nodes).toHaveLength(2);
      expect(result.nodes[0].data.name).toBe("investigate");
      expect(result.nodes[1].data.name).toBe("implement");
      expect(result.edges).toHaveLength(1);
      expect(result.edges[0].source).toBe("investigate");
      expect(result.edges[0].target).toBe("implement");
      expect(result.edges[0].data.conditions[0].type).toBe("file_exists");
    } else {
      throw new Error("Round-trip failed: " + result.error);
    }
  });
});
