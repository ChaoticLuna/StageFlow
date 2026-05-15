import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EdgeEditor from "./EdgeEditor";
import type { Edge } from "reactflow";
import type { EdgeData } from "../types";

function makeEdge(overrides: Partial<Edge<EdgeData>> = {}): Edge<EdgeData> {
  return {
    id: "analyze-plan",
    source: "analyze",
    target: "plan",
    data: {
      conditions: [{ type: "always", params: {} }],
      on_fail: null,
      description: "Analysis complete",
    },
    ...overrides,
  } as Edge<EdgeData>;
}

const defaultStageNames = ["pick", "analyze", "plan", "implement", "verify", "done"];

describe("EdgeEditor", () => {
  describe("header", () => {
    it("renders source → target in the header", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText(/analyze.*plan/)).toBeDefined();
    });

    it("has a close button in the header", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const closeButtons = screen.getAllByText("×");
      expect(closeButtons.length).toBeGreaterThan(0);
    });
  });

  describe("description", () => {
    it("renders the description input with initial value", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByDisplayValue("Analysis complete")).toBeDefined();
    });

    it("renders empty description input when no description", () => {
      render(
        <EdgeEditor
          edge={makeEdge({ data: { conditions: [], on_fail: null, description: "" } })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const input = screen.getByPlaceholderText("Describe this transition...");
      expect(input).toBeDefined();
    });
  });

  describe("conditions", () => {
    it("shows condition count in the label", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("Conditions (1)")).toBeDefined();
    });

    it("shows hint when no conditions are defined", () => {
      render(
        <EdgeEditor
          edge={makeEdge({ data: { conditions: [], on_fail: null, description: "" } })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText(/No conditions/)).toBeDefined();
    });

    it("renders the condition type label in the select option", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const matches = screen.getAllByText(/Always/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });

    it("shows condition ordinal number", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("#1")).toBeDefined();
    });

    it("renders multiple conditions", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [
                { type: "always", params: {} },
                { type: "file_exists", params: { path: "test.md" } },
              ],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("#1")).toBeDefined();
      expect(screen.getByText("#2")).toBeDefined();
    });

    it("adds a condition when + Add is clicked", () => {
      render(
        <EdgeEditor
          edge={makeEdge({ data: { conditions: [], on_fail: null, description: "" } })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      fireEvent.click(screen.getByText("+ Add"));
      expect(screen.getByText("#1")).toBeDefined();
    });

    it("removes a condition when × is clicked on condition header", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [
                { type: "always", params: {} },
                { type: "file_exists", params: { path: "test.md" } },
              ],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("#2")).toBeDefined();
      const removeButtons = screen.getAllByTitle("Remove condition");
      fireEvent.click(removeButtons[0]);
      expect(screen.queryByText("#2")).toBeNull();
    });

    it("shows condition description text", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [{ type: "file_exists", params: { path: "test.md" } }],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("Check that a file exists on disk")).toBeDefined();
    });
  });

  describe("logic toggle", () => {
    it("renders AND and OR buttons", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("AND")).toBeDefined();
      expect(screen.getByText("OR")).toBeDefined();
    });

    it("shows ALL hint in AND mode", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("ALL conditions must pass for the transition to fire.")).toBeDefined();
    });

    it("switches to OR mode and shows ANY hint", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      fireEvent.click(screen.getByText("OR"));
      expect(screen.getByText("ANY condition can pass for the transition to fire.")).toBeDefined();
    });
  });

  describe("on_fail target", () => {
    it("renders on_fail selector", () => {
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("On Failure Target")).toBeDefined();
    });

    it("excludes source and target from fail targets", () => {
      render(
        <EdgeEditor
          edge={makeEdge({ source: "analyze", target: "plan" })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const failOptions = screen.getAllByRole("option").filter(
        (o) => !(o as HTMLOptionElement).value.startsWith("None")
      );
      const failNames = failOptions.map((o) => o.textContent);
      expect(failNames).not.toContain("analyze");
      expect(failNames).not.toContain("plan");
      expect(failNames).toContain("pick");
      expect(failNames).toContain("implement");
    });

    it("shows current on_fail value even if not in fail targets", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [],
              on_fail: "legacy_stage",
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByText("legacy_stage (current)")).toBeDefined();
    });
  });

  describe("save and cancel", () => {
    it("calls onUpdate and onClose when Save is clicked", () => {
      const onUpdate = vi.fn();
      const onClose = vi.fn();
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={onUpdate}
          onClose={onClose}
        />
      );
      fireEvent.click(screen.getByText("Save Changes"));
      expect(onUpdate).toHaveBeenCalledWith(
        "analyze-plan",
        expect.objectContaining({ description: "Analysis complete" })
      );
      expect(onClose).toHaveBeenCalled();
    });

    it("wraps multiple conditions in any_of when OR mode with >1 conditions", () => {
      const onUpdate = vi.fn();
      const onClose = vi.fn();
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [
                { type: "file_exists", params: { path: "a.md" } },
                { type: "file_exists", params: { path: "b.md" } },
              ],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={onUpdate}
          onClose={onClose}
        />
      );
      fireEvent.click(screen.getByText("OR"));
      fireEvent.click(screen.getByText("Save Changes"));
      expect(onUpdate).toHaveBeenCalledWith(
        "analyze-plan",
        expect.objectContaining({
          conditions: [{ type: "any_of", params: { conditions: expect.any(Array) } }],
        })
      );
    });

    it("calls onClose when Cancel is clicked", () => {
      const onClose = vi.fn();
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={onClose}
        />
      );
      fireEvent.click(screen.getByText("Cancel"));
      expect(onClose).toHaveBeenCalled();
    });

    it("calls onClose when overlay is clicked", () => {
      const onClose = vi.fn();
      render(
        <EdgeEditor
          edge={makeEdge()}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={onClose}
        />
      );
      fireEvent.click(screen.getByText("Save Changes").closest(".edge-editor-overlay")!);
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("param inputs", () => {
    it("renders text input for text param", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [{ type: "file_exists", params: { path: "findings.md" } }],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByDisplayValue("findings.md")).toBeDefined();
    });

    it("renders select input for select params", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [{ type: "git_status", params: { op: "clean" } }],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      expect(screen.getByDisplayValue("clean")).toBeDefined();
    });

    it("renders number input for number params", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [{ type: "http_status", params: { expected_status: 200 } }],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const input = screen.getByDisplayValue("200");
      expect(input).toBeDefined();
    });

    it("renders textarea for json params", () => {
      render(
        <EdgeEditor
          edge={makeEdge({
            data: {
              conditions: [{
                type: "any_of",
                params: { conditions: [{ always: true }] },
              }],
              on_fail: null,
              description: "",
            },
          })}
          stageNames={defaultStageNames}
          onUpdate={vi.fn()}
          onClose={vi.fn()}
        />
      );
      const textarea = screen.getByText(/always/);
      expect(textarea).toBeDefined();
    });
  });
});
