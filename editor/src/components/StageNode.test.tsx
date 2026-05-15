import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "reactflow";
import StageNode from "./StageNode";
import type { StageData } from "../types";

function renderStageNode(data: Partial<StageData> = {}) {
  const nodeData: StageData = {
    name: "implement",
    tools: ["Edit", "Write"],
    description: "Implementation phase",
    on_enter: [],
    on_exit: [],
    ...data,
  };

  return render(
    <ReactFlowProvider>
      <StageNode
        id="test-node"
        type="stageNode"
        data={nodeData}
        selected={false}
        xPos={0}
        yPos={0}
        zIndex={0}
        isConnectable={true}
        dragging={false}
      />
    </ReactFlowProvider>
  );
}

describe("StageNode", () => {
  it("renders the stage name", () => {
    renderStageNode({ name: "implement" });
    expect(screen.getByText("implement")).toBeDefined();
  });

  it("renders the description when present", () => {
    renderStageNode({ description: "Implementation phase" });
    expect(screen.getByText("Implementation phase")).toBeDefined();
  });

  it("shows tool count badge", () => {
    renderStageNode({ tools: ["Read", "Grep", "Edit"] });
    expect(screen.getByText("3 tools")).toBeDefined();
  });

  it("shows singular tool badge", () => {
    renderStageNode({ tools: ["Read"] });
    expect(screen.getByText("1 tool")).toBeDefined();
  });

  it("shows 'all tools' badge when tools array is empty", () => {
    renderStageNode({ tools: [], description: "" });
    expect(screen.getByText("all tools")).toBeDefined();
  });

  it("shows terminal badge for terminal stage names", () => {
    renderStageNode({ name: "done", tools: [] });
    expect(screen.getByText("terminal")).toBeDefined();
  });

  it("shows hook badges when hooks are present", () => {
    renderStageNode({
      on_enter: [{ python: "print('in')" }],
      on_exit: [{ shell: "echo done" }],
    });
    expect(screen.getByText("1 in")).toBeDefined();
    expect(screen.getByText("1 out")).toBeDefined();
  });

  it("does not show description when empty", () => {
    renderStageNode({ description: "" });
    expect(screen.queryByText("Implementation phase")).toBeNull();
  });
});
